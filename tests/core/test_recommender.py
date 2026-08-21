"""Contract tests for KnowledgeRecommender — the read-only "what works?"
advisor over a KnowledgeGraph."""

from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.knowledge.recommender import KnowledgeRecommender


def _graph_with_data():
    kg = KnowledgeGraph()
    kg.record("gridworld", "yolo_csrt", 0.92, tags=["dl", "realtime"])
    kg.record("gridworld", "csrt_kcf", 0.75, tags=["classic"])
    kg.record_failure("gridworld", "hough_circles", 0.18,
                      failure_reason="HUD", tags=["cv"])
    return kg


class TestRecommend:
    def test_best_single_approach(self):
        rec = KnowledgeRecommender(_graph_with_data())
        assert rec.recommend("gridworld") == "yolo_csrt"

    def test_unknown_domain_returns_none(self):
        rec = KnowledgeRecommender(KnowledgeGraph())
        assert rec.recommend("empty_domain") is None


class TestRecommendTop:
    def test_top_k_successes_only(self):
        rec = KnowledgeRecommender(_graph_with_data())
        top = rec.recommend_top("gridworld")
        assert len(top) == 2  # the failure node is excluded (outcome <= 0.5)
        assert [t["outcome"] for t in top] == [0.92, 0.75]
        assert top[0]["approach"] == "yolo_csrt"
        assert top[0]["tags"] == ["dl", "realtime"]

    def test_top_k_limited(self):
        rec = KnowledgeRecommender(_graph_with_data())
        assert len(rec.recommend_top("gridworld", top_k=1)) == 1


class TestFailures:
    def test_failures_list_reason(self):
        rec = KnowledgeRecommender(_graph_with_data())
        failures = rec.failures("gridworld")
        assert failures == [{
            "approach": "hough_circles",
            "outcome": 0.18,
            "failure_reason": "HUD",
        }]

    def test_would_repeat_failure(self):
        rec = KnowledgeRecommender(_graph_with_data())
        assert rec.would_repeat_failure("gridworld", "hough_circles") is True
        assert rec.would_repeat_failure("gridworld", "yolo_csrt") is False


class TestSummarize:
    def test_summary_with_proven_and_avoid(self):
        rec = KnowledgeRecommender(_graph_with_data())
        summary = rec.summarize("gridworld")
        assert summary.startswith("Proven: yolo_csrt (0.92), csrt_kcf (0.75)")
        assert "Avoid: hough_circles (failed: HUD)" in summary
        assert ". " in summary

    def test_summary_without_failures(self):
        kg = KnowledgeGraph()
        kg.record("navigation", "a_star", 0.8)
        rec = KnowledgeRecommender(kg)
        assert rec.summarize("navigation") == "Proven: a_star (0.8)"

    def test_summary_empty_domain(self):
        rec = KnowledgeRecommender(KnowledgeGraph())
        assert rec.summarize("empty_domain") == "Proven: "


class TestReadOnlyContract:
    def test_recommending_never_writes_to_graph(self):
        kg = _graph_with_data()
        rec = KnowledgeRecommender(kg)
        before = kg.stats["total_nodes"]
        rec.recommend("gridworld")
        rec.recommend_top("gridworld")
        rec.failures("gridworld")
        rec.summarize("gridworld")
        assert kg.stats["total_nodes"] == before