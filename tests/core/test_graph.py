"""
KnowledgeGraph (core/knowledge/graph.py) — honest contract coverage.
"""
from telos.core.knowledge.graph import KnowledgeGraph


class TestKnowledgeGraph:
    def test_record_and_edges(self):
        kg = KnowledgeGraph()
        nid = kg.record(domain="gridworld", approach="north", outcome=0.9)
        assert nid is not None
        nid2 = kg.record(domain="gridworld", approach="east", outcome=0.4)
        kg.add_edge(nid, nid2, edge_type="follows")
        assert kg.has_adjacency(nid)
        assert len(kg.edges_for(nid)) == 1

    def test_traversal(self):
        kg = KnowledgeGraph()
        a = kg.record("gridworld", "A", 0.9)
        b = kg.record("gridworld", "B", 0.8)
        c = kg.record("gridworld", "C", 0.7)
        kg.add_edge(a, b, "follows")
        kg.add_edge(b, c, "follows")
        assert kg.bfs(a) == [a, b, c]
        assert kg.find_path(a, c) is not None
        assert kg.dfs(a)  # reaches all

    def test_recommend_and_best(self):
        kg = KnowledgeGraph()
        kg.record("gridworld", "good", 0.9)
        kg.record("gridworld", "bad", 0.2)
        best = kg.best_approach("gridworld")
        assert best in ("good", "bad")
        assert kg.recommend("gridworld", top_k=2)

    def test_remove_edge(self):
        kg = KnowledgeGraph()
        a = kg.record("gridworld", "A", 0.9)
        b = kg.record("gridworld", "B", 0.8)
        eid = kg.add_edge(a, b, "follows")
        assert kg.remove_edge(eid) is True
        assert not kg.has_adjacency(a)
