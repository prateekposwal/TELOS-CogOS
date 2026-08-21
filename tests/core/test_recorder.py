"""Contract tests for OutcomeRecorder and KnowledgeRecommender — record with
full context and ask "what works?" (read-only) before starting."""
import pytest

from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.knowledge.recorder import OutcomeRecorder
from telos.core.knowledge.recommender import KnowledgeRecommender


def _graph():
    g = KnowledgeGraph()
    g._max_hot_nodes = 100
    return g


class TestOutcomeRecorder:
    """Records wins/losses with contextual tags."""

    def test_success_tags_with_success(self):
        g = _graph()
        rec = OutcomeRecorder(g)
        nid = rec.success("devdomain", "refactor", 0.92)
        assert nid
        node = g._nodes[nid]
        assert "success" in node.tags

    def test_failure_tags_with_failure_and_reason(self):
        g = _graph()
        rec = OutcomeRecorder(g)
        nid = rec.failure("devdomain", "hough_circles", "HUD contamination")
        node = g._nodes[nid]
        assert "failure" in node.tags
        assert "HUD contamination" in (node.failure_reason or "")

    def test_from_user_records_user_feedback(self):
        g = _graph()
        rec = OutcomeRecorder(g)
        nid = rec.from_user("devdomain", "mog2_white",
                            "points to shirt not ball")
        node = g._nodes[nid]
        assert "user_report: points to shirt not ball" in (node.failure_reason or "")
        assert node.params.get("user_verbatim") == "points to shirt not ball"

    def test_record_cycle_keeps_di(self):
        g = _graph()
        rec = OutcomeRecorder(g)
        nid = rec.record_cycle("devdomain", "refactor", 0.8, cycle=5, di=0.95)
        node = g._nodes[nid]
        assert node.params["cycle"] == 5
        assert node.params["di"] == 0.95


class TestKnowledgeRecommender:
    """Read-only best-approach advisor."""

    def _populated(self):
        g = _graph()
        rec = OutcomeRecorder(g)
        rec.success("devdomain", "yolo_csrt", 0.92)
        rec.success("devdomain", "csrt_kcf", 0.75)
        rec.failure("devdomain", "hough_circles", "HUD contamination")
        return g

    def test_recommend_returns_best(self):
        g = self._populated()
        assert KnowledgeRecommender(g).recommend("devdomain") == "yolo_csrt"

    def test_failures_are_reported(self):
        g = self._populated()
        fails = KnowledgeRecommender(g).failures("devdomain")
        assert any(f["approach"] == "hough_circles" for f in fails)

    def test_summarize_names_proven_and_avoid(self):
        g = self._populated()
        s = KnowledgeRecommender(g).summarize("devdomain")
        assert "yolo_csrt" in s
        assert "hough_circles" in s

    def test_would_repeat_failure_detects_known_failure(self):
        g = self._populated()
        rec = KnowledgeRecommender(g)
        assert rec.would_repeat_failure("devdomain", "hough_circles") is True
        assert rec.would_repeat_failure("devdomain", "yolo_csrt") is False