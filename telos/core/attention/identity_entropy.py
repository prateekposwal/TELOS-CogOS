"""
Identity Entropy Tracker — Perceived Action-Space Under Stress.

Axiom 4.1 (Identity Shapes Decisions): The perceived action-space |A_t|
is not fixed — it expands and contracts based on the agent's cognitive
state. Under threat-dominated cognition, |A_t| shrinks: the agent perceives
fewer options and defaults to reactive/defensive choices. Under
opportunity-dominated cognition, |A_t| expands: more counterfactuals
are generated and explored.

This principle is formalized as Identity Entropy:
  H_id(t) = log2(|A_t|)

Where |A_t| is the number of distinct action trajectories the system
perceives as viable at time t. A collapsing H_id signals identity
constriction — the system is losing access to its own capabilities.

This tracker implements:
  1. Rolling action-space size measurement
  2. Entropy collapse rate (how fast options disappear under stress)
  3. Threshold-based alerting when action-space contracts dangerously
  4. Forward projection of identity entropy under current trend
"""

import numpy as np
from typing import List, Optional, Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger('telos_attention')


@dataclass
class EntropySignal:
    """An actionable signal about identity entropy state.

    Used by the pipeline to decide whether intervention is needed
    (e.g., forcing opportunity-seeking behavior when entropy is collapsing).
    """
    current_entropy: float
    collapse_rate: float
    is_collapsing: bool
    is_expanding: bool
    cycles_since_change: int
    recommended_action: str


class IdentityEntropyTracker:
    """Tracks perceived action-space size over time.

    The action-space size |A_t| represents how many distinct options
    the system perceives at cycle t. Under threat/stress, this contracts.
    Under safety/opportunity, it expands.

    Uses a rolling window to compute trends without storing unbounded history.
    All operations are O(1) with respect to window size.

    Thresholds:
      - COLLAPSE_THRESHOLD: rate below which action-space is contracting
      - CRITICAL_ENTROPY_FRACTION: fraction of baseline that triggers alert
      - EXPANSION_THRESHOLD: rate above which action-space is growing
    """

    COLLAPSE_THRESHOLD = -0.3
    CRITICAL_ENTROPY_FRACTION = 0.3
    EXPANSION_THRESHOLD = 0.2

    def __init__(self, baseline_action_space: int = 10, window_size: int = 15):
        self.baseline = max(1, baseline_action_space)
        self.window_size = window_size
        self._sizes: List[int] = []
        self._cycle_count: int = 0
        self._cycles_since_last_change: int = 0
        self._last_size: Optional[int] = None

    def record(self, action_space_size: int) -> None:
        """Record the perceived action-space size for this cycle.

        Args:
            action_space_size: Number of distinct action options perceived.
                In practice, this is derived from the number of viable
                counterfactual trajectories or distinct strategic options.
        """
        self._cycle_count += 1
        self._sizes.append(action_space_size)
        if len(self._sizes) > self.window_size:
            self._sizes = self._sizes[-self.window_size:]

        if self._last_size is not None and action_space_size != self._last_size:
            self._cycles_since_last_change = 0
        else:
            self._cycles_since_last_change += 1
        self._last_size = action_space_size

    @property
    def current_size(self) -> float:
        """Current action-space size (rolling mean over window).

        This is the smoothed |A_t| value used for trend detection.
        """
        if not self._sizes:
            return float(self.baseline)
        return float(np.mean(self._sizes))

    @property
    def raw_size(self) -> Optional[int]:
        """Most recently recorded raw action-space size."""
        return self._sizes[-1] if self._sizes else None

    @property
    def collapse_rate(self) -> float:
        """Rate of change of action-space size.

        Positive = expanding (more options perceived).
        Negative = contracting (fewer options — threat-dominated cognition).
        Zero = stable.

        Computed as the slope of a linear fit over the rolling window.
        """
        if len(self._sizes) < 3:
            return 0.0
        recent = self._sizes[-min(self.window_size, len(self._sizes)):]
        xs = np.arange(len(recent), dtype=float)
        ys = np.array(recent, dtype=float)
        mean_x = np.mean(xs)
        mean_y = np.mean(ys)
        num = float(np.sum((xs - mean_x) * (ys - mean_y)))
        den = float(np.sum((xs - mean_x) ** 2)) + 1e-9
        return num / den

    @property
    def is_collapsing(self) -> bool:
        """True if action-space is contracting at a concerning rate.

        Under threat-dominated cognition, this triggers early.
        The system can then intervene to broaden its attention.
        """
        return self.collapse_rate < self.COLLAPSE_THRESHOLD

    @property
    def is_expanding(self) -> bool:
        """True if action-space is growing (opportunity-dominated cognition)."""
        return self.collapse_rate > self.EXPANSION_THRESHOLD

    @property
    def is_critical(self) -> bool:
        """True if action-space has contracted below critical fraction.

        This is a late warning — identity entropy is critically low,
        meaning the system can only perceive a narrow set of actions.
        Immediate intervention is recommended.
        """
        return self.current_size < self.baseline * self.CRITICAL_ENTROPY_FRACTION

    def assess(self) -> EntropySignal:
        """Produce an actionable signal about the current entropy state.

        The recommended_action field provides a human-readable suggestion
        for pipeline intervention.
        """
        action = "monitor — identity entropy stable"
        if self.is_critical:
            action = (
                "ESCALATE — identity entropy critically low, action-space "
                "collapsed. Initiate opportunity-seeking override to expand "
                "perceived options."
            )
        elif self.is_collapsing:
            action = (
                "WARN — action-space contracting under threat-dominated "
                "attention. Consider allocating more budget to opportunity "
                "exploration and counterfactual diversity."
            )
        elif self.is_expanding:
            action = (
                "ENCOURAGE — action-space expanding. Maintain exploratory "
                "attention allocation to sustain counterfactual diversity."
            )

        return EntropySignal(
            current_entropy=self.current_size,
            collapse_rate=self.collapse_rate,
            is_collapsing=self.is_collapsing,
            is_expanding=self.is_expanding,
            cycles_since_change=self._cycles_since_last_change,
            recommended_action=action,
        )

    def project_size(self, horizon: int = 3) -> float:
        """Predict action-space size `horizon` steps ahead under current trend.

        Used by the pipeline to anticipate whether identity entropy will
        recover or continue collapsing without intervention.
        """
        if len(self._sizes) < 2:
            return float(self.baseline)
        projected = self.current_size + self.collapse_rate * horizon
        return max(1.0, projected)

    @property
    def stats(self) -> Dict:
        """Complete entropy metrics snapshot for DecisionTrace."""
        signal = self.assess()
        return {
            "current_size": self.current_size,
            "raw_size": self.raw_size,
            "baseline": self.baseline,
            "collapse_rate": self.collapse_rate,
            "is_collapsing": self.is_collapsing,
            "is_expanding": self.is_expanding,
            "is_critical": self.is_critical,
            "cycles_since_change": self._cycles_since_last_change,
            "projected_next_3": self.project_size(horizon=3),
            "assessment": signal.recommended_action,
            "history": self._sizes[-10:] if self._sizes else [],
        }
