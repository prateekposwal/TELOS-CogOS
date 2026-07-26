"""End-to-end integration test for TelosV14Pipeline.

Tests full orchestration: execute() → 9 phases → Council → Axiom → PipelineResult.
Uses MockSimulator + ReflexStream + 3 council validators.
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
    """Minimal pipeline with one stream and three validators."""
    sim = MockSimulator()
    sim.initialize()
    config = PipelineConfig(
        simulator=sim,
        compute_budget_ms=200.0,
        state_dim=2,
        n_worlds=5,
        horizon=3,
        quality_threshold=0.3,
    )
    pl = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    pl.register_stream(ReflexStream(skill_lib))
    pl.register_validator(RealityValidator())
    pl.register_validator(ConstraintValidator())
    pl.register_validator(MissionDriftDetector(drift_threshold=10.0))
    return pl


class TestPipelineIntegration:

    def test_happy_path_full_execution(self, pipeline):
        """Assertion 1: Pipeline completes and returns PipelineResult."""
        state = np.array([1.0, 2.0])
        result = pipeline.execute(state)
        assert result is not None
        assert result.pipeline_phase is not None
        assert result.health_score >= 0.0

    def test_council_validates_normal_state(self, pipeline):
        """Assertion 2: Council validates and produces DI/MD."""
        state = np.array([0.5, -0.3])
        result = pipeline.execute(state)
        assert result.decision_integrity >= 0.0
        assert result.mission_drift >= 0.0

    def test_council_blocks_nan_state(self, pipeline):
        """Assertion 3: Council blocks invalid (NaN) state."""
        state = np.array([float('nan'), 2.0])
        result = pipeline.execute(state)
        assert result.council_blocked is True
        assert result.selected_trajectory is None

    def test_decision_trace_integrity(self, pipeline):
        """Assertion 4: DecisionTrace has required fields with correct types."""
        state = np.array([3.0, 1.0])
        result = pipeline.execute(state)
        trace = result.decision_trace
        assert trace is not None
        assert isinstance(trace.decision_integrity, float)
        assert isinstance(trace.mission_drift, float)
        assert hasattr(trace, 'council_signals')
        assert 0.0 <= result.health_score <= 1.0

    def test_health_score_bounded_multiple_cycles(self, pipeline):
        """Assertion 5: Health stays in [0,1] across repeated execution."""
        state = np.array([0.0, 0.0])
        for _ in range(5):
            result = pipeline.execute(state)
            assert 0.0 <= result.health_score <= 1.0
            if result.selected_trajectory is not None:
                state = state + np.array([0.1, 0.0])

    def test_shutdown_cleanup(self, pipeline):
        """Assertion 6: shutdown() does not raise."""
        try:
            pipeline.shutdown()
        except Exception as e:
            pytest.fail(f"shutdown() raised: {e}")
