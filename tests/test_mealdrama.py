"""Tests for MealDrama adapter v2 — diet profiles, regions, discovery."""

import numpy as np
import pytest

from telos.adapters.meal_library import (
    MEAL_LIBRARY, DIET_TYPES, REGIONS,
    get_dishes, get_dishes_by_diet, get_dishes_by_region, get_dishes_by_slot,
    compute_diet_compatibility, compute_search_quality, compute_region_diversity,
)
from telos.adapters.mealdrama_adapter import (
    MealDramaSim, MealDramaAdpt, GOAL_STATE, STATE_DIM,
    _extract_features, suggest_next_dishes,
)


class TestMealLibrary:
    def test_meal_library_has_dishes(self):
        assert len(MEAL_LIBRARY) > 20

    def test_all_dishes_have_required_fields(self):
        for dish in MEAL_LIBRARY:
            assert "id" in dish
            assert "name" in dish
            assert "region" in dish
            assert "diet" in dish
            assert "slots" in dish
            assert dish["region"] in REGIONS
            for s in dish["slots"]:
                assert s in ["breakfast", "lunch", "dinner", "snacks"]

    def test_all_diets_represented(self):
        for diet in DIET_TYPES:
            dishes = get_dishes_by_diet(diet)
            assert len(dishes) > 0, f"No dishes for diet {diet}"

    def test_all_regions_represented(self):
        for region in REGIONS:
            dishes = get_dishes_by_region(region)
            assert len(dishes) > 0, f"No dishes for region {region}"

    def test_get_dishes_filters_by_diet(self):
        veg = get_dishes(diet="vegetarian")
        nonveg = get_dishes(diet="non_veg")
        assert len(veg) > 0
        assert len(nonveg) > 0
        assert len(veg) != len(nonveg)

    def test_get_dishes_filters_by_region(self):
        north = get_dishes(region="north_indian")
        italian = get_dishes(region="italian")
        assert len(north) > 0
        assert len(italian) > 0

    def test_get_dishes_filters_by_slot(self):
        breakfast = get_dishes(slot="breakfast")
        dinner = get_dishes(slot="dinner")
        assert len(breakfast) > 0
        assert len(dinner) > 0

    def test_get_dishes_combined_filters(self):
        result = get_dishes(diet="eggetarian", region="north_indian", slot="breakfast")
        assert all("egg" in d["diet"] or "eggetarian" in d["diet"] for d in result)
        assert all(d["region"] == "north_indian" for d in result)
        assert all("breakfast" in d["slots"] for d in result)

    def test_jain_diet_no_root_vegetables(self):
        jain = get_dishes_by_diet("jain")
        for d in jain:
            assert "jain" in d["diet"]

    def test_eggetarian_has_egg_dishes(self):
        egg = get_dishes_by_diet("eggetarian")
        assert any("egg" in d["id"] or "Egg" in d["name"] for d in egg)

    def test_non_veg_has_chicken_dishes(self):
        nv = get_dishes_by_diet("non_veg")
        assert any("chicken" in d["id"] for d in nv)


class TestDietCompatibility:
    def test_100_pct_for_perfect_match(self):
        tray = {
            "breakfast": [{"id": "egg-bhurji"}],
            "lunch": [{"id": "egg-curry"}],
            "dinner": [{"id": "egg-dosa"}],
        }
        score = compute_diet_compatibility(tray, "eggetarian")
        assert score == 1.0

    def test_0_pct_for_no_match(self):
        tray = {
            "breakfast": [{"id": "aloo-paratha"}],
            "lunch": [{"id": "rajma-chawal"}],
            "dinner": [{"id": "dal-makhani"}],
        }
        score = compute_diet_compatibility(tray, "non_veg")
        assert score == 0.0

    def test_partial_match(self):
        tray = {
            "breakfast": [{"id": "egg-bhurji"}],
            "lunch": [{"id": "rajma-chawal"}],
        }
        score = compute_diet_compatibility(tray, "eggetarian")
        assert 0.4 < score < 0.6  # 1 of 2 dishes match

    def test_empty_tray_returns_zero(self):
        score = compute_diet_compatibility({}, "vegetarian")
        assert score == 0.0


class TestSearchQuality:
    def test_high_quality_when_many_options_available(self):
        tray = {"breakfast": [{"id": "aloo-paratha"}]}
        score = compute_search_quality(tray, "vegetarian")
        assert score > 0.8  # many veg dishes not in tray

    def test_low_quality_when_tray_is_full(self):
        all_veg = get_dishes_by_diet("vegetarian")
        tray = {"breakfast": [{"id": d["id"]} for d in all_veg[:5]]}
        score = compute_search_quality(tray, "vegetarian")
        assert score < 1.0


class TestRegionDiversity:
    def test_single_region(self):
        tray = {"lunch": [{"id": "rajma-chawal"}]}
        score = compute_region_diversity(tray)
        assert score == pytest.approx(1.0 / len(REGIONS), abs=0.01)

    def test_multiple_regions(self):
        tray = {
            "lunch": [{"id": "rajma-chawal"}],
            "dinner": [{"id": "pasta-arrabbiata"}],
        }
        score = compute_region_diversity(tray)
        assert score == 2.0 / len(REGIONS)

    def test_empty_tray(self):
        score = compute_region_diversity({})
        assert score == 0.0


class TestExtractFeatures:
    def test_default_snapshot(self):
        state = _extract_features(
            {"breakfast": [{"id": "aloo-paratha"}], "lunch": [], "dinner": []},
            {"2026-07-22": {"breakfast": [{"meal_id": "aloo-paratha"}]}},
            ["Rice", "Dal"],
            health_goal="balanced",
        )
        assert len(state) == STATE_DIM
        assert 0.0 <= state[10] <= 1.0  # diet_match
        assert 0.0 <= state[11] <= 1.0  # search_quality
        assert 0.0 <= state[12] <= 1.0  # region_diversity

    def test_diet_match_low_when_mismatched(self):
        state = _extract_features(
            {"breakfast": [{"id": "chicken-curry"}], "lunch": [], "dinner": []},
            {"2026-07-22": {"breakfast": [{"meal_id": "chicken-curry"}]}},
            [],
            diet_profile="vegetarian",
        )
        assert state[10] == 0.0  # chicken not vegetarian

    def test_diet_match_high_when_matched(self):
        state = _extract_features(
            {"breakfast": [{"id": "poha"}], "lunch": [], "dinner": []},
            {"2026-07-22": {"breakfast": [{"meal_id": "poha"}]}},
            [],
            diet_profile="vegetarian",
        )
        assert state[10] == 1.0

    def test_region_flag_when_preferred_set(self):
        state = _extract_features(
            {"lunch": [{"id": "rajma-chawal"}]},
            {"2026-07-22": {"lunch": [{"meal_id": "rajma-chawal"}]}},
            [],
            preferred_regions=["north_indian"],
        )
        assert state[13] == 1.0  # preferred_regions flag

    def test_no_region_flag_when_not_set(self):
        state = _extract_features(
            {"lunch": [{"id": "rajma-chawal"}]},
            {"2026-07-22": {"lunch": [{"meal_id": "rajma-chawal"}]}},
            [],
        )
        assert state[13] == 0.0


class TestMealDramaSim:
    def test_initialization(self):
        sim = MealDramaSim(diet_profile="non_veg", preferred_regions=["north_indian"])
        assert sim.diet_profile == "non_veg"
        assert sim.preferred_regions == ["north_indian"]

    def test_legal_transitions_shape(self):
        sim = MealDramaSim()
        state = np.zeros(STATE_DIM)
        transitions = sim.legal_transitions(state)
        assert len(transitions) == 9
        for t in transitions:
            assert len(t) == STATE_DIM

    def test_transition_clips_values(self):
        sim = MealDramaSim()
        state = np.ones(STATE_DIM)
        action = np.ones(STATE_DIM)
        next_state = sim.transition(state, action)
        assert np.all(next_state <= 1.0)
        assert np.all(next_state >= 0.0)

    def test_simulate_returns_worlds(self):
        sim = MealDramaSim()
        state = np.zeros(STATE_DIM)
        futures = sim.simulate(state, horizon=3)
        assert len(futures) == 3

    def test_get_facts_includes_diet_metrics(self):
        sim = MealDramaSim(diet_profile="vegan")
        state = np.zeros(STATE_DIM)
        facts = sim.get_facts(state)
        assert "diet_compatibility" in facts.metrics
        assert "search_quality" in facts.metrics
        assert "region_diversity" in facts.metrics
        assert facts.metadata["diet_profile"] == "vegan"


class TestSuggestNextDishes:
    def test_suggests_diet_compatible_dishes(self):
        tray = {"lunch": [{"id": "rajma-chawal"}]}
        suggestions = suggest_next_dishes(tray, "eggetarian", count=5)
        assert len(suggestions) > 0
        for d in suggestions:
            assert "egg" in d["diet"] or "eggetarian" in d["diet"]

    def test_excludes_existing_dishes(self):
        tray = {"lunch": [{"id": "rajma-chawal"}]}
        suggestions = suggest_next_dishes(tray, "vegetarian", count=20)
        ids = [d["id"] for d in suggestions]
        assert "rajma-chawal" not in ids

    def test_preferred_regions_prioritized(self):
        tray = {}
        suggestions = suggest_next_dishes(tray, "vegetarian",
                                           preferred_regions=["italian"], count=10)
        # Italian dishes should appear first
        regions = [d["region"] for d in suggestions]
        assert regions[0] == "italian"

    def test_empty_tray_returns_many_suggestions(self):
        suggestions = suggest_next_dishes({}, "vegetarian", count=100)
        all_veg = get_dishes_by_diet("vegetarian")
        assert len(suggestions) == min(len(all_veg), 100)


class TestEndToEnd:
    def test_full_pipeline_runs_with_diet(self):
        from telos.core.runtime import PipelineConfig, TelosV14Pipeline
        from telos.core.streams.implementations import (
            ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
        )
        from telos.core.streams.inquiry_stream import InquiryStream
        from telos.core.council.validators import (
            RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
        )
        from telos.core.ledger.skill_library import SkillLibrary
        from telos.core.simulation import CounterfactualEngine

        sim = MealDramaSim(diet_profile="non_veg")
        state = _extract_features(
            {"lunch": [{"id": "chicken-curry"}]},
            {"2026-07-22": {"lunch": [{"meal_id": "chicken-curry"}]}},
            ["Chicken", "Rice", "Spices"],
            diet_profile="non_veg",
        )

        pipeline = TelosV14Pipeline(PipelineConfig(
            adapter=MealDramaAdpt(), simulator=sim,
            compute_budget_ms=100.0, state_dim=STATE_DIM, n_worlds=5, horizon=3,
        ))
        skill_lib = SkillLibrary()
        sim_engine = CounterfactualEngine(sim)
        pipeline.register_stream(ReflexStream(skill_lib))
        pipeline.register_stream(PerceptionStream(skill_lib))
        pipeline.register_stream(MemoryStream(skill_lib))
        pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
        pipeline.register_stream(InquiryStream(skill_lib))
        pipeline.register_validator(RealityValidator())
        pipeline.register_validator(ConstraintValidator())
        pipeline.register_validator(MemoryAdvisor(skill_lib))
        pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))

        result = pipeline.execute(state, user_name="MD-App-Test")
        assert result.decision_trace is not None
        assert result.decision_trace.decision_integrity > 0

    def test_all_diet_profiles_work(self):
        for diet in DIET_TYPES:
            dishes = get_dishes_by_diet(diet)
            assert len(dishes) > 0, f"Diet {diet} has no dishes"

    def test_state_dim_matches_goal(self):
        assert len(GOAL_STATE) == STATE_DIM
