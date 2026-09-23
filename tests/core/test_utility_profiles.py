"""Contract tests for identity utility profiles — named weight vectors that
turn dimension scores into a weighted utility, plus the engine that selects
the active profile."""
import pytest

from telos.core.identity.utility_profiles import (
    UtilityProfile, UtilityDimension, IdentityUtilityEngine,
    COLLABORATIVE_PROFILE, TELOS_PROFILE,
)


class TestUtilityProfile:
    def test_compute_weighted_score(self):
        p = UtilityProfile(
            name="t", description="d",
            weights={UtilityDimension.CORRECTNESS: 0.8,
                     UtilityDimension.SAFETY: 0.2},
            identity_markers=["marker"],
        )
        u = p.compute({UtilityDimension.CORRECTNESS: 1.0,
                       UtilityDimension.SAFETY: 0.0})
        assert u == pytest.approx(0.8)

    def test_compute_ignores_unweighted_dims(self):
        p = UtilityProfile(
            name="t", description="d",
            weights={UtilityDimension.CORRECTNESS: 1.0},
            identity_markers=[],
        )
        u = p.compute({UtilityDimension.EXPLORATION: 1.0})
        assert u == pytest.approx(0.5)  # default when no matching weight

    def test_collaborative_profile_prioritizes_collaboration(self):
        # The real collaborative profile favors being helpful over being
        # strictly correct (per its own description + weights).
        assert COLLABORATIVE_PROFILE.weights[UtilityDimension.COLLABORATION] > \
            COLLABORATIVE_PROFILE.weights[UtilityDimension.CORRECTNESS]

    def test_telos_profile_prioritizes_correctness(self):
        assert TELOS_PROFILE.weights[UtilityDimension.CORRECTNESS] > \
            TELOS_PROFILE.weights[UtilityDimension.COLLABORATION]


class TestIdentityUtilityEngine:
    def test_selection_with_no_markers_returns_balanced(self):
        from telos.core.identity.utility_profiles import BALANCED_PROFILE
        engine = IdentityUtilityEngine()
        assert engine.select_profile([]) is BALANCED_PROFILE

    def test_selection_with_correctness_marker(self):
        from telos.core.identity.utility_profiles import COLLABORATIVE_PROFILE
        engine = IdentityUtilityEngine()
        profile = engine.select_profile(COLLABORATIVE_PROFILE.identity_markers)
        assert profile is not None

    def test_register_profile_adds_custom(self):
        from telos.core.identity.utility_profiles import UtilityProfile, UtilityDimension
        engine = IdentityUtilityEngine()
        p = UtilityProfile(
            name="Mine", description="custom",
            weights={UtilityDimension.CORRECTNESS: 1.0},
            identity_markers=["mine"],
        )
        engine.register_profile(p)
        assert engine._profiles["mine"] is p