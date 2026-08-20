"""
TELOS v6 — Epistemic State (Phase 5) and Reality Gap (Phase 4).

Epistemic state:
    KNOWN      — adequate evidence + validated model
    UNCERTAIN  — model exists but evidence/model fidelity insufficient for certainty
    UNKNOWN    — relevant information is missing
    UNMODELED  — no adequate model exists for the relevant phenomenon

It is DERIVED from existing signals (tripartite U, evidence, confidence,
validation status, Reality Gap, model fidelity) — NOT a second uncertainty
engine. "Unknowable" is deliberately NOT a v6 category.

Reality Gap (Phase 4):
    Reuses the existing MD = ||predicted - observed|| as its foundation but
    attributes it PER MODEL and distinguishes:
        A. Unfalsified model  — never meaningfully tested (validation_count=0)
        B. Empirically validated model — repeatedly low Reality Gap
    A model that has never been falsified is NOT equivalent to one that has
    repeatedly demonstrated low Reality Gap. Repeated failures must be able
    to DECREASE authority (Learning changes authority, P5).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List
import numpy as np


class EpistemicState(str, Enum):
    KNOWN = "KNOWN"
    UNCERTAIN = "UNCERTAIN"
    UNKNOWN = "UNKNOWN"
    UNMODELED = "UNMODELED"


@dataclass
class ModelRealityGap:
    """Per-model reality-gap tracker.

    model_id      : identity/version of the world model this tracks
    validation_count : how many times the model has been tested against reality
    total_gap     : running sum of MD (for mean)
    gap_history   : recent individual gaps
    ever_falsified: True if any prediction contradicted observation strongly
    """
    model_id: str
    validation_count: int = 0
    total_gap: float = 0.0
    gap_history: List[float] = field(default_factory=list)
    ever_falsified: bool = False
    _max_history: int = 50
    _falsification_threshold: float = 0.6

    @property
    def mean_gap(self) -> float:
        return self.total_gap / self.validation_count if self.validation_count else 0.0

    @property
    def recent_mean_gap(self) -> float:
        """Mean gap over the recent WINDOW (finite gap_history).

        This is what model-fidelity should track. Unlike the cumulative
        `mean_gap`, it FORGETS old gaps, so a model that was falsified in the
        past can RECOVER fidelity once corrective evidence accumulates. Recovery
        is real (it requires the recent window to fill with accurate predictions),
        not a single-observation erasure of the falsification.
        """
        if not self.gap_history:
            return 0.0
        return sum(self.gap_history) / len(self.gap_history)

    @property
    def is_falsified(self) -> bool:
        return self.ever_falsified

    @property
    def tested(self) -> bool:
        return self.validation_count > 0

    def record(self, predicted: np.ndarray, observed: np.ndarray) -> float:
        """Record one prediction-vs-observation and update gap stats.

        Args:
            predicted: the model's predicted vector for a step.
            observed: the observed vector the world actually produced.

        Returns the MD gap for this observation.
        """
        if predicted is None or observed is None:
            return 0.0
        if predicted.shape != observed.shape:
            # Different spaces => can't compare; treat as high uncertainty
            gap = 1.0
        else:
            gap = float(np.linalg.norm(np.asarray(predicted) - np.asarray(observed)))
        self.validation_count += 1
        self.total_gap += gap
        self.gap_history.append(gap)
        if len(self.gap_history) > self._max_history:
            self.gap_history.pop(0)
        if gap > self._falsification_threshold:
            self.ever_falsified = True
        return gap

    def to_dict(self) -> Dict[str, object]:
        return {
            "model_id": self.model_id,
            "validation_count": self.validation_count,
            "mean_gap": round(self.mean_gap, 4),
            "ever_falsified": self.ever_falsified,
            "tested": self.tested,
            "recent_gap": round(self.gap_history[-1], 4) if self.gap_history else None,
        }


class RealityGapTracker:
    """Owns per-model Reality Gap trackers (Phase 4).

    The single authority for model fidelity assessment. Components that need
    to know "is my model reliable?" query this instead of re-reading MD.
    """

    def __init__(self, default_falsification_threshold: float = 0.6):
        self._models: Dict[str, ModelRealityGap] = {}
        self._default_threshold = default_falsification_threshold

    def model(self, model_id: str) -> ModelRealityGap:
        if model_id not in self._models:
            self._models[model_id] = ModelRealityGap(
                model_id=model_id,
                _falsification_threshold=self._default_threshold,
            )
        return self._models[model_id]

    def record(self, model_id: str, predicted: np.ndarray,
               observed: np.ndarray) -> float:
        return self.model(model_id).record(predicted, observed)

    def model_fidelity(self, model_id: str) -> Optional[float]:
        """0-1 fidelity estimate from the RECENT reality-gap window.

        Args:
            model_id: the model whose recent reality-gap window is queried.

        Returns None if the model is unfalsified (untested) — you cannot claim
        fidelity without validation. Untested != reliable.

        Uses the recent-window mean (not cumulative), so a past falsification
        does NOT permanently keep fidelity at zero: after sustained corrective
        evidence, fidelity recovers (authority can be restored — P5 up-direction).
        """
        m = self._models.get(model_id)
        if m is None or not m.tested or not m.gap_history:
            return None
        # fidelity = 1 - recent_mean_gap, clamped to [0,1]
        return float(np.clip(1.0 - m.recent_mean_gap, 0.0, 1.0))

    def to_dict(self) -> Dict[str, object]:
        return {mid: m.to_dict() for mid, m in self._models.items()}

    @property
    def models(self) -> Dict[str, ModelRealityGap]:
        return dict(self._models)


def derive_epistemic_state(*, model_fidelity: Optional[float],
                           tested: bool,
                           composite_uncertainty: float,
                           missing_info: bool = False,
                           has_model: bool = True) -> EpistemicState:
    """Derive an EpistemicState label from existing signals (Phase 5).

    Args:
        model_fidelity: 0-1 fidelity or None if the model is untested.
        tested: whether the model has been validated against reality.
        composite_uncertainty: tripartite U composite (0-1).
        missing_info: whether relevant information is known to be missing.
        has_model: whether any model exists for the phenomenon.

    Rules:
        UNMODELED -> no model exists for the phenomenon.
        KNOWN     -> validated model (tested + fidelity high) and low uncertainty
                     and no known-missing info.
        UNKNOWN   -> relevant information is known-missing.
        UNCERTAIN -> otherwise (model exists but evidence/fidelity insufficient,
                     or uncertainty elevated).
    """
    if not has_model:
        return EpistemicState.UNMODELED
    if missing_info:
        return EpistemicState.UNKNOWN
    if tested and model_fidelity is not None and model_fidelity >= 0.7 \
            and composite_uncertainty < 0.3:
        return EpistemicState.KNOWN
    return EpistemicState.UNCERTAIN
