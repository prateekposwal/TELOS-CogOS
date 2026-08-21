"""Contract tests for KGInferenceEngine — similarity and failure patterns."""

from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.knowledge.inference import KGInferenceEngine


class TestEuclideanDistance:
    def test_identical_params_distance_zero(self):
        eng = KGInferenceEngine(KnowledgeGraph())
        assert eng._euclidean_distance({"x": 1.0, "y": 2.0}, {"x": 1.0, "y": 2.0}) == 0.0

    def test_missing_keys_treated_as_zero(self):
        eng = KGInferenceEngine(KnowledgeGraph())
        # union of keys: x, y, z; p1 lacks z, p2 lacks x -> all compared against 0
        dist = eng._euclidean_distance({"x": 3.0}, {"y": 4.0})
        assert dist == 5.0  # sqrt(3^2 + 4^2)

    def test_scalar_distance(self):
        eng = KGInferenceEngine(KnowledgeGraph())
        assert eng._euclidean_distance({"speed": 0.0}, {"speed": 3.0}) == 3.0


class TestFindSimilarOutcomes:
    def _graph_with_params(self):
        kg = KnowledgeGraph()
        a = kg.record("gridworld", "algo_a", 0.9, params={"speed": 0.5, "size": 1.0})
        b = kg.record("gridworld", "algo_b", 0.8, params={"speed": 0.9, "size": 1.0})
        c = kg.record("gridworld", "algo_c", 0.7, params={"size": 0.0})
        no_params = kg.record("gridworld", "algo_d", 0.6)
        return kg, (a, b, c, no_params)

    def test_returns_closest_by_euclidean_distance(self):
        kg, (a, b, c, _) = self._graph_with_params()
        eng = KGInferenceEngine(kg)
        query = {"speed": 0.4, "size": 1.0}
        nodes = eng.find_similar_outcomes(query, top_k=3)
        assert [n.node_id for n in nodes] == [a, b, c]

    def test_nodes_without_params_are_skipped(self):
        kg, (a, b, c, no_params) = self._graph_with_params()
        eng = KGInferenceEngine(kg)
        nodes = eng.find_similar_outcomes({"speed": 0.4, "size": 1.0}, top_k=5)
        assert no_params not in [n.node_id for n in nodes]

    def test_top_k_limits_results(self):
        kg, _ = self._graph_with_params()
        eng = KGInferenceEngine(kg)
        assert len(eng.find_similar_outcomes({"speed": 0.4, "size": 1.0}, top_k=1)) == 1

    def test_empty_graph_returns_empty(self):
        eng = KGInferenceEngine(KnowledgeGraph())
        assert eng.find_similar_outcomes({"anything": 1.0}) == []


class TestDetectFailurePatterns:
    def test_groups_failures_by_blocking_validator(self):
        kg = KnowledgeGraph()
        kg.record_failure("gridworld", "hough_circles", 0.18,
                          failure_reason="HUD",
                          params={"blocking_validator": "reality_gap"})
        kg.record_failure("gridworld", "hough_lines", 0.2,
                          failure_reason="haze",
                          params={"blocking_validator": "reality_gap"})
        kg.record_failure("gridworld", "naive_track", 0.1,
                          failure_reason="occlusion",
                          params={"blocking_validator": "safety_gate"})
        eng = KGInferenceEngine(kg)
        patterns = eng.detect_failure_patterns("gridworld")
        # failures are scored desc by (1 - outcome); the lowest-outcome
        # (safety_gate) node sorts first
        assert [p["validator"] for p in patterns] == ["safety_gate", "reality_gap"]
        assert patterns[0]["count"] == 1
        assert patterns[0]["reason"] == "occlusion"
        assert patterns[1]["count"] == 2
        assert patterns[1]["reason"] == "HUD"

    def test_unknown_validator_default(self):
        kg = KnowledgeGraph()
        kg.record_failure("gridworld", "flat", 0.2, failure_reason="walls")
        eng = KGInferenceEngine(kg)
        patterns = eng.detect_failure_patterns("gridworld")
        assert patterns[0]["validator"] == "unknown"

    def test_no_failures_returns_empty(self):
        kg = KnowledgeGraph()
        kg.record("gridworld", "yolo_csrt", 0.92)
        eng = KGInferenceEngine(kg)
        assert eng.detect_failure_patterns("gridworld") == []