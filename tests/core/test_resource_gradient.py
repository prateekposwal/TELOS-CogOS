"""
ResourceGradientTracker — P4 resource accounting + reallocation loop.

Honest contract coverage (telos/core/accounting/resource_gradient.py):
  - compute_gradients: ∂J/∂r_i via +10% perturbation per resource dimension,
    against a fake CommitmentOptimizer with a known linear score so the
    gradient magnitude is asserted exactly.
  - Guard behavior: None optimizer and empty budget dicts yield zero gradients.
  - reallocate: R_{t+1} = argmax_R U_R shifts budget from negative-gradient to
    positive-gradient resources (normalized to sum ~1.0, negative floor at 0.05).
  - Properties (gradients / gradient_history / dominant_resource /
    reallocations_performed) and to_dict serialization.
"""
import pytest

from telos.core.accounting.resource_gradient import ResourceGradientTracker


class FakeCommitment:
    def __init__(self, commitment):
        self.commitment = commitment


class LinearCommitmentOptimizer:
    """commitment is a linear function of the perturbable resources so each
    gradient equals the analytic slope (delta_j / delta collapses to slope)."""

    def evaluate(self, **kwargs):
        c = (
            (1.0 - kwargs["maintenance_cost"]) * 0.3
            + (1.0 - kwargs["recovery_cost"]) * 0.3
            + (1.0 - kwargs["identity_cost"]) * 0.2
            + kwargs["future_option_value"] * 0.1
            + (1.0 - kwargs["prediction_error"]) * 0.1
        )
        return FakeCommitment(c)


def make_budgets():
    return {
        "energy": {"value": 0.5},
        "memory": {"value": 0.4},
        "identity": {"value": 0.3},
        "recovery": {"value": 0.2},
    }


class TestComputeGradients:
    def test_resource_dimensions_exposed(self):
        t = ResourceGradientTracker()
        assert t.RESOURCE_DIMENSIONS == ["energy", "memory", "identity", "recovery"]
        assert t.PERTURBATION_FRACTION == 0.10

    def test_fresh_tracker_has_zero_gradients(self):
        t = ResourceGradientTracker()
        assert t.gradients == {
            "energy": 0.0, "memory": 0.0, "identity": 0.0, "recovery": 0.0
        }
        assert t.dominant_resource is None
        assert t.reallocations_performed == 0

    def test_gradients_match_analytic_slopes(self):
        """With a linear score, delta_j/delta must equal the score's slope for
        each resource: energy +0.29, memory +0.05, identity -0.20, recovery -0.30."""
        t = ResourceGradientTracker()
        g = t.compute_gradients(LinearCommitmentOptimizer(), make_budgets())
        assert g["energy"] == pytest.approx(0.29, abs=1e-6)
        assert g["memory"] == pytest.approx(0.05, abs=1e-6)
        assert g["identity"] == pytest.approx(-0.20, abs=1e-6)
        assert g["recovery"] == pytest.approx(-0.30, abs=1e-6)

    def test_dominant_resource_is_highest_positive_gradient(self):
        t = ResourceGradientTracker()
        t.compute_gradients(LinearCommitmentOptimizer(), make_budgets())
        assert t.dominant_resource == "energy"

    def test_none_optimizer_yields_zero_gradients(self):
        t = ResourceGradientTracker()
        g = t.compute_gradients(None, make_budgets())
        assert g == {r: 0.0 for r in t.RESOURCE_DIMENSIONS}
        assert t.gradient_history == []

    def test_empty_budgets_yield_zero_gradients(self):
        t = ResourceGradientTracker()
        g = t.compute_gradients(LinearCommitmentOptimizer(), {})
        assert g == {r: 0.0 for r in t.RESOURCE_DIMENSIONS}

    def test_optimizer_raising_is_guarded(self):
        class Broken:
            def evaluate(self, **kwargs):
                raise RuntimeError("boom")
        t = ResourceGradientTracker()
        g = t.compute_gradients(Broken(), make_budgets())
        assert g == {r: 0.0 for r in t.RESOURCE_DIMENSIONS}

    def test_gradient_history_records_base_score(self):
        t = ResourceGradientTracker()
        t.compute_gradients(LinearCommitmentOptimizer(), make_budgets())
        hist = t.gradient_history
        assert len(hist) == 1
        assert hist[0]["_base_score"] == pytest.approx(0.645)
        assert set(hist[0]) == set(t.RESOURCE_DIMENSIONS + ["_base_score"])

    def test_gradient_history_is_capped(self):
        class Flat:
            def evaluate(self, **kwargs):
                return FakeCommitment(0.5)
        t = ResourceGradientTracker()
        for _ in range(60):
            t.compute_gradients(Flat(), make_budgets())
        assert len(t.gradient_history) == 50


class TestReallocate:
    def test_shift_toward_positive_gradient(self):
        """Equal starting shares: energy (positive, strongest gradient) gains,
        recovery (negative) loses, output re-normalized to ~1.0."""
        t = ResourceGradientTracker()
        budgets = {"energy": 0.25, "memory": 0.25, "identity": 0.25, "recovery": 0.25}
        g = {"energy": 0.29, "memory": 0.05, "identity": -0.2, "recovery": -0.3}
        r = t.reallocate(budgets, g)
        assert r["energy"] > 0.25
        assert r["memory"] > 0.25
        assert r["identity"] < 0.25
        assert r["recovery"] < 0.25
        assert sum(r.values()) == pytest.approx(1.0, abs=1e-6)

    def test_negative_floor_at_0_05(self):
        """A resource with a zero allocation and a negative gradient is floored
        to at least 0.05, never driven to zero."""
        t = ResourceGradientTracker()
        budgets = {
            "energy": {"utilization": 1.0},
            "memory": {"utilization": 1.0},
            "identity": {"utilization": 1.0},
            "recovery": {"utilization": 0.0},
        }
        g = {"energy": 0.29, "memory": 0.05, "identity": -0.2, "recovery": -0.3}
        r = t.reallocate(budgets, g)
        assert r["recovery"] > 0.0
        assert sum(r.values()) == pytest.approx(1.0, abs=1e-6)

    def test_partial_gradients_only_shift_listed_resources(self):
        """Only the listed (energy) resource gains; the unlisted resources keep
        their relative equal share but are all scaled down slightly by the
        re-normalization that keeps the total at 1.0."""
        t = ResourceGradientTracker()
        budgets = {"energy": 0.25, "memory": 0.25, "identity": 0.25, "recovery": 0.25}
        r = t.reallocate(budgets, {"energy": 0.29})
        assert r["energy"] > 0.25
        assert r["memory"] == pytest.approx(r["identity"], abs=1e-12)
        assert r["memory"] == pytest.approx(r["recovery"], abs=1e-12)
        assert r["memory"] == pytest.approx(0.25 / (1.0 + 0.05 * 0.29), abs=1e-6)
        assert sum(r.values()) == pytest.approx(1.0, abs=1e-6)

    def test_reallocation_count_increments(self):
        t = ResourceGradientTracker()
        budgets = {"energy": 0.25, "memory": 0.25, "identity": 0.25, "recovery": 0.25}
        t.reallocate(budgets, {"energy": 1.0})
        t.reallocate(budgets, {"energy": 1.0})
        assert t.reallocations_performed == 2

    def test_missing_dimension_defaults_to_equal_share(self):
        t = ResourceGradientTracker()
        r = t.reallocate({"energy": {"utilization": 1.0}}, {})
        # missing dimensions default to 0.25, then normalize across all 4
        assert set(r.keys()) == set(t.RESOURCE_DIMENSIONS)
        assert sum(r.values()) == pytest.approx(1.0, abs=1e-6)


class TestSerialization:
    def test_to_dict(self):
        t = ResourceGradientTracker()
        t.compute_gradients(LinearCommitmentOptimizer(), make_budgets())
        d = t.to_dict()
        assert set(d) == {"gradients", "dominant_resource", "reallocations_performed", "recent_history"}
        assert d["dominant_resource"] == "energy"
        assert d["reallocations_performed"] == 0
        assert len(d["recent_history"]) == 1
        assert d["recent_history"][0]["_base_score"] == pytest.approx(0.645)

    def test_recent_history_truncated_to_five(self):
        class Flat:
            def evaluate(self, **kwargs):
                return FakeCommitment(0.5)
        t = ResourceGradientTracker()
        for _ in range(10):
            t.compute_gradients(Flat(), make_budgets())
        assert len(t.to_dict()["recent_history"]) == 5
