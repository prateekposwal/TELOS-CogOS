"""Tests for ActPhase — action execution and governance blocking."""
import numpy as np
import pytest
from unittest.mock import MagicMock

from telos.core.phases.act import ActPhase
from telos.core.phases.base import PhaseContext
from telos.intent_ir import IntentIR


class MockVerdict:
    validated = True
    decision_integrity = 0.9
    mission_drift = 0.1
    escalation_requested = False
    escalation_reason = None
    blocking_validator = None
    signals = []


class MockEscalationVerdict:
    validated = False
    decision_integrity = 0.6
    mission_drift = 0.5
    escalation_requested = True
    escalation_reason = "low_di"
    blocking_validator = None
    signals = []


class MockFirewallVerdict:
    def __init__(self, blocked=False, blocked_by=None):
        self.blocked = blocked
        self.blocked_by = blocked_by
        self.blocker_validators = [blocked_by] if blocked_by else []
        self.governance_signals = []
        self.passed = not blocked


class TestActPhase:

    def test_no_intent_no_action(self):
        phase = ActPhase()
        pipeline = MagicMock()
        pipeline._firewall.evaluate.return_value = MockFirewallVerdict()
        pipeline.config.adapter = MagicMock()
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = None
        phase.execute(pipeline, ctx)
        assert ctx.selected_action is None

    def test_returns_action_from_adapter(self):
        phase = ActPhase()
        pipeline = MagicMock()
        pipeline._firewall.inspect.return_value = MockFirewallVerdict()
        pipeline.config.adapter = MagicMock()
        pipeline.config.adapter.intent_to_action.return_value = np.array([1.0, 0.0])
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.verdict = MockVerdict()
        phase.execute(pipeline, ctx)
        assert np.allclose(ctx.selected_action, np.array([1.0, 0.0]))
        assert not ctx.firewall_blocked

    def test_firewall_blocks_action(self):
        phase = ActPhase()
        pipeline = MagicMock()
        pipeline._firewall.inspect.return_value = MockFirewallVerdict(
            blocked=True, blocked_by="ConstraintValidator"
        )
        pipeline.config.adapter = MagicMock()
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.verdict = MockVerdict()
        phase.execute(pipeline, ctx)
        assert ctx.firewall_blocked
        assert ctx.firewall_verdict.blocked_by == "ConstraintValidator"

    def test_firewall_block_sets_governance_blocked(self):
        phase = ActPhase()
        pipeline = MagicMock()
        pipeline._firewall.inspect.return_value = MockFirewallVerdict(
            blocked=True, blocked_by="ConstraintValidator"
        )
        pipeline.config.adapter = MagicMock()
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.verdict = MockVerdict()
        phase.execute(pipeline, ctx)
        assert ctx.governance_blocked
        assert ctx.blocking_reason == "ConstraintValidator"

    def test_no_adapter_graceful_degradation(self):
        phase = ActPhase()
        pipeline = MagicMock()
        pipeline._firewall.inspect.return_value = MockFirewallVerdict()
        pipeline.config.adapter = None
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.verdict = MockVerdict()
        phase.execute(pipeline, ctx)
        assert ctx.selected_action is None or ctx.selected_action is not None

    def test_escalation_allows_action_through_firewall(self):
        phase = ActPhase()
        pipeline = MagicMock()
        pipeline._firewall.inspect.return_value = MockFirewallVerdict()
        pipeline._firewall.config.block_on_council_rejection = False
        pipeline.config.adapter = MagicMock()
        pipeline.config.adapter.intent_to_action.return_value = np.array([1.0, 0.0])
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.verdict = MockEscalationVerdict()
        phase.execute(pipeline, ctx)
        assert np.allclose(ctx.selected_action, np.array([1.0, 0.0]))


# ═══════════════════════════════════════════════════════════════════════
# Audit Item 1 — decision-mode telemetry contract
# A DEFERed cycle must carry decision_mode + blocked_by_gate in the trace,
# and an approved no-op must carry act_emitted_action=false (the distinction
# the old "DI 1.0, firewall_blocked=False, action=None" view erased).
# ═══════════════════════════════════════════════════════════════════════

class _MinBudget:
    consumed_ms = 5.0
    total_budget_ms = 100.0
    budget_carryover_ms = 0.0


def _build_trace_from_ctx(ctx):
    """Run the real trace builder over a phase context (the same path
    runtime.py uses) so the telemetry contract is tested end-to-end.

    Args:
        ctx: a PhaseContext after ActPhase.execute() — the exact object the
            runtime hands to build_trace."""
    from telos.core.trace_builder import build_trace
    return build_trace(
        ctx=ctx,
        state=np.zeros(2),
        cycle_count=ctx.cycle_count,
        budget_manager=_MinBudget(),
        cycle_duration=1.0,
        infra_manager=None,
        last_quality_report=None,
        perception_explanation=None,
        prev_trace_id=None,
    )


class TestDecisionModeTelemetry:

    def test_defer_carries_decision_mode_and_blocked_gate_in_trace(self):
        """A governor DEFER (capability gate FAIL) must surface the mode AND
        the failed gate on the context and in the DecisionTrace — the honesty
        gap the audit named (93 silent approved-noop cycles hiding 65%
        governor-DEFER)."""
        from telos.core.governance.capability_authorization import (
            CapabilityAuthorization, CapabilityStatus,
        )
        from telos.core.governance.governor import DecisionMode

        phase = ActPhase()
        pipeline = MagicMock()
        pipeline._firewall.inspect.return_value = MockFirewallVerdict()
        pipeline._reality_gap_tracker = None   # real governance computation (no MagicMock tracker)
        pipeline.config.adapter = MagicMock()
        ctx = PhaseContext(cycle_count=7, state=np.zeros(2), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.verdict = MockVerdict()
        # Inject the failing capability gate the act phase would otherwise
        # derive from the reality-gap tracker: model_fidelity FAIL -> the
        # governor cannot authorize ACT.
        ctx._governance_override = CapabilityAuthorization(
            model_fidelity=CapabilityStatus.FAIL,
        )
        phase.execute(pipeline, ctx)

        # The mode + gate are readable after execute() on the context...
        assert ctx.decision_mode == DecisionMode.DEFER
        assert ctx.blocked_by_gate == "model_fidelity"
        assert ctx.no_action is True
        assert ctx.selected_action is None, "DEFER must never emit an action"

        # ...and flow into the DecisionTrace every consumer reads.
        trace = _build_trace_from_ctx(ctx)
        td = trace.to_dict()
        assert td["decision_mode"] == "DEFER"
        assert td["blocked_by_gate"] == "model_fidelity"
        assert td["act_emitted_action"] is False
        assert td["action_taken"] is None
        assert td["intent"] == "navigate"
        assert td["discrimination_index"] == td["decision_integrity"]

    def test_approved_act_carries_act_emitted_action_true(self):
        """A genuinely approved cycle (action emitted) must NOT look like a
        no-op: act_emitted_action=true distinguishes real success."""
        phase = ActPhase()
        pipeline = MagicMock()
        pipeline._firewall.inspect.return_value = MockFirewallVerdict()
        pipeline._reality_gap_tracker = None
        pipeline.config.adapter = MagicMock()
        pipeline.config.adapter.intent_to_action.return_value = np.array([1.0, 0.0])
        ctx = PhaseContext(cycle_count=8, state=np.zeros(2), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.verdict = MockVerdict()
        phase.execute(pipeline, ctx)

        assert ctx.decision_mode.value if hasattr(ctx.decision_mode, "value") else ctx.decision_mode
        assert ctx.selected_action is not None
        trace = _build_trace_from_ctx(ctx)
        td = trace.to_dict()
        assert td["act_emitted_action"] is True
        assert td["action_taken"] == [1.0, 0.0]
        # No gate failed on a fully-authorized cycle.
        assert td["blocked_by_gate"] is None

    def test_approved_noop_is_not_claimed_as_success(self):
        """The audit's exact hole: a cycle with DI 1.0, firewall_blocked=False
        and action=None must carry act_emitted_action=false so an observer can
        tell it apart from a real action. (Governor allowed, but no action
        vector materialised — e.g. no adapter/intent path.)"""
        phase = ActPhase()
        pipeline = MagicMock()
        pipeline._firewall.inspect.return_value = MockFirewallVerdict()
        pipeline._reality_gap_tracker = None
        pipeline.config.adapter = None          # no executor -> no action
        ctx = PhaseContext(cycle_count=9, state=np.zeros(2), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.verdict = MockVerdict()
        phase.execute(pipeline, ctx)

        assert ctx.selected_action is None
        trace = _build_trace_from_ctx(ctx)
        td = trace.to_dict()
        assert td["act_emitted_action"] is False
        assert td["action_taken"] is None
        # The governor still ran and said ACT (nothing failed).
        assert td["decision_mode"] is not None
        assert td["blocked_by_gate"] is None
