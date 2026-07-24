"""Tests for EvaluatePhase — intent ranking with UCB and dominant-stream penalty."""
import numpy as np
from unittest.mock import MagicMock

from telos.core.phases.evaluate import EvaluatePhase
from telos.core.phases.base import PhaseContext
from telos.intent_ir import IntentIR


class TestEvaluatePhase:

    def test_ranks_intents_by_weight_times_confidence(self):
        phase = EvaluatePhase()
        pipeline = MagicMock()
        pipeline._planner = MagicMock()
        pipeline._planner.select_representation.return_value = "cartesian"
        pipeline._infra_manager.policy.exploration_bonus.return_value = 0.0
        pipeline._infra_manager.calibrator.is_stuck.return_value = False
        pipeline._infra_manager.calibrator.dominant_stream = None
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = [
            (IntentIR(intent_type="navigate", confidence=0.9), 1.0),
            (IntentIR(intent_type="scan", confidence=0.5), 0.3),
        ]
        phase.execute(pipeline, ctx)
        assert ctx.representation == "cartesian"
        # First intent should remain first after ranking
        assert ctx.intents[0][0].intent_type == "navigate"

    def test_handles_empty_intents(self):
        phase = EvaluatePhase()
        pipeline = MagicMock()
        pipeline._planner = MagicMock()
        pipeline._planner.select_representation.return_value = "cartesian"
        pipeline._infra_manager.policy.exploration_bonus.return_value = 0.0
        pipeline._infra_manager.calibrator.is_stuck.return_value = False
        pipeline._infra_manager.calibrator.dominant_stream = None
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = []
        phase.execute(pipeline, ctx)
        assert ctx.intents == []

    def test_no_planner_fallback(self):
        phase = EvaluatePhase()
        pipeline = MagicMock()
        pipeline._planner = None
        pipeline._infra_manager.policy.exploration_bonus.return_value = 0.0
        pipeline._infra_manager.calibrator.is_stuck.return_value = False
        pipeline._infra_manager.calibrator.dominant_stream = None
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.intents = [
            (IntentIR(intent_type="navigate", confidence=0.8), 1.0),
        ]
        phase.execute(pipeline, ctx)
        assert ctx.representation == "cartesian"
