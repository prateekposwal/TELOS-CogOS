"""Contract tests for CommitmentScore and SystemicStrainTracker — the
J(τ) commitment functional (Λ axiom 5.1 extension) and rolling strain."""
import pytest

from telos.core.decision.commitment_optimizer import (
    CommitmentScore, SystemicStrainTracker,
)


class TestCommitmentScore:
    def test_positive_reward_leads_to_full_commitment(self):
        c = CommitmentScore(expected_reward=1.0)
        assert c.commitment > 0.8
        assert c.is_full is True

    def test_heavy_costs_suppress(self):
        c = CommitmentScore(expected_reward=0.0, maintenance_cost=2.0,
                            recovery_cost=2.0, opportunity_cost=2.0)
        assert c.is_suppressed is True

    def test_clamped_bounds(self):
        c = CommitmentScore(expected_reward=100.0)
        assert 0.0 <= c.commitment <= 1.0

    def test_to_dict_serializable(self):
        c = CommitmentScore(expected_reward=0.6)
        d = c.to_dict()
        assert "commitment" in d and "is_full" in d
        import json
        json.dumps(d)


class TestSystemicStrainTracker:
    def test_strain_starts_zero(self):
        t = SystemicStrainTracker()
        assert t.current_strain == 0.0
        assert not t.is_critical

    def test_accumulating_strain_rises(self):
        t = SystemicStrainTracker(strain_threshold=5.0)
        t.record_strain(3.0, 3.0)  # 6.0 > 5.0
        assert t.current_strain >= 6.0
        assert t.is_critical is True

    def test_trend_needs_history(self):
        t = SystemicStrainTracker()
        assert t.trend == "insufficient_data"

    def test_trend_rising(self):
        t = SystemicStrainTracker()
        for v in [1.0, 2.0, 3.0]:
            t.record_strain(v, 0.0)
        assert t.trend == "rising"