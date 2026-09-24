"""Tests for RepresentationPlanner — budget-aware meta-reasoning between
Cartesian and Polar coordinate representations."""

import numpy as np
import pytest

from telos.core.planner import RepresentationPlanner
from telos.core.attention import BudgetManager
from telos.world.facts import DomainFacts
from telos.representations.transform import IdentityTransform, PolarTransform


def make_facts(state, constraints=None, events=None, resources=None):
    return DomainFacts(
        state=np.asarray(state, dtype=float),
        resources=resources if resources is not None else {"energy": 1.0},
        constraints=constraints or [],
        events=events or [],
        metrics={},
    )


class TestConstruction:
    def test_defaults(self):
        bm = BudgetManager(total_budget_ms=100.0)
        planner = RepresentationPlanner(bm)
        assert planner.current_representation == "cartesian"
        assert planner._cycle_count == 0
        assert planner.budget_manager is bm

    def test_candidate_reps(self):
        assert RepresentationPlanner.CANDIDATE_REPS == ["cartesian", "polar"]
        assert RepresentationPlanner.SELECTION_COST_MS == 3.0


class TestGetTransform:
    def test_polar_transform(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        assert isinstance(planner.get_transform("polar"), PolarTransform)

    def test_cartesian_and_unknown_default_to_identity(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        assert isinstance(planner.get_transform("cartesian"), IdentityTransform)
        assert isinstance(planner.get_transform("spherical"), IdentityTransform)


class TestSelectRepresentation:
    def test_keeps_cartesian_for_origin_state(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        rep = planner.select_representation(make_facts([0.0, 0.0]))
        assert rep == "cartesian"
        assert planner._cycle_count == 1
        assert planner.budget_manager.consumed_ms == RepresentationPlanner.SELECTION_COST_MS

    def test_switches_to_polar_for_high_norm_state(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        rep = planner.select_representation(make_facts([10.0, 10.0]))
        assert rep == "polar"
        assert planner.current_representation == "polar"

    def test_budget_exhaustion_keeps_current_and_does_not_consume(self):
        bm = BudgetManager(total_budget_ms=2.0, consumed_ms=2.0)
        planner = RepresentationPlanner(bm)
        rep = planner.select_representation(make_facts([10.0, 10.0]))
        assert rep == "cartesian"
        assert planner._cycle_count == 1
        assert planner.budget_manager.consumed_ms == 2.0
        assert planner.selection_history == []

    def test_selection_history_records_switched_and_budget(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        planner.select_representation(make_facts([0.0, 0.0]))
        entry = planner.selection_history[0]
        assert entry["cycle"] == 1
        assert entry["selected"] == "cartesian"
        assert set(entry["scores"]) == {"cartesian", "polar"}
        assert entry["switched"] is False
        assert entry["budget_remaining"] == pytest.approx(100.0 - 3.0)


class TestGeometryScoring:
    def test_cartesian_score_prefers_low_norm(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        near = planner._score_cartesian_geometry(np.array([0.0, 0.0]))
        far = planner._score_cartesian_geometry(np.array([20.0, 0.0]))
        assert near > far

    def test_polar_score_needs_two_dimensions(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        assert planner._score_polar_geometry(np.array([3.0])) == 0.0

    def test_polar_score_prefers_high_norm(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        high = planner._score_polar_geometry(np.array([10.0, 10.0]))
        low = planner._score_polar_geometry(np.array([0.0, 0.0]))
        assert high > low

    def test_complexity_from_fact_counts(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        facts = make_facts(
            [0.0, 0.0],
            constraints=["c1", "c2"],
            events=["e1", "e2"],
            resources={"r1": 1.0, "r2": 1.0},
        )
        expected = (2 * 0.2 + 2 * 0.15 + 2 * 0.1) / 3.0
        assert planner._compute_complexity(facts) == pytest.approx(expected)

    def test_geometry_scores_bounded_in_unit_interval(self):
        planner = RepresentationPlanner(BudgetManager(total_budget_ms=100.0))
        for state in ([0.0, 0.0], [3.0, -4.0], [100.0, 100.0]):
            assert 0.0 <= planner._score_cartesian_geometry(np.array(state)) <= 1.0
            assert 0.0 <= planner._score_polar_geometry(np.array(state)) <= 1.0