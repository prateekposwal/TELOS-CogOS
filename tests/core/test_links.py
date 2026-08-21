"""Contract tests for KnowledgeLinker — the one canonical cross-graph
registry binding knowledge nodes <-> theories <-> SCM structures, plus the
identity self-observation node registry."""

from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.knowledge.links import KnowledgeLinker
from telos.core.reasoning.genealogy import TheoryGenealogy
from telos.core.reasoning.causal.scm import StructuralCausalModel


class TestNodeTheoryLinks:
    def test_link_is_bidirectional(self):
        linker = KnowledgeLinker()
        linker.link_node_to_theory("node_1", "theory_1")
        linker.link_node_to_theory("node_2", "theory_1")
        assert linker.theories_for_node("node_1") == ["theory_1"]
        assert linker.nodes_for_theory("theory_1") == ["node_1", "node_2"]

    def test_unlink_cleans_both_directions(self):
        linker = KnowledgeLinker()
        linker.link_node_to_theory("node_1", "theory_1")
        linker.link_node_to_theory("node_1", "theory_2")
        linker.unlink_node("node_1")
        assert linker.theories_for_node("node_1") == []
        assert linker.nodes_for_theory("theory_1") == []
        assert linker.nodes_for_theory("theory_2") == []

    def test_missing_links_return_empty(self):
        linker = KnowledgeLinker()
        assert linker.theories_for_node("nope") == []
        assert linker.nodes_for_theory("nope") == []


class TestTheoryScmLinks:
    def test_link_snapshots_sorted_edges(self):
        linker = KnowledgeLinker()
        scm = StructuralCausalModel()
        scm.add_edge("position", "distance")
        scm.add_edge("action", "position")
        scm.set_value("position", [1, 2])
        linker.link_theory_to_scm("t1", scm)
        view = linker.scm_for_theory("t1")
        # graph_summary preserves add_edge insertion order
        assert view["edges"] == ["position → distance", "action → position"]
        assert set(view["variables"]) == {"position"}
        assert view["interventions"] == 0
        assert linker._theory_to_scm["t1"].startswith("scm_")

    def test_relink_replaces_snapshot(self):
        linker = KnowledgeLinker()
        scm1 = StructuralCausalModel()
        scm1.add_edge("a", "b")
        scm2 = StructuralCausalModel()
        scm2.add_edge("x", "y")
        linker.link_theory_to_scm("t", scm1)
        linker.link_theory_to_scm("t", scm2)
        assert linker.scm_for_theory("t")["edges"] == ["x → y"]

    def test_unknown_theory_returns_none(self):
        linker = KnowledgeLinker()
        assert linker.scm_for_theory("missing") is None

    def test_scm_without_graph_summary_defaults_empty(self):
        class BareSCM:
            pass
        linker = KnowledgeLinker()
        sid = linker.link_theory_to_scm("t", BareSCM())
        assert linker.scm_for_theory("t") == {"edges": [], "variables": [], "interventions": 0}


class TestIdentityRegistry:
    def test_link_and_list_identity_nodes(self):
        linker = KnowledgeLinker()
        linker.link_identity_node("id_node_b")
        linker.link_identity_node("id_node_a")
        assert linker.identity_nodes() == ["id_node_a", "id_node_b"]
        assert linker.is_identity_node("id_node_a")
        assert not linker.is_identity_node("regular_node")

    def test_to_dict_serializes_identity_nodes(self):
        linker = KnowledgeLinker()
        linker.link_identity_node("self_obs_1")
        assert linker.to_dict()["identity_nodes"] == ["self_obs_1"]


class TestGetConnectedStructure:
    def test_full_neighborhood_across_graphs(self):
        kg = KnowledgeGraph()
        n1 = kg.record("x", "algo_1", 0.9)
        n2 = kg.record("x", "algo_2", 0.8)
        kg.add_edge(n1, n2, edge_type="competes")

        genealogy = TheoryGenealogy()
        parent = genealogy.register("BaseTheory", cycle=0)
        child = genealogy.register("RefinedTheory", parent_id=parent, cycle=1)

        scm = StructuralCausalModel()
        scm.add_edge("position", "distance")
        scm.set_value("position", [1, 2])

        linker = KnowledgeLinker()
        linker.attach_genealogy(genealogy)
        linker.link_node_to_theory(n1, child)
        linker.link_theory_to_scm(child, scm)

        structure = linker.get_connected_structure(n1, knowledge_graph=kg)
        assert structure["node_id"] == n1
        assert structure["linked_theory_count"] == 1
        assert structure["knowledge_neighbors"][0]["node_id"] == n2
        assert structure["knowledge_neighbors"][0]["domain"] == "x"
        assert structure["knowledge_neighbors"][0]["approach"] == "algo_2"
        theory = structure["theories"][0]
        assert theory["name"] == "RefinedTheory"
        assert theory["parent_id"] == parent
        assert theory["birth_cycle"] == 1
        assert theory["scm"]["edges"] == ["position → distance"]
        assert theory.get("related_nodes", []) == []

    def test_identity_flags_in_connected_structure(self):
        kg = KnowledgeGraph()
        n1 = kg.record("x", "self_obs_a", 0.5)
        n2 = kg.record("x", "self_obs_b", 0.5)
        linker = KnowledgeLinker()
        linker.link_identity_node(n1)
        linker.link_identity_node(n2)
        structure = linker.get_connected_structure(n1, knowledge_graph=kg)
        assert structure["identity_node"] is True
        assert structure["sibling_identity_nodes"] == [n2]

    def test_archived_neighbor_still_reported(self):
        kg = KnowledgeGraph()
        n1 = kg.record("x", "algo_1", 0.9)
        n2 = kg.record("x", "algo_2", 0.8)
        kg.add_edge(n1, n2)
        kg._archive(n2)
        assert n2 in kg._archived_nodes
        linker = KnowledgeLinker()
        structure = linker.get_connected_structure(n1, knowledge_graph=kg)
        assert structure["knowledge_neighbors"][0]["node_id"] == n2

    def test_isolated_node(self):
        linker = KnowledgeLinker()
        kg = KnowledgeGraph()
        n = kg.record("x", "solo", 0.5)
        structure = linker.get_connected_structure(n, knowledge_graph=kg)
        assert structure["linked_theory_count"] == 0
        assert structure["knowledge_neighbors"] == []
        assert structure["theories"] == []


class TestSerialization:
    def test_to_dict_full_table(self):
        linker = KnowledgeLinker()
        linker.link_node_to_theory("n1", "t1")
        scm = StructuralCausalModel()
        scm.add_edge("a", "b")
        linker.link_theory_to_scm("t1", scm)
        d = linker.to_dict()
        assert d["node_to_theory"]["n1"] == ["t1"]
        assert d["theory_to_scm"]["t1"].startswith("scm_")
        assert isinstance(d["scm_structures"], dict)
        assert d["identity_nodes"] == []