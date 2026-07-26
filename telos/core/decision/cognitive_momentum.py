"""CognitiveMomentum — measures decision inertia as a weighted sum of recent actions.

M_c = Σ w_i · a_i

High momentum → system is locked into a policy trajectory.
Low momentum → system is reactive, easily perturbed.

Detects policy lock-in and recommends un-sticking actions.
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class MomentumRecord:
    cycle: int
    intent_type: str
    action_vector: List[float]
    weight: float
    timestamp: float = field(default_factory=time.time)


class CognitiveMomentum:
    def __init__(self, window_size: int = 10, lock_in_threshold: float = 0.8,
                 decay_factor: float = 0.9):
        self._window_size = window_size
        self._lock_in_threshold = lock_in_threshold
        self._decay_factor = decay_factor
        self._history: List[MomentumRecord] = []
        self._last_lock_in_cycle: Optional[int] = None

    def record_decision(self, cycle: int, intent_type: str,
                        action_vector: Optional[List[float]] = None) -> None:
        weight = self._decay_factor ** len(self._history)
        record = MomentumRecord(
            cycle=cycle,
            intent_type=intent_type,
            action_vector=action_vector or [0.0, 0.0],
            weight=weight,
        )
        self._history.append(record)
        if len(self._history) > self._window_size:
            self._history.pop(0)

    @property
    def momentum(self) -> float:
        if not self._history:
            return 0.0
        total_weight = sum(r.weight for r in self._history)
        if total_weight == 0:
            return 0.0
        weighted = sum(r.weight * self._intent_magnitude(r) for r in self._history)
        return min(1.0, weighted / total_weight)

    def _intent_magnitude(self, record: MomentumRecord) -> float:
        vec = record.action_vector
        magnitude = math.sqrt(sum(v * v for v in vec)) if vec else 0.0
        return min(1.0, magnitude / 5.0)

    @property
    def is_locked_in(self) -> bool:
        return self.momentum >= self._lock_in_threshold

    @property
    def dominant_intent_type(self) -> Optional[str]:
        if not self._history:
            return None
        counts: Dict[str, float] = {}
        for r in self._history:
            counts[r.intent_type] = counts.get(r.intent_type, 0.0) + r.weight
        return max(counts, key=counts.get) if counts else None

    @property
    def intent_diversity(self) -> float:
        if len(self._history) < 2:
            return 1.0
        types = set(r.intent_type for r in self._history)
        return len(types) / min(len(self._history), self._window_size)

    def recommend_unstick(self) -> Optional[str]:
        if not self.is_locked_in:
            return None
        dominant = self.dominant_intent_type
        if dominant in ("reflex", "plan_trajectory"):
            return f"momentum_too_high_on_{dominant}"
        if self.intent_diversity < 0.3:
            return "try_unfamiliar_intent_type"
        return None

    @property
    def momentum_trend(self) -> str:
        if len(self._history) < 3:
            return "insufficient_data"
        recent = self._history[-3:]
        vals = [self._intent_magnitude(r) for r in recent]
        if vals[-1] > vals[0] * 1.1:
            return "increasing"
        if vals[-1] < vals[0] * 0.9:
            return "decreasing"
        return "stable"

    def to_dict(self) -> Dict:
        return {
            "momentum": self.momentum,
            "is_locked_in": self.is_locked_in,
            "dominant_intent_type": self.dominant_intent_type,
            "intent_diversity": self.intent_diversity,
            "trend": self.momentum_trend,
            "recommendation": self.recommend_unstick(),
            "history_length": len(self._history),
        }
