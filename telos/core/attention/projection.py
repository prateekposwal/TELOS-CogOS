"""
Attention Projection Engine — The Law of Attention and Trajectory.

The core insight (Axiom 4.7): "An agent's sustained allocation of attention
determines which counterfactual futures are generated, which in turn shapes
the trajectory of subsequent decisions."

This engine formalizes that law with measurable metrics:
  1. Attention Allocation Ratio (threat vs opportunity)
  2. Identity Entropy (rolling action-space size)
  3. Counterfactual Diversity (variance of simulated futures)
  4. Trajectory Divergence Prediction
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger('telos_attention')


@dataclass
class AttentionAllocation:
    """How attention budget (100 units) was split across cognitive modes.

    The split determines which counterfactual futures are explored:
      - High threat_ratio → focus on safe/defensive worlds
      - High opportunity_ratio → diverse exploration of possibilities
      - High maintenance_ratio → stabilization, preserving status quo
    """
    threat_ratio: float
    opportunity_ratio: float
    maintenance_ratio: float
    stream_breakdown: Dict[str, float] = field(default_factory=dict)
    total_budget: float = 100.0

    def __post_init__(self):
        # Normalize to ensure they sum to 1.0
        total = self.threat_ratio + self.opportunity_ratio + self.maintenance_ratio
        if total > 0:
            self.threat_ratio /= total
            self.opportunity_ratio /= total
            self.maintenance_ratio /= total

    @property
    def is_threat_dominated(self) -> bool:
        return self.threat_ratio > 0.5

    @property
    def is_opportunity_dominated(self) -> bool:
        return self.opportunity_ratio > 0.5

    @property
    def threat_budget(self) -> float:
        return self.total_budget * self.threat_ratio

    @property
    def opportunity_budget(self) -> float:
        return self.total_budget * self.opportunity_ratio

    @property
    def maintenance_budget(self) -> float:
        return self.total_budget * self.maintenance_ratio


@dataclass
class TrajectoryProjection:
    """Predicted trajectory divergence given current attention policy.

    The projection captures how the Law of Attention will shape future
    trajectories based on:
      - Momentum: how locked-in the current attention policy is
      - Diversity: how much counterfactual exploration is happening
      - Entropy: how many action options are perceived
      - Threat bias: how much attention is on threats vs opportunities
    """
    expected_divergence: float
    attention_momentum: float
    diversity_budget: float
    projected_identity_entropy: float


class AttentionProjectionEngine:
    """Models the Law of Attention and Trajectory.

    Tracks how attention allocation shapes counterfactual generation,
    which in turn determines trajectory outcomes. Provides early warning
    when attention is pathologically locked-in.

    The engine is O(1) per operation — all history is rolling-window bounded.

    Metrics tracked:
      - Attention allocation ratios (rolling window of N cycles)
      - Identity Entropy (action-space diversity over time)
      - Counterfactual Diversity (variance of simulated futures)
      - Trajectory divergence predictions
    """

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self._allocation_history: List[AttentionAllocation] = []
        self._action_space_sizes: List[int] = []
        self._counterfactual_variances: List[float] = []
        self._trajectory_divergences: List[float] = []
        self._cycle_count: int = 0
        self._default_action_space_size: int = 10

    @property
    def current_allocation(self) -> Optional[AttentionAllocation]:
        """Most recent attention allocation."""
        if not self._allocation_history:
            return None
        return self._allocation_history[-1]

    @property
    def mean_threat_ratio(self) -> float:
        """Rolling mean of threat allocation over the window."""
        if not self._allocation_history:
            return 0.0
        recent = self._allocation_history[-self.window_size:]
        return float(np.mean([a.threat_ratio for a in recent]))

    @property
    def mean_opportunity_ratio(self) -> float:
        """Rolling mean of opportunity allocation over the window."""
        if not self._allocation_history:
            return 0.0
        recent = self._allocation_history[-self.window_size:]
        return float(np.mean([a.opportunity_ratio for a in recent]))

    @property
    def mean_maintenance_ratio(self) -> float:
        """Rolling mean of maintenance allocation over the window."""
        if not self._allocation_history:
            return 0.0
        recent = self._allocation_history[-self.window_size:]
        return float(np.mean([a.maintenance_ratio for a in recent]))

    def record_allocation(self, allocation: AttentionAllocation) -> None:
        """Record an attention budget allocation for this cycle."""
        self._cycle_count += 1
        self._allocation_history.append(allocation)
        if len(self._allocation_history) > self.window_size * 2:
            self._allocation_history = self._allocation_history[-self.window_size:]

    def record_action_space(self, action_space_size: int) -> None:
        """Record the perceived action-space size (Identity Entropy input).

        Under threat-dominated cognition, |A_t| shrinks because the system
        narrows focus to defensive options. Under opportunity-dominated,
        |A_t| expands.
        Args:
            action_space_size: the action_space_size argument for this call.
        """
        self._action_space_sizes.append(action_space_size)
        if len(self._action_space_sizes) > self.window_size:
            self._action_space_sizes = self._action_space_sizes[-self.window_size:]

    def record_counterfactual_variance(self, variance: float) -> None:
        """Record the variance of simulated futures (Counterfactual Diversity).

        Decision quality is bounded by the variance of simulated futures.
        Low diversity means the system is blind to alternative trajectories.
        """
        self._counterfactual_variances.append(variance)
        if len(self._counterfactual_variances) > self.window_size:
            self._counterfactual_variances = self._counterfactual_variances[-self.window_size:]

    def record_trajectory_divergence(self, predicted: np.ndarray,
                                     actual: np.ndarray) -> None:
        """Record observed divergence between projected and actual state.

        High divergence indicates the simulation model is misaligned with
        reality — often because attention was fixated on the wrong signals.
        Args:
            predicted: the predicted value
        """
        divergence = float(np.linalg.norm(predicted - actual))
        self._trajectory_divergences.append(divergence)
        if len(self._trajectory_divergences) > self.window_size:
            self._trajectory_divergences = self._trajectory_divergences[-self.window_size:]

    @property
    def identity_entropy(self) -> float:
        """Rolling mean action-space size.

        High entropy = many options perceived (opportunity-dominated).
        Low entropy = few options perceived (threat-dominated).
        This directly shapes decision quality per the Law.
        """
        if not self._action_space_sizes:
            return float(self._default_action_space_size)
        recent = self._action_space_sizes[-min(self.window_size, len(self._action_space_sizes)):]
        return float(np.mean(recent))

    @property
    def entropy_collapse_rate(self) -> float:
        """Rate of change of action-space size.

        Negative values indicate contraction under threat-dominated cognition.
        The more negative, the faster the system is narrowing its options.
        """
        if len(self._action_space_sizes) < 3:
            return 0.0
        recent = self._action_space_sizes[-min(self.window_size, len(self._action_space_sizes)):]
        if len(recent) < 2:
            return 0.0
        xs = np.arange(len(recent), dtype=float)
        ys = np.array(recent, dtype=float)
        mean_x = np.mean(xs)
        mean_y = np.mean(ys)
        num = float(np.sum((xs - mean_x) * (ys - mean_y)))
        den = float(np.sum((xs - mean_x) ** 2)) + 1e-9
        return num / den

    @property
    def counterfactual_diversity(self) -> float:
        """Rolling mean of counterfactual variance.

        High diversity = rich counterfactual generation → better decisions.
        Low diversity = attention locked on narrow set of futures.
        Bounded by how much attention is allocated to opportunity exploration.
        """
        if not self._counterfactual_variances:
            return 0.0
        recent = self._counterfactual_variances[-min(self.window_size, len(self._counterfactual_variances)):]
        return float(np.mean(recent))

    @property
    def attention_momentum(self) -> float:
        """How locked-in the attention policy is (0 = flexible, 1 = rigid).

        Computed as the autocorrelation of threat_ratio over the window.
        High momentum → system keeps allocating attention the same way
        regardless of changing conditions — a pathological pattern.
        Per the Law, identical initial states diverge exponentially under
        different attention policies, but a locked-in policy cannot adapt.
        """
        if len(self._allocation_history) < 3:
            return 0.0
        ratios = [a.threat_ratio for a in self._allocation_history[-self.window_size:]]
        if len(ratios) < 3:
            return 0.0
        arr = np.array(ratios)
        mean_r = float(np.mean(arr))
        # Lag-1 autocorrelation as momentum proxy
        num = float(np.sum((arr[1:] - mean_r) * (arr[:-1] - mean_r)))
        den = float(np.sum((arr - mean_r) ** 2)) + 1e-9
        return float(np.clip(abs(num) / den, 0.0, 1.0))

    @property
    def is_attention_locked(self) -> bool:
        """True if attention policy is pathologically rigid.

        A locked attention policy violates the Law because it prevents
        the system from generating diverse counterfactual futures,
        leading to exponential divergence from optimal trajectories.
        """
        return self.attention_momentum > 0.85 and self.mean_threat_ratio > 0.6

    @property
    def is_identity_collapse(self) -> bool:
        """True if action-space is contracting dangerously.

        Identity collapse is the mechanism by which threat-dominated
        cognition degrades decision quality. The system perceives fewer
        and fewer options until only reactive/defensive choices remain.
        """
        threshold = self._default_action_space_size * 0.4
        return (self.entropy_collapse_rate < -0.5
                and self.identity_entropy < threshold)

    def project_trajectory(self, current_state: np.ndarray,
                           horizon: int = 3) -> TrajectoryProjection:
        """Predict trajectory divergence given current attention policy.

        The Law states: attention allocation → counterfactual generation →
        trajectory shape. This projection quantifies that causal chain.

        The expected divergence captures how much the trajectory will
        deviate from optimal given:
          - Momentum penalty: rigid policies diverge more under change
          - Diversity penalty: low diversity = blind to alternatives
          - Entropy penalty: contracted action-space = reactive not strategic
          - Threat penalty: high threat = narrow focus, more divergence

        Args:
            current_state: The current world state vector
            horizon: How many steps ahead to project

        Returns:
            TrajectoryProjection with expected divergence and metrics
        """
        # Base divergence proportional to state norm
        divergence_base = float(np.linalg.norm(current_state)) * 0.1 + 0.1

        # Each penalty multiplies divergence by 1x-3x
        momentum_penalty = 1.0 + self.attention_momentum * 2.0
        diversity_penalty = 1.0 + max(0.0, (1.0 - self.counterfactual_diversity * 5.0))
        entropy_deficit = max(0.0, (self._default_action_space_size - self.identity_entropy)
                              / self._default_action_space_size)
        entropy_penalty = 1.0 + entropy_deficit * 2.0
        threat_penalty = 1.0 + self.mean_threat_ratio * 1.5

        expected_divergence = (divergence_base * momentum_penalty
                               * diversity_penalty * entropy_penalty * threat_penalty)

        # Diversity budget: remaining capacity for counterfactual exploration
        max_diversity = 2.0
        diversity_budget = max(0.0, max_diversity - self.counterfactual_diversity)

        # Projected identity entropy
        projected_entropy = max(1.0, self.identity_entropy
                                + self.entropy_collapse_rate * horizon)

        return TrajectoryProjection(
            expected_divergence=expected_divergence,
            attention_momentum=self.attention_momentum,
            diversity_budget=diversity_budget,
            projected_identity_entropy=projected_entropy,
        )

    @property
    def stats(self) -> Dict:
        """Complete attention metrics snapshot for DecisionTrace."""
        return {
            "identity_entropy": self.identity_entropy,
            "entropy_collapse_rate": self.entropy_collapse_rate,
            "counterfactual_diversity": self.counterfactual_diversity,
            "attention_momentum": self.attention_momentum,
            "mean_threat_ratio": self.mean_threat_ratio,
            "mean_opportunity_ratio": self.mean_opportunity_ratio,
            "mean_maintenance_ratio": self.mean_maintenance_ratio,
            "is_attention_locked": self.is_attention_locked,
            "is_identity_collapse": self.is_identity_collapse,
            "trajectory_divergences": (
                self._trajectory_divergences[-5:]
                if self._trajectory_divergences else []
            ),
            "allocation_count": len(self._allocation_history),
            "default_action_space": self._default_action_space_size,
        }
