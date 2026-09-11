"""Tests for SelectPhase — intent selection from evaluated candidates."""
import numpy as np
from unittest.mock import MagicMock

from telos.core.phases.select import SelectPhase
from telos.core.phases.base import PhaseContext
from telos.intent_ir import IntentIR


class TestSelectPhase:

    def test_selects_highest_weighted_intent(self):
        phase = SelectPhase()
        pipeline = MagicMock()
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        intents = [
            (IntentIR(intent_type="navigate", confidence=0.9), 1.0),
            (IntentIR(intent_type="scan", confidence=0.5), 0.3),
        ]
        ctx.intents = intents
        phase.execute(pipeline, ctx)
        assert ctx.selected_intent is not None
        assert ctx.selected_intent.intent_type == "navigate"

    def test_injects_bootstrap_keeper_when_no_intents(self):
        # Hardening fix (2026-09-11): on fresh/wiped knowledge with no stream
        # intents, the select phase injects a legitimate bootstrap_navigate
        # keeper intent instead of leaving selected_intent=None to cycle the
        # firewall's 'no_intent' block forever (selected_action=None loop).
        phase = SelectPhase()
        pipeline = MagicMock()
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = []
        phase.execute(pipeline, ctx)
        assert ctx.selected_intent is not None
        assert ctx.selected_intent.intent_type == "bootstrap_navigate"
        assert ctx.selected_intent.params.get("bootstrap") is True
        # The keeper is a REAL candidate for council/firewall (may still be
        # blocked on integrity grounds — that is honest governance).
        assert any(i.intent_type == "bootstrap_navigate"
                   for i, _ in ctx.intents)

    def test_selects_intent_even_with_zero_confidence(self):
        phase = SelectPhase()
        pipeline = MagicMock()
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = [
            (IntentIR(intent_type="navigate", confidence=0.0), 1.0),
            (IntentIR(intent_type="scan", confidence=0.0), 0.3),
        ]
        phase.execute(pipeline, ctx)
        assert ctx.selected_intent is not None
        assert ctx.selected_intent.intent_type == "navigate"

    def test_uses_synthesis_output_when_available(self):
        phase = SelectPhase()
        pipeline = MagicMock()
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        from telos.core.phases.base import SynthesisOutput
        reconciled = IntentIR(intent_type="synthesized_plan", confidence=0.85)
        ctx.synthesis = SynthesisOutput(
            reconciled_intent=reconciled,
            raw_intents=[],
            compatibility_score=0.9,
            conflicts=[],
        )
        phase.execute(pipeline, ctx)
        assert ctx.selected_intent is not None
        assert ctx.selected_intent.intent_type == "synthesized_plan"