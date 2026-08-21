"""Tests for the TheoryBuilder dataclasses: AbstractionLevel, Experience,
Pattern, Hypothesis (with its falsification machinery), and Theory."""

from telos.core.reasoning.theory.dataclasses import (
    AbstractionLevel,
    Experience,
    Pattern,
    Hypothesis,
    Theory,
)


class TestAbstractionLevel:
    def test_level_values(self):
        assert AbstractionLevel.EXPERIENCE.value == "experience"
        assert AbstractionLevel.PATTERN.value == "pattern"
        assert AbstractionLevel.HYPOTHESIS.value == "hypothesis"
        assert AbstractionLevel.THEORY.value == "theory"


class TestExperience:
    def test_default_domain_is_unknown(self):
        exp = Experience(id="e1", context={"x": 1}, action="go",
                         outcome=0.8, confidence=0.9, timestamp=1.0)
        assert exp.domain == "unknown"

    def test_fields_round_trip(self):
        exp = Experience(id="e1", context={"x": 1}, action="go",
                         outcome=0.8, confidence=0.9, timestamp=1.0,
                         domain="grid")
        assert exp.id == "e1"
        assert exp.context == {"x": 1}
        assert exp.action == "go"
        assert exp.outcome == 0.8
        assert exp.confidence == 0.9
        assert exp.domain == "grid"


class TestPattern:
    def test_fields_round_trip(self):
        pat = Pattern(id="p1", name="successful-go", experiences=["e1", "e2"],
                      common_context={"terrain": "flat"}, avg_outcome=0.85,
                      confidence=0.7, created=1.0, last_updated=2.0,
                      support_count=2)
        assert pat.id == "p1"
        assert pat.experiences == ["e1", "e2"]
        assert pat.common_context == {"terrain": "flat"}
        assert pat.avg_outcome == 0.85
        assert pat.support_count == 2


class TestHypothesis:
    def test_defaults(self):
        h = Hypothesis(id="h1", description="d", context_signature={},
                       action="go", predicted_outcome=1.0, confidence=0.5,
                       supporting_patterns=["p1"])
        assert h.tests_passed == 0
        assert h.tests_failed == 0
        assert h.created == 0.0
        assert h.falsified is False
        assert h.parent_theory_id is None

    def test_test_ratio_zero_with_no_tests(self):
        h = Hypothesis(id="h1", description="d", context_signature={},
                       action="go", predicted_outcome=1.0, confidence=0.5,
                       supporting_patterns=[])
        assert h.test_ratio == 0.0

    def test_test_ratio_counts_passes_over_total(self):
        h = Hypothesis(id="h1", description="d", context_signature={},
                       action="go", predicted_outcome=1.0, confidence=0.5,
                       supporting_patterns=[])
        h.tests_passed = 3
        h.tests_failed = 1
        assert h.test_ratio == 0.75

    def test_survival_within_tolerance_strengthens(self):
        h = Hypothesis(id="h1", description="d", context_signature={},
                       action="go", predicted_outcome=1.0, confidence=0.5,
                       supporting_patterns=[])
        assert h.test(0.9, tolerance=0.2) is True
        assert h.tests_passed == 1
        assert h.confidence == 0.6

    def test_confidence_capped_at_one(self):
        h = Hypothesis(id="h1", description="d", context_signature={},
                       action="go", predicted_outcome=1.0, confidence=0.95,
                       supporting_patterns=[])
        for _ in range(3):
            h.test(1.0, tolerance=0.2)
        assert h.confidence == 1.0

    def test_failure_outside_tolerance_weakens(self):
        h = Hypothesis(id="h1", description="d", context_signature={},
                       action="go", predicted_outcome=1.0, confidence=0.5,
                       supporting_patterns=[])
        assert h.test(2.0, tolerance=0.2) is False
        assert h.tests_failed == 1
        assert h.confidence == 0.3
        assert h.falsified is False

    def test_confidence_floor_zero(self):
        h = Hypothesis(id="h1", description="d", context_signature={},
                       action="go", predicted_outcome=1.0, confidence=0.05,
                       supporting_patterns=[])
        h.test(5.0, tolerance=0.2)
        assert h.confidence == 0.0

    def test_falsified_when_confidence_below_threshold(self):
        h = Hypothesis(id="h1", description="d", context_signature={},
                       action="go", predicted_outcome=1.0, confidence=0.15,
                       supporting_patterns=[])
        h.test(5.0, tolerance=0.2)
        assert h.confidence == 0.0
        assert h.falsified is True

    def test_exact_match_survives(self):
        h = Hypothesis(id="h1", description="d", context_signature={},
                       action="go", predicted_outcome=1.0, confidence=0.5,
                       supporting_patterns=[])
        assert h.test(1.0, tolerance=0.2) is True


class TestTheory:
    def test_defaults(self):
        t = Theory(id="t1", name="n", description="d", hypothesis_id="h1",
                   context_signature={}, action="go", predicted_outcome=1.0,
                   confidence=0.8, tests_passed=5, tests_failed=1,
                   domains=["grid"], created=1.0)
        assert t.promoted_from == AbstractionLevel.HYPOTHESIS
        assert t.parent_theory_id is None

    def test_fields_round_trip(self):
        t = Theory(id="t1", name="n", description="d", hypothesis_id="h1",
                   context_signature={"terrain": "flat"}, action="go",
                   predicted_outcome=1.0, confidence=0.8, tests_passed=5,
                   tests_failed=1, domains=["grid", "logistics"], created=1.0,
                   promoted_from=AbstractionLevel.THEORY,
                   parent_theory_id="t0")
        assert t.context_signature == {"terrain": "flat"}
        assert t.domains == ["grid", "logistics"]
        assert t.promoted_from == AbstractionLevel.THEORY
        assert t.parent_theory_id == "t0"