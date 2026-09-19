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


# A model whose last REAL validation (an acted cycle's prediction-vs-observation
# record) is older than this many cycles is "currently unvalidated" — its gap
# history is frozen, not fresh. Stale evidence is not current falsification
# (Λ6.5): reporting an ancient gap as today's model state is what locked the
# no-action trap (a single 2.88 gap, never refreshed, vetoed ACT forever).
STALE_MODEL_VALIDATION_CYCLES = 300


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
    last_validation_cycle: Optional[int] = None
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

    def currently_falsified(self, now_cycle: Optional[int] = None) -> bool:
        """Whether the model is falsified by CURRENT evidence.

        Contrast with the sticky ``is_falsified`` (ever falsified). Honesty
        rule (Λ6.5): a gap history that has not been refreshed within
        STALE_MODEL_VALIDATION_CYCLES is frozen, not fresh — absence of new
        validation is uncertainty, not ongoing falsification. Fresh evidence
        scores on the recent window: recovered models (recent mean gap below
        threshold) are no longer falsified.

        Args:
            now_cycle: current pipeline cycle (None = no recency judgement).

        Returns:
            True only when evidence is fresh AND the recent mean gap exceeds
            the falsification threshold.
        """
        if (self.last_validation_cycle is not None and now_cycle is not None
                and (now_cycle - self.last_validation_cycle)
                > STALE_MODEL_VALIDATION_CYCLES):
            return False
        recent = self.recent_mean_gap or 0.0
        return self.ever_falsified and recent > self._falsification_threshold

    @property
    def tested(self) -> bool:
        return self.validation_count > 0

    def record(self, predicted: np.ndarray, observed: np.ndarray,
               cycle: Optional[int] = None) -> float:
        """Record one prediction-vs-observation and update gap stats.

        Args:
            predicted: the model's predicted vector for a step.
            observed: the observed vector the world actually produced.
            cycle: pipeline cycle of this validation (recency stamp — lets
                consumers distinguish CURRENT falsification from stale).

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
        if cycle is not None:
            self.last_validation_cycle = cycle
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
            "last_validation_cycle": self.last_validation_cycle,
            "recent_gap": round(self.gap_history[-1], 4) if self.gap_history else None,
        }

    def to_state(self) -> Dict[str, object]:
        """Export the FULL evidence state for durable persistence.

        Unlike :meth:`to_dict` (a rounded human summary), this is the lossless
        record a restart needs to reconstruct the authority: the complete gap
        history, the sticky ``ever_falsified`` flag, the recency stamp, and the
        per-model falsification threshold. Persisting the rounded summary would
        silently drop the evidence that a model was falsified.

        Returns:
            Dict of the model's complete evidence state.
        """
        return {
            "model_id": self.model_id,
            "validation_count": int(self.validation_count),
            "total_gap": float(self.total_gap),
            "gap_history": [float(g) for g in self.gap_history],
            "ever_falsified": bool(self.ever_falsified),
            "last_validation_cycle": self.last_validation_cycle,
            "falsification_threshold": float(self._falsification_threshold),
        }

    @classmethod
    def from_state(cls, data: Dict[str, object]) -> "ModelRealityGap":
        """Reconstruct a model's evidence state from a persisted record.

        Strict by construction: a malformed record raises ``ValueError`` so the
        caller can fail CLOSED (an unreadable safety record must never be
        silently treated as "nothing was ever falsified").

        Args:
            data: a :meth:`to_state` record.

        Returns:
            The reconstructed ModelRealityGap.

        Raises:
            ValueError: when the record is not a well-formed evidence state.
        """
        if not isinstance(data, dict):
            raise ValueError("model state must be an object")
        mid = data.get("model_id")
        if not isinstance(mid, str) or not mid.strip():
            raise ValueError("model state is missing a model_id")
        raw_hist = data.get("gap_history", [])
        if raw_hist is None:
            raw_hist = []
        if not isinstance(raw_hist, list):
            raise ValueError("gap_history must be a list")
        try:
            history = [float(g) for g in raw_hist]
        except (TypeError, ValueError) as e:
            raise ValueError(f"gap_history contains a non-numeric gap: {e}")
        if any(g != g for g in history):  # NaN guard
            raise ValueError("gap_history contains NaN")
        try:
            count = int(data.get("validation_count", 0))
            total = float(data.get("total_gap", 0.0))
        except (TypeError, ValueError) as e:
            raise ValueError(f"malformed validation counters: {e}")
        if count < 0:
            raise ValueError("validation_count must be >= 0")
        if count > 0 and not history:
            # An INCOMPLETE record: the model claims validations but carries no
            # measured gaps. Treating this as fidelity 1.0 would let a truncated
            # revocation record silently GRANT authority — fail closed instead.
            raise ValueError(
                "incomplete evidence: validation_count > 0 with no gap_history")
        raw_cycle = data.get("last_validation_cycle")
        if raw_cycle is not None:
            try:
                raw_cycle = int(raw_cycle)
            except (TypeError, ValueError) as e:
                raise ValueError(f"last_validation_cycle must be an int: {e}")
        raw_thr = data.get("falsification_threshold", 0.6)
        try:
            thr = float(raw_thr)
        except (TypeError, ValueError) as e:
            raise ValueError(f"falsification_threshold must be a number: {e}")
        m = cls(model_id=mid, _falsification_threshold=thr)
        m.validation_count = count
        m.total_gap = total
        m.gap_history = history[-m._max_history:]
        m.ever_falsified = bool(data.get("ever_falsified", False))
        m.last_validation_cycle = raw_cycle
        return m


def _authority_restrictiveness(m: ModelRealityGap) -> tuple:
    """Order two states by how much authority they WITHHOLD (higher = stricter).

    Used only to break an ambiguous (equal/unknown-timestamp) reload conflict.
    The more restrictive state wins — ambiguity never resolves toward granting
    more authority (fail-closed).

    Args:
        m: the model state to score.

    Returns:
        A sortable tuple; a larger tuple withholds more authority.
    """
    return (1 if m.ever_falsified else 0, float(m.recent_mean_gap),
            int(m.validation_count))


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
               observed: np.ndarray, cycle: Optional[int] = None) -> float:
        return self.model(model_id).record(predicted, observed, cycle=cycle)

    def model_fidelity(self, model_id: str,
                       now_cycle: Optional[int] = None,
                       stale_window: Optional[int] = None) -> Optional[float]:
        """0-1 fidelity estimate from the RECENT reality-gap window.

        Args:
            model_id: the model whose recent reality-gap window is queried.
            now_cycle: current pipeline cycle; with a recency stamp on the
                model this makes stale evidence "currently unvalidated" and
                returns None instead of a frozen veto.
            stale_window: how many cycles without a REAL validation before the
                model counts as stale (defaults to the truth window
                STALE_MODEL_VALIDATION_CYCLES; the act gate passes a short
                window because a per-step gap is only current for a few cycles
                in a dynamically-shifting world).

        Returns None if the model is currently unvalidated (untested OR stale)
        — you cannot claim fidelity without current validation.
        Untested/stale != reliable.

        Uses the recent-window mean (not cumulative), so a past falsification
        does NOT permanently keep fidelity at zero: after sustained corrective
        evidence, fidelity recovers (authority can be restored — P5 up-direction).
        """
        m = self._models.get(model_id)
        if m is None or not m.tested or not m.gap_history:
            return None
        # Stale evidence is not current truth (Λ6.5): if the model was last
        # REALLY validated too long ago, its recent_gap is frozen — report
        # "currently unvalidated" (None, act-then-learn) rather than a stale
        # veto. This is what lets a no-action trap recover once motion flows.
        _window = stale_window or STALE_MODEL_VALIDATION_CYCLES
        if (now_cycle is not None and m.last_validation_cycle is not None
                and (now_cycle - m.last_validation_cycle) > _window):
            return None
        # fidelity = 1 - recent_mean_gap, clamped to [0,1]
        return float(np.clip(1.0 - m.recent_mean_gap, 0.0, 1.0))

    def to_dict(self) -> Dict[str, object]:
        return {mid: m.to_dict() for mid, m in self._models.items()}

    def to_state(self) -> Dict[str, object]:
        """Export every model's FULL evidence state (lossless persistence).

        Returns:
            Mapping model_id -> :meth:`ModelRealityGap.to_state`.
        """
        return {mid: m.to_state() for mid, m in self._models.items()}

    def load_state(self, data: Dict[str, object]) -> None:
        """Restore persisted evidence, recency- and restriction-safe.

        Merge rule (deterministic, fail-closed):

          * an untested side yields to a tested one;
          * when both carry a recency stamp, the NEWER validation wins (stale
            positive evidence can never outrank newer valid falsification);
          * when timestamps are equal/unknown (ambiguous ordering), the MORE
            RESTRICTIVE state wins — ambiguity never resolves toward granting
            more authority.

        Args:
            data: a :meth:`to_state` mapping.

        Raises:
            ValueError: when the payload is not a well-formed evidence mapping;
                callers MUST fail closed (do not grant authority).
        """
        if not isinstance(data, dict):
            raise ValueError("authority state must be a JSON object")
        for mid, entry in data.items():
            if not isinstance(mid, str) or not isinstance(entry, dict):
                raise ValueError("authority state entry is malformed")
            restored = ModelRealityGap.from_state(dict(entry, model_id=mid))
            existing = self._models.get(mid)
            if existing is None or existing.validation_count == 0:
                self._models[mid] = restored
                continue
            if restored.validation_count == 0:
                continue
            le = existing.last_validation_cycle
            li = restored.last_validation_cycle
            if le is not None and li is not None and le != li:
                self._models[mid] = restored if li > le else existing
                continue
            # Equal/ambiguous ordering: fail-closed (more restrictive wins).
            self._models[mid] = (
                restored
                if _authority_restrictiveness(restored)
                >= _authority_restrictiveness(existing)
                else existing)

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
