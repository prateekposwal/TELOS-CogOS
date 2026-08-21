"""Tests for StructuralCausalModel — Kahn-topological do() semantics,
counterfactual queries, domain-facts parsing, and graph_summary contract."""

import numpy as np

from telos.core.reasoning.causal.scm import StructuralCausalModel
from telos.world.facts import DomainFacts


class TestDoInterventionSemantics:
    def test_do_sets_value_breaking_incoming_edges(self):
        scm = StructuralCausalModel()
        scm.add_edge("a", "b", equation=lambda c: c["a"] * 2)
        scm.add_edge("b", "c", equation=lambda c: c["b"] + 1)
        state = scm.do("b", 10)
        assert state["b"] == 10
        assert state["c"] == 11
        assert "a" not in state

    def test_do_skips_equationless_nodes_but_propagates_downstream(self):
        scm = StructuralCausalModel()
        scm.add_edge("x", "y")
        scm.add_edge("y", "z", equation=lambda c: (c["y"] or 0) + 1)
        state = scm.do("x", 5)
        assert state["x"] == 5
        assert "y" not in state
        assert state["z"] == 1

    def test_do_returns_a_mapping_not_a_live_view(self):
        scm = _chain()
        scm.set_value("a", 1)
        scm.set_value("b", 2)
        scm.set_value("c", 3)
        state = scm.do("a", 4)
        state["a"] = 999
        assert scm.get_value("a") == 4


class TestCausalParentsSettleBeforeDescendants:
    def test_diamond_descendants_see_settled_parents(self):
        scm = StructuralCausalModel()
        scm.add_edge("root", "left", equation=lambda c: c["root"] + 1)
        scm.add_edge("root", "right", equation=lambda c: c["root"] * 2)
        scm.add_edge("left", "leaf", equation=lambda c: c["left"] + c["right"])
        scm.add_edge("right", "leaf", equation=lambda c: c["left"] + c["right"])
        for v in ("root", "left", "right", "leaf"):
            scm.set_value(v, 0)
        state = scm.do("root", 10)
        assert state["left"] == 11
        assert state["right"] == 20
        assert state["leaf"] == 31

    def test_do_leaves_unrelated_variables_untouched(self):
        scm = StructuralCausalModel()
        scm.add_edge("root", "left", equation=lambda c: c["root"] + 1)
        scm.add_edge("u", "v", equation=lambda c: c["u"] + 100)
        scm.set_value("root", 1)
        scm.set_value("u", 1)
        scm.set_value("v", 0)
        state = scm.do("root", 5)
        assert state["left"] == 6
        assert state["u"] == 1
        assert state["v"] == 0

    def test_topological_order_lists_causes_before_effects(self):
        scm = StructuralCausalModel()
        scm.add_edge("a", "b")
        scm.add_edge("b", "c")
        ordering = scm._topological_order(["a", "b", "c"])
        assert ordering.index("a") < ordering.index("b") < ordering.index("c")


class TestInterventionHistory:
    def test_graph_summary_reports_intervention_count(self):
        scm = StructuralCausalModel()
        scm.add_edge("a", "b", equation=lambda c: c["a"] * 2)
        scm.do("a", 2)
        scm.do("a", 3)
        assert scm.graph_summary["interventions"] == 2

    def test_graph_summary_serialization_contract(self):
        scm = StructuralCausalModel()
        scm.add_edge("a", "b", equation=lambda c: c["a"] * 2)
        scm.set_value("a", 1)
        scm.do("a", 2)
        summary = scm.graph_summary
        assert summary["edges"] == ["a \u2192 b"]
        assert "a" in summary["variables"]
        assert "b" in summary["variables"]
        assert summary["interventions"] == 1
        assert summary["has_structural_equations"] is True


class TestCounterfactual:
    def test_counterfactual_applies_evidence_then_intervention(self):
        scm = _chain()
        scm.set_value("a", 1)
        scm.set_value("b", 0)
        scm.set_value("c", 0)
        state = scm.counterfactual(evidence={"a": 5}, intervention={"a": 3})
        assert state["a"] == 3
        assert state["b"] == 6
        assert state["c"] == 7

    def test_counterfactual_restores_original_state(self):
        scm = _chain()
        scm.set_value("a", 1)
        scm.set_value("b", 2)
        scm.set_value("c", 3)
        scm.counterfactual(evidence={"a": 8}, intervention={"a": 9})
        assert scm.get_value("a") == 1
        assert scm.get_value("b") == 2
        assert scm.get_value("c") == 3


class TestDomainFacts:
    def test_parse_domain_facts_edges_resources_and_metadata(self):
        scm = StructuralCausalModel()
        facts = DomainFacts(
            state=np.array([0.0]),
            resources={"energy": 10.0, "position": 1.0},
            constraints=["agent \u2192 action"],
            events=[],
            metrics={},
            metadata={"causal_edges": ["sensor \u2192 belief"]},
        )
        scm.parse_domain_facts(facts)
        edges = set(scm.graph_summary["edges"])
        assert "agent \u2192 action" in edges
        assert "sensor \u2192 belief" in edges
        assert "position \u2192 next_position" in edges
        assert scm.get_value("energy") == 10.0
        assert scm.get_value("position") == 1.0

    def test_parse_domain_facts_none_is_a_noop(self):
        scm = StructuralCausalModel()
        scm.parse_domain_facts(None)
        assert scm.graph_summary == {
            "edges": [],
            "variables": [],
            "interventions": 0,
            "has_structural_equations": False,
        }

    def test_terrain_and_action_standard_edges(self):
        scm = StructuralCausalModel()
        facts = DomainFacts(
            state=np.array([0.0]),
            resources={"terrain": 1, "action": "go"},
            constraints=[],
            events=[],
            metrics={},
        )
        scm.parse_domain_facts(facts)
        edges = set(scm.graph_summary["edges"])
        assert "terrain \u2192 cost" in edges
        assert "action \u2192 state_change" in edges


class TestCounterfactualWorlds:
    def test_generates_worlds_via_do_with_variants(self):
        scm = StructuralCausalModel()
        scm.add_edge("action", "state_change")
        worlds = scm.generate_counterfactual_worlds(
            base_state=np.array([1.0, 2.0]),
            actions=["move", "turn"],
            n_worlds=4,
        )
        assert len(worlds) == 4
        assert worlds[0]["action"] == "move"
        assert worlds[1]["action"] == "move_variant_0"
        assert worlds[2]["action"] == "turn"
        assert worlds[3]["action"] == "turn_variant_0"
        for world in worlds:
            assert "position" in world
        assert scm.graph_summary["interventions"] == 4

    def test_respects_n_worlds_bound(self):
        scm = StructuralCausalModel()
        scm.add_edge("action", "state_change")
        worlds = scm.generate_counterfactual_worlds(
            base_state=np.array([1.0]),
            actions=["move", "turn"],
            n_worlds=1,
        )
        assert len(worlds) == 1
        assert worlds[0]["action"] in ("move", "turn")


class TestReset:
    def test_reset_clears_graph_values_and_history(self):
        scm = _chain()
        scm.set_value("a", 1)
        scm.do("a", 2)
        scm.reset()
        assert scm.graph_summary == {
            "edges": [],
            "variables": [],
            "interventions": 0,
            "has_structural_equations": False,
        }


def _chain():
    scm = StructuralCausalModel()
    scm.add_edge("a", "b", equation=lambda c: c["a"] * 2)
    scm.add_edge("b", "c", equation=lambda c: c["b"] + 1)
    return scm