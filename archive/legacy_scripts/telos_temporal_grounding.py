"""
TELOS Temporal Grounding & Temporal Presence Index (TPI)

Monitors and manages the tri-state attention vector (P, F, H) to prevent
Future-Locking and ensure the runtime remains anchored to the present state.
"""
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass, field
from collections import deque


@dataclass
class TemporalPresenceState:
    present: float   # P: attention on current state/execution
    future: float    # F: attention on simulation/planning
    history: float   # H: attention on past ledgers/learning

    def __post_init__(self):
        total = self.present + self.future + self.history
        if abs(total - 1.0) > 1e-6:
            inv = 1.0 / total if total > 0 else 1.0
            self.present *= inv
            self.future *= inv
            self.history *= inv

    @property
    def is_balanced(self) -> bool:
        return (abs(self.present - 1/3) < 0.15 and
                abs(self.future - 1/3) < 0.15 and
                abs(self.history - 1/3) < 0.15)

    @property
    def is_future_locked(self) -> bool:
        return self.future > 0.7

    @property
    def is_past_locked(self) -> bool:
        return self.history > 0.7

    def grounding_factor(self) -> float:
        """τ(P): penalizes low present-attention. Range [0, 1]."""
        return float(np.clip(self.present * 2.0, 0.0, 1.0))


class TemporalPresenceIndex:
    """Tracks and manages the (P, F, H) attention vector per step."""

    def __init__(self, window_size: int = 20):
        self._history: deque = deque(maxlen=window_size)
        self._anchor_count = 0
        self._future_lock_events = 0

    def compute(self, simulation_depth: float, historical_lookback: float,
                immediate_focus: float) -> TemporalPresenceState:
        """Compute TPI from current runtime metrics.

        Args:
            simulation_depth:  ratio of simulation budget used (0-1)
            historical_lookback:  ratio of historical data consulted (0-1)
            immediate_focus:   ratio of compute spent on current-state ops (0-1)
        """
        total = simulation_depth + historical_lookback + immediate_focus
        if total < 1e-9:
            state = TemporalPresenceState(present=1/3, future=1/3, history=1/3)
            self._history.append(state)
            return state
        state = TemporalPresenceState(
            present=immediate_focus / total,
            future=simulation_depth / total,
            history=historical_lookback / total,
        )
        self._history.append(state)
        if state.is_future_locked:
            self._future_lock_events += 1
        return state

    def check_anchor_required(self, state: TemporalPresenceState,
                              threshold: float = 0.6) -> bool:
        """Return True if future attention exceeds threshold → anchor needed."""
        return state.future > threshold

    def record_anchor(self) -> None:
        self._anchor_count += 1

    def get_statistics(self) -> dict:
        recent = list(self._history)
        avg_p = float(np.mean([s.present for s in recent])) if recent else 1/3
        avg_f = float(np.mean([s.future for s in recent])) if recent else 1/3
        avg_h = float(np.mean([s.history for s in recent])) if recent else 1/3
        return {
            'avg_present': round(avg_p, 4),
            'avg_future': round(avg_f, 4),
            'avg_history': round(avg_h, 4),
            'anchor_count': self._anchor_count,
            'future_lock_events': self._future_lock_events,
            'is_balanced': abs(avg_p - 1/3) < 0.15,
        }


class TemporalAnchor:
    """Implements the 'Return to Present' protocol.

    After simulation, forces a context switch back to the current state (S_t)
    before pruning/selection — preventing the runtime from optimizing futures
    it hasn't yet grounded.
    """

    def __init__(self, tpi: Optional[TemporalPresenceIndex] = None):
        self.tpi = tpi or TemporalPresenceIndex()
        self._last_anchor_state: Optional[np.ndarray] = None
        self._anchor_violations = 0

    def anchor(self, current_state: np.ndarray,
               simulation_metrics: dict) -> TemporalPresenceState:
        """Force return to present state and compute TPI."""
        sim_depth = simulation_metrics.get('simulation_depth', 0.5)
        hist_lookback = simulation_metrics.get('historical_lookback', 0.3)
        imm_focus = simulation_metrics.get('immediate_focus', 0.2)

        presence = self.tpi.compute(sim_depth, hist_lookback, imm_focus)
        self._last_anchor_state = current_state.copy()
        self.tpi.record_anchor()

        if presence.is_future_locked:
            self._anchor_violations += 1

        return presence

    def get_grounding_weight(self, presence: TemporalPresenceState) -> float:
        """τ(P): Temporal Grounding Factor for objective weighting."""
        return presence.grounding_factor()

    def get_statistics(self) -> dict:
        base = self.tpi.get_statistics()
        base['anchor_violations'] = self._anchor_violations
        return base
