"""
CausalProbe — assumption discovery V2: epistemic honesty + intervention-based
causal direction, layered on the existing discovery architecture.

It EXTENDS `AssumptionDiscoverer` (no new subsystem): same evidence envelope
(EvidenceInfo/ValidationStatus), same RealityGapTracker, same KnowledgeGraph /
TheoryBuilder integration (wired by the runner).

The core epistemic ladder (Phase 2) — never force causation:
    OBSERVED_CORRELATION        correlated, but intervening does not move it
    CAUSAL_HYPOTHESIS           a causal direction is proposed, not yet tested
    SUPPORTED_CAUSAL_RELATION   intervening on the cause moves the effect
    FALSIFIED_RELATION          a proposed causal edge was refuted by experiment
    UNRESOLVED_RELATION         insufficient evidence / direction unresolvable

The distinguishing test is interventional (do-calculus): a relation is causal
ONLY if `do(cause)` moves the effect; a merely-correlated pair (confounder,
latent) is downgraded to OBSERVED_CORRELATION, not promoted to causation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

import numpy as np

from telos.world.evidence import EvidenceInfo, EvidenceSource, ValidationStatus
from telos.world.epistemic import RealityGapTracker


class CausalStatus(str, Enum):
    """The epistemic ladder — correlation is not causation."""
    OBSERVED_CORRELATION = "OBSERVED_CORRELATION"
    CAUSAL_HYPOTHESIS = "CAUSAL_HYPOTHESIS"
    SUPPORTED_CAUSAL_RELATION = "SUPPORTED_CAUSAL_RELATION"
    FALSIFIED_RELATION = "FALSIFIED_RELATION"
    UNRESOLVED_RELATION = "UNRESOLVED_RELATION"


class SamplableWorld(Protocol):
    """A world that can be sampled observationally or under an intervention."""
    variables: List[str]

    def sample(self, n: int, do: Optional[Dict[str, float]] = None,
               rng: Optional[np.random.RandomState] = None) -> Dict[str, np.ndarray]:
        ...


@dataclass
class DiscoveredRelation:
    """A candidate causal relation with its epistemic status + audit trace.

    Args:
        cause/effect: the ordered pair.
        status: a CausalStatus (the honesty ladder).
        observed_correlation: |corr| under observation.
        intervention_effect: |E[effect|do(cause=+1)] - E[effect|do(cause=-1)]|.
        direction_confidence: belief in the stated direction [0,1].
        uncertainty: 1 - confidence.
        falsifier: the experiment that would refute the causal claim.
        evidence: the provenance / validation envelope.
        trace: per-stage booleans (Phase 8 audit).
    """
    cause: str
    effect: str
    status: CausalStatus
    observed_correlation: float
    intervention_effect: float
    direction_confidence: float
    uncertainty: float
    falsifier: str
    statement: str = ""
    evidence: EvidenceInfo = field(default_factory=EvidenceInfo)
    trace: Dict[str, bool] = field(default_factory=dict)

    @property
    def is_causal(self) -> bool:
        """True only for a SUPPORTED causal relation."""
        return self.status == CausalStatus.SUPPORTED_CAUSAL_RELATION

    def info_value(self, decision_sensitivity: float, test_cost: float = 1.0) -> float:
        """Value of testing this relation — DECISION-RELEVANT, not mere entropy.

        value = decision_sensitivity × uncertainty × falsifiability ÷ cost

        Args:
            decision_sensitivity: would a different action be chosen if this
                relation were true vs false? (0..1) — from the counterfactual hook.
            test_cost: relative intervention cost.

        Returns:
            The information value.
        """
        return (decision_sensitivity * self.uncertainty * 1.0 / max(test_cost, 1e-6))

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict.

        Returns:
            The relation as a JSON-serializable dict.
        """
        return {
            "cause": self.cause, "effect": self.effect, "status": self.status.value,
            "observed_correlation": round(self.observed_correlation, 3),
            "intervention_effect": round(self.intervention_effect, 3),
            "direction_confidence": round(self.direction_confidence, 3),
            "uncertainty": round(self.uncertainty, 3),
            "statement": self.statement, "falsifier": self.falsifier,
            "trace": self.trace,
        }


def _corr(x: np.ndarray, y: np.ndarray) -> float:
    if np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


class CausalProbe:
    """Discovers causal structure by intervening (do-calculus), not just observing.

    Args:
        n: samples per query.
        tau_effect: minimum interventional mean-shift to call a relation causal.
        tau_corr: minimum |corr| to call a pair correlated.
        seed: RNG seed.
    """

    def __init__(self, n: int = 400, tau_effect: float = 0.15,
                 tau_corr: float = 0.15, seed: int = 0):
        self.n = n
        self.tau_effect = tau_effect
        self.tau_corr = tau_corr
        self.seed = seed
        self.reality_gap = RealityGapTracker()
        self._rng = np.random.RandomState(seed)

    # Intervention levels tried (max mean-shift wins) so NON-LINEAR effects
    # (e.g. Y=X^2) are detected where a single symmetric pair would cancel.
    _LEVELS = [(-1.0, 0.0), (0.0, 1.0), (-1.0, 1.0)]

    def _do_effect_stat(self, world: SamplableWorld, cause: str,
                        effect: str) -> tuple:
        """Interventional mean shift AND its standard error (max over do-levels).

        Args:
            world: the samplable world.
            cause: the intervened variable.
            effect: the measured variable.

        Returns:
            (effect, se) for the strongest do-level pair.
        """
        best_eff, best_se = 0.0, 1.0
        for k, (lo, hi) in enumerate(self._LEVELS):
            hi_s = world.sample(self.n, do={cause: hi},
                                rng=np.random.RandomState(self.seed + 10 * k + 1))
            lo_s = world.sample(self.n, do={cause: lo},
                                rng=np.random.RandomState(self.seed + 10 * k + 2))
            eff = abs(float(np.mean(hi_s[effect]) - np.mean(lo_s[effect])))
            se = float(np.sqrt(np.var(hi_s[effect]) / self.n + np.var(lo_s[effect]) / self.n))
            if eff - 3 * se > best_eff - 3 * best_se:
                best_eff, best_se = eff, max(se, 1e-9)
        return best_eff, max(best_se, 1e-9)

    def _do_effect(self, world: SamplableWorld, cause: str, effect: str) -> float:
        """Interventional effect magnitude (see `_do_effect_stat`)."""
        return self._do_effect_stat(world, cause, effect)[0]

    def _is_significant(self, eff: float, se: float) -> bool:
        """A causal effect must beat both a floor AND 3× its standard error."""
        return eff > self.tau_effect and eff > 3.0 * se

    def classify(self, world: SamplableWorld, cause: str, effect: str) -> DiscoveredRelation:
        """Classify a pair into the epistemic ladder via observation + intervention.

        Args:
            world: the samplable world.
            cause: candidate cause.
            effect: candidate effect.

        Returns:
            A DiscoveredRelation with status, confidence, falsifier, and trace.
        """
        obs = world.sample(self.n, rng=np.random.RandomState(self.seed))
        corr = _corr(obs[cause], obs[effect])
        eff_ab, se_ab = self._do_effect_stat(world, cause, effect)
        eff_ba, se_ba = self._do_effect_stat(world, effect, cause)
        sig_ab = self._is_significant(eff_ab, se_ab)
        sig_ba = self._is_significant(eff_ba, se_ba)

        # Resolve the TRUE direction: intervening on the cause must move the
        # effect. If only do(effect) moves cause, the causal edge is REVERSED.
        out_c, out_e = cause, effect
        if sig_ab and not sig_ba:
            status = CausalStatus.SUPPORTED_CAUSAL_RELATION
            direction_conf = min(1.0, eff_ab); shift = eff_ab
        elif sig_ba and not sig_ab:
            status = CausalStatus.SUPPORTED_CAUSAL_RELATION
            out_c, out_e = effect, cause          # reversed direction
            direction_conf = min(1.0, eff_ba); shift = eff_ba
        elif sig_ab and sig_ba:
            status = CausalStatus.UNRESOLVED_RELATION      # mutual/feedback
            direction_conf = 0.0; shift = 0.0
        elif abs(corr) > self.tau_corr:
            status = CausalStatus.OBSERVED_CORRELATION     # confounded / latent
            direction_conf = 0.0; shift = 0.0
        else:
            status = CausalStatus.UNRESOLVED_RELATION      # no evidence
            direction_conf = 0.0; shift = 0.0

        self.reality_gap.record("causal_probe", np.array([shift]), np.array([shift]))

        rel = DiscoveredRelation(
            cause=out_c, effect=out_e, status=status,
            observed_correlation=abs(corr), intervention_effect=max(eff_ab, eff_ba),
            direction_confidence=direction_conf, uncertainty=1.0 - direction_conf,
            statement=(f"intervening on {out_c} moves {out_e}"
                       if status == CausalStatus.SUPPORTED_CAUSAL_RELATION
                       else f"{cause} and {effect} are {'correlated' if abs(corr) > self.tau_corr else 'unrelated'} "
                            f"but not causally resolved"),
            falsifier=(f"refute by setting {out_c} to two levels and observing "
                       f"{out_e} unchanged (do-calculus)."),
            evidence=EvidenceInfo(
                source=EvidenceSource.MEASUREMENT,
                validation_status=(ValidationStatus.MEASURED
                                   if status == CausalStatus.SUPPORTED_CAUSAL_RELATION
                                   else ValidationStatus.OBSERVED),
                confidence=direction_conf),
            trace={"observed": True, "hypothesized": status != CausalStatus.UNRESOLVED_RELATION,
                   "experiment": True, "evidence": True, "reality_gap": True,
                   "theory": False, "knowledge_graph": False, "decision": False},
        )
        return rel

    def classify_all(self, world: SamplableWorld,
                     pairs: Optional[List[tuple]] = None) -> List[DiscoveredRelation]:
        """Classify all ordered variable pairs (or a given list).

        Args:
            world: the world.
            pairs: optional list of (cause, effect) tuples.

        Returns:
            The relations.
        """
        if pairs is None:
            vs = world.variables
            pairs = [(a, b) for a in vs for b in vs if a != b]
        return [self.classify(world, a, b) for a, b in pairs]

    # ── Counterfactual decision relevance — MOVED (V3) ───────────────────────
    #
    # The local `decision_sensitivity` calculation that lived here has been
    # REMOVED. Counterfactual decision sensitivity now has exactly ONE
    # authoritative implementation:
    #     telos.core.discovery.experiment_selection.CanonicalExperimentSelector
    # which delegates to the canonical
    #     CounterfactualEngine.compute_value_of_information().
    # CausalProbe is now purely a discovery/classification surface.
