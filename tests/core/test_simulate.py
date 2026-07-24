"""Tests for SimulatePhase — counterfactual simulation and budget awareness."""
import numpy as np
import pytest
from unittest.mock import MagicMock

from telos.core.phases.simulate import SimulatePhase
from telos.core.phases.base import PhaseContext
from telos.core.simulation import CounterfactualEngine
from tests.core.conftest import MockSimulator


class TestSimulatePhase:

    def test_no_sim_engine_skips_simulation(self):
        phase = SimulatePhase()
        pipeline = MagicMock()
        pipeline._sim_engine = None
        pipeline._infra_manager.adaptive_horizon = None
        pipeline.config.horizon = 8
        pipeline.config.feedback_lag = 0
        pipeline.budget_manager.check_budget.return_value = True
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        phase.execute(pipeline, ctx)
        assert ctx.worlds_generated == 0
        assert ctx.sim_options is None

    def test_budget_check_prevents_simulation(self):
        phase = SimulatePhase()
        pipeline = MagicMock()
        pipeline._sim_engine = CounterfactualEngine(MockSimulator())
        pipeline._infra_manager.adaptive_horizon = None
        pipeline.config.horizon = 8
        pipeline.config.feedback_lag = 0
        pipeline.budget_manager.check_budget.return_value = False
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        phase.execute(pipeline, ctx)
        assert ctx.worlds_generated == 0

    def test_simulates_worlds(self):
        phase = SimulatePhase()
        pipeline = MagicMock()
        sim = MockSimulator()
        pipeline._sim_engine = CounterfactualEngine(sim)
        pipeline._infra_manager.adaptive_horizon = None
        pipeline.config.horizon = 4
        pipeline.config.feedback_lag = 0
        pipeline.config.n_worlds = 5
        pipeline.budget_manager.check_budget.return_value = True
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.effective_n_worlds = 5
        phase.execute(pipeline, ctx)
        assert ctx.worlds_generated > 0
        assert ctx.sim_options is not None

    def test_sets_predicted_state_and_confidence(self):
        phase = SimulatePhase()
        pipeline = MagicMock()
        sim = MockSimulator()
        pipeline._sim_engine = CounterfactualEngine(sim)
        pipeline._infra_manager.adaptive_horizon = None
        pipeline.config.horizon = 4
        pipeline.config.feedback_lag = 0
        pipeline.config.n_worlds = 5
        pipeline.budget_manager.check_budget.return_value = True
        ctx = PhaseContext(cycle_count=1, state=np.array([1.0, 2.0]), user_name=None)
        ctx.effective_n_worlds = 5
        phase.execute(pipeline, ctx)
        assert ctx.predicted_state is not None
        assert ctx.simulation_confidence > 0.0

    def test_effective_horizon_respects_feedback_lag(self):
        phase = SimulatePhase()
        pipeline = MagicMock()
        pipeline._infra_manager.adaptive_horizon = None
        pipeline.config.horizon = 3
        pipeline.config.feedback_lag = 2
        pipeline._sim_engine = None
        pipeline.budget_manager.check_budget.return_value = True
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        phase.execute(pipeline, ctx)
        assert ctx.effective_horizon == max(3, 2 + 1)

    def test_adaptive_horizon_from_infra(self):
        phase = SimulatePhase()
        pipeline = MagicMock()
        pipeline._infra_manager.adaptive_horizon = 10
        pipeline.config.horizon = 3
        pipeline.config.feedback_lag = 0
        pipeline._sim_engine = None
        pipeline.budget_manager.check_budget.return_value = True
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        phase.execute(pipeline, ctx)
        assert ctx.effective_horizon == 10

    def test_strategic_options_data_populated(self):
        phase = SimulatePhase()
        pipeline = MagicMock()
        sim = MockSimulator()
        pipeline._sim_engine = CounterfactualEngine(sim)
        pipeline._infra_manager.adaptive_horizon = None
        pipeline.config.horizon = 4
        pipeline.config.feedback_lag = 0
        pipeline.config.n_worlds = 5
        pipeline.budget_manager.check_budget.return_value = True
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        ctx.effective_n_worlds = 5
        phase.execute(pipeline, ctx)
        assert len(ctx.strategic_options_data) > 0
        assert "score" in ctx.strategic_options_data[0]
        assert "horizon" in ctx.strategic_options_data[0]
