"""Contract tests for TimeHorizonSeparator — four-horizon utility evaluation
with discount factors, weight profiles, and irreversible vetos."""
import pytest

from telos.core.decision.time_horizon import (
    TimeHorizonSeparator, Horizon, HorizonEvaluation, BALANCED_HORIZON,
)


class TestHorizonSeparator:
    def test_evaluate_produces_total_and_utilities(self):
        s = TimeHorizonSeparator()
        ev = s.evaluate("a1", "do x",
                        {"immediate": 0.5, "short_term": 0.5,
                         "long_term": 0.5, "irreversible": 0.5})
        assert isinstance(ev, HorizonEvaluation)
        assert 0.0 <= ev.total_utility <= 1.0
        assert len(ev.horizon_utilities) == 4

    def test_discounted_utility_is_scaled(self):
        hu = BALANCED_HORIZON  # verify weights exist
        assert abs(sum(hu.weights.values()) - 1.0) < 1e-6

    def test_irreversible_negative_vetoes(self):
        s = TimeHorizonSeparator()
        ev = s.evaluate("a2", "irreversible harm",
                        {"immediate": 0.9, "short_term": 0.9,
                         "long_term": 0.9, "irreversible": 0.1},
                        irreversible_flag=True,
                        irreversible_description="permanent consequence")
        assert ev.vetoed is True
        assert "permanent consequence" in ev.veto_reason
        assert ev.total_utility == 0.0

    def test_set_active_profile_validates(self):
        s = TimeHorizonSeparator()
        assert s.set_active_profile("farsighted") is True
        assert s.set_active_profile("no_such_profile") is False

    def test_set_discount_factor_clamps(self):
        s = TimeHorizonSeparator()
        s.set_discount_factor(Horizon.LONG_TERM, 2.0)
        assert s._discount_factors[Horizon.LONG_TERM] == 1.0