"""Contract tests for telos/core/council/validators/mission.py.

MissionDriftDetector is a reality-check: does the planned trajectory actually
stay close to observation? It blocks on instantaneous or cumulative drift
past its thresholds, and widens drift tolerance during other-uncertainty
investigation (omega_vector).
"""
import numpy as np
import pytest

from telos.core.council.validators.mission import MissionDriftDetector
from telos.world.world import World
from telos.intent_ir import IntentIR


def _validate(detector, observed, predicted, **kwargs):
    world = World(state=np.asarray(observed, dtype=float))
    trajectory = type("Traj", (), {"state": np.asarray(predicted, dtype=float)})()
    intent = IntentIR(intent_type="move", confidence=0.8,
                      params={"trajectory": trajectory})
    return detector.validate(world, intent, **kwargs)


class TestMissionDriftDetector:
    def test_name(self):
        assert MissionDriftDetector().name == "MissionDriftDetector"

    def test_default_thresholds(self):
        d = MissionDriftDetector()
        assert d.drift_threshold == 5.0
        assert d.cumulative_threshold == 10.0

    def test_no_intent_is_neutral(self):
        d = MissionDriftDetector()
        sig = d.validate(World(state=np.zeros(2)), None)
        assert sig.passed is True
        assert sig.confidence == 0.0
        assert sig.evidence_weight == 0.0
        assert d._drift_history == []

    def test_low_drift_passes_and_records(self):
        d = MissionDriftDetector(drift_threshold=5.0)
        sig = _validate(d, observed=[0, 0], predicted=[1, 0])
        assert sig.passed is True
        assert sig.confidence == 0.7
        assert sig.metadata["instantaneous_drift"] == 1.0
        assert len(d._drift_history) == 1

    def test_instantaneous_drift_blocks(self):
        d = MissionDriftDetector(drift_threshold=5.0)
        sig = _validate(d, observed=[0, 0], predicted=[0, 100])
        assert sig.passed is False
        assert sig.confidence == -0.8
        assert "instantaneous drift" in sig.reason
        assert sig.metadata["cumulative_drift"] == 100.0
        assert sig.evidence_weight == pytest.approx(0.9)

    def test_sustained_drift_blocks_cumulatively(self):
        d = MissionDriftDetector(drift_threshold=5.0, cumulative_threshold=10.0)
        found = None
        for _ in range(12):
            sig = _validate(d, observed=[0, 0], predicted=[2, 0])
            if not sig.passed:
                found = sig
                break
        assert found is not None, "cumulative drift must eventually block"
        assert "cumulative drift" in found.reason
        assert found.metadata["cumulative_drift"] == 12.0

    def test_single_small_drift_does_not_block_cumulative(self):
        d = MissionDriftDetector(cumulative_threshold=25.0)
        sig = _validate(d, observed=[0, 0], predicted=[2, 0])
        sig = _validate(d, observed=[0, 0], predicted=[2, 0])
        assert sig.passed is True
        assert sig.metadata["cumulative_drift"] == 4.0

    def test_reset_drift_clears_history(self):
        d = MissionDriftDetector()
        _validate(d, observed=[0, 0], predicted=[1, 0])
        assert len(d._drift_history) >= 1
        d.reset_drift()
        assert d._drift_history == []

    def test_window_is_bounded(self):
        d = MissionDriftDetector()
        for _ in range(300):
            _validate(d, observed=[0, 0], predicted=[1, 0])
        assert len(d._drift_history) <= MissionDriftDetector._MAX_DRIFT_WINDOW

    def test_omega_other_widens_instantaneous_tolerance(self):
        normal = MissionDriftDetector(drift_threshold=5.0)
        widened = MissionDriftDetector(drift_threshold=5.0)
        # 5.2 > 5.0 -> blocked under normal tolerance.
        sig_normal = _validate(normal, observed=[0, 0], predicted=[0, 5.2])
        assert sig_normal.passed is False
        # omega_vector other=0.5 -> tolerance_mult = 1.1 -> threshold 5.5.
        sig_widened = _validate(
            widened, observed=[0, 0], predicted=[0, 5.2],
            omega_vector={"other": 0.5},
        )
        assert sig_widened.passed is True
        assert "within bounds" in sig_widened.reason

    def test_low_omega_leaves_tolerance_unchanged(self):
        d = MissionDriftDetector(drift_threshold=5.0)
        sig = _validate(
            d, observed=[0, 0], predicted=[0, 5.2],
            omega_vector={"other": 0.1},
        )
        assert sig.passed is False