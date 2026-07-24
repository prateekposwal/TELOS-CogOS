"""
OmegaThresholdLearner — Self-tuning threshold for the Ω operator.

Uses Beta(α, β) statistics per omega bucket to dynamically adjust the
threshold at which the Ω operator triggers inquiry mode. Lowers the
threshold if inquiries improve DI, raises it if they lead to blocked cycles.

Persists across sessions via checkpoint save/load.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger('telos_omega_threshold')


class OmegaThresholdLearner:
    """Self-tuning threshold for the Ω operator using Beta(α, β) statistics.

    Tracks inquiry outcomes per 0.1-width omega bucket.
    Lowers threshold if inquiries improve DI.
    Raises threshold if inquiries lead to blocked cycles.
    Persists across sessions via checkpoint save/load.
    """

    def __init__(self, default_threshold: float = 0.5):
        self.default_threshold = default_threshold
        self.buckets: Dict[str, Dict] = {}  # bucket_key -> {'alpha': n, 'beta': n, 'count': n}

    def record_outcome(self, omega_value: float, di_improved: bool, was_blocked: bool) -> None:
        """Record whether an inquiry at this omega level was beneficial.

        Args:
            omega_value: The omega value at which inquiry was triggered
            di_improved: Whether decision integrity improved after the inquiry
            was_blocked: Whether the inquiry led to a blocked cycle
        """
        bucket = self._bucket_key(omega_value)
        if bucket not in self.buckets:
            self.buckets[bucket] = {'alpha': 1, 'beta': 1, 'count': 0}
        b = self.buckets[bucket]
        if di_improved and not was_blocked:
            b['alpha'] += 1  # success
        else:
            b['beta'] += 1   # failure
        b['count'] += 1
        logger.debug(f"OmegaThreshold: recorded omega={omega_value:.2f} "
                      f"(bucket={bucket}), di_improved={di_improved}, "
                      f"was_blocked={was_blocked} — now α={b['alpha']}, β={b['beta']}")

    def get_threshold(self) -> float:
        """Beta(α, β) posterior mean per bucket, smoothed.

        Returns:
            Adaptive threshold float. Falls back to default if insufficient data.
        """
        if not self.buckets:
            return self.default_threshold

        # Find the omega value where P(success) drops below 0.5
        candidates = []
        for bucket_key, b in self.buckets.items():
            if b['count'] < 3:
                continue  # not enough data
            p_success = b['alpha'] / (b['alpha'] + b['beta'])
            candidates.append((float(bucket_key), p_success))

        if not candidates:
            return self.default_threshold

        candidates.sort()
        for omega_val, p in candidates:
            if p < 0.5:
                # Lower threshold slightly below the failure point
                return max(0.2, omega_val - 0.05)

        return self.default_threshold

    def _bucket_key(self, val: float) -> str:
        """Bucket a value into 0.1-width intervals, e.g. 0.42 -> '0.4'."""
        return f"{int(val * 10) * 0.1:.1f}"

    def to_dict(self) -> Dict:
        return {
            'default_threshold': self.default_threshold,
            'buckets': self.buckets,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'OmegaThresholdLearner':
        t = cls(default_threshold=d.get('default_threshold', 0.5))
        t.buckets = d.get('buckets', {})
        return t
