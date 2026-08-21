"""Tests for the first-class Experiment record and run_experiment lifecycle
(hypothesis -> intervention -> predicted -> observed -> confirm/falsify ->
EXPERIMENT-stamped evidence)."""

from telos.core.reasoning.theory.experiment import (
    Experiment,
    ExperimentOutcome,
    run_experiment,
)
from telos.core.reasoning.theory.dataclasses import Hypothesis
from telos.world.evidence import EvidenceSource, ValidationStatus


def _hypothesis(predicted: float = 1.0, confidence: float = 0.5) -> Hypothesis:
    return Hypothesis(
        id="h_exp",
        description="when go then outcome=1.0",
        context_signature={"domain": "mock"},
        action="go",
        predicted_outcome=predicted,
        confidence=confidence,
        supporting_patterns=["p1"],
    )


class TestExperimentOutcome:
    def test_enum_values(self):
        assert ExperimentOutcome.CONFIRMED.value == "CONFIRMED"
        assert ExperimentOutcome.FALSIFIED.value == "FALSIFIED"
        assert ExperimentOutcome.INCONCLUSIVE.value == "INCONCLUSIVE"


class TestExperimentDefaults:
    def test_default_experiment_is_inconclusive_with_experiment_evidence(self):
        exp = Experiment(hypothesis_id="h1", intervention="go",
                         predicted=1.0, observed=0.5)
        assert exp.outcome == ExperimentOutcome.INCONCLUSIVE
        assert exp.hypothesis_survived is False
        assert exp.reality_gap == 0.0
        assert exp.tolerance == 0.2
        assert exp.evidence.source == EvidenceSource.EXPERIMENT
        assert exp.evidence.validation_status == ValidationStatus.OBSERVED
        assert exp.timestamp > 0


class TestRunExperimentConfirmed:
    def test_confirmed_survives_and_raises_confidence(self):
        h = _hypothesis(predicted=1.0, confidence=0.5)
        exp = run_experiment(h, predicted=1.0, observed=1.05, tolerance=0.2)
        assert exp.outcome == ExperimentOutcome.CONFIRMED
        assert exp.hypothesis_survived is True
        assert abs(exp.reality_gap - 0.05) < 1e-9
        assert h.tests_passed == 1
        assert h.confidence == 0.6
        assert h.falsified is False
        assert exp.evidence.validation_status == ValidationStatus.VALIDATED
        assert exp.evidence.source == EvidenceSource.EXPERIMENT
        assert exp.evidence.confidence == 0.6


class TestRunExperimentFalsified:
    def test_falsified_when_observed_outside_tolerance(self):
        h = _hypothesis(predicted=1.0, confidence=0.5)
        exp = run_experiment(h, predicted=1.0, observed=2.0, tolerance=0.2)
        assert exp.outcome == ExperimentOutcome.FALSIFIED
        assert exp.hypothesis_survived is False
        assert abs(exp.reality_gap - 1.0) < 1e-9
        assert h.tests_failed == 1
        assert h.confidence == 0.3
        assert exp.evidence.validation_status == ValidationStatus.FALSIFIED

    def test_repeated_failures_falsify_the_hypothesis(self):
        h = _hypothesis(predicted=1.0, confidence=0.15)
        run_experiment(h, predicted=1.0, observed=3.0, tolerance=0.2)
        assert h.falsified is True
        assert h.confidence == 0.0


class TestRunExperimentInconclusive:
    def test_inconclusive_when_survives_but_prediction_missed(self):
        h = _hypothesis(predicted=1.0, confidence=0.5)
        exp = run_experiment(h, predicted=2.0, observed=0.9, tolerance=0.2)
        assert exp.outcome == ExperimentOutcome.INCONCLUSIVE
        assert exp.hypothesis_survived is True
        assert abs(exp.reality_gap - 1.1) < 1e-9
        assert h.tests_passed == 1
        assert exp.evidence.validation_status == ValidationStatus.OBSERVED


class TestExperimentRecord:
    def test_counts_intervention_and_evidence(self):
        exp = Experiment(hypothesis_id="h1", intervention="grab",
                         predicted=1.0, observed=0.0,
                         outcome=ExperimentOutcome.FALSIFIED,
                         hypothesis_survived=False, reality_gap=1.0)
        assert exp.hypothesis_id == "h1"
        assert exp.intervention == "grab"
        assert exp.evidence.source == EvidenceSource.EXPERIMENT

    def test_to_dict_contract(self):
        h = _hypothesis(predicted=1.0, confidence=0.5)
        exp = run_experiment(h, predicted=1.0, observed=0.12345, tolerance=0.2)
        d = exp.to_dict()
        assert d["hypothesis_id"] == "h_exp"
        assert d["intervention"] == "go"
        assert d["predicted"] == 1.0
        assert d["observed"] == 0.12345
        assert d["reality_gap"] == round(abs(1.0 - 0.12345), 4)
        assert d["outcome"] == ExperimentOutcome.FALSIFIED.value
        assert d["hypothesis_survived"] is False
        assert d["tolerance"] == 0.2
        assert isinstance(d["evidence"], dict)
        assert d["evidence"]["source"] == "EXPERIMENT"