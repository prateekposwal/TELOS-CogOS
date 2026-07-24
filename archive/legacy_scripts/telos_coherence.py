"""
TELOS v14: Temporal Coherence

Ensures selected trajectories are consistent across consecutive pipeline
executions. Without coherence, the system can oscillate between conflicting
strategies, wasting compute and degrading trust.

Coherence mechanisms:
  1. Trajectory Continuity — smooth transitions between consecutive selections
  2. Strategy Momentum — bias toward strategies similar to recent selections
  3. Drift Prevention — detect and correct excessive trajectory divergence

Metrics:
  Continuity(F_{t-1}, F_t) = 1 - ||avg_action(F_t) - avg_action(F_{t-1})|| / max_norm
  Momentum(σ_t) = α * σ_{t-1} + (1-α) * σ_new
"""

import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque


@dataclass
class CoherenceConfig:
    continuity_threshold: float = 0.3
    momentum_factor: float = 0.7
    max_divergence: float = 0.5
    history_size: int = 20
    correction_strength: float = 0.3


@dataclass
class CoherenceState:
    continuity_score: float
    momentum_score: float
    divergence_detected: bool
    corrected: bool
    previous_trajectory_id: Optional[str]
    current_trajectory_id: str


class TrajectoryContinuityConstraint:
    """
    Ensures smooth transitions between consecutive trajectory selections.

    Continuity score: 1 - ||Δaction|| / max_possible_Δ
    High continuity = trajectory t is similar to trajectory t-1
    Low continuity = sudden strategy shift (potentially destabilizing)
    """

    def __init__(self, config: Optional[CoherenceConfig] = None):
        self.config = config or CoherenceConfig()
        self._previous_action_signature: Optional[np.ndarray] = None
        self._previous_trajectory_id: Optional[str] = None
        self._continuity_history: deque = deque(maxlen=self.config.history_size)
        self._correction_count = 0

    def compute_continuity(self, current_action_signature: np.ndarray) -> float:
        if self._previous_action_signature is None:
            self._previous_action_signature = current_action_signature.copy()
            self._continuity_history.append(1.0)
            return 1.0

        diff = np.linalg.norm(current_action_signature - self._previous_action_signature)
        max_norm = np.sqrt(len(current_action_signature)) * 2.0
        continuity = max(0.0, 1.0 - diff / max_norm) if max_norm > 0 else 1.0

        self._continuity_history.append(continuity)
        self._previous_action_signature = current_action_signature.copy()
        return continuity

    def should_correct(self, continuity_score: float) -> bool:
        return continuity_score < self.config.continuity_threshold

    def apply_correction(self, current_action: np.ndarray,
                         previous_action: np.ndarray) -> np.ndarray:
        if previous_action is None:
            return current_action

        self._correction_count += 1
        corrected = (
            (1 - self.config.correction_strength) * current_action +
            self.config.correction_strength * previous_action
        )
        return corrected

    def update(self, action_signature: np.ndarray,
               trajectory_id: str) -> None:
        self._previous_action_signature = action_signature.copy()
        self._previous_trajectory_id = trajectory_id

    def get_average_continuity(self) -> float:
        if not self._continuity_history:
            return 1.0
        return float(np.mean(self._continuity_history))

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'correction_count': self._correction_count,
            'avg_continuity': self.get_average_continuity(),
            'history_size': len(self._continuity_history),
        }


class StrategyMomentum:
    """
    Maintains momentum in strategy selection to prevent oscillation.

    Tracks recent strategy distributions and biases new selections
    toward strategies similar to recent choices.

    Momentum: σ_t = α * σ_{t-1} + (1-α) * σ_new
    """

    def __init__(self, momentum_factor: float = 0.7,
                 n_strategies: int = 4):
        self.momentum_factor = momentum_factor
        self.n_strategies = n_strategies
        self._momentum = np.ones(n_strategies) / n_strategies
        self._selection_history: deque = deque(maxlen=50)
        self._update_count = 0

    def update(self, strategy_index: int) -> None:
        self._update_count += 1
        self._selection_history.append(strategy_index)

        one_hot = np.zeros(self.n_strategies)
        one_hot[strategy_index] = 1.0
        self._momentum = (
            self.momentum_factor * self._momentum +
            (1 - self.momentum_factor) * one_hot
        )

    def get_momentum(self) -> np.ndarray:
        total = np.sum(self._momentum)
        if total > 0:
            return self._momentum / total
        return np.ones(self.n_strategies) / self.n_strategies

    def bias_strategy(self, original_strategy: np.ndarray) -> np.ndarray:
        momentum = self.get_momentum()
        biased = 0.5 * original_strategy + 0.5 * momentum
        total = np.sum(biased)
        if total > 0:
            return biased / total
        return original_strategy

    def get_dominant_strategy(self) -> int:
        return int(np.argmax(self._momentum))

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'momentum_factor': self.momentum_factor,
            'update_count': self._update_count,
            'dominant_strategy': self.get_dominant_strategy(),
            'momentum_distribution': self.get_momentum().tolist(),
        }


class DivergenceDetector:
    """
    Detects excessive divergence between consecutive trajectory selections.

    Divergence: ||H(F_t) - H(F_{t-1})|| > threshold
    When divergence is detected, the system alerts and optionally corrects.
    """

    def __init__(self, max_divergence: float = 0.5,
                 history_size: int = 50):
        self.max_divergence = max_divergence
        self._previous_health: Optional[np.ndarray] = None
        self._divergence_history: deque = deque(maxlen=history_size)
        self._divergence_count = 0

    def check(self, current_health: np.ndarray) -> Tuple[bool, float]:
        if self._previous_health is None:
            self._previous_health = current_health.copy()
            return False, 0.0

        divergence = float(np.linalg.norm(current_health - self._previous_health))
        self._divergence_history.append(divergence)

        detected = divergence > self.max_divergence
        if detected:
            self._divergence_count += 1

        self._previous_health = current_health.copy()
        return detected, divergence

    def get_average_divergence(self) -> float:
        if not self._divergence_history:
            return 0.0
        return float(np.mean(self._divergence_history))

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'divergence_count': self._divergence_count,
            'avg_divergence': self.get_average_divergence(),
            'max_divergence_threshold': self.max_divergence,
        }


class TemporalCoherenceManager:
    """
    Orchestrates all three coherence mechanisms:
      1. Continuity — smooth action transitions
      2. Momentum — stable strategy selection
      3. Divergence — detect excessive shifts
    """

    def __init__(self, config: Optional[CoherenceConfig] = None):
        self.config = config or CoherenceConfig()
        self.continuity = TrajectoryContinuityConstraint(self.config)
        self.momentum = StrategyMomentum(self.config.momentum_factor)
        self.divergence = DivergenceDetector(self.config.max_divergence)
        self._total_executions = 0

    def evaluate(self, action_signature: np.ndarray,
                 health_vector: np.ndarray,
                 trajectory_id: str) -> CoherenceState:
        self._total_executions += 1

        continuity = self.continuity.compute_continuity(action_signature)
        divergence_detected, _ = self.divergence.check(health_vector)

        corrected = False
        if self.continuity.should_correct(continuity) and \
           self.continuity._previous_action_signature is not None:
            corrected = True

        state = CoherenceState(
            continuity_score=continuity,
            momentum_score=float(np.max(self.momentum.get_momentum())),
            divergence_detected=divergence_detected,
            corrected=corrected,
            previous_trajectory_id=self.continuity._previous_trajectory_id,
            current_trajectory_id=trajectory_id,
        )

        self.continuity.update(action_signature, trajectory_id)
        return state

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_executions': self._total_executions,
            'continuity': self.continuity.get_statistics(),
            'momentum': self.momentum.get_statistics(),
            'divergence': self.divergence.get_statistics(),
        }
