"""Contract tests for telos.core.knowledge.explanation.engine.ExplanationCompression.

Covers the compression engine contract:
  - instance registration and id generation
  - rule formation once enough similar instances accumulate
  - rule matching / explain() compressed vs. no-match responses
  - compress() metrics, rule status lifecycle, and retirement
  - get_top_rules ordering and to_dict() serialization
"""
import pytest

from telos.core.knowledge.explanation.engine import ExplanationCompression
from telos.core.knowledge.explanation.dataclasses import (
    ExplanationInstance,
    CompressedRule,
    CompressionMetrics,
    RuleStatus,
)


def test_add_instance_registers_and_matches_shape():
    engine = ExplanationCompression()
    iid = engine.add_instance("ball missing", "occlusion", "ball behind player")
    assert isinstance(iid, str)
    assert iid.startswith("exp_")
    assert len(engine._instances) == 1
    assert engine._instances[iid].phenomenon == "ball missing"
    assert engine._instances[iid].cause == "occlusion"
    assert engine._instances[iid].mechanism == "ball behind player"
    assert engine._instances[iid].source == "pipeline"


def test_add_instance_default_confidence_and_context():
    engine = ExplanationCompression()
    iid = engine.add_instance("p", "c", "m")
    inst = engine._instances[iid]
    assert inst.confidence == 0.5
    assert inst.context == {}
    assert inst.source == "pipeline"


def test_add_instance_uses_provided_context_confidence_source():
    engine = ExplanationCompression()
    iid = engine.add_instance("p", "c", "m", context={"lane": 2}, confidence=0.9, source="user")
    inst = engine._instances[iid]
    assert inst.context == {"lane": 2}
    assert inst.confidence == 0.9
    assert inst.source == "user"


def test_rule_forms_after_minimum_similar_instances():
    engine = ExplanationCompression(min_instances_per_rule=5)
    for _ in range(5):
        engine.add_instance("ball missing", "occlusion by player",
                            "the player blocked the camera view")
    assert len(engine._rules) == 1
    rule = next(iter(engine._rules.values()))
    assert len(rule.instances_explained) == 5
    assert rule.coverage_count == 5


def test_rule_not_formed_below_minimum():
    engine = ExplanationCompression(min_instances_per_rule=5)
    for _ in range(3):
        engine.add_instance("ball missing", "occlusion by player",
                            "player blocked the view")
    assert len(engine._rules) == 0
    assert len(engine._instances) == 3


def test_explain_compressed_when_rule_matches():
    engine = ExplanationCompression(min_instances_per_rule=3)
    for _ in range(3):
        engine.add_instance("ball missing", "occlusion by player",
                            "the player blocked the camera view")
    # Query must share keywords with the formed rule's condition pattern.
    result = engine.explain("ball missing", "occlusion by player")
    assert result["compressed"] is True
    assert result["explained_by_rule"] is not None
    assert result["rule_description"] is not None
    assert result["explanation"] is not None
    assert result["coverage"] >= 3
    assert "accuracy" in result
    assert "parsimony" in result


def test_explain_no_match_returns_false():
    engine = ExplanationCompression()
    result = engine.explain("nova collapsing", "hydrogen exhaustion")
    assert result["compressed"] is False
    assert result["explained_by_rule"] is None
    assert "message" in result


def test_compress_returns_metrics_and_records_log():
    engine = ExplanationCompression(min_instances_per_rule=3)
    for _ in range(3):
        engine.add_instance("ball missing", "occlusion by player",
                            "player blocked the camera view")
    metrics = engine.compress()
    assert isinstance(metrics, CompressionMetrics)
    assert metrics.total_instances == 3
    assert metrics.total_rules >= 1
    assert metrics.compression_ratio > 0
    assert engine._total_compressions == 1
    assert engine._compression_log[-1]["total_instances"] == 3


def test_compress_marks_rule_active_with_sufficient_coverage():
    engine = ExplanationCompression(min_instances_per_rule=3)
    for _ in range(3):
        engine.add_instance("ball missing", "occlusion by player", "player blocked view")
    engine.compress()
    rule = next(iter(engine._rules.values()))
    # Coverage meets min_instances, so the rule becomes ACTIVE.
    assert rule.status == RuleStatus.ACTIVE


def test_compress_updates_accuracy_from_confidence():
    engine = ExplanationCompression(min_instances_per_rule=3)
    for _ in range(3):
        engine.add_instance("ball missing", "occlusion by player",
                            "player blocked view", confidence=0.9)
    engine.compress()
    rule = next(iter(engine._rules.values()))
    # All covered instances have confidence > 0.5 -> accuracy 1.0
    assert rule.accuracy == pytest.approx(1.0)


def test_get_top_rules_returns_sorted_active():
    engine = ExplanationCompression()
    rule_a = CompressedRule(
        id="ra", description="a", condition_pattern="x y z",
        explanation_template="t", instances_explained=["1"],
        coverage_count=5, accuracy=0.9, parsimony=0.8, status=RuleStatus.ACTIVE,
    )
    rule_b = CompressedRule(
        id="rb", description="b", condition_pattern="x y z",
        explanation_template="t", instances_explained=["2"],
        coverage_count=1, accuracy=0.1, parsimony=0.2, status=RuleStatus.ACTIVE,
    )
    engine._rules["ra"] = rule_a
    engine._rules["rb"] = rule_b
    top = engine.get_top_rules(1)
    assert [r.id for r in top] == ["ra"]


def test_get_top_rules_excludes_retired():
    engine = ExplanationCompression()
    active = CompressedRule(
        id="act", description="a", condition_pattern="a b",
        explanation_template="t", instances_explained=[],
        coverage_count=5, accuracy=0.9, parsimony=0.8, status=RuleStatus.ACTIVE,
    )
    retired = CompressedRule(
        id="ret", description="r", condition_pattern="a b",
        explanation_template="t", instances_explained=[],
        coverage_count=1, accuracy=0.1, parsimony=0.2, status=RuleStatus.RETIRED,
    )
    engine._rules["act"] = active
    engine._rules["ret"] = retired
    top = engine.get_top_rules(10)
    assert [r.id for r in top] == ["act"]


def test_compression_ratio_property():
    engine = ExplanationCompression(min_instances_per_rule=3)
    for _ in range(3):
        engine.add_instance("ball missing", "occlusion by player", "player blocked view")
    engine.compress()
    assert engine.compression_ratio == pytest.approx(3.0)


def test_to_dict_reports_counts_and_totals():
    engine = ExplanationCompression(min_instances_per_rule=3)
    for _ in range(3):
        engine.add_instance("ball missing", "occlusion by player", "player blocked view")
    engine.compress()
    d = engine.to_dict()
    assert d["total_instances"] == 3
    assert d["total_rules"]["active"] == 1
    assert d["compression_ratio"] == 3.0
    assert len(d["top_rules"]) >= 1
    top = d["top_rules"][0]
    assert "id" in top and "coverage" in top and "status" in top
    assert "compression_history" in d


def test_retirement_of_low_coverage_rules_on_compress():
    engine = ExplanationCompression(min_instances_per_rule=5,
                                    retirement_threshold=0.2)
    # A strong rule covering most instances.
    for _ in range(7):
        engine.add_instance("ball missing", "occlusion by player", "player blocked camera view")
    # Inject a tiny rule whose coverage is below the retirement threshold.
    small = CompressedRule(
        id="small_rule", description="small", condition_pattern="xxx kk",
        explanation_template="t", instances_explained=["i1"], coverage_count=1,
        accuracy=0.5, parsimony=0.9, status=RuleStatus.ACTIVE,
    )
    engine._rules["small_rule"] = small
    engine.compress()
    retired = [r for r in engine._rules.values() if r.status == RuleStatus.RETIRED]
    assert [r.id for r in retired] == ["small_rule"]


def test_parsimony_is_bounded_to_unit_interval():
    engine = ExplanationCompression()
    assert engine._compute_parsimony("short") == 0.9
    assert 0.0 <= engine._compute_parsimony("") <= 1.0
