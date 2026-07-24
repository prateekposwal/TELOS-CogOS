"""Tests for KnowledgeGraph, KnowledgeRecommender, and OutcomeRecorder."""

from telos.core.knowledge.graph import KnowledgeGraph, ProjectNode
from telos.core.knowledge.recommender import KnowledgeRecommender
from telos.core.knowledge.recorder import OutcomeRecorder


class TestKnowledgeGraph:
    """Spiderweb memory — record, search, tick, persist."""

    def test_record_and_search(self):
        kg = KnowledgeGraph()
        kg.record("test_domain", "approach_a", 0.92, tags=["fast", "accurate"])
        kg.record("test_domain", "approach_b", 0.45, tags=["slow"])
        kg.record("test_domain", "approach_c", 0.12, failure_reason="crashed",
                  tags=["broken"])
        assert kg.stats["total_nodes"] == 3
        assert kg.stats["successes"] == 1
        assert kg.stats["failures"] == 2

    def test_recommend_returns_best(self):
        kg = KnowledgeGraph()
        kg.record("search", "algo_c", 0.95)
        kg.record("search", "algo_b", 0.70)
        kg.record("search", "algo_a", 0.50)
        best = kg.recommend("search", top_k=1)
        assert len(best) == 1
        assert best[0].approach == "algo_c"

    def test_recommend_empty_domain(self):
        kg = KnowledgeGraph()
        assert kg.recommend("nonexistent", top_k=1) == []

    def test_best_approach(self):
        kg = KnowledgeGraph()
        kg.record("domain", "winner", 0.99)
        kg.record("domain", "loser", 0.10)
        assert kg.best_approach("domain") == "winner"

    def test_best_approach_unknown_domain(self):
        assert KnowledgeGraph().best_approach("void") is None

    def test_search_failures(self):
        kg = KnowledgeGraph()
        kg.record("x", "good", 0.90)
        kg.record("x", "bad", 0.15, failure_reason="timeout")
        kg.record("x", "ugly", 0.05, failure_reason="segfault")
        fails = kg.search_failures("x")
        assert len(fails) == 2
        assert all(f.outcome <= 0.5 for f in fails)
        assert fails[0].failure_reason  # sorted by severity

    def test_search_failures_empty(self):
        kg = KnowledgeGraph()
        kg.record("x", "only_good", 0.99)
        assert kg.search_failures("x") == []

    def test_search_by_tags(self):
        kg = KnowledgeGraph()
        kg.record("d", "a1", 0.9, tags=["vision"])
        kg.record("d", "a2", 0.8, tags=["nlp"])
        kg.record("d", "a3", 0.7, tags=["vision"])
        results = kg.search(tags=["vision"], top_k=5)
        assert len(results) == 2
        assert all("vision" in n.tags for n in results)

    def test_search_combines_domain_and_tags(self):
        kg = KnowledgeGraph()
        kg.record("d1", "a1", 0.9, tags=["vision"])
        kg.record("d2", "a2", 0.8, tags=["vision"])
        results = kg.search(domain="d1", tags=["vision"])
        assert len(results) == 1
        assert results[0].approach == "a1"

    def test_activate_boosts_node(self):
        kg = KnowledgeGraph()
        nid = kg.record("d", "a", 0.5)
        node = kg._nodes[nid]
        assert node.access_count == 1
        kg.activate(nid, boost=0.5)
        assert node.activation == 1.5
        assert node.access_count == 2

    def test_tick_decays_activation(self):
        kg = KnowledgeGraph(max_hot_nodes=100)
        kg.record("d", "a", 0.5)
        nid = list(kg._nodes.keys())[0]
        start = kg._nodes[nid].activation
        archived = kg.tick()
        assert kg._nodes[nid].activation < start
        assert archived == 0  # not cold enough to archive

    def test_tick_archives_cold_nodes(self):
        kg = KnowledgeGraph(max_hot_nodes=100)
        kg.record("d", "cold_node", 0.5)
        nid = list(kg._nodes.keys())[0]
        kg._nodes[nid].activation = 0.001  # force below archive floor
        archived = kg.tick()
        assert archived == 1
        assert nid not in kg._nodes

    def test_domain_summary(self):
        kg = KnowledgeGraph()
        kg.record("d", "win", 0.95)
        kg.record("d", "fail", 0.10, failure_reason="oops")
        s = kg.domain_summary("d")
        assert s["best_approach"] == "win"
        assert s["best_outcome"] == 0.95
        assert len(s["known_solutions"]) == 1
        assert len(s["known_failures"]) == 1
        assert s["known_failures"][0]["reason"] == "oops"

    def test_recommend_returns_multiple(self):
        kg = KnowledgeGraph()
        for i in range(5):
            kg.record("multi", f"algo_{i}", 0.9 - i * 0.1)
        best = kg.recommend("multi", top_k=3)
        assert len(best) == 3
        assert best[0].approach == "algo_0"
        assert best[2].approach == "algo_2"

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "kg.json"
        kg1 = KnowledgeGraph()
        kg1.record("d", "original", 0.87, tags=["test"])
        kg1.save(str(path))

        kg2 = KnowledgeGraph()
        kg2.load(str(path))
        assert kg2.stats["total_nodes"] == 1
        node = kg2._nodes[list(kg2._nodes.keys())[0]]
        assert node.approach == "original"
        assert node.outcome == 0.87
        assert node.tags == ["test"]

    def test_load_nonexistent_file_does_nothing(self):
        kg = KnowledgeGraph()
        kg.load("/tmp/nonexistent_knowledge.json")
        assert kg.stats["total_nodes"] == 0

    def test_record_success_helper(self):
        kg = KnowledgeGraph()
        nid = kg.record_success("d", "approach", 0.95, tags=["test"])
        node = kg._nodes[nid]
        assert node.is_success
        assert node.outcome == 0.95

    def test_record_failure_helper(self):
        kg = KnowledgeGraph()
        nid = kg.record_failure("d", "approach", 0.10, "timeout", tags=["test"])
        node = kg._nodes[nid]
        assert node.is_failure
        assert node.failure_reason == "timeout"

    def test_node_properties(self):
        s = ProjectNode(node_id="1", domain="d", approach="a", outcome=0.9)
        assert s.is_success
        assert not s.is_failure
        f = ProjectNode(node_id="2", domain="d", approach="b", outcome=0.3)
        assert f.is_failure
        assert not f.is_success

    def test_stats_counts(self):
        kg = KnowledgeGraph()
        kg.record("d", "ok", 0.7)
        kg.record("d", "ko", 0.3)
        assert kg.stats["successes"] == 1
        assert kg.stats["failures"] == 1
        assert kg.stats["domains"] == ["d"]


class TestKnowledgeRecommender:
    """Read-only advisor wrapping KnowledgeGraph."""

    def test_recommend_single(self):
        kg = KnowledgeGraph()
        kg.record("d", "best", 0.99)
        kg.record("d", "worst", 0.01)
        rec = KnowledgeRecommender(kg)
        assert rec.recommend("d") == "best"

    def test_recommend_top_k(self):
        kg = KnowledgeGraph()
        kg.record("d", "a", 0.9)
        kg.record("d", "b", 0.8)
        rec = KnowledgeRecommender(kg)
        top = rec.recommend_top("d", top_k=2)
        assert len(top) == 2
        assert top[0]["approach"] == "a"
        assert top[1]["approach"] == "b"

    def test_failures_list(self):
        kg = KnowledgeGraph()
        kg.record("d", "good", 0.9)
        kg.record_failure("d", "bad", 0.1, "error_x")
        rec = KnowledgeRecommender(kg)
        fails = rec.failures("d")
        assert len(fails) == 1
        assert fails[0]["failure_reason"] == "error_x"

    def test_would_repeat_failure_true(self):
        kg = KnowledgeGraph()
        kg.record_failure("d", "bad_algo", 0.1, "oops")
        rec = KnowledgeRecommender(kg)
        assert rec.would_repeat_failure("d", "bad_algo")

    def test_would_repeat_failure_false(self):
        kg = KnowledgeGraph()
        kg.record("d", "good_algo", 0.9)
        rec = KnowledgeRecommender(kg)
        assert not rec.would_repeat_failure("d", "good_algo")

    def test_would_repeat_failure_unknown_domain(self):
        rec = KnowledgeRecommender(KnowledgeGraph())
        assert not rec.would_repeat_failure("void", "anything")

    def test_summarize_with_successes(self):
        kg = KnowledgeGraph()
        kg.record("d", "algo", 0.95)
        rec = KnowledgeRecommender(kg)
        s = rec.summarize("d")
        assert "Proven:" in s
        assert "algo" in s

    def test_summarize_with_failures(self):
        kg = KnowledgeGraph()
        kg.record_failure("d", "broken", 0.05, "timeout")
        rec = KnowledgeRecommender(kg)
        s = rec.summarize("d")
        assert "Avoid:" in s
        assert "broken" in s

    def test_summarize_empty_domain(self):
        rec = KnowledgeRecommender(KnowledgeGraph())
        s = rec.summarize("void")
        assert "Proven:" in s
        assert "Avoid:" not in s


class TestOutcomeRecorder:
    """Records outcomes with context into KnowledgeGraph."""

    def test_success(self):
        kg = KnowledgeGraph()
        rec = OutcomeRecorder(kg)
        nid = rec.success("d", "algo", 0.95, tags=["test"])
        node = kg._nodes[nid]
        assert node.outcome == 0.95
        assert "success" in node.tags

    def test_failure(self):
        kg = KnowledgeGraph()
        rec = OutcomeRecorder(kg)
        nid = rec.failure("d", "algo", "timeout", tags=["test"])
        node = kg._nodes[nid]
        assert node.outcome == 0.15
        assert node.failure_reason == "timeout"
        assert "failure" in node.tags

    def test_from_user(self):
        kg = KnowledgeGraph()
        rec = OutcomeRecorder(kg)
        nid = rec.from_user("d", "algo", "circle is off the ball")
        node = kg._nodes[nid]
        assert "user_report" in node.failure_reason
        assert "circle is off the ball" in node.params.get("user_verbatim", "")

    def test_record_params(self):
        kg = KnowledgeGraph()
        rec = OutcomeRecorder(kg)
        nid = rec.record_params("d", "algo", 0.8, {"threshold": 32, "fps": 30})
        node = kg._nodes[nid]
        assert node.params["threshold"] == 32
        assert node.params["fps"] == 30

    def test_record_generic(self):
        kg = KnowledgeGraph()
        rec = OutcomeRecorder(kg)
        nid = rec.record("x", "algo", 0.4, tags=["neutral"])
        node = kg._nodes[nid]
        assert node.outcome == 0.4
        assert "neutral" in node.tags

    def test_record_cycle(self):
        kg = KnowledgeGraph()
        rec = OutcomeRecorder(kg)
        nid = rec.record_cycle("d", "algo", 0.85, cycle=5, di=0.92)
        node = kg._nodes[nid]
        assert node.params["cycle"] == 5
        assert node.params["di"] == 0.92

    def test_graph_stats_after_recording(self):
        kg = KnowledgeGraph()
        rec = OutcomeRecorder(kg)
        rec.success("x", "a", 0.9)
        rec.failure("x", "b", "crash")
        rec.failure("x", "c", "timeout")
        assert kg.stats["successes"] == 1
        assert kg.stats["failures"] == 2

    def test_node_to_dict(self):
        kg = KnowledgeGraph()
        rec = OutcomeRecorder(kg)
        nid = rec.success("d", "algo", 0.85, tags=["t1"])
        d = kg._nodes[nid].to_dict()
        assert d["approach"] == "algo"
        assert d["outcome"] == 0.85
