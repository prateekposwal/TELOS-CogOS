"""Contract tests for the theory builder pipeline.

The module `telos.core.reasoning.theory_builder` re-exports the
`TheoryBuilder` implemented in `telos.core.reasoning.theory.builder` plus
the dataclasses. The re-export must resolve to the real implementation and
the experience -> pattern -> hypothesis -> test -> theory pipeline must
behave as documented.
"""

from telos.core.reasoning import theory_builder as tb_mod
from telos.core.reasoning.theory.builder import TheoryBuilder as RealTheoryBuilder
from telos.core.reasoning.theory_builder import (
    TheoryBuilder, AbstractionLevel, Experience, Pattern, Hypothesis, Theory,
)
from telos.core.reasoning.genealogy import TheoryGenealogy

import pytest


class TestReExportContract:
    def test_reexport_is_same_class(self):
        assert TheoryBuilder is RealTheoryBuilder
        assert AbstractionLevel.EXPERIENCE.value == "experience"
        assert AbstractionLevel.THEORY.value == "theory"

    def test_dataclass_defaults(self):
        hyp = Hypothesis(
            id="h1", description="d", context_signature={}, action="a",
            predicted_outcome=0.9, confidence=0.5, supporting_patterns=[],
        )
        assert hyp.test_ratio == 0.0
        assert hyp.falsified is False


class TestExperienceAddition:
    def test_add_experience_returns_id_and_increments(self):
        b = TheoryBuilder()
        eid = b.add_experience({"signal": 1.0}, "navigate", 0.9,
                               confidence=0.8, domain="gridworld")
        assert eid.startswith("exp_")
        assert b.total_experiences == 1
        exp = b._experiences[eid]
        assert isinstance(exp, Experience)
        assert exp.action == "navigate"
        assert exp.outcome == 0.9
        assert exp.domain == "gridworld"

    def test_observe_outcome_bridges_pipeline(self):
        b = TheoryBuilder()
        eid = b.observe_outcome(outcome=0.9, context="state_7",
                                action="navigate", domain="gridworld")
        exp = b._experiences[eid]
        assert exp.context["state_preview"] == "state_7"[:80]
        assert exp.domain == "gridworld"
        assert b._cycle == 1

    def test_build_runs_full_pipeline_and_reports(self):
        b = TheoryBuilder(min_experiences_for_pattern=1,
                          min_patterns_for_hypothesis=1,
                          min_tests_for_theory=1,
                          theory_confidence_threshold=0.1)
        summary = b.build({"a": 1}, "probe", 0.9)
        assert set(summary) == {
            "experience_id", "hypotheses_tested", "hypotheses_survived",
            "new_patterns", "new_hypotheses", "new_theories",
        }
        assert summary["experience_id"].startswith("exp_")
        assert summary["new_patterns"] == 1
        assert summary["new_hypotheses"] == 1
        assert summary["new_theories"] == 0  # no tests accumulated yet


class TestAbstraction:
    def _pattern_builder(self):
        return TheoryBuilder(min_experiences_for_pattern=2,
                             min_patterns_for_hypothesis=2,
                             min_tests_for_theory=2,
                             theory_confidence_threshold=0.5)

    def test_cluster_forms_pattern_from_repeated_experiences(self):
        b = self._pattern_builder()
        for _ in range(2):
            b.add_experience({"signal": 1.0}, "navigate", 0.9, domain="gridworld")
        patterns = b.cluster()
        assert len(patterns) == 1
        pattern = patterns[0]
        assert isinstance(pattern, Pattern)
        assert pattern.name == "navigate_high"
        assert pattern.avg_outcome == pytest.approx(0.9)
        assert pattern.support_count == 2
        assert pattern.common_context == {"signal": 1.0}
        assert b.total_patterns == 1

    def test_cluster_is_idempotent(self):
        b = self._pattern_builder()
        for _ in range(2):
            b.add_experience({"signal": 1.0}, "navigate", 0.9)
        assert len(b.cluster()) == 1
        assert b.cluster() == []  # experiences are indexed after cluster

    def test_too_few_experiences_no_pattern(self):
        b = self._pattern_builder()
        for _ in range(2):
            b.add_experience({"signal": 1.0}, "navigate", 0.9)
        b.cluster()
        # a third distinct-action experience with < 2 members forms nothing
        b.add_experience({"x": 0}, "weird", 0.5)
        assert b.cluster() == []

    def test_hypothesize_from_supported_pattern(self):
        b = self._pattern_builder()
        for _ in range(2):
            b.add_experience({"signal": 1.0}, "navigate", 0.9)
        b.cluster()
        hyps = b.hypothesize()
        assert len(hyps) == 1
        hyp = hyps[0]
        assert isinstance(hyp, Hypothesis)
        assert hyp.action == "navigate"
        assert hyp.predicted_outcome == pytest.approx(0.9)
        assert hyp.confidence == pytest.approx(0.6 * 0.8)
        assert b.total_hypotheses == 1


class TestHypothesisTesting:
    def test_matching_context_and_action_survives(self):
        b = TheoryBuilder(min_experiences_for_pattern=2,
                          min_patterns_for_hypothesis=2)
        for _ in range(2):
            b.add_experience({"signal": 1.0}, "navigate", 0.9)
        b.cluster()
        b.hypothesize()
        results = b.test_hypotheses({"signal": 1.0}, "navigate", 0.9)
        assert results == [(b.get_active_hypotheses()[0].id, True)]

    def test_wrong_action_does_not_test(self):
        b = TheoryBuilder(min_experiences_for_pattern=2,
                          min_patterns_for_hypothesis=2)
        for _ in range(2):
            b.add_experience({"signal": 1.0}, "navigate", 0.9)
        b.cluster()
        b.hypothesize()
        assert b.test_hypotheses({"signal": 1.0}, "fly", 0.9) == []

    def test_context_numeric_tolerance(self):
        b = TheoryBuilder()
        # diff 1 is within 0.2 * |10| = 2.0
        assert b._context_matches({"temp": 10}, {"temp": 11})
        # diff 10 is outside 0.2 * |10|
        assert not b._context_matches({"temp": 10}, {"temp": 20})
        # non-numeric equality
        assert b._context_matches({"k": "v"}, {"k": "v"})
        assert not b._context_matches({"k": "v"}, {"k": "other"})
        # missing key fails
        assert not b._context_matches({"k": 1}, {})
        # empty signature matches anything
        assert b._context_matches({}, {"anything": 1})

    def test_hypothesis_falsified_after_many_confounding_tests(self):
        hyp = Hypothesis(
            id="h", description="d", context_signature={}, action="navigate",
            predicted_outcome=0.9, confidence=0.05, supporting_patterns=[],
        )
        survived = hyp.test(0.1)  # error 0.8 > 0.2
        assert survived is False
        assert hyp.falsified is True
        assert hyp.test_ratio == 0.0


class TestPromotion:
    def _promote_navigate_theory(self, builder, genealogy=None, hook=None):
        if genealogy is not None:
            builder.set_genealogy(genealogy)
        if hook is not None:
            builder.set_promotion_hook(hook)
        for _ in range(2):
            builder.add_experience({"signal": 1.0}, "navigate", 0.9,
                                   domain="gridworld")
        builder.cluster()
        builder.hypothesize()
        for _ in range(2):
            builder.test_hypotheses({"signal": 1.0}, "navigate", 0.9)
        return builder.promote()

    def test_promotes_well_tested_and_confident_hypothesis(self):
        b = TheoryBuilder(min_experiences_for_pattern=2,
                          min_patterns_for_hypothesis=2,
                          min_tests_for_theory=2,
                          theory_confidence_threshold=0.5)
        promoted = self._promote_navigate_theory(b)
        assert len(promoted) == 1
        theory = promoted[0]
        assert isinstance(theory, Theory)
        assert theory.action == "navigate"
        assert theory.domains == ["gridworld"]
        assert theory.confidence == pytest.approx(0.68)
        assert theory.tests_passed == 2
        assert theory.name.startswith("Theory: navigate")
        assert b.total_theories == 1

    def test_promotion_registers_genealogy_and_calls_hook(self):
        b = TheoryBuilder(min_experiences_for_pattern=2,
                          min_patterns_for_hypothesis=2,
                          min_tests_for_theory=2,
                          theory_confidence_threshold=0.5)
        genealogy = TheoryGenealogy()
        hook_calls = []
        promoted = self._promote_navigate_theory(b, genealogy=genealogy,
                                                 hook=lambda t, g: hook_calls.append((t, g)))
        assert len(hook_calls) == 1
        theory, gid = hook_calls[0]
        assert gid in genealogy._nodes
        assert genealogy._nodes[gid].name == theory.name
        assert theory._genealogy_id == gid

    def test_second_same_action_theory_parents_to_first(self):
        b = TheoryBuilder(min_experiences_for_pattern=2,
                          min_patterns_for_hypothesis=2,
                          min_tests_for_theory=2,
                          theory_confidence_threshold=0.5)
        first = self._promote_navigate_theory(b)[0]

        second_seed = Hypothesis(
            id="hyp_seeded", description="seed", context_signature={"b": 2},
            action="navigate", predicted_outcome=0.9, confidence=0.9,
            supporting_patterns=["pat_seed"], tests_passed=6,
        )
        b._hypotheses[second_seed.id] = second_seed
        promoted = b.promote()
        second = [t for t in promoted if t.hypothesis_id == second_seed.id][0]
        assert second.parent_theory_id == first.id

    def test_insufficient_tests_do_not_promote(self):
        b = TheoryBuilder(min_experiences_for_pattern=2,
                          min_patterns_for_hypothesis=2,
                          min_tests_for_theory=5,
                          theory_confidence_threshold=0.5)
        promoted = self._promote_navigate_theory(b)
        assert promoted == []


class TestQueriesAndGain:
    def test_get_active_excludes_falsified(self):
        b = TheoryBuilder()
        hyp = Hypothesis(
            id="h", description="d", context_signature={}, action="navigate",
            predicted_outcome=0.9, confidence=0.05, supporting_patterns=[],
        )
        hyp.falsified = True
        b._hypotheses["h"] = hyp
        assert b.get_active_hypotheses() == []
        assert b.get_active_hypotheses() == []

    def test_estimate_theory_gain_fertile_when_empty(self):
        b = TheoryBuilder()
        assert b.estimate_theory_gain({}, "action") == 0.8

    def test_estimate_theory_gain_bounded(self):
        b = TheoryBuilder(min_experiences_for_pattern=1,
                          min_patterns_for_hypothesis=1)
        for i in range(5):
            b.add_experience({"i": i}, f"a{i}", 0.9)
        b.cluster()
        gain = b.estimate_theory_gain({}, "anything")
        assert 0.0 <= gain <= 1.0

    def test_to_dict_shape(self):
        b = TheoryBuilder()
        d = b.to_dict()
        assert d["total_experiences"] == 0
        assert d["total_theories"] == 0
        assert d["theories"] == []
        assert "active_hypotheses" in d