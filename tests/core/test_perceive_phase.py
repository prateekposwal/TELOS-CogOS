"""Tests for PerceivePhase — world construction and knowledge consultation."""
import numpy as np
from unittest.mock import MagicMock

from telos.core.phases.perceive import PerceivePhase
from telos.core.phases.base import PhaseContext


class TestPerceivePhase:

    def test_builds_world_with_metadata(self):
        phase = PerceivePhase()
        pipeline = MagicMock()
        pipeline._infra_manager.consult_knowledge.return_value = {
            "adjust_risk": 0.0, "adjust_exploration": 0.0,
            "quality_adjustment": 0.0,
        }
        pipeline._perception_quality.assess.return_value = MagicMock(
            to_dict=lambda: {"quality_score": 0.8},
        )
        pipeline._resolution_gate.evaluate.return_value = MagicMock(
            passed=True, proxy_activated=False, reason="ok",
        )
        pipeline.config.simulator = MagicMock()
        pipeline.config.simulator.get_facts.return_value = MagicMock(
            metrics={"uncertainty": 0.1},
            constraints=[],
        )
        pipeline.config.simulator.domain = "test_domain"
        pipeline.config.n_worlds = 30
        pipeline.config.adaptive_worlds_enabled = True
        pipeline.trust_manager.authorize_knowledge_release.return_value = True
        pipeline.ledger.upsert_user.return_value = MagicMock(
            trust_level=0.5, relationship_summary="new_user",
            total_interactions=1,
        )
        pipeline._infra_manager.policy.current.recovery_mode = False
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name="test_user")
        phase.execute(pipeline, ctx)
        assert ctx.perceive is not None
        assert ctx.perceive.world is not None
        assert ctx.perceive.effective_n_worlds > 0
        assert "test_user" in str(ctx.perceive.world.metadata)

    def test_no_user_no_failure(self):
        phase = PerceivePhase()
        pipeline = MagicMock()
        pipeline._infra_manager.consult_knowledge.return_value = {
            "adjust_risk": 0.0, "adjust_exploration": 0.0,
            "quality_adjustment": 0.0,
        }
        pipeline._perception_quality.assess.return_value = MagicMock(
            to_dict=lambda: {"quality_score": 0.8},
        )
        pipeline._resolution_gate.evaluate.return_value = MagicMock(
            passed=True, proxy_activated=False, reason="ok",
        )
        pipeline.config.simulator = MagicMock()
        pipeline.config.simulator.get_facts.return_value = MagicMock(
            metrics={"uncertainty": 0.1}, constraints=[],
        )
        pipeline.config.simulator.domain = "test_domain"
        pipeline.config.n_worlds = 30
        pipeline.config.adaptive_worlds_enabled = True
        pipeline.trust_manager.authorize_knowledge_release.return_value = True
        pipeline._infra_manager.policy.current.recovery_mode = False
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        phase.execute(pipeline, ctx)
        assert ctx.perceive is not None
        assert ctx.perceive.world is not None
