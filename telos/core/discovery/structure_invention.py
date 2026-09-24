"""
StructureInvention (V9) — expand the hypothesis SPACE itself, under bounded search.

V8 chose among a KNOWN mechanism vocabulary (delay vs mediation). V9 must decide
whether an ADDITIONAL, previously-absent intermediate entity is *required* — not
assume mediation is available.

Bounded structural vocabulary (primitives): VARIABLE, RELATION, LAG, MEDIATOR,
COMMON_CAUSE, composed only as:  X->Y | X->Y(lag) | X->M->Y | X<-M->Y.

Hard rules
  * INVENTED != ASSERTED: an invented intermediate is HYPOTHESIZED (never
    OBSERVED); it is never given the hidden variable's name.
  * OCCAM: a complexity cost is attached; selection is explanatory-adequacy minus
    complexity (components kept separate). A latent is added only when the
    evidence REQUIRES it.
  * AMBIGUITY -> UNRESOLVED: equal-complexity candidates that both fit stay
    CANDIDATE; nothing is promoted.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

from telos.world.evidence import EvidenceInfo, EvidenceSource, ValidationStatus


class VariableStatus(str, Enum):
    """The status of a variable — an invented object is never OBSERVED."""
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    HYPOTHESIZED = "HYPOTHESIZED"
    LATENT = "LATENT"


# complexity: direct=1, one latent=2, two latents=3
_COMPLEXITY = {"direct": 1, "direct_delay": 1, "mediated": 2, "common_cause": 2}


@dataclass
class StructuralHypothesis:
    """A candidate structure (CANDIDATE until evidence supports it)."""
    family: str
    statement: str
    structure: str
    introduces_latent: bool
    variable_status: VariableStatus
    required_test: str
    complexity: int = 1
    provenance: str = "invented"
    evidence: EvidenceInfo = field(default_factory=lambda: EvidenceInfo(
        source=EvidenceSource.DERIVED_INFERENCE,
        validation_status=ValidationStatus.UNVALIDATED))

    def to_dict(self) -> Dict:
        return {"family": self.family, "statement": self.statement,
                "structure": self.structure, "introduces_latent": self.introduces_latent,
                "variable_status": self.variable_status.value,
                "required_test": self.required_test, "complexity": self.complexity,
                "provenance": self.provenance,
                "status": self.evidence.validation_status.value}


def _xcorr_lag(x, y, max_lag=4) -> Tuple[int, float]:
    best_k, best_r = 0, 0.0
    for k in range(1, max_lag + 1):
        a, b = x[:-k], y[k:]
        if len(a) < 10 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
            continue
        r = float(np.corrcoef(a, b)[0, 1])
        if r > best_r:
            best_k, best_r = k, r
    return best_k, best_r


@dataclass
class InventionResult:
    candidates: List[StructuralHypothesis]
    preferred: Optional[StructuralHypothesis]
    adequacy: float
    complexity: int
    unresolved: bool


class StructureInventor:
    """Bounded structure invention from observations (+ optional intervention).

    Args:
        corr_threshold: contemporaneous |corr| that counts as an association.
        lag_threshold: lagged |corr| that counts as a lagged signal.
    """

    def __init__(self, corr_threshold: float = 0.3, lag_threshold: float = 0.4):
        self.corr_threshold = float(corr_threshold)
        self.lag_threshold = float(lag_threshold)

    def _mk(self, family: str, statement: str, structure: str, latent: bool,
            test: str) -> StructuralHypothesis:
        return StructuralHypothesis(
            family=family, statement=statement, structure=structure,
            introduces_latent=latent,
            variable_status=VariableStatus.HYPOTHESIZED if latent else VariableStatus.OBSERVED,
            required_test=test, complexity=_COMPLEXITY[family])

    def infer(self, x_name: str, y_name: str, x: np.ndarray, y: np.ndarray, *,
              intermediate: Optional[bool] = None,
              intervention_changes_y: Optional[bool] = None) -> InventionResult:
        """Infer the structures consistent with the observations.

        Args:
            x_name/y_name: observed variable names.
            x/y: series.
            intermediate: whether an intermediate signal was observed under
                intervention (None = not tested).
            intervention_changes_y: do(x) changes y? (None = not tested).

        Returns:
            InventionResult (candidates + preferred or UNRESOLVED).
        """
        corr = abs(float(np.corrcoef(x, y)[0, 1])) if np.std(x) > 1e-9 and np.std(y) > 1e-9 else 0.0
        k, r = _xcorr_lag(x, y)
        lagged = (r >= self.lag_threshold and corr < self.corr_threshold)

        cands: List[StructuralHypothesis] = []
        if corr < self.corr_threshold and not lagged:
            return InventionResult([], None, 0.0, 0, False)   # no signal (noise)

        if lagged:
            # a delayed association: direct-delay fits with fewer assumptions;
            # a latent mediator is introduced ONLY if the evidence requires it.
            direct = self._mk("direct_delay",
                              f"{x_name} delays into {y_name}",
                              f"{x_name} --lag {k}--> {y_name}", False,
                              f"intervene on {x_name}; {y_name} responds after {k} steps with no intermediate")
            med = self._mk("mediated",
                           f"{x_name} acts on {y_name} via an unobserved intermediate",
                           f"{x_name} -> H1 -> {y_name}", True,
                           f"intervene on {x_name}; look for an intermediate that precedes {y_name}")
            if intermediate is True:
                cands = [med]                      # evidence REQUIRES the extra entity
            else:
                # both fit; Occam prefers the simpler (no unnecessary latent)
                cands = [direct, med]
        else:
            # synchronous association: direction/latent structure unknown without
            # an intervention.
            if intervention_changes_y is True:
                cands = [self._mk("direct", f"{x_name} causes {y_name}",
                                  f"{x_name} -> {y_name}", False,
                                  f"already discriminating: do({x_name}) moves {y_name}")]
            elif intervention_changes_y is False:
                cands = [self._mk("common_cause",
                                  f"{x_name} and {y_name} share an unobserved common cause",
                                  f"{x_name} <- H1 -> {y_name}", True,
                                  f"do({x_name}) does NOT move {y_name}")]
            else:
                # ambiguous: direction (and hence latent structure) unresolved
                cands = [self._mk("direct", f"{x_name} causes {y_name}",
                                  f"{x_name} -> {y_name}", False, f"intervene to fix direction"),
                         self._mk("direct", f"{y_name} causes {x_name}",
                                  f"{y_name} -> {x_name}", False, f"intervene to fix direction")]

        adequacy = min(1.0, max(corr, r))
        return self._prefer(cands, adequacy)

    def _prefer(self, cands: List[StructuralHypothesis], adequacy: float) -> InventionResult:
        if not cands:
            return InventionResult([], None, adequacy, 0, False)
        min_c = min(c.complexity for c in cands)
        simplest = [c for c in cands if c.complexity == min_c]
        if len(simplest) == 1:
            return InventionResult(cands, simplest[0], adequacy, min_c, False)
        # equal-complexity, both fit => UNRESOLVED (no promotion)
        return InventionResult(cands, None, adequacy, min_c, True)
