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

    Bitcoin-inspired Difficulty Adjustment:
      - Tracks decision_difficulty as a function of trajectory_quality,
        worlds_simulated, and council_blocks
      - Harder problems → lower threshold (more inquiry allowed)
      - Maintains a rolling window of the last 20 difficulty values
    """

    def __init__(self, default_threshold: float = 0.5):
        self.default_threshold = default_threshold
        self.buckets: Dict[str, Dict] = {}  # bucket_key -> {'alpha': n, 'beta': n, 'count': n}
        # ── Difficulty Adjustment (Bitcoin-inspired) ──────────────────────
        self.decision_difficulty: float = 0.0
        self._difficulty_history: list = []  # rolling window, last 20
        self._max_difficulty_history: int = 20
        self._seed_priors()

    def _seed_priors(self) -> None:
        """Pre-populate buckets with weak synthetic priors.

        Low omega values (< 0.3): inquiry tends to improve DI → more alpha.
        Mid omega values (0.3-0.7): mixed results → balanced alpha/beta.
        High omega values (> 0.7): inquiry tends to waste compute → more beta.

        Priors are weak (3-5 synthetic observations) so real data overrides them.
        Checkpoint restore overwrites these entirely — this only affects cold start.
        """
        for i in range(11):
            bucket_key = f"{i * 0.1:.1f}"
            omega_val = i * 0.1
            if omega_val < 0.3:
                alpha = 4
                beta = 1
            elif omega_val < 0.7:
                alpha = 3
                beta = 3
            else:
                alpha = 1
                beta = 4
            self.buckets[bucket_key] = {
                'alpha': alpha,
                'beta': beta,
                'count': alpha + beta,
            }

    def compute_decision_difficulty(self, trajectory_quality: float,
                                     worlds_simulated: int,
                                     council_blocks: int) -> float:
        """Compute decision difficulty from pipeline signals.

        Factors:
          - trajectory_quality: lower quality = harder (inverted)
          - worlds_simulated: fewer worlds = less evidence = harder
          - council_blocks: more blocks = more contention = harder

        Returns:
            A float in [0.0, 1.0] where higher = more difficult.
        """
        # Invert quality so lower quality = higher difficulty
        quality_factor = 1.0 - max(0.0, min(1.0, trajectory_quality))

        # Normalize worlds: fewer worlds = harder
        worlds_factor = 1.0 - min(1.0, worlds_simulated / 50.0)

        # Council blocks: more blocks = harder
        block_factor = min(1.0, council_blocks / 10.0)

        difficulty = (quality_factor * 0.4 + worlds_factor * 0.3 + block_factor * 0.3)
        difficulty = max(0.0, min(1.0, difficulty))

        # Store in rolling history
        self._difficulty_history.append(difficulty)
        if len(self._difficulty_history) > self._max_difficulty_history:
            self._difficulty_history = self._difficulty_history[-self._max_difficulty_history:]

        self.decision_difficulty = difficulty
        return difficulty

    def get_threshold(self) -> float:
        """Beta(α, β) posterior mean per bucket, smoothed.

        Bitcoin-inspired: harder problems → lower threshold (more inquiry allowed).

        Returns:
            Adaptive threshold float. Falls back to default if insufficient data.
        """
        base_threshold = self.default_threshold

        if self.buckets:
            # Find the omega value where P(success) drops below 0.5
            candidates = []
            for bucket_key, b in self.buckets.items():
                if b['count'] < 3:
                    continue  # not enough data
                p_success = b['alpha'] / (b['alpha'] + b['beta'])
                candidates.append((float(bucket_key), p_success))

            if candidates:
                candidates.sort()
                for omega_val, p in candidates:
                    if p < 0.5:
                        base_threshold = max(0.2, omega_val - 0.05)
                        break

        # ── Difficulty adjustment: harder problems → lower threshold ──
        if self._difficulty_history:
            avg_difficulty = sum(self._difficulty_history) / len(self._difficulty_history)
            # Scale: at max difficulty, reduce threshold by up to 0.3
            difficulty_adjustment = avg_difficulty * 0.3
            adjusted = base_threshold - difficulty_adjustment
            return max(0.1, min(0.9, adjusted))

        return base_threshold

    def record_outcome(self, omega_value: float, di_improved: bool, was_blocked: bool) -> None:
        """Record whether an inquiry at this omega level was beneficial."""
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

    def _bucket_key(self, val: float) -> str:
        """Bucket a value into 0.1-width intervals, e.g. 0.42 -> '0.4'."""
        return f"{int(val * 10) * 0.1:.1f}"

    def to_dict(self) -> Dict:
        return {
            'default_threshold': self.default_threshold,
            'buckets': self.buckets,
            'decision_difficulty': self.decision_difficulty,
            'difficulty_history': self._difficulty_history,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'OmegaThresholdLearner':
        t = cls(default_threshold=d.get('default_threshold', 0.5))
        restored = d.get('buckets', {})
        # Merge restored data over seeded priors: restored buckets replace seed data
        for k, v in restored.items():
            t.buckets[k] = v
        t.decision_difficulty = d.get('decision_difficulty', 0.0)
        t._difficulty_history = d.get('difficulty_history', [])
        return t