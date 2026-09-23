"""
CalibrationTracker — the honest-confidence ledger.

TELOS emits confidence everywhere (intent confidence, DI, tripartite U) but
had no mechanism that checked whether those numbers were TRUE. The tracker
records ``(predicted_confidence, realized_outcome)`` pairs, one per cycle,
and reports:

  * **Brier score** — mean squared error of the confidence as a forecast.
  * **ECE (Expected Calibration Error)** — the average |accuracy − confidence|
    across probability bins. 0.0 = perfectly calibrated.
  * **Reliability curve** — per-bin confidence vs. realized accuracy, the raw
    material for a recalibration map.
  * **calibrated_confidence(p)** — maps a claimed confidence to the empirical
    accuracy observed at that confidence level (shrinkage toward the global
    base rate when a bin is under-sampled).

Design constraints (matching the codebase's invariants):
  * Λ1.2 (Process over Outcomes): the tracker only *observes* — it never
    changes the decision path. The CalibrationValidator is the optional,
    opt-in consumer.
  * Λ4.7 (retention): all histories are bounded windows; a long-lived run
    cannot grow them without limit.

Pure and dependency-light (numpy only) so it is trivially testable.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Deque, Dict, List, Optional

import numpy as np

# Λ4.7 retention cap: one (predicted, realized) pair per cycle; keep the most
# recent N so a multi-thousand-cycle run stays bounded.
_DEFAULT_WINDOW = 200

# A bin needs at least this many samples before its empirical accuracy is
# trusted as a recalibration target (below it we shrink toward the base rate).
_DEFAULT_MIN_BIN_SAMPLES = 5


@dataclass
class CalibrationStats:
    """A point-in-time snapshot of the tracker (JSON-serializable)."""
    sample_count: int = 0
    brier_score: Optional[float] = None
    ece: Optional[float] = None
    mean_confidence: Optional[float] = None
    mean_accuracy: Optional[float] = None
    overconfidence: Optional[float] = None
    is_calibrated: bool = False
    bins: List[Dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Return a plain dict for traces / dashboards.

        Returns:
            The dataclass as a dict.
        """
        return asdict(self)


class CalibrationTracker:
    """Records confidence-vs-outcome pairs and measures calibration.

    Args:
        window: maximum number of recent pairs retained (Λ4.7).
        n_bins: number of probability bins for ECE / the reliability curve.
        min_samples: minimum pairs before any calibration metric is reported
            (an honest "not enough data yet" gate — never a fabricated score).
        min_bin_samples: minimum pairs per bin before its empirical accuracy
            is used directly as a recalibration target.
    """

    def __init__(self, window: int = _DEFAULT_WINDOW, n_bins: int = 10,
                 min_samples: int = 20,
                 min_bin_samples: int = _DEFAULT_MIN_BIN_SAMPLES):
        self.window = max(1, int(window))
        self.n_bins = max(1, int(n_bins))
        self.min_samples = max(1, int(min_samples))
        self.min_bin_samples = max(1, int(min_bin_samples))
        self._predicted: Deque[float] = deque(maxlen=self.window)
        self._realized: Deque[float] = deque(maxlen=self.window)

    # ── Recording ────────────────────────────────────────────────────────────

    def record(self, predicted: float, realized: float) -> None:
        """Record one (claimed confidence, realized outcome) pair.

        Both values are clamped to [0, 1]; a non-finite value is dropped
        (never silently coerced to a fabricated 0.5).

        Args:
            predicted: the confidence the system claimed, in [0, 1].
            realized: the realized outcome, in [0, 1] (1.0 = success).
        """
        try:
            p = float(predicted)
            y = float(realized)
        except (TypeError, ValueError):
            return
        if not np.isfinite(p) or not np.isfinite(y):
            return
        self._predicted.append(float(np.clip(p, 0.0, 1.0)))
        self._realized.append(float(np.clip(y, 0.0, 1.0)))

    def reset(self) -> None:
        """Clear all recorded pairs."""
        self._predicted.clear()
        self._realized.clear()

    # ── Basic accessors ──────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._predicted)

    @property
    def sample_count(self) -> int:
        """Number of retained (predicted, realized) pairs."""
        return len(self._predicted)

    @property
    def has_signal(self) -> bool:
        """True once enough pairs exist for an honest calibration metric."""
        return self.sample_count >= self.min_samples

    def _arrays(self):
        return (np.asarray(self._predicted, dtype=float),
                np.asarray(self._realized, dtype=float))

    # ── Metrics ──────────────────────────────────────────────────────────────

    def brier_score(self) -> Optional[float]:
        """Mean squared error of confidence-as-forecast, or None if too few.

        Returns:
            Brier score in [0, 1] (lower is better), or None under min_samples.
        """
        if not self.has_signal:
            return None
        p, y = self._arrays()
        return float(np.mean((p - y) ** 2))

    def reliability_curve(self) -> List[Dict[str, float]]:
        """Per-bin confidence vs. realized accuracy.

        Returns:
            One dict per non-empty bin: ``{lo, hi, count, confidence,
            accuracy, gap}``. Empty when there is no signal.
        """
        if self.sample_count == 0:
            return []
        p, y = self._arrays()
        edges = np.linspace(0.0, 1.0, self.n_bins + 1)
        idx = np.clip((p * self.n_bins).astype(int), 0, self.n_bins - 1)
        curve: List[Dict[str, float]] = []
        for b in range(self.n_bins):
            mask = idx == b
            count = int(np.count_nonzero(mask))
            if count == 0:
                continue
            conf = float(np.mean(p[mask]))
            acc = float(np.mean(y[mask]))
            curve.append({
                "lo": float(edges[b]),
                "hi": float(edges[b + 1]),
                "count": count,
                "confidence": conf,
                "accuracy": acc,
                "gap": abs(acc - conf),
            })
        return curve

    def ece(self) -> Optional[float]:
        """Expected Calibration Error (count-weighted mean bin gap).

        Returns:
            ECE in [0, 1] (0.0 = perfectly calibrated), or None under
            min_samples.
        """
        if not self.has_signal:
            return None
        total = self.sample_count
        return float(sum(b["count"] / total * b["gap"]
                         for b in self.reliability_curve()))

    def mean_confidence(self) -> Optional[float]:
        """Mean claimed confidence, or None when empty."""
        if self.sample_count == 0:
            return None
        return float(np.mean(self._predicted))

    def mean_accuracy(self) -> Optional[float]:
        """Mean realized outcome (base rate), or None when empty."""
        if self.sample_count == 0:
            return None
        return float(np.mean(self._realized))

    def overconfidence(self) -> Optional[float]:
        """Mean confidence minus mean accuracy (positive = overconfident).

        Returns:
            The signed gap, or None when empty.
        """
        if self.sample_count == 0:
            return None
        return float(np.mean(self._predicted) - np.mean(self._realized))

    def is_calibrated(self, ece_threshold: float = 0.25) -> bool:
        """Whether recent ECE is within tolerance.

        Args:
            ece_threshold: maximum acceptable ECE.

        Returns:
            True when there is a signal AND ECE ≤ threshold; False otherwise
            (including the honest "insufficient data" case).
        """
        e = self.ece()
        return bool(e is not None and e <= ece_threshold)

    # ── Recalibration ────────────────────────────────────────────────────────

    def calibrated_confidence(self, raw: float) -> float:
        """Map a claimed confidence to its empirically-observed accuracy.

        Uses the reliability bin containing ``raw`` when that bin has enough
        samples; otherwise shrinks ``raw`` toward the global base rate by the
        fraction of the required sample budget collected so far. With no data
        at all the raw claim is returned unchanged (honest identity map).

        Args:
            raw: a claimed confidence in [0, 1].

        Returns:
            A recalibrated confidence in [0, 1].
        """
        try:
            r = float(raw)
        except (TypeError, ValueError):
            return 0.5
        if not np.isfinite(r):
            return 0.5
        r = float(np.clip(r, 0.0, 1.0))
        if self.sample_count == 0:
            return r

        bin_idx = min(int(r * self.n_bins), self.n_bins - 1)
        for b in self.reliability_curve():
            lo_idx = min(int(b["lo"] * self.n_bins), self.n_bins - 1)
            if lo_idx == bin_idx and b["count"] >= self.min_bin_samples:
                return float(np.clip(b["accuracy"], 0.0, 1.0))

        # Under-sampled bin: shrink toward the global base rate.
        base = self.mean_accuracy()
        if base is None:
            return r
        w = min(1.0, self.sample_count / float(2 * self.min_samples))
        return float(np.clip((1.0 - w) * r + w * base, 0.0, 1.0))

    # ── Snapshot ─────────────────────────────────────────────────────────────

    def stats(self) -> CalibrationStats:
        """Return a snapshot of the current calibration state.

        Returns:
            A CalibrationStats (metrics are None until min_samples is reached).
        """
        e = self.ece()
        return CalibrationStats(
            sample_count=self.sample_count,
            brier_score=self.brier_score(),
            ece=e,
            mean_confidence=self.mean_confidence(),
            mean_accuracy=self.mean_accuracy(),
            overconfidence=self.overconfidence(),
            is_calibrated=bool(e is not None and e <= 0.25),
            bins=self.reliability_curve() if self.has_signal else [],
        )

    def to_dict(self) -> Dict:
        """Return the stats snapshot as a plain dict.

        Returns:
            The CalibrationStats dict.
        """
        return self.stats().to_dict()
