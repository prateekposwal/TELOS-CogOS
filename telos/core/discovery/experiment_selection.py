"""
Canonical experiment selection — decision value from the CounterfactualEngine.

ONE authoritative mechanism: the decision sensitivity of a candidate experiment
is the spread of achievable outcomes across the hypothesis's truth states, and
the value is computed with the EXISTING
`CounterfactualEngine.compute_value_of_information()` — not a parallel
calculation.

Candidate assumption
  → possible truth states (a simulator per hypothesis)
  → CounterfactualEngine.generate_options → compute_value_of_information
  → decision sensitivity
  → × uncertainty ÷ experiment cost
  → experiment value → selection

Epistemic safety (Phase 5): a hypothesis the engine CANNOT evaluate (no sim, no
world, no transition) is reported as UNKNOWN — never silently zero-valued.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Any, Dict, List, Optional

import numpy as np


def _t_critical(alpha: float, df: float) -> float:
    """Two-sided Student-t critical value: P(|T_df| > t) = alpha.

    Uses scipy when available (core does NOT depend on it); otherwise a stdlib
    Cornish-Fisher expansion around the normal quantile.  At large df this -> the
    normal critical value, so existing behavior at adequate sample sizes holds.
    """
    try:                                        # optional, not a core dependency
        from scipy import stats
        return float(stats.t.ppf(1.0 - alpha / 2.0, df))
    except Exception:
        pass

    def _norm_ppf(p: float) -> float:
        return NormalDist().inv_cdf(p)
    z = _norm_ppf(1.0 - alpha / 2.0)
    z2 = z * z
    return (z
            + (z ** 3 + z) / (4.0 * df)
            + (5.0 * z ** 5 + 16.0 * z ** 3 + 3.0 * z) / (96.0 * df ** 2)
            + (3.0 * z ** 7 + 19.0 * z ** 5 + 17.0 * z ** 3 - 15.0 * z) / (384.0 * df ** 3))

from telos.core.simulation import CounterfactualEngine
from telos.core.contracts.domain_model import DomainSimulator


@dataclass
class Hypothesis:
    """One truth state of a candidate assumption.

    Args:
        id: stable id.
        simulator: a DomainSimulator representing this truth state.
        uncertainty: current uncertainty in this hypothesis [0,1].
        test_cost: relative cost of the experiment that would test it.
    """
    id: str
    simulator: DomainSimulator
    uncertainty: float = 0.5
    test_cost: float = 1.0
    # V14: an independent PREDICTIVE model per structural hypothesis.  `predictor`
    # maps an experiment id -> predicted outcome (a scalar).  It must be derived
    # from the hypothesis' own structure, NEVER from the discovered structure
    # (that would be circular).  `structure` is an optional human-readable label.
    structure: Optional[str] = None
    predictor: Optional[Any] = None
    # Optional uncertainty model: `predictor_se(experiment) -> standard error` of
    # the prediction.  When every live hypothesis provides one, structural
    # discrimination becomes a SIGNIFICANCE TEST (spread / pooled SE) instead of a
    # raw magnitude (see CanonicalExperimentSelector.z_threshold).
    predictor_se: Optional[Any] = None
    # Optional degrees of freedom of the SE (`predictor_df(experiment) -> df`).
    # When provided, the significance gate uses a finite-df (Welch/Satterthwaite)
    # t critical value instead of the normal z_threshold.
    predictor_df: Optional[Any] = None
    # V17 — distributional evidence provenance.  A statistic carries the FAMILY
    # it belongs to and its DISTRIBUTIONAL ORDER (not moment-specific names):
    # two hypotheses are only comparable on a COMMON feature family.  Different
    # families (e.g. a 2nd-order vs a higher-order statistic) must never be
    # compared as if they were the same evidence.
    feature_family: Optional[str] = None
    distributional_order: Optional[int] = None


@dataclass
class ExperimentOption:
    """A scored experiment.

    Args:
        hypothesis_id: the hypothesis this experiment would test.
        status: "VALUED" or "UNKNOWN" (engine could not evaluate it).
        sensitivity: canonical decision sensitivity (None when UNKNOWN).
        uncertainty: the hypothesis uncertainty.
        cost: the test cost.
        value: sensitivity × uncertainty ÷ cost (None when UNKNOWN).
    """
    hypothesis_id: str
    status: str
    sensitivity: Optional[float]
    uncertainty: float
    cost: float
    value: Optional[float]

    def to_dict(self) -> dict:
        return {"hypothesis_id": self.hypothesis_id, "status": self.status,
                "sensitivity": None if self.sensitivity is None else round(self.sensitivity, 4),
                "uncertainty": round(self.uncertainty, 4), "cost": round(self.cost, 4),
                "value": None if self.value is None else round(self.value, 4)}


@dataclass
class StructuralExperimentOption:
    """V14: an experiment scored for STRUCTURAL discrimination, separately from
    canonical decision VoI.

    Args:
        experiment: experiment id.
        decision_voi: canonical decision VoI (unchanged V3 semantics), shared
            across experiments (it values the hypothesis, not the experiment).
        structural_discrimination: spread of predicted outcomes across the live
            hypotheses (0 == all hypotheses predict the same result).  None when
            unsupported (a hypothesis has no predictor).
        predictions: {hypothesis_id: predicted outcome}.
        supported: whether every live hypothesis could predict this experiment.
    """
    experiment: str
    decision_voi: Optional[float]
    structural_discrimination: Optional[float]
    predictions: Dict[str, float] = field(default_factory=dict)
    supported: bool = False

    def to_dict(self) -> dict:
        return {"experiment": self.experiment,
                "decision_voi": self.decision_voi,
                "structural_discrimination": self.structural_discrimination,
                "predictions": {k: (round(v, 4) if isinstance(v, float)
                                    else [round(x, 4) for x in v] if isinstance(v, (list, tuple))
                                    else v)
                                for k, v in self.predictions.items()},
                "supported": self.supported}


class CanonicalExperimentSelector:
    """Selects experiments by CANONICAL counterfactual decision value.

    Args:
        engine: the canonical CounterfactualEngine (its simulator is swapped per
            hypothesis during option generation, then restored).
        horizon: simulation horizon.
        n_worlds: world branches per hypothesis.
    """

    def __init__(self, engine: CounterfactualEngine, horizon: int = 3,
                 n_worlds: int = 8, z_threshold: float = 3.0):
        self.engine = engine
        self.horizon = horizon
        self.n_worlds = n_worlds
        # significance gate for uncertainty-aware structural discrimination
        self.z_threshold = z_threshold

    def _options_for(self, simulator: DomainSimulator, state):
        """Generate options under a hypothesis's simulator.

        Args:
            simulator: the hypothesis simulator.
            state: current state.

        Returns:
            The options (empty when the engine cannot simulate).
        """
        prev = self.engine.simulator
        self.engine.simulator = simulator
        try:
            return self.engine.generate_options(state, self.horizon, self.n_worlds)
        except Exception:
            return []
        finally:
            self.engine.simulator = prev

    def evaluate(self, state, hypotheses: List[Hypothesis]) -> List[ExperimentOption]:
        """Score every candidate experiment with the canonical engine.

        Args:
            state: current state.
            hypotheses: candidate truth states.

        Returns:
            One ExperimentOption per hypothesis (status UNKNOWN when unvaluable).
        """
        pooled: List[Any] = []
        owner: List[str] = []
        by_h = {}
        for h in hypotheses:
            opts = self._options_for(h.simulator, state)
            by_h[h.id] = opts
            for o in opts:
                pooled.append(o)
                owner.append(h.id)

        if not pooled:
            return [ExperimentOption(h.id, "UNKNOWN", None, h.uncertainty,
                                     h.test_cost, None) for h in hypotheses]

        optimal = max(o.score for o in pooled)
        voi = self.engine.compute_value_of_information(pooled, optimal)  # CANONICAL

        # Decision sensitivity of a hypothesis = how much the BEST achievable
        # outcome changes if that hypothesis is true: the VoI of its best option
        # (the min |score - optimal| over its options), not its worst option.
        sens: dict = {}
        for hid, v in zip(owner, voi):
            sens[hid] = float(v) if hid not in sens else min(sens[hid], float(v))

        options: List[ExperimentOption] = []
        for h in hypotheses:
            if not by_h.get(h.id):
                options.append(ExperimentOption(h.id, "UNKNOWN", None, h.uncertainty,
                                                h.test_cost, None))
            else:
                s = sens.get(h.id, 0.0)
                options.append(ExperimentOption(
                    h.id, "VALUED", s, h.uncertainty, h.test_cost,
                    s * h.uncertainty / max(h.test_cost, 1e-6)))
        return options

    def select(self, state, hypotheses: List[Hypothesis]) -> Optional[ExperimentOption]:
        """Pick the highest-value VALUED experiment.

        Args:
            state: current state.
            hypotheses: candidate truth states.

        Returns:
            The selected option, or None when every candidate is UNKNOWN (the
            honest "insufficient evidence" outcome — never a zero-value default).
        """
        valued = [o for o in self.evaluate(state, hypotheses) if o.status == "VALUED"]
        if not valued:
            return None
        return max(valued, key=lambda o: o.value)

    # ── V14: structural discrimination (extends, does not replace, V3) ──────

    def structural_discrimination(self, hypotheses: List[Hypothesis],
                                  experiment: str) -> Optional[float]:
        """Spread of predicted outcomes across live hypotheses for an experiment.

        Returns None when any hypothesis cannot predict (unsupported), 0.0 when
        every hypothesis predicts the SAME outcome (the experiment cannot
        distinguish them), else max - min of the predictions.
        """
        preds: List[Any] = []
        ses: List[Optional[float]] = []
        dfs: List[Optional[float]] = []
        for h in hypotheses:
            p = getattr(h, "predictor", None)
            if p is None:
                return None
            v = p(experiment)
            if v is None:
                return None
            preds.append(v)
            se_fn = getattr(h, "predictor_se", None)
            ses.append(float(se_fn(experiment)) if se_fn is not None
                       and se_fn(experiment) is not None else None)
            df_fn = getattr(h, "predictor_df", None)
            dfs.append(float(df_fn(experiment)) if df_fn is not None
                       and df_fn(experiment) is not None else None)
        if len(preds) < 2:
            return 0.0
        # V14b: predictions may be scalars (single outcome) OR trajectories
        # (a temporal/state probe).  The spread is the same max-min rule, taken
        # per time-step and maxed — the policy is unchanged.
        if any(isinstance(v, (list, tuple)) for v in preds):
            m = max(len(v) for v in preds if isinstance(v, (list, tuple)))
            def _vec(v: Any) -> List[float]:
                if isinstance(v, (list, tuple)):
                    return [float(x) for x in v] + [0.0] * (m - len(v))
                return [float(v)] * m
            mat = [_vec(v) for v in preds]
            return max(max(col) - min(col) for col in zip(*mat))
        lo_f = min(range(len(preds)), key=lambda j: preds[j])
        hi_f = max(range(len(preds)), key=lambda j: preds[j])
        fams = [getattr(h, "feature_family", None) for h in hypotheses]
        if (fams[lo_f] is not None and fams[hi_f] is not None
                and fams[lo_f] != fams[hi_f]):
            return 0.0                     # not comparable across evidence families
        spread = max(float(v) for v in preds) - min(float(v) for v in preds)
        # Numerical floor: floating-point noise is not evidence of a distinction
        # (and would otherwise pass the significance gate when SE ~ 0).
        if spread <= 1e-9:
            return 0.0
        # Σe fix: when every live hypothesis provides a standard error, the
        # distinction is only reportable if it is SIGNIFICANT (spread / pooled
        # SE > z_threshold).  A non-significant difference returns 0.0, so the
        # selector abstains (NO_VALUE) rather than choosing on noise.  No SEs
        # => legacy raw-spread behaviour is preserved.
        if all(s is not None and s > 0 for s in ses):
            lo, hi = min(range(len(preds)), key=lambda j: preds[j]), \
                max(range(len(preds)), key=lambda j: preds[j])
            pooled = float(np.sqrt(ses[lo] ** 2 + ses[hi] ** 2))
            if pooled > 0:
                # z_threshold defines the intended NORMAL-reference level; at
                # finite df use the corresponding t critical value (Welch /
                # Satterthwaite df from the two compared predictions).
                alpha = math.erfc(self.z_threshold / math.sqrt(2.0))
                if (dfs[lo] is not None and dfs[hi] is not None
                        and dfs[lo] > 0 and dfs[hi] > 0):
                    v1, v2 = ses[lo] ** 2, ses[hi] ** 2
                    df = (v1 + v2) ** 2 / (v1 ** 2 / dfs[lo] + v2 ** 2 / dfs[hi])
                    crit = _t_critical(alpha, df)
                else:
                    crit = self.z_threshold        # legacy normal reference
                return spread if spread / pooled > crit else 0.0
        return spread

    def evaluate_structural(self, state, hypotheses: List[Hypothesis],
                            experiments: List[str],
                            attempted: Optional[set] = None,
                            ) -> List[StructuralExperimentOption]:
        """Score every candidate experiment for structural discrimination.
        `attempted` experiments are reported as unsupported (never re-run)."""
        attempted = set(attempted or [])
        canon = self.select(state, hypotheses)
        dvoi = None if canon is None else canon.value
        out: List[StructuralExperimentOption] = []
        for e in experiments:
            if e in attempted:
                out.append(StructuralExperimentOption(e, dvoi, None, {}, False))
                continue
            preds = {h.id: h.predictor(e) for h in hypotheses
                     if getattr(h, "predictor", None) is not None}
            disc = self.structural_discrimination(hypotheses, e)
            supported = disc is not None and len(preds) == len(hypotheses)
            out.append(StructuralExperimentOption(e, dvoi, disc, preds, supported))
        return out

    def select_experiment(self, state, hypotheses: List[Hypothesis],
                          experiments: List[str],
                          attempted: Optional[set] = None,
                          ) -> "tuple":
        """EXPLICIT selection policy (no weighted coefficients):

        1. reject unsupported/impossible (or already-attempted) experiments;
        2. prefer canonical decision VoI when it is decision-relevant AND the
           structural discriminations are tied;
        3. when structural discrimination is available (>0), prefer the
           experiment that best distinguishes the live hypotheses;
        4. otherwise terminate with NO_VALUE (all predictions identical).

        Returns (choice|None, reason, options).
        """
        opts = self.evaluate_structural(state, hypotheses, experiments, attempted)
        avail = [o for o in opts if o.supported]
        if not avail:
            return None, "EXHAUSTED", opts
        best_struct = max(o.structural_discrimination for o in avail)
        dvoi = avail[0].decision_voi
        if best_struct is not None and best_struct > 0 and dvoi in (None, 0.0):
            best = max(avail, key=lambda o: o.structural_discrimination)
            return best, "STRUCTURAL_DISCRIMINATION", opts
        if best_struct is not None and best_struct > 0:
            # decision VoI is tied/zero across experiments -> break by structure
            best = max(avail, key=lambda o: o.structural_discrimination)
            return best, "STRUCTURAL_DISCRIMINATION", opts
        if dvoi is not None and dvoi > 0:
            return avail[0], "DECISION_VOI", opts
        return None, "NO_VALUE", opts
