"""Contract tests for telos.core.knowledge.explanation.dataclasses.

Covers ExplanationInstance, CompressedRule (incl. derived score/coverage),
CompressionMetrics, and the RuleStatus enum. The scanner maps dataclasses.py
back to test_dataclasses.py, but that namespace is already occupied by other
content, so this parallel test file uses a basename that unambiguously
references the explanation dataclasses module.
"""
import time

from telos.core.knowledge.explanation.dataclasses import (
    RuleStatus,
    ExplanationInstance,
    CompressedRule,
    CompressionMetrics,
)


def test_rule_status_enum_values():
    assert RuleStatus.FORMING.value == "forming"
    assert RuleStatus.ACTIVE.value == "active"
    assert RuleStatus.REFINING.value == "refining"
    assert RuleStatus.RETIRED.value == "retired"
    assert set(RuleStatus) == {
        RuleStatus.FORMING, RuleStatus.ACTIVE,
        RuleStatus.REFINING, RuleStatus.RETIRED,
    }


def test_explanation_instance_requires_core_fields():
    inst = ExplanationInstance(
        id="exp_1", phenomenon="ball missing", cause="occlusion",
        mechanism="player behind ball", context={"lane": 1},
        confidence=0.8, source="pipeline",
    )
    assert inst.id == "exp_1"
    assert inst.phenomenon == "ball missing"
    assert inst.cause == "occlusion"
    assert inst.mechanism == "player behind ball"
    assert inst.context == {"lane": 1}
    assert inst.confidence == 0.8
    assert inst.source == "pipeline"
    assert inst.timestamp > 0


def test_explanation_instance_timestamp_defaults_to_now():
    before = time.time()
    inst = ExplanationInstance(id="e", phenomenon="p", cause="c",
                               mechanism="m", context={}, confidence=0.5,
                               source="s")
    assert before <= inst.timestamp <= time.time()


def test_compressed_rule_compression_score():
    rule = CompressedRule(
        id="r1", description="desc", condition_pattern="a b c",
        explanation_template="template", instances_explained=["i1", "i2"],
        coverage_count=2, accuracy=0.8, parsimony=0.9, status=RuleStatus.ACTIVE,
    )
    assert rule.coverage_count == 2
    assert rule.accuracy == 0.8
    assert rule.parsimony == 0.9
    expected = 2 * 0.4 + 0.8 * 0.3 + 0.9 * 0.3
    assert rule.compression_score == expected


def test_compressed_rule_compression_score_weights():
    # coverage weight 0.4 dominates; more coverage -> higher score
    low = CompressedRule(id="a", description="d", condition_pattern="p",
                         explanation_template="t", instances_explained=[],
                         coverage_count=1, accuracy=0.8, parsimony=0.9,
                         status=RuleStatus.ACTIVE)
    high = CompressedRule(id="b", description="d", condition_pattern="p",
                          explanation_template="t", instances_explained=[],
                          coverage_count=10, accuracy=0.8, parsimony=0.9,
                          status=RuleStatus.ACTIVE)
    assert high.compression_score > low.compression_score


def test_compressed_rule_timestamps_default():
    rule = CompressedRule(
        id="r", description="d", condition_pattern="p",
        explanation_template="t", instances_explained=[], coverage_count=0,
        accuracy=0.5, parsimony=0.5, status=RuleStatus.FORMING,
    )
    assert rule.first_formed > 0
    assert rule.last_used > 0
    assert rule.times_applied == 0
    assert rule.coverage_ratio == 0.0


def test_compression_metrics_fields():
    metrics = CompressionMetrics(
        total_instances=100, total_rules=3, compression_ratio=33.33,
        top_rule_coverage=0.7, top_3_coverage=0.9,
        average_accuracy=0.8, average_parsimony=0.75,
    )
    assert metrics.total_instances == 100
    assert metrics.total_rules == 3
    assert metrics.compression_ratio == 33.33
    assert metrics.top_rule_coverage == 0.7
    assert metrics.top_3_coverage == 0.9
    assert metrics.average_accuracy == 0.8
    assert metrics.average_parsimony == 0.75
