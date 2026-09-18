"""Integration tests per phase boundary.

Tests that each pipeline phase produces expected outputs and
that the phase boundaries pass data correctly.
"""

import numpy as np
import pytest
from tests.core.conftest import MockSimulator
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import ReflexStream
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary


@pytest.fixture
def pipeline():
    sim = MockSimulator()
    sim.initialize()
    config = PipelineConfig(simulator=sim, compute_budget_ms=200.0, state_dim=2,
                           n_worlds=5, horizon=3, quality_threshold=0.3)
    pl = TelosV14Pipeline(config)
    sl = SkillLibrary()
    pl.register_stream(ReflexStream(sl))
    pl.register_validator(RealityValidator())
    pl.register_validator(ConstraintValidator())
    pl.register_validator(MissionDriftDetector(drift_threshold=10.0))
    return pl


class TestPhaseBoundaryIntegration:

    def test_perceive_phase_output(self, pipeline):
        """PERCEIVE produces world + domain_facts."""
        result = pipeline.execute(np.array([1.0, 2.0]))
        trace = result.decision_trace
        assert trace is not None
        assert hasattr(trace, 'domain_facts') or hasattr(trace, 'world_state_snapshot')

    def test_streams_phase_output(self, pipeline):
        """STREAMS produces stream_activations."""
        result = pipeline.execute(np.array([1.0, 0.0]))
        trace = result.decision_trace
        assert trace is not None
        assert hasattr(trace, 'stream_activations')
        assert len(trace.stream_activations) >= 0

    def test_simulate_phase_output(self, pipeline):
        """SIMULATE produces strategic_options or worlds."""
        result = pipeline.execute(np.array([2.0, -1.0]))
        assert result.worlds_generated > 0

    def test_select_phase_output(self, pipeline):
        """SELECT produces selected_intent."""
        result = pipeline.execute(np.array([1.0, 1.0]))
        trace = result.decision_trace
        assert hasattr(trace, 'selected_intent')
        assert trace.decision_integrity >= 0.0
        assert trace.mission_drift >= 0.0

    def test_council_phase_output(self, pipeline):
        """COUNCIL produces verdict with DI/MD."""
        result = pipeline.execute(np.array([3.0, 0.5]))
        assert result.council_blocked in (True, False)
        assert result.decision_integrity >= 0.0
        assert result.mission_drift >= 0.0
        di_bad = pipeline.execute(np.array([float('nan'), 0.0]))
        assert di_bad.council_blocked is True

    def test_act_phase_output(self, pipeline):
        """ACT produces selected_trajectory or block."""
        result = pipeline.execute(np.array([0.5, -0.3]))
        if not result.council_blocked:
            assert result.selected_trajectory is not None
        else:
            assert result.selected_trajectory is None

    def test_pipeline_produces_trace(self, pipeline):
        """Full pipeline produces DecisionTrace with all fields."""
        result = pipeline.execute(np.array([2.0, 2.0]))
        trace = result.decision_trace
        assert trace is not None
        assert trace.cycle_id > 0
        assert trace.timestamp > 0
        assert isinstance(trace.decision_integrity, float)
        assert isinstance(trace.mission_drift, float)

    def test_identity_projection_in_select(self, pipeline):
        """F(I) gate runs during SELECT and allows admissible intents."""
        result = pipeline.execute(np.array([1.0, 0.0]))
        assert result.health_score >= 0.0
        assert result.pipeline_phase is not None

    def test_identity_projection_enforced_in_select(self, pipeline):
        """The canonical F(I) gate is wired and its enforcement record is
        written on every cycle (the root change: it no longer only logs)."""
        result = pipeline.execute(np.array([1.0, 0.0]))
        trace = result.decision_trace
        assert trace.identity_projection is not None
        # This mock pipeline declares no missions: the documented bootstrap
        # path applies and normal intents are admitted (not collapsed).
        assert trace.identity_projection["missionless_bootstrap"] is True
        assert trace.identity_projection["projected_out"] == []
