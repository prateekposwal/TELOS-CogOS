"""
Model-class assessment (V10) — domain-agnostic, vocabulary-free.

The frontier question: does TELOS's machinery transfer to an unseen domain whose
ontology it was NOT given? This module makes NO reference to `mediated` /
`common_cause` / `direct_delay` — it uses only generic, domain-free primitives
(correlation, lagged correlation, intervention effects, autocorrelation) to
decide what CLASS of model is even adequate:

  SUFFICIENT                    the current model class explains the evidence
  ADDITIONAL_STRUCTURE_REQUIRED an extra (unnamed) degree of freedom is needed
  UNRESOLVED                    the evidence cannot distinguish the candidates
  MODEL_CLASS_INSUFFICIENT      NO model in the assumed class can explain it

Crucially distinguishing UNRESOLVED (not yet distinguished) from
MODEL_CLASS_INSUFFICIENT (cannot be explained by the class at all) — the former
is a witness gap, the latter is a model-class failure.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

import numpy as np


class ModelClassVerdict(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    ADDITIONAL_STRUCTURE_REQUIRED = "ADDITIONAL_STRUCTURE_REQUIRED"
    UNRESOLVED = "UNRESOLVED"
    MODEL_CLASS_INSUFFICIENT = "MODEL_CLASS_INSUFFICIENT"


def _corr(x, y) -> float:
    if np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _lag_corr(x, y, k: int) -> float:
    if len(x) <= k:
        return 0.0
    return _corr(x[:-k], y[k:])


def assess(x: np.ndarray, y: np.ndarray, *, do_xy: Optional[float] = None,
           do_yx: Optional[float] = None, intermediate: Optional[bool] = None,
           effect_threshold: float = 0.15, corr_threshold: float = 0.3,
           lag_threshold: float = 0.4) -> Dict[str, Any]:
    """Assess what model CLASS is adequate for an observed variable pair.

    Args:
        x: first series.
        y: second series.
        do_xy: interventional effect of x on y (None = not tested).
        do_yx: interventional effect of y on x (None = not tested).
        intermediate: whether an intermediate signal was observed (optional).
        effect_threshold: |effect| to count as causal.
        corr_threshold: |corr| to count as an association.
        lag_threshold: lagged |corr| to count as a delayed signal.

    Returns:
        {"verdict": ModelClassVerdict, "corr", "lag", "do_xy", "do_yx", "autocorr"}.
    """
    corr = _corr(x, y)
    lag = max(_lag_corr(x, y, k) for k in (1, 2, 3))
    autocorr = _corr(x[1:], x[:-1])
    sx = do_xy is not None and abs(do_xy) > effect_threshold
    sy = do_yx is not None and abs(do_yx) > effect_threshold

    verdict: ModelClassVerdict
    association = abs(corr) >= corr_threshold or lag >= lag_threshold
    if sx and sy:
        # BIDIRECTIONAL: the assumed acyclic class cannot express this.
        verdict = ModelClassVerdict.MODEL_CLASS_INSUFFICIENT
    elif lag >= lag_threshold and abs(corr) < corr_threshold:
        # a delayed-only association: direct-delay suffices unless an observed
        # intermediate requires an extra, unnamed degree of freedom.
        verdict = (ModelClassVerdict.ADDITIONAL_STRUCTURE_REQUIRED
                   if intermediate is True else ModelClassVerdict.SUFFICIENT)
    elif association:
        # a (mostly contemporaneous) association
        if do_xy is None and do_yx is None:
            verdict = ModelClassVerdict.UNRESOLVED          # direction unclear
        elif sx or sy:
            verdict = ModelClassVerdict.SUFFICIENT
        else:
            # association with NO observed intervention effect: a latent common
            # cause / hidden state is required (not mere noise).
            verdict = ModelClassVerdict.ADDITIONAL_STRUCTURE_REQUIRED
    else:
        # no association — noise, or a stateful system with no observable edge
        verdict = (ModelClassVerdict.MODEL_CLASS_INSUFFICIENT
                   if abs(autocorr) > 0.6 else ModelClassVerdict.UNRESOLVED)
    return {"verdict": verdict, "corr": round(corr, 3), "lag": round(lag, 3),
            "do_xy": do_xy, "do_yx": do_yx, "autocorr": round(autocorr, 3)}
