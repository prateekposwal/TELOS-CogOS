"""Tests for the KnowledgeGraph edge layer — typed/weighted edges, traversal,
activation spread (Λ4.7 Law of Attention and Trajectory), serialization."""

import json
import pytest

from telos.core.knowledge.graph import KnowledgeGraph, Edge


def _graph_with_chain():
    """n1 - n2 - n3 - n4, plus a side node n5 connected to n2."""
    kg = KnowledgeGraph()
    n1 = kg.record("x", "n1", 0.9)
    n2 = kg.record("x", "n2", 0.8)
    n3 = kg.record("x", "n3", 0.7)
    n4 = kg.record("x", "n4", 0.6)
    n5 = kg.record("x", "n5", 0.5)
    kg.add_edge(n1, n2, edge_type="informs", weight=0.8)
    kg.add_edge(n2, n3, edge_type="informs", weight=0.6)
    kg.add_edge(n3, n4, edge_type="informs", weight=0.4)
    kg.add_edge(n2, n5, edge_type="competes", weight=0.3)
    return kg, (n1, n2, n3, n4, n5)


class TestEdgeStore:
    def test_add_edge_returns_stable_id(self):
        kg = KnowledgeGraph()
        a = kg.record("d", "a", 0.5)
        b = kg.record("d", "b", 0.5)
        e1 = kg.add_edge(a, b, edge_type="related", weight=0.7)
        e2 = kg.add_edge(a, b, edge_type="related", weight=0.9)  # idempotent update
        assert e1 == e2
        assert len(kg._edges) == 1
        assert kg._edges[e1].weight == 0.9

    def test_add_edge_rejects_missing_endpoints(self):
        kg = KnowledgeGraph()
        a = kg.record("d", "a", 0.5)
        with pytest.raises(ValueError):
            kg.add_edge("ghost", a)
        with pytest.raises(ValueError):
            kg.add_edge(a, "ghost")

    def test_add_edge_rejects_self_loop(self):
        kg = KnowledgeGraph()
        a = kg.record("d", "a", 0.5)
        with pytest.raises(ValueError):
            kg.add_edge(a, a)

    def test_add_edge_rejects_negative_weight(self):
        kg = KnowledgeGraph()
        a = kg.record("d", "a", 0.5)
        b = kg.record("d", "b", 0.5)
        with pytest.raises(ValueError):
            kg.add_edge(a, b, weight=-1.0)

    def test_remove_edge(self):
        kg = KnowledgeGraph()
        a = kg.record("d", "a", 0.5)
        b = kg.record("d", "b", 0.5)
        eid = kg.add_edge(a, b)
        assert kg.remove_edge(eid) is True
        assert kg.remove_edge(eid) is False  # already gone
        assert kg.has_adjacency(a) is False
        assert len(kg._edges) == 0

    def test_edges_for_and_get_edges(self):
        kg, (n1, n2, n3, n4, n5) = _graph_with_chain()
        incident = kg.edges_for(n2)
        assert len(incident) == 3  # n1, n3, n5
        typed = kg.get_edges(edge_type="informs")
        assert len(typed) == 3
        all_edges = kg.get_edges()
        assert len(all_edges) == 4

    def test_stats_reports_edges(self):
        kg, _ = _graph_with_chain()
        s = kg.stats
        assert s["total_edges"] == 4
        assert set(s["edge_types"]) == {"informs", "competes"}


class TestTraversal:
    def test_get_neighbors(self):
        kg, (n1, n2, n3, n4, n5) = _graph_with_chain()
        assert set(kg.get_neighbors(n2)) == {n1, n3, n5}
        assert set(kg.get_neighbors(n2, edge_type="informs")) == {n1, n3}
        assert kg.get_neighbors(n2, edge_type="competes") == [n5]
        assert kg.get_neighbors("isolated") == []

    def test_has_adjacency(self):
        kg = KnowledgeGraph()
        iso = kg.record("d", "iso", 0.5)
        assert kg.has_adjacency(iso) is False
        a = kg.record("d", "a", 0.5)
        kg.add_edge(iso, a)
        assert kg.has_adjacency(iso) is True

    def test_bfs(self):
        kg, (n1, n2, n3, n4, n5) = _graph_with_chain()
        order = kg.bfs(n1, max_depth=3)
        assert order == [n1, n2, n3, n5, n4]  # level order
        assert kg.bfs(n1, max_depth=1) == [n1, n2]
        assert kg.bfs("isolated") == ["isolated"]

    def test_dfs(self):
        kg, (n1, n2, n3, n4, n5) = _graph_with_chain()
        order = kg.dfs(n1, max_depth=3)
        assert order[0] == n1
        assert set(order) == {n1, n2, n3, n4, n5}
        assert len(order) == len(set(order))  # no repeats

    def test_find_path_shortest(self):
        kg, (n1, n2, n3, n4, n5) = _graph_with_chain()
        assert kg.find_path(n1, n4) == [n1, n2, n3, n4]
        assert kg.find_path(n5, n4) == [n5, n2, n3, n4]

    def test_find_path_none(self):
        kg = KnowledgeGraph()
        a = kg.record("d", "a", 0.5)
        b = kg.record("d", "b", 0.5)  # isolated
        assert kg.find_path(a, b) is None
        assert kg.find_path(a, "missing") is None

    def test_find_path_same_node(self):
        kg = KnowledgeGraph()
        a = kg.record("d", "a", 0.5)
        assert kg.find_path(a, a) == [a]


class TestActivationSpread:
    def test_activation_flows_along_edges(self):
        kg, (n1, n2, n3, n4, n5) = _graph_with_chain()
        for n in (n1, n2, n3, n4, n5):
            kg._nodes[n].activation = 0.0
        kg._nodes[n2].activation = 1.0
        affected = kg.activate(n1, boost=0.5, spread=0.4, depth=2)
        assert affected == 4  # n1 + n2 (0.2) + n3/n5 (0.08)
        assert kg._nodes[n1].activation == 0.5
        assert abs(kg._nodes[n2].activation - 1.2) < 1e-9
        assert abs(kg._nodes[n3].activation - 0.08) < 1e-9
        assert abs(kg._nodes[n5].activation - 0.08) < 1e-9
        assert kg._nodes[n4].activation == 0.0  # 3 hops away, not reached

    def test_activation_no_spread_keeps_old_semantics(self):
        kg = KnowledgeGraph()
        a = kg.record("d", "a", 0.5)
        b = kg.record("d", "b", 0.5)
        kg.add_edge(a, b)
        affected = kg.activate(a, boost=0.5)  # spread=0.3 default, depth=1
        assert affected >= 1
        assert kg._nodes[a].activation == 1.5

    def test_activation_returns_zero_for_unknown_node(self):
        kg = KnowledgeGraph()
        assert kg.activate("missing", boost=0.5) == 0

    def test_activation_archived_neighbors_traversed_not_boosted(self):
        kg = KnowledgeGraph()
        a = kg.record("d", "a", 0.5)
        b = kg.record("d", "b", 0.5)
        c = kg.record("d", "c", 0.5)
        kg.add_edge(a, b)
        kg.add_edge(b, c)
        kg._nodes[a].activation = 0.0
        kg._nodes[c].activation = 0.0
        kg._archive(b)
        assert b in kg._archived_nodes
        affected = kg.activate(a, boost=0.5, spread=0.4, depth=2)
        # a boosted; b archived not boosted; c reached THROUGH archived b
        assert affected == 2
        assert abs(kg._nodes[c].activation - 0.08) < 1e-9


class TestEdgeSerialization:
    def test_save_load_roundtrip_preserves_edges(self, tmp_path):
        path = tmp_path / "kg.json"
        kg, (n1, n2, n3, n4, n5) = _graph_with_chain()
        kg.save(str(path))

        kg2 = KnowledgeGraph()
        kg2.load(str(path))
        assert kg2.stats["total_edges"] == 4
        assert set(kg2.get_neighbors(n2)) == {n1, n3, n5}
        e = kg2.get_edges(edge_type="competes")[0]
        assert e.weight == 0.3
        assert e.edge_type == "competes"

    def test_load_old_format_without_edges(self, tmp_path):
        path = tmp_path / "old.json"
        path.write_text(json.dumps({"nodes": {}, "archived_nodes": {}}))
        kg = KnowledgeGraph()
        kg.load(str(path))
        assert kg.stats["total_edges"] == 0

    def test_edge_to_dict_roundtrip(self):
        e = Edge(edge_id="e1", src="a", dst="b", edge_type="informs",
                 weight=0.7, metadata={"cycle": 3}, timestamp=1.0)
        d = e.to_dict()
        assert d["src"] == "a" and d["weight"] == 0.7 and d["metadata"] == {"cycle": 3}
