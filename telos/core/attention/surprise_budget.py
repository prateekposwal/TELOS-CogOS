"""
SurpriseBudget — Prediction Error Drives Computational Budget Allocation.

Prateek's insight: "Prediction error drives computational budget. Large errors =
more attention. Don't waste cycles on predictable events."

Most systems allocate a fixed compute budget regardless of surprise. The
SurpriseBudget module dynamically adjusts resource allocation based on
how surprised the system is by recent observations.

Key principle: Attention is a scarce resource. Spend it where predictions fail.
When the world is predictable, coast. When surprise spikes, allocate more
compute to understanding why.

Architecture:
  - Surprise = prediction error (residual magnitude) across observation stream
  - Running surprise signal with exponential decay
  - Budget multiplier: base_budget * (1 + surprise_bonus)
  - Surprise saturation: too much surprise triggers meta-cognitive overload
  - Predictability tracking: what fraction of observations are correctly predicted?
  - Budget is distributed across pipeline phases proportional to surprise per phase

The surprise signal is normalized [0,1] and fed to:
  - BudgetManager: scale compute budget for next cycle
  - AttentionProjectionEngine: allocate more attention to surprising channels
  - MetaCognitionModule: trigger state changes (e.g., exploration mode)
"""

from __future__ import annotations

import logging
import math
import time
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger('telos_surprise_budget')


@dataclass
class SurpriseSignal:
    """A single surprise measurement."""
    cycle: int
    surprise_level: float        # 0-1 normalized surprise
    source: str                  # Which observation channel
    prediction_error: float      # Raw error magnitude
    expected_error: float        # Expected error (baseline)
    novelty: float               # How novel is this surprise? 0=known pattern, 1=unprecedented

    @property
    def surprise_ratio(self) -> float:
        """How many times larger than expected."""
        if self.expected_error <= 0:
            return 1.0 if self.prediction_error > 0 else 0.0
        return self.prediction_error / self.expected_error


@dataclass
class BudgetAllocation:
    """How the surprise budget is allocated across pipeline phases."""
    cycle: int
    total_budget_ms: float
    surprise_bonus_ms: float
    base_budget_ms: float
    phase_allocations: Dict[str, float]  # phase_name -> ms
    surprise_level: float
    predictability: float  # Fraction of correct predictions


class SurpriseBudget:
    """Dynamic budget allocation driven by prediction surprise.

    The surprise budget:
    1. Tracks prediction errors across observation streams
    2. Maintains a running surprise signal (exponentially weighted)
    3. Computes budget multiplier from surprise
    4. Allocates extra budget to phases that handle surprising observations
    5. Tracks predictability (inverse of average surprise)

    Budget formula:
      effective_budget = base_budget * (1.0 + S * gain)
      where S = surprise_signal [0,1], gain = configured amplification

    Integration:
      - Consumes prediction errors from UnknownUnknownDetector
      - Feeds BudgetManager with dynamic budget ceiling
      - Sends allocation signals to AttentionProjectionEngine
    """

    def __init__(self, base_budget_ms: float = 1000.0,
                 surprise_gain: float = 2.0,
                 decay_half_life: int = 10,
                 max_budget_multiplier: float = 4.0,
                 min_budget_multiplier: float = 0.5):
        self._base_budget_ms = base_budget_ms
        self._surprise_gain = surprise_gain
        self._decay_rate = 0.5 ** (1.0 / max(decay_half_life, 1))  # exponential decay
        self._max_multiplier = max_budget_multiplier
        self._min_multiplier = min_budget_multiplier

        # Surprise tracking
        self._surprise_signal: float = 0.0  # Running signal [0,1]
        self._surprise_history: List[SurpriseSignal] = []
        self._max_history = 200

        # Per-channel tracking
        self._channel_surprise: Dict[str, float] = {}

        # Predictability tracking
        self._prediction_window: deque = deque(maxlen=100)  # True for correct, False for incorrect
        self._total_predictions: int = 0
        self._correct_predictions: int = 0

        # Budget history
        self._allocations: List[BudgetAllocation] = []
        self._max_allocations = 100

        # Phase sensitivity: which phases get extra budget from surprise
        self._phase_sensitivity = {
            "perceive": 0.3,
            "streams": 0.1,
            "simulate": 0.4,
            "evaluate": 0.1,
            "select": 0.1,
            "council": 0.0,
            "act": 0.0,
        }

        logger.info(f"SurpriseBudget: initialized (base={base_budget_ms}ms, "
                   f"gain={surprise_gain}, decay_hl={decay_half_life})")

    def record_prediction(self, correct: bool, channel: str = "default",
                           error: float = 0.0,
                           expected_error: float = 0.0) -> SurpriseSignal:
        """Record a prediction outcome and compute surprise.

        Args:
            correct: Whether the prediction was correct
            channel: Which observation channel this prediction belongs to
            error: Raw prediction error magnitude
            expected_error: Expected error magnitude (baseline)

        Returns:
            SurpriseSignal with computed surprise level
        """
        self._total_predictions += 1
        if correct:
            self._correct_predictions += 1

        self._prediction_window.append(correct)

        # Compute surprise from error
        if expected_error > 0 and error > 0:
            ratio = error / expected_error
            # Surprise scales logarithmically with error/expected ratio
            surprise = min(1.0, math.log2(1 + ratio) / 5.0)
        elif not correct and error > 0:
            surprise = min(1.0, error / 5.0)
        else:
            surprise = 0.0 if correct else 0.5

        # Novelty: how much this surprises RELATIVE to recent surprises
        if self._surprise_history:
            recent_avg = np.mean([s.surprise_level for s in self._surprise_history[-20:]]) if len(self._surprise_history) >= 20 else 0.0
            novelty = max(0.0, min(1.0, surprise - recent_avg + 0.5))
        else:
            novelty = surprise

        signal = SurpriseSignal(
            cycle=sum(1 for _ in []),
            surprise_level=surprise,
            source=channel,
            prediction_error=error,
            expected_error=expected_error,
            novelty=novelty,
        )
        # Assign approximate cycle count
        if self._surprise_history:
            signal.cycle = self._surprise_history[-1].cycle + 1

        self._surprise_history.append(signal)
        if len(self._surprise_history) > self._max_history:
            self._surprise_history.pop(0)

        # Update running surprise signal (exponential moving average)
        self._surprise_signal = (
            self._surprise_signal * self._decay_rate +
            surprise * (1.0 - self._decay_rate)
        )

        # Update per-channel surprise
        if channel not in self._channel_surprise:
            self._channel_surprise[channel] = surprise
        else:
            self._channel_surprise[channel] = (
                self._channel_surprise[channel] * self._decay_rate +
                surprise * (1.0 - self._decay_rate)
            )

        return signal

    @property
    def surprise_level(self) -> float:
        """Current surprise signal [0,1]."""
        return self._surprise_signal

    @property
    def predictability(self) -> float:
        """Fraction of recent predictions that were correct [0,1]."""
        if not self._prediction_window:
            return 0.5
        return sum(self._prediction_window) / len(self._prediction_window)

    def compute_information_gain(self, error: float, expected: float,
                                  novelty: float = 0.0) -> float:
        ratio = error / max(expected, 1e-6)
        ig = math.log2(1 + ratio) / 5.0 * (0.5 + novelty * 0.5)
        return min(1.0, ig)

    def compute_budget(self, cycle: int) -> BudgetAllocation:
        """Compute the budget allocation for this cycle based on surprise.

        Returns:
            BudgetAllocation with phase-specific budgets
        """
        # Budget multiplier from surprise
        raw_multiplier = 1.0 + self._surprise_signal * self._surprise_gain
        multiplier = max(self._min_multiplier,
                        min(self._max_multiplier, raw_multiplier))

        total_budget = self._base_budget_ms * multiplier
        surprise_bonus = total_budget - self._base_budget_ms

        # Allocate across phases
        total_sensitivity = sum(self._phase_sensitivity.values())
        phase_allocs = {}
        for phase, sensitivity in self._phase_sensitivity.items():
            if total_sensitivity > 0:
                base_share = 1.0 / len(self._phase_sensitivity)
                # Surprise boosts sensitive phases
                surprise_share = sensitivity / total_sensitivity if total_sensitivity > 0 else base_share
                # Blend: base allocation + surprise boost
                blend = base_share * (1.0 - self._surprise_signal * 0.5) + surprise_share * (self._surprise_signal * 0.5)
                phase_allocs[phase] = total_budget * blend
            else:
                phase_allocs[phase] = total_budget / len(self._phase_sensitivity)

        allocation = BudgetAllocation(
            cycle=cycle,
            total_budget_ms=total_budget,
            surprise_bonus_ms=surprise_bonus,
            base_budget_ms=self._base_budget_ms,
            phase_allocations=phase_allocs,
            surprise_level=self._surprise_signal,
            predictability=self.predictability,
        )

        self._allocations.append(allocation)
        if len(self._allocations) > self._max_allocations:
            self._allocations.pop(0)

        if self._surprise_signal > 0.5:
            logger.info(
                f"SurpriseBudget: high surprise ({self._surprise_signal:.2f}) → "
                f"budget {self._base_budget_ms:.0f} → {total_budget:.0f}ms "
                f"(x{multiplier:.2f})"
            )

        return allocation

    def get_surprising_channels(self, threshold: float = 0.3) -> List[Tuple[str, float]]:
        """Get observation channels sorted by current surprise level.
            Args:
                threshold: the threshold argument for this call.
        """
        channels = [(ch, surp) for ch, surp in self._channel_surprise.items()
                    if surp >= threshold]
        channels.sort(key=lambda x: -x[1])
        return channels

    def get_surprise_trend(self, window: int = 10) -> str:
        """Describe the trend of surprise over recent cycles.
            Args:
                window: the window argument for this call.
        """
        if len(self._surprise_history) < window:
            return "insufficient_data"
        recent = [s.surprise_level for s in self._surprise_history[-window:]]
        if len(recent) < 2:
            return "stable"
        first_half = sum(recent[:window//2]) / (window//2)
        second_half = sum(recent[window//2:]) / (window - window//2)
        if second_half > first_half + 0.1:
            return "increasing"
        elif second_half < first_half - 0.1:
            return "decreasing"
        return "stable"

    def reset(self) -> None:
        """Reset surprise signal (e.g., after a domain change)."""
        self._surprise_signal = 0.0
        self._channel_surprise = {}
        self._prediction_window.clear()
        logger.info("SurpriseBudget: reset")

    def to_dict(self) -> Dict:
        return {
            "surprise_level": round(self.surprise_level, 3),
            "predictability": round(self.predictability, 3),
            "base_budget_ms": self._base_budget_ms,
            "surprise_gain": self._surprise_gain,
            "decay_rate": round(self._decay_rate, 3),
            "surprise_trend": self.get_surprise_trend(),
            "surprising_channels": self.get_surprising_channels(threshold=0.2),
            "channel_surprise": {
                ch: round(s, 3) for ch, s in
                sorted(self._channel_surprise.items(), key=lambda x: -x[1])[:10]
            },
            "total_predictions": self._total_predictions,
            "correct_predictions": self._correct_predictions,
            "accuracy": round(self._correct_predictions / max(self._total_predictions, 1), 3),
            "recent_allocations": [
                {
                    "cycle": a.cycle,
                    "total_budget_ms": round(a.total_budget_ms, 1),
                    "surprise_bonus_ms": round(a.surprise_bonus_ms, 1),
                    "surprise_level": round(a.surprise_level, 3),
                }
                for a in self._allocations[-5:]
            ],
        }
