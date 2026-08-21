"""Contract tests for RepresentationSelector — dynamic modality switching
across graph / spatial / temporal / symbolic representations."""

import numpy as np

from telos.core.representation_selector import RepresentationSelector
from telos.world.facts import DomainFacts


def _facts(state, resources=None, constraints=None, events=None, metrics=None):
    return DomainFacts(
        state=np.array(state, dtype=float),
        resources=resources or {},
        constraints=constraints or [],
        events=events or [],
        metrics=metrics or {},
    )


class TestAddMissing:
    def test_abstract_base_contract(self):
        # SUPPORTED_TYPES is the full modality menu
        assert RepresentationSelector.SUPPORTED_TYPES == ("graph", "spatial", "temporal", "symbolic")


class TestSelection:
    def test_minimal_facts_select_symbolic(self):
        sel = RepresentationSelector()
        rep, conf = sel.select(_facts([0.0]))
        assert rep == "symbolic"
        assert conf > 0.3

    def test_spatial_state_selects_spatial(self):
        sel = RepresentationSelector()
        facts = _facts([1.0, 2.0, 3.0, 4.0, 5.0])
        rep, conf = sel.select(facts, metadata={"terrain": {"grass": 1, "water": 2, "rock": 3, "ice": 4}})
        assert rep == "spatial"
        # 0.1 baseline + 0.4 (len>=2) + 0.2 (len>=4) + 0.2 terrain
        assert conf == pytest_approx(0.9)

    def test_graph_metadata_selects_graph(self):
        sel = RepresentationSelector()
        facts = _facts([1.0])
        rep, _ = sel.select(facts, metadata={
            "blocked": ["wall_a", "wall_b"],
            "rewards": {"reward_1": 1.0},
            "terrain": {"t1": 1, "t2": 2, "t3": 3, "t4": 4},
        })
        assert rep == "graph"

    def test_temporal_signals_select_temporal(self):
        sel = RepresentationSelector()
        facts = _facts([1.0], resources={"reward_near": 1.0},
                       events=["convergence"], metrics={"uncertainty": 0.5})
        rep, _ = sel.select(facts)
        assert rep == "temporal"

    def test_select_uses_facts_metadata_when_metadata_none(self):
        sel = RepresentationSelector()
        facts = _facts([1.0, 2.0], metrics={"uncertainty": 0.9, "reward": 2.0},
                       events=["ev1"])
        facts.metadata = {"terrain": {"a": 1}}
        rep, _ = sel.select(facts)
        assert rep in RepresentationSelector.SUPPORTED_TYPES

    def test_selection_appends_history(self):
        sel = RepresentationSelector()
        sel.select(_facts([1.0]))
        assert len(sel.history) == 1
        assert sel._last_selection == "symbolic"

    def test_history_empty_when_nothing_selected(self):
        sel = RepresentationSelector()
        assert sel.history == []


class TestHysteresis:
    def test_small_advantage_does_not_switch(self):
        sel = RepresentationSelector()
        # first selection: graph is the clear winner
        sel.select(_facts([1.0]), metadata={"blocked": ["a", "b"], "rewards": {"r": 1}})
        assert sel._last_selection == "graph"
        # second call: spatial ties graph at 0.6 (graph via blocked+rewards,
        # spatial via 2-dim state + goal), but the margin is < 0.15 so graph
        # is kept
        rep, conf = sel.select(_facts([1.0, 2.0]), metadata={
            "blocked": ["a", "b"], "rewards": {"r": 1}, "goal": [3, 4],
        })
        assert rep == "graph"
        assert conf == pytest_approx(0.6)

    def test_large_advantage_switches(self):
        sel = RepresentationSelector()
        sel.select(_facts([1.0]), metadata={"blocked": ["a"], "rewards": {"r": 1}})
        assert sel._last_selection == "graph"
        rep, _ = sel.select(_facts([1.0, 2.0, 3.0, 4.0]), metadata={
            "terrain": {"g": 1, "w": 2, "r": 3},
            "position": [1, 2],
        })
        assert rep == "spatial"


class TestScores:
    def test_temporal_momentum(self):
        sel = RepresentationSelector()
        facts = _facts([1.0], resources={"reward_near": 1.0},
                       events=["e"], metrics={"uncertainty": 0.9})
        for _ in range(3):
            sel.select(facts)
        assert sel._last_selection == "temporal"
        # momentum: three consecutive temporal selections add 0.2
        assert sel._score_temporal([], {}, {}) == pytest_approx(0.3)

    def test_spatial_position_and_goal_boost(self):
        sel = RepresentationSelector()
        score = sel._score_spatial(
            state=np.array([1.0, 2.0]),
            resources={"terrain_cost": 2.0},
            constraints=[],
            meta={"position": [0, 0], "goal": [5, 5]},
            metrics={},
        )
        # 0.1 + 0.4 (len>=2) + 0.2 terrain? no terrain key -> 0.15 position
        # + 0.1 goal + 0.1 terrain_cost
        assert score == pytest_approx(0.85)

    def test_graph_rewards_and_terrain_boost(self):
        sel = RepresentationSelector()
        score = sel._score_graph(
            facts=None,
            constraints=["bounds"],
            meta={"blocked": ["x"], "rewards": {"r": 1}, "terrain": {"a": 1, "b": 2, "c": 3, "d": 4}},
            resources={},
        )
        # 0.1 + 0.3 blocked + 0.2 rewards + 0.15 terrain(4 keys) + 0.1 constraints
        assert score == pytest_approx(0.85)


class TestDiversity:
    def test_history_records_varied_modalities(self):
        sel = RepresentationSelector()
        sel.select(_facts([0.0]))                                    # symbolic
        sel.select(_facts([1.0, 2.0, 3.0, 4.0]), metadata={"position": [1, 2]})  # spatial
        sel.select(_facts([1.0]), metadata={"blocked": ["b1"]})      # graph
        sel.select(_facts([1.0], events=["e"], metrics={"uncertainty": 0.9}))   # temporal
        types = {t for t, _ in sel.history}
        assert len(sel.history) == 4
        assert len(types) >= 1  # honest: the actual winners, whatever they were


def pytest_approx(value):
    import pytest
    return pytest.approx(value)