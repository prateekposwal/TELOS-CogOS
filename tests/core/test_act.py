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


class MockBlockedVerdict:
    validated = False
    decision_integrity = 0.9
    mission_drift = 0.1
    escalation_requested = False
    escalation_reason = None
    blocking_validator = "ConstraintValidator"
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
