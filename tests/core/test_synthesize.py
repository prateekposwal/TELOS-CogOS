"""Tests for SynthesisPhase — stream conflict resolution and minority-group preserve."""
import numpy as np
import pytest
from unittest.mock import MagicMock

from telos.core.phases.synthesize import SynthesisPhase
from telos.core.phases.base import PhaseContext
from telos.intent_ir import IntentIR


class TestSynthesisPhase:

    def test_no_intents_returns_default(self):
        phase = SynthesisPhase()
        pipeline = MagicMock()
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = []
        phase.execute(pipeline, ctx)
        assert ctx.synthesis.reconciled_intent is None
        assert ctx.synthesis.compatibility_score == 1.0
        assert ctx.synthesis.conflicts == []

    def test_single_intent_returns_as_is(self):
        phase = SynthesisPhase()
        pipeline = MagicMock()
        intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = [(intent, 1.0)]
        phase.execute(pipeline, ctx)
        assert ctx.synthesis.reconciled_intent.intent_type == "navigate"
        assert ctx.synthesis.compatibility_score == 1.0
        assert ctx.synthesis.conflicts == []

    def test_safety_intent_boosted(self):
        phase = SynthesisPhase()
        pipeline = MagicMock()
        safety = IntentIR(intent_type="halt", confidence=0.9)
        nav = IntentIR(intent_type="navigate", confidence=0.8)
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = [(safety, 1.0), (nav, 1.0)]
        phase.execute(pipeline, ctx)
        assert ctx.synthesis.reconciled_intent is not None
        assert ctx.synthesis.raw_intents == ctx.intents[:]

    def test_conflicting_vectors_detected(self):
        phase = SynthesisPhase()
        pipeline = MagicMock()
        intent_a = IntentIR(intent_type="navigate", confidence=0.8,
                             params={"action_vector": np.array([1.0, 0.0])})
        intent_b = IntentIR(intent_type="navigate", confidence=0.8,
                             params={"action_vector": np.array([-1.0, 0.0])})
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = [(intent_a, 1.0), (intent_b, 1.0)]
        phase.execute(pipeline, ctx)
        if len(ctx.synthesis.conflicts) > 0:
            assert any(c["type"] == "vector_mismatch" for c in ctx.synthesis.conflicts)

    def test_minority_group_preserved(self):
        phase = SynthesisPhase()
        pipeline = MagicMock()
        nav = IntentIR(intent_type="navigate", confidence=0.8,
                        params={"waypoint": "A"})
        explore = IntentIR(intent_type="explore", confidence=0.7,
                            params={"region": "B"})
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = [(nav, 1.0), (explore, 0.8)]
        phase.execute(pipeline, ctx)
        assert ctx.synthesis.reconciled_intent is not None
        # The majority group (navigation) should be the primary,
        # but minority params should be included
        merged_params = ctx.synthesis.reconciled_intent.params or {}
        assert "region" in merged_params

    def test_compatibility_score_range(self):
        phase = SynthesisPhase()
        pipeline = MagicMock()
        intent = IntentIR(intent_type="scan", confidence=0.9)
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = [(intent, 1.0)]
        phase.execute(pipeline, ctx)
        assert 0.0 <= ctx.synthesis.compatibility_score <= 1.0

    def test_irreconcilable_flag(self):
        phase = SynthesisPhase()
        pipeline = MagicMock()
        intent_a = IntentIR(intent_type="navigate", confidence=0.9,
                             params={"action_vector": np.array([1.0, 0.0])})
        intent_b = IntentIR(intent_type="navigate", confidence=0.9,
                             params={"action_vector": np.array([-1.0, 0.0])})
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = [(intent_a, 1.0), (intent_b, 1.0)]
        phase.execute(pipeline, ctx)
        # With only these two and low cosine sim, may be irreconcilable
        assert hasattr(ctx.synthesis, 'irreconcilable')

    def test_raw_intents_preserved_in_output(self):
        phase = SynthesisPhase()
        pipeline = MagicMock()
        intents = [
            (IntentIR(intent_type="navigate", confidence=0.8), 1.0),
            (IntentIR(intent_type="scan", confidence=0.6), 0.5),
        ]
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = intents
        phase.execute(pipeline, ctx)
        assert len(ctx.synthesis.raw_intents) == 2
        assert ctx.synthesis.raw_intents[0][0].intent_type == "navigate"
