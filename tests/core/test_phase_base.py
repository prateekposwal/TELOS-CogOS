"""Tests for telos/core/phases/base.py — phase output dataclasses and the
Phase ABC contract."""

import numpy as np
import pytest

from telos.intent_ir import IntentIR
from telos.core.phases.base import (
    ActOutput,
    CouncilOutput,
    EvaluateOutput,
    PerceiveOutput,
    Phase,
    PhaseContext,
    SelectOutput,
    SessionContinuity,
    SimulateOutput,
    StreamActivation,
    StreamsOutput,
    SynthesisOutput,
)


class TestDataclasses:
    def test_stream_activation_defaults(self):
        sa = StreamActivation(
            stream_name="reflex",
            priority=0.8,
            intent=IntentIR(),
            cost_ms=1.0,
            budget_remaining_ms=9.0,
        )
        assert sa.activated is True

    def test_synthesis_irreconcilable_default(self):
        out = SynthesisOutput(
            reconciled_intent=None, raw_intents=[], compatibility_score=0.0,
            conflicts=[],
        )
        assert out.irreconcilable is False

    def test_session_continuity_defaults(self):
        sc = SessionContinuity()
        assert sc.truncated_history == []
        assert sc.session_essence is None


class TestPhaseContext:
    def test_required_fields(self):
        state = np.zeros(3)
        ctx = PhaseContext(cycle_count=2, state=state, user_name="Prateek")
        assert ctx.cycle_count == 2
        assert ctx.user_name == "Prateek"
        assert ctx.state is state

    def test_defaults(self):
        ctx = PhaseContext(cycle_count=0, state=np.zeros(2), user_name=None)
        assert ctx.effective_n_worlds == 5
        assert ctx.effective_horizon == 3
        assert ctx.representation == "cartesian"
        assert ctx.worlds_generated == 0
        assert ctx.simulation_confidence == 0.0
        assert ctx.council_blocked is False
        assert ctx.firewall_blocked is False
        assert ctx.governance_blocked is False
        assert ctx.blocking_reason == ""
        assert ctx.escalation_pending is False
        assert ctx.decision_criticality == "medium"
        assert ctx.identity_cost_weight == 1.0
        assert ctx.curiosity_bonus == 1.0
        assert ctx.representation_confidence == 0.0
        assert ctx.terminal_value == 0.0
        assert ctx.no_action is False
        assert ctx.inquiry_skipped is False
        assert ctx.inquiry_omega_value == 0.0
        assert ctx.inquiry_blend == 0.0

    def test_optional_phase_outputs_default_none(self):
        ctx = PhaseContext(cycle_count=0, state=np.zeros(2), user_name=None)
        for attr in ("perceive", "streams", "simulate", "evaluate", "synthesis",
                     "select", "council", "act"):
            assert getattr(ctx, attr) is None

    def test_assignable_phase_outputs(self):
        ctx = PhaseContext(cycle_count=0, state=np.zeros(2), user_name=None)
        out = PerceiveOutput(
            world=object(), domain_facts=object(), quality_report=object(),
            gate_verdict=object(), knowledge_report={}, effective_n_worlds=2,
        )
        ctx.perceive = out
        assert ctx.perceive is out

    def test_collection_defaults(self):
        ctx = PhaseContext(cycle_count=0, state=np.zeros(2), user_name=None)
        assert ctx.stream_activations == []
        assert ctx.intents == []
        assert ctx.chat_history == []
        assert isinstance(ctx.session, SessionContinuity)


class TestPhaseABC:
    def test_phase_is_abstract(self):
        with pytest.raises(TypeError):
            Phase()

    def test_concrete_phase_executes(self):
        calls = []

        class ConcretePhase(Phase):
            name = "test"

            def execute(self, pipeline, ctx):
                calls.append((pipeline, ctx))

        ph = ConcretePhase()
        pipeline = object()
        ctx = PhaseContext(cycle_count=1, state=np.zeros(2), user_name=None)
        ph.execute(pipeline, ctx)
        assert calls == [(pipeline, ctx)]

    def test_post_execute_default_noop(self):
        class ConcretePhase(Phase):
            name = "test"

            def execute(self, pipeline, ctx):
                pass

        ph = ConcretePhase()
        assert ph.post_execute(object(), PhaseContext(
            cycle_count=1, state=np.zeros(2), user_name=None)) is None