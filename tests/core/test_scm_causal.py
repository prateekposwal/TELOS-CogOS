"""Tests for StructuralCausalModel do() propagation in topological order."""

from telos.core.reasoning.causal.scm import StructuralCausalModel


def _chain_model():
    """a -> b -> c with structural equations b=a*2, c=b+1."""
    scm = StructuralCausalModel()
    scm.add_edge("a", "b", equation=lambda causes: causes["a"] * 2)
    scm.add_edge("b", "c", equation=lambda causes: causes["b"] + 1)
    return scm


class TestTopologicalPropagation:
    def test_do_propagates_in_causal_order(self):
        scm = _chain_model()
        scm.set_value("a", 1)
        scm.set_value("b", 0)  # stale
        scm.set_value("c", 0)  # stale
        state = scm.do("a", 3)
        # c must see the UPDATED b (b=6), not the stale b=0
        assert state["b"] == 6
        assert state["c"] == 7

    def test_do_breaks_incoming_edges(self):
        scm = _chain_model()
        scm.set_value("a", 1)
        state = scm.do("b", 10)  # intervene on b directly
        assert state["b"] == 10
        assert state["c"] == 11  # downstream still updated
        # a is untouched by the intervention
        assert state["a"] == 1

    def test_do_without_equations_sets_value_only(self):
        scm = StructuralCausalModel()
        scm.add_edge("x", "y")  # no equation
        scm.set_value("x", 1)
        state = scm.do("x", 5)
        assert state["x"] == 5
        assert state.get("y") is None  # no equation, never set -> absent

    def test_cycle_in_graph_does_not_hang(self):
        scm = StructuralCausalModel()
        scm.add_edge("p", "q", equation=lambda causes: (causes["q"] or 0) + 1)
        scm.add_edge("q", "p", equation=lambda causes: (causes["p"] or 0) + 1)
        scm.set_value("p", 1)
        scm.set_value("q", 1)
        state = scm.do("p", 2)  # must terminate
        assert state["p"] == 2

    def test_chain_order_structural(self):
        scm = _chain_model()
        ordered = scm._topological_order(["a", "b", "c"])
        assert ordered.index("a") < ordered.index("b") < ordered.index("c")

    def test_topological_order_cycle_remainder(self):
        scm = StructuralCausalModel()
        scm.add_edge("x", "y")
        scm.add_edge("y", "x")  # cycle
        ordered = scm._topological_order(["x", "y"])
        assert len(ordered) == 2  # all emitted, no hang


class TestCounterfactualBasics:
    def test_counterfactual_restores_state(self):
        scm = _chain_model()
        scm.set_value("a", 1)
        scm.counterfactual(evidence={"a": 2}, intervention={"a": 9})
        assert scm.get_value("a") == 1  # original restored

    def test_graph_edit_distance(self):
        scm1 = _chain_model()
        scm2 = StructuralCausalModel()
        scm2.add_edge("a", "b", equation=lambda c: c["a"] * 2)
        d = scm1.graph_edit_distance(scm2)
        assert 0.0 < d <= 1.0
