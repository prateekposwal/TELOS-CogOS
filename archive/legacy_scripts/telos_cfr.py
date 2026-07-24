"""
TELOS v14: Regret Tracking Engine

Implements regret-based trajectory evaluation and selection. Tracks how much
utility was "left on the table" by each selection and uses regret matching
to bias future selections toward historically better trajectories.

Note: This is a single-player regret tracker, not full multi-player CFR.
The "counterfactual" aspect is approximated by comparing against the best
alternative at each step, rather than computing full counterfactual values
against a model of other players. Convergence guarantees from full CFR
do not strictly apply here, but the empirical behavior is similar:
regret decreases over time as the engine learns which trajectories
consistently underperform.

Key equations:
  R(F_i) = max(0, u(F*_t) - u(F_i,t))   (one-sided instant regret)
  σ(F_i) = max(0, R(F_i)) / Σ_j max(0, R(F_j))   (regret-matched strategy)

Over time, the strategy converges to minimize regret against the best
alternative trajectory.
"""

import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque


@dataclass
class RegretSnapshot:
    """State of regret at a single time step."""
    step: int
    utilities: List[float]
    selected_index: int
    instant_regret: float
    cumulative_regret: np.ndarray
    strategy: np.ndarray
    timestamp: float


@dataclass
class TrajectoryRegretReport:
    """Final regret analysis for a set of trajectories."""
    n_trajectories: int
    n_steps: int
    average_strategy: np.ndarray
    final_cumulative_regret: np.ndarray
    converged: bool
    avg_instant_regret: float
    max_cumulative_regret: float
    selections: List[int]


class CounterfactualRegretEngine:
    """
    Regret tracking engine for trajectory selection.

    At each decision round:
      1. Observe utilities of all candidate trajectories
      2. Compute instant regret = max(0, best_alternative - chosen)
      3. Update cumulative regret
      4. Use regret matching to produce next strategy

    Note: This is a single-player regret tracker, not full multi-player CFR.
    Convergence guarantees from full CFR do not strictly apply, but the
    empirical behavior is similar: regret decreases over time.

    Properties:
      - Average strategy converges to minimize regret (empirically)
      - Instant regret decreases over time (empirically)
      - Strategy becomes increasingly focused on top trajectories
    """

    def __init__(self, max_trajectories: int = 100,
                 regret_floor: float = 0.0,
                 convergence_threshold: float = 1e-4):
        self.max_trajectories = max_trajectories
        self.regret_floor = regret_floor
        self.convergence_threshold = convergence_threshold
        self._cumulative_regret: Optional[np.ndarray] = None
        self._cumulative_strategy: Optional[np.ndarray] = None
        self._step_count = 0
        self._history: deque = deque(maxlen=500)
        self._total_regret_updates = 0

    def _resize_arrays(self, n: int) -> None:
        n = min(n, self.max_trajectories)
        if self._cumulative_regret is None:
            self._cumulative_regret = np.zeros(n)
            self._cumulative_strategy = np.zeros(n)
            return
        old_regret = self._cumulative_regret.copy()
        old_strategy = self._cumulative_strategy.copy()
        self._cumulative_regret = np.zeros(n)
        self._cumulative_strategy = np.zeros(n)
        copy_len = min(len(old_regret), n)
        self._cumulative_regret[:copy_len] = old_regret[:copy_len]
        self._cumulative_strategy[:copy_len] = old_strategy[:copy_len]

    def initialize(self, n_trajectories: int) -> None:
        n = min(n_trajectories, self.max_trajectories)
        self._cumulative_regret = np.zeros(n)
        self._cumulative_strategy = np.zeros(n)
        self._step_count = 0

    def update(self, utilities: List[float],
               selected_index: int) -> float:
        n = len(utilities)
        if self._cumulative_regret is None:
            self.initialize(n)
        elif len(self._cumulative_regret) != n:
            self._resize_arrays(n)

        utilities_arr = np.array(utilities[:n])
        chosen_utility = utilities_arr[selected_index]

        instant_regret = 0.0
        for i in range(n):
            if i != selected_index:
                regret = max(0.0, utilities_arr[i] - chosen_utility)
                self._cumulative_regret[i] += regret
                instant_regret = max(instant_regret, regret)

        strategy = self.get_strategy()
        self._cumulative_strategy += strategy
        self._step_count += 1
        self._total_regret_updates += 1

        snapshot = RegretSnapshot(
            step=self._step_count,
            utilities=utilities[:n],
            selected_index=selected_index,
            instant_regret=instant_regret,
            cumulative_regret=self._cumulative_regret.copy(),
            strategy=strategy,
            timestamp=time.time(),
        )
        self._history.append(snapshot)

        return instant_regret

    def get_strategy(self) -> np.ndarray:
        if self._cumulative_regret is None:
            return np.array([])

        positive = np.maximum(self._cumulative_regret, 0.0)
        total = np.sum(positive)
        if total > 1e-12:
            return positive / total
        n = len(positive)
        return np.ones(n) / n

    def get_average_strategy(self) -> np.ndarray:
        if self._cumulative_strategy is None:
            return np.array([])
        total = np.sum(self._cumulative_strategy)
        if total > 1e-12:
            return self._cumulative_strategy / total
        n = len(self._cumulative_strategy)
        return np.ones(n) / n

    def select_trajectory(self, utilities: List[float]) -> int:
        n = len(utilities)
        if self._cumulative_regret is None:
            self.initialize(n)
        elif len(self._cumulative_regret) != n:
            self._resize_arrays(n)

        strategy = self.get_strategy()
        strategy = strategy / strategy.sum() if strategy.sum() > 0 else strategy

        if np.random.random() < 0.05:
            return int(np.random.randint(n))

        return int(np.random.choice(n, p=strategy))

    def evaluate_selection_regret(self, utilities: List[float],
                                  selected_index: int) -> float:
        if len(utilities) <= 1:
            return 0.0
        best_alt = max(
            utilities[i] for i in range(len(utilities))
            if i != selected_index
        )
        return max(0.0, best_alt - utilities[selected_index])

    def is_converged(self) -> bool:
        if len(self._history) < 10:
            return False
        recent = list(self._history)[-10:]
        regrets = [h.instant_regret for h in recent]
        avg_recent = float(np.mean(regrets))
        return avg_recent < self.convergence_threshold

    def get_report(self) -> TrajectoryRegretReport:
        avg_strategy = self.get_average_strategy()
        selections = [h.selected_index for h in self._history]
        regrets = [h.instant_regret for h in self._history]

        return TrajectoryRegretReport(
            n_trajectories=len(self._cumulative_regret) if self._cumulative_regret is not None else 0,
            n_steps=self._step_count,
            average_strategy=avg_strategy,
            final_cumulative_regret=(
                self._cumulative_regret.copy()
                if self._cumulative_regret is not None
                else np.array([])
            ),
            converged=self.is_converged(),
            avg_instant_regret=float(np.mean(regrets)) if regrets else 0.0,
            max_cumulative_regret=(
                float(np.max(self._cumulative_regret))
                if self._cumulative_regret is not None
                else 0.0
            ),
            selections=selections,
        )

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_updates': self._total_regret_updates,
            'step_count': self._step_count,
            'converged': self.is_converged(),
            'max_trajectories': self.max_trajectories,
        }
