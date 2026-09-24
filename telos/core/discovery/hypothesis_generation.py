"""
HypothesisGenerator (V8) — turn UNEXPLAINED RESIDUALS into candidate structure.

V3–V7 reason over an EXISTING hypothesis space. V8 crosses the boundary: when no
current model explains an observation, GENERATE a candidate explanation.

Consumes existing artifacts (observations, existing predictions, EvidenceInfo,
RealityGapTracker semantics) — it is not a second reasoning stack.

Hard rules
  * GENERATED != BELIEVED: a generated hypothesis enters as CANDIDATE with
    validation status UNVALIDATED — never SUPPORTED.
  * NOISE IS NOT A PUZZLE: a candidate is produced only when a residual is
    significant, repeatable (consistent across splits), and decision-relevant.
  * NO LEAKAGE: the generator sees only observations and observed variable names;
    it never names a hidden/latent variable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from telos.world.evidence import EvidenceInfo, EvidenceSource, ValidationStatus


@dataclass
class HypothesisCandidate:
    """A generated (NOT believed) candidate explanation.

    Args:
        statement: human-readable candidate.
        proposed_variables: observed variables involved.
        proposed_relations: candidate relationships.
        mechanism: the proposed mechanism kind (e.g. "delay", "mediation").
        explains: what residual/observation it explains.
        contradicts: what it would contradict.
        required_test: the experiment that would discriminate/test it.
        provenance: "generated" (never a ground-truth label).
        evidence: UNVALIDATED provenance envelope (CANDIDATE, not SUPPORTED).
    """
    statement: str
    proposed_variables: List[str]
    proposed_relations: List[str]
    mechanism: str
    explains: str
    contradicts: str
    required_test: str
    provenance: str = "generated"
    predicted_lag: int = 1
    predicts_intermediate: bool = False
    evidence: EvidenceInfo = field(default_factory=lambda: EvidenceInfo(
        source=EvidenceSource.DERIVED_INFERENCE,
        validation_status=ValidationStatus.UNVALIDATED))

    def to_dict(self) -> Dict:
        return {"statement": self.statement, "proposed_variables": self.proposed_variables,
                "proposed_relations": self.proposed_relations, "mechanism": self.mechanism,
                "explains": self.explains, "contradicts": self.contradicts,
                "required_test": self.required_test, "provenance": self.provenance,
                "predicted_lag": self.predicted_lag,
                "predicts_intermediate": self.predicts_intermediate,
                "status": self.evidence.validation_status.value}


def _xcorr_lag(x: np.ndarray, y: np.ndarray, max_lag: int = 4) -> Tuple[int, float]:
    """Best positive lag k maximising corr(x[:-k], y[k:]) (Y responds AFTER X)."""
    best_k, best_r = 0, 0.0
    for k in range(1, max_lag + 1):
        a, b = x[:-k], y[k:]
        if len(a) < 10 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
            continue
        r = float(np.corrcoef(a, b)[0, 1])
        if r > best_r:
            best_k, best_r = k, r
    return best_k, best_r


class HypothesisGenerator:
    """Generates candidate explanations from unexplained residuals.

    Args:
        min_lag_corr: minimum lagged correlation to count as a residual signal.
        require_repeatable: require the lag/ sign to hold in both halves.
        decision_relevant: only generate when the pair matters to a decision.
    """

    def __init__(self, min_lag_corr: float = 0.4, require_repeatable: bool = True):
        self.min_lag_corr = float(min_lag_corr)
        self.require_repeatable = bool(require_repeatable)

    def residual(self, x: np.ndarray, y: np.ndarray) -> Optional[int]:
        """Return the significant, repeatable lag (1..k) or None (noise).

        Args:
            x: cause series.
            y: effect series.

        Returns:
            The lag, or None when the residual is not a real puzzle.
        """
        k, r = _xcorr_lag(x, y)
        if r < self.min_lag_corr or k == 0:
            return None
        if self.require_repeatable:
            half = len(x) // 2
            k1, r1 = _xcorr_lag(x[:half], y[:half])
            k2, r2 = _xcorr_lag(x[half:], y[half:])
            if not (k1 == k2 == k and r1 >= self.min_lag_corr and r2 >= self.min_lag_corr):
                return None
        return k

    def generate(self, x_name: str, y_name: str, x: np.ndarray, y: np.ndarray,
                 decision_relevant: bool = True) -> List[HypothesisCandidate]:
        """Generate candidate explanations for a lagged residual (or none).

        Two competing candidates are produced, each with a DIFFERENT
        discriminating test: a direct delayed effect vs an unobserved mediator.

        Args:
            x_name: cause variable name (observed).
            y_name: effect variable name (observed).
            x: cause series.
            y: effect series.
            decision_relevant: whether the pair bears on a decision.

        Returns:
            A list of candidates (empty when no real residual).
        """
        if not decision_relevant:
            return []
        k = self.residual(x, y)
        if k is None:
            return []
        explains = (f"{x_name} changes and {y_name} follows ~{k} step(s) later, "
                    f"which the immediate models do not predict")
        return [
            HypothesisCandidate(
                statement=f"{x_name} affects {y_name} directly with a {k}-step delay",
                proposed_variables=[x_name, y_name],
                proposed_relations=[f"{x_name} -> {y_name} (lag {k})"],
                mechanism="delayed_direct",
                explains=explains,
                contradicts=f"an immediate (lag-0) {x_name}->{y_name} model",
                required_test=(f"intervene on {x_name}; if {y_name} responds ONLY after "
                               f"{k} steps with no intermediate signal, delay wins"),
                predicted_lag=k, predicts_intermediate=False),
            HypothesisCandidate(
                statement=f"{x_name} acts on {y_name} through an unobserved mediator",
                proposed_variables=[x_name, y_name],
                proposed_relations=[f"{x_name} -> ? -> {y_name}"],
                mechanism="mediated",
                explains=explains,
                contradicts=f"a single-step {x_name}->{y_name} path",
                required_test=(f"intervene on {x_name} and look for an intermediate "
                               f"response that precedes {y_name}"),
                predicted_lag=k, predicts_intermediate=True),
        ]

    def discriminate(self, candidates: List[HypothesisCandidate],
                     observed_intermediate: bool) -> Dict[str, object]:
        """Run the discriminating experiment: is an intermediate signal present?

        Args:
            candidates: the generated candidates.
            observed_intermediate: whether an intermediate response was observed.

        Returns:
            {"survivor": candidate|None, "falsified": [statements], "resolved": bool}.
        """
        survivors = [c for c in candidates if c.predicts_intermediate == observed_intermediate]
        falsified = [c.statement for c in candidates
                     if c.predicts_intermediate != observed_intermediate]
        survivor = survivors[0] if len(survivors) == 1 else None
        if survivor is not None:
            survivor.evidence.validation_status = ValidationStatus.MEASURED
        return {"survivor": survivor.to_dict() if survivor else None,
                "falsified": falsified, "resolved": survivor is not None}
