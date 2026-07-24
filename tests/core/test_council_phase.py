"""Tests for CouncilPhase — epistemic integrity validation and alternative fallback."""
import numpy as np
from unittest.mock import MagicMock

from telos.core.phases.council import CouncilPhase
from telos.core.phases.base import PhaseContext, SynthesisOutput
from telos.core.council.base import CouncilVerdict, ValidationSignal
from telos.intent_ir import IntentIR


class TestCouncilPhase:

    def test_validates_selected_intent(self):
        phase = CouncilPhase()
        pipeline = MagicMock()
        pipeline.council.evaluate.return_value = CouncilVerdict(
            validated=True, decision_integrity=0.9, mission_drift=0.1,
            signals=[], blocking_validator=None,
            escalation_requested=False, escalation_reason=None,
        )
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        phase.execute(pipeline, ctx)
        assert ctx.verdict.validated
        assert ctx.verdict.decision_integrity == 0.9

    def test_council_block_sets_verdict(self):
        phase = CouncilPhase()
        pipeline = MagicMock()
        pipeline.council.evaluate.return_value = CouncilVerdict(
            validated=False, decision_integrity=0.3, mission_drift=2.0,
            signals=[ValidationSignal(validator_name="test", passed=False,
                                       confidence=-0.8, reason="blocked",
                                       evidence_weight=0.5, verdict="BLOCK")],
            blocking_validator="RealityValidator",
            escalation_requested=False, escalation_reason=None,
        )
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.intents = [(ctx.selected_intent, 1.0)]
        phase.execute(pipeline, ctx)
        assert not ctx.verdict.validated
        assert ctx.verdict.blocking_validator == "RealityValidator"

    def test_falls_back_to_alternative_on_block(self):
        phase = CouncilPhase()
        pipeline = MagicMock()
        primary = IntentIR(intent_type="navigate", confidence=0.9)
        alt = IntentIR(intent_type="scan", confidence=0.6)
        pipeline.council.evaluate.side_effect = [
            CouncilVerdict(validated=False, decision_integrity=0.3, mission_drift=2.0,
                            signals=[], blocking_validator="test",
                            escalation_requested=False, escalation_reason=None),
            CouncilVerdict(validated=True, decision_integrity=0.8, mission_drift=0.2,
                            signals=[], blocking_validator=None,
                            escalation_requested=False, escalation_reason=None),
        ]
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = primary
        ctx.intents = [(primary, 1.0), (alt, 0.6)]
        phase.execute(pipeline, ctx)
        assert ctx.selected_intent is alt
        assert ctx._council_fallback_attempted

    def test_synthesis_irreconcilable_injects_escalate(self):
        phase = CouncilPhase()
        pipeline = MagicMock()
        pipeline.council.evaluate.return_value = CouncilVerdict(
            validated=True, decision_integrity=0.9, mission_drift=0.1,
            signals=[], blocking_validator=None,
            escalation_requested=False, escalation_reason=None,
        )
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
        ctx.synthesis = SynthesisOutput(
            reconciled_intent=ctx.selected_intent,
            raw_intents=[],
            compatibility_score=0.2,
            conflicts=[{"type": "vector_mismatch"}],
            irreconcilable=True,
        )
        phase.execute(pipeline, ctx)
        assert ctx.verdict.escalation_requested
