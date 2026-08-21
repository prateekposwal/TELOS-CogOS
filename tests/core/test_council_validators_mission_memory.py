"""Contract tests for MissionDriftDetector and MemoryAdvisor validators.

MissionDriftDetector is a reality-check on whether the planned trajectory
actually produces the mission outcome; it tracks cumulative drift (a warning
is a single high-drift cycle, a block is sustained drift). MemoryAdvisor
scores intents against the skill library's learned lessons.
"""
import numpy as np
import pytest

from telos.core.council.validators.mission import MissionDriftDetector
from telos.core.council.validators.memory import MemoryAdvisor
from telos.core.ledger.skill_library import SkillLibrary
from telos.intent_ir import IntentIR
from telos.world.world import World


class TestMissionDriftDetector:
    """Sustained drift triggers a block; a single spike is a warning."""

    def _validate_drift(self, detector, predicted, observed):
        world = World(state=np.asarray(observed, dtype=float))
        trajectory = type("Traj", (), {"state": np.asarray(predicted, dtype=float)})()
        intent = IntentIR(intent_type="move", confidence=0.8,
                          params={"trajectory": trajectory})
        return detector.validate(world, intent)

    def test_no_intent_is_neutral(self):
        d = MissionDriftDetector()
        sig = d.validate(World(state=np.zeros(2)), None)
        assert sig.passed is True

    def test_low_drift_passes_and_records(self):
        d = MissionDriftDetector(drift_threshold=5.0)
        sig = self._validate_drift(d, observed=[0, 0], predicted=[1, 0])
        assert sig.passed is True
        assert len(d._drift_history) >= 1

    def test_instantaneous_drift_blocks(self):
        d = MissionDriftDetector(drift_threshold=5.0)
        sig = self._validate_drift(d, observed=[0, 0], predicted=[0, 100])
        assert sig.passed is False
        assert "instantaneous drift" in sig.reason

    def test_sustained_drift_blocks_cumulatively(self):
        d = MissionDriftDetector(drift_threshold=5.0, cumulative_threshold=10.0)
        # Each cycle: |predicted - observed| = 2.0 (below 5), but repeated
        # accumulation crosses the cumulative 10.0 threshold -> block.
        blocked_at_least_once = False
        for _ in range(60):
            sig = self._validate_drift(d, observed=[0, 0], predicted=[2, 0])
            if not sig.passed:
                blocked_at_least_once = True
                assert "cumulative drift" in sig.reason
                break
        assert blocked_at_least_once, "sustained drift must eventually block"

    def test_reset_drift_clears_history(self):
        d = MissionDriftDetector()
        self._validate_drift(d, observed=[0, 0], predicted=[1, 0])
        assert len(d._drift_history) >= 1
        d.reset_drift()
        assert d._drift_history == []

    def test_window_is_bounded(self):
        d = MissionDriftDetector()
        for i in range(300):
            self._validate_drift(d, observed=[0, 0], predicted=[1, 0])
        assert len(d._drift_history) <= MissionDriftDetector._MAX_DRIFT_WINDOW


class TestMemoryAdvisor:
    """Scores intents against the learned skill library."""

    def test_no_intent_is_neutral(self):
        advisor = MemoryAdvisor(SkillLibrary())
        sig = advisor.validate(World(state=np.zeros(2)), None)
        assert sig.passed is True

    def test_clean_intent_advises_pass(self):
        advisor = MemoryAdvisor(SkillLibrary())
        sig = advisor.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="move", confidence=0.8),
        )
        assert sig.passed is True
        assert sig.validator_name == "MemoryAdvisor"