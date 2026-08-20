"""
TELOS v6 — Phase 10: first-class Experiment reusing TheoryBuilder falsification.

The existing TheoryBuilder has hypothesis/falsification machinery
(Hypothesis.test(): predicted vs actual within tolerance, confidence up/down,
falsification at low confidence). We do NOT build a parallel scientific engine.

This adds a thin, first-class `Experiment` record that ties:
    hypothesis -> intervention -> predicted -> observed -> reality gap
                -> confirm/falsify -> evidence (source=EXPERIMENT)

so an experiment outcome can flow back into the evidence/Reality-Gap /
capability-authorization loop (Learning changes authority).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Dict
import time

from telos.world.evidence import EvidenceInfo, EvidenceSource, ValidationStatus
from telos.core.reasoning.theory.dataclasses import Hypothesis


class ExperimentOutcome(str, Enum):
    CONFIRMED = "CONFIRMED"
    FALSIFIED = "FALSIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class Experiment:
    """A single falsification test of a hypothesis.

    hypothesis_id   : which Hypothesis was tested.
    intervention    : what was done / the action taken.
    predicted       : the observable the hypothesis predicted.
    observed        : what actually happened.
    reality_gap     : |predicted - observed| (Reality-Gap measure).
    outcome         : CONFIRMED / FALSIFIED / INCONCLUSIVE.
    hypothesis_survived : bool (did it survive the test, per Hypothesis.test).
    evidence        : EvidenceInfo stamped source=EXPERIMENT.
    timestamp       : when.
    """
    hypothesis_id: str
    intervention: str
    predicted: float
    observed: float
    reality_gap: float = 0.0
    outcome: ExperimentOutcome = ExperimentOutcome.INCONCLUSIVE
    hypothesis_survived: bool = False
    evidence: EvidenceInfo = field(
        default_factory=lambda: EvidenceInfo(
            source=EvidenceSource.EXPERIMENT,
            validation_status=ValidationStatus.OBSERVED,
        )
    )
    tolerance: float = 0.2
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "intervention": self.intervention,
            "predicted": self.predicted,
            "observed": self.observed,
            "reality_gap": round(self.reality_gap, 4),
            "outcome": self.outcome.value,
            "hypothesis_survived": self.hypothesis_survived,
            "evidence": self.evidence.to_dict(),
            "tolerance": self.tolerance,
        }


def run_experiment(hypothesis: Hypothesis, predicted: float,
                   observed: float, tolerance: float = 0.2) -> Experiment:
    """Run one experiment against a Hypothesis, reusing its falsification logic.

    This mutates the Hypothesis (tests_passed/failed, confidence, falsified)
    exactly as `Hypothesis.test()` does, and packages the result as a
    first-class Experiment with Reality-Gap + EXPERIMENT evidence.

    Args:
        hypothesis: the Hypothesis under test (mutated in place).
        predicted:  the prediction the hypothesis makes for THIS experiment
                    (usually == hypothesis.predicted_outcome).
        observed:   the actual observed outcome.
        tolerance:  acceptance window for survival.

    Returns:
        The completed Experiment.
    """
    survived = hypothesis.test(observed, tolerance=tolerance)
    reality_gap = abs(float(predicted) - float(observed))
    if not survived:
        outcome = ExperimentOutcome.FALSIFIED
    elif reality_gap <= tolerance:
        outcome = ExperimentOutcome.CONFIRMED
    else:
        outcome = ExperimentOutcome.INCONCLUSIVE
    evidence = EvidenceInfo(
        source=EvidenceSource.EXPERIMENT,
        validation_status=(
            ValidationStatus.VALIDATED if outcome == ExperimentOutcome.CONFIRMED
            else ValidationStatus.FALSIFIED if outcome == ExperimentOutcome.FALSIFIED
            else ValidationStatus.OBSERVED
        ),
        confidence=hypothesis.confidence,
    )
    return Experiment(
        hypothesis_id=hypothesis.id,
        intervention=hypothesis.action,
        predicted=float(predicted),
        observed=float(observed),
        reality_gap=reality_gap,
        outcome=outcome,
        hypothesis_survived=survived,
        evidence=evidence,
        tolerance=tolerance,
    )
