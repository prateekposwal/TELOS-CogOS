"""Contract tests for telos.core.knowledge.explanation_compression.

The module is a re-export of the `telos.core.knowledge.explanation`
package; these tests exercise the real engine behavior behind the public
names it advertises: RuleStatus, ExplanationInstance, CompressedRule,
CompressionMetrics, ExplanationCompression.
"""

from telos.core.knowledge.explanation_compression import (
    RuleStatus, ExplanationInstance, CompressedRule,
    CompressionMetrics, ExplanationCompression,
)
from telos.core.knowledge.explanation.engine import ExplanationCompression as Engine


class TestReExportContract:
    def test_public_names_resolve_to_real_objects(self):
        assert Engine is ExplanationCompression
        assert RuleStatus.FORMING.value == "forming"
        assert RuleStatus.ACTIVE.value == "active"
        assert RuleStatus.REFINING.value == "refining"
        assert RuleStatus.RETIRED.value == "retired"

    def test_compressed_rule_compression_score_weights(self):
        rule = CompressedRule(
            id="r1", description="d", condition_pattern="a b c",
            explanation_template="t", instances_explained=["e1"],
            coverage_count=5, accuracy=0.8, parsimony=0.9,
            status=RuleStatus.ACTIVE,
        )
        assert rule.coverage_ratio == 0.0  # computed externally, stored as 0
        expected = 5 * 0.4 + 0.8 * 0.3 + 0.9 * 0.3
        assert rule.compression_score == expected


class TestRuleFormation:
    def test_empty_engine_has_no_rules(self):
        eng = ExplanationCompression()
        assert eng.to_dict()["total_instances"] == 0
        assert eng.to_dict()["total_rules"]["active"] == 0

    def test_insufficient_instances_never_form_rule(self):
        eng = ExplanationCompression(min_instances_per_rule=5)
        for _ in range(4):
            eng.add_instance("grid exploration", "blocked path",
                             "wall collision", confidence=0.9)
        assert len(eng._rules) == 0
        assert len(eng._instances) == 4

    def test_rule_forms_when_min_instances_reached(self):
        eng = ExplanationCompression(min_instances_per_rule=5)
        for _ in range(5):
            eng.add_instance("grid exploration", "blocked path",
                             "wall collision", confidence=0.9)
        assert len(eng._rules) == 1
        rule = next(iter(eng._rules.values()))
        assert rule.coverage_count == 5
        assert rule.status == RuleStatus.ACTIVE
        assert rule.condition_pattern == "blocked exploration grid path"

    def test_similar_instance_merges_into_existing_rule(self):
        eng = ExplanationCompression(min_instances_per_rule=5)
        for _ in range(5):
            eng.add_instance("grid exploration", "blocked path",
                             "wall collision", confidence=0.9)
        new_id = eng.add_instance("grid exploration", "blocked path",
                                  "wall collision", confidence=0.9)
        rule = next(iter(eng._rules.values()))
        assert rule.coverage_count == 6
        assert eng._instance_to_rule[new_id] == rule.id

    def test_dissimilar_instance_does_not_match_rule(self):
        eng = ExplanationCompression(min_instances_per_rule=5)
        for _ in range(5):
            eng.add_instance("grid exploration", "blocked path",
                             "wall collision", confidence=0.9)
        new_id = eng.add_instance("quantum teleportation", "superposition",
                                  "entangled collapse", confidence=0.9)
        assert new_id not in eng._instance_to_rule


class TestExplain:
    def test_explain_matches_rule(self):
        eng = ExplanationCompression(min_instances_per_rule=2)
        for _ in range(2):
            eng.add_instance("grid exploration", "blocked path",
                             "wall collision", confidence=0.9)
        result = eng.explain("grid exploration", "blocked path")
        assert result["compressed"] is True
        assert result["coverage"] == 2
        assert result["accuracy"] == 0.7  # initial estimate before compress()

    def test_explain_missing_returns_compressed_false(self):
        eng = ExplanationCompression(min_instances_per_rule=2)
        for _ in range(2):
            eng.add_instance("grid exploration", "blocked path",
                             "wall collision", confidence=0.9)
        result = eng.explain("birdwatching habitat", "migration route")
        assert result["compressed"] is False
        assert result["explained_by_rule"] is None


class TestCompressCycle:
    def test_compress_measures_ratio_and_coverage(self):
        eng = ExplanationCompression(min_instances_per_rule=5)
        for _ in range(5):
            eng.add_instance("grid exploration", "blocked path",
                             "wall collision", confidence=0.9)
        metrics = eng.compress()
        assert isinstance(metrics, CompressionMetrics)
        assert metrics.total_instances == 5
        assert metrics.total_rules == 1
        assert metrics.compression_ratio == 5.0
        assert metrics.top_rule_coverage == 1.0
        assert metrics.average_accuracy == 1.0
        assert metrics.average_parsimony > 0.0

    def test_low_coverage_rule_is_retired(self):
        eng = ExplanationCompression(min_instances_per_rule=2)
        for _ in range(2):
            eng.add_instance("grid exploration", "blocked path",
                             "wall collision", confidence=0.9)
        for i in range(50):
            eng.add_instance(f"unique phenomenon {i}", f"unique cause {i}",
                             "mechanism", confidence=0.5)
        eng.compress()
        rule = next(iter(eng._rules.values()))
        assert rule.status == RuleStatus.RETIRED

    def test_compression_ratio_property(self):
        eng = ExplanationCompression(min_instances_per_rule=5)
        for _ in range(5):
            eng.add_instance("grid exploration", "blocked path",
                             "wall collision", confidence=0.9)
        assert eng.compression_ratio == 5.0


class TestParsimony:
    def test_short_pattern_is_most_parsimonious(self):
        eng = ExplanationCompression()
        assert eng._compute_parsimony("a b c") == 0.9
        assert eng._compute_parsimony("") == 0.5

    def test_long_pattern_penalized(self):
        eng = ExplanationCompression()
        long = " ".join(f"w{i}" for i in range(40))
        assert eng._compute_parsimony(long) < 0.5