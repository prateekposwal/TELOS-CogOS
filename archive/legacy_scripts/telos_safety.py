"""
TELOS v14: Safety Gate, Uncertainty Quantification, Multi-Objective Selection

Three tightly-coupled subsystems that ensure trajectory selection is:
  1. Safe: hard gate blocks execution of dangerous trajectories
  2. Principled: uncertainty quantification makes selection statistically sound
  3. Holistic: multi-objective Pareto selection across all health dimensions

Safety Gate:
  If min(H_i) < threshold for ANY dimension → block execution
  Fallback: generate emergency trajectory from current state

Uncertainty Quantification:
  Track sample counts and variance per trajectory
  Confidence interval: u ± z * σ / √n
  Confidence-weighted utility: U_eff = U - λ * (σ / √n)

Multi-Objective Selection:
  Pareto dominance: F_i dominates F_j iff ∀k H_k(F_i) ≥ H_k(F_j) ∧ ∃k H_k(F_i) > H_k(F_j)
  Pareto front: set of non-dominated trajectories
  Preference weighting: scalarize with user weights
"""

import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque, OrderedDict
from enum import Enum


HEALTH_DIMENSIONS = [
    'mission_integrity', 'knowledge', 'trust',
    'energy', 'attention', 'recovery',
]


# ═══════════════════════════════════════════════════════════
# 1. SAFETY GATE
# ═══════════════════════════════════════════════════════════

class SafetyLevel(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    SAFE = "safe"


@dataclass
class SafetyCheckResult:
    level: SafetyLevel
    passed: bool
    dimension_scores: Dict[str, float]
    violations: List[str]
    recommendation: str


@dataclass
class SafetyConfig:
    min_health_per_dimension: float = 0.15
    min_average_health: float = 0.25
    max_corruption: float = 0.95
    max_mission_drift: float = 0.80
    min_survival_probability: float = 0.10
    emergency_fallback_enabled: bool = True


class SafetyGate:
    """
    Hard safety gate that blocks execution of dangerous trajectories.

    Checks:
      1. No individual health dimension below min_health_per_dimension
      2. Average health above min_average_health
      3. Corruption below max_corruption
      4. Mission drift below max_mission_drift
      5. Survival probability above min_survival_probability

    If ANY check fails → block execution and generate fallback.
    """

    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self._gate_checks = 0
        self._gate_blocks = 0
        self._gate_passes = 0
        self._history: deque = deque(maxlen=200)

    def check(self, health_vector: np.ndarray,
              corruption: float = 0.0,
              mission_drift: float = 0.0,
              survival_probability: float = 1.0) -> SafetyCheckResult:
        self._gate_checks += 1
        violations = []

        dim_names = HEALTH_DIMENSIONS
        dim_scores = {}
        for i, name in enumerate(dim_names[:len(health_vector)]):
            dim_scores[name] = float(health_vector[i])

        for name, score in dim_scores.items():
            if score < self.config.min_health_per_dimension:
                violations.append(
                    f"{name}={score:.3f} < {self.config.min_health_per_dimension}"
                )

        avg_health = float(np.mean(health_vector)) if len(health_vector) > 0 else 0.0
        if avg_health < self.config.min_average_health:
            violations.append(
                f"avg_health={avg_health:.3f} < {self.config.min_average_health}"
            )

        if corruption > self.config.max_corruption:
            violations.append(
                f"corruption={corruption:.3f} > {self.config.max_corruption}"
            )

        if mission_drift > self.config.max_mission_drift:
            violations.append(
                f"drift={mission_drift:.3f} > {self.config.max_mission_drift}"
            )

        if survival_probability < self.config.min_survival_probability:
            violations.append(
                f"survival={survival_probability:.3f} < {self.config.min_survival_probability}"
            )

        passed = len(violations) == 0

        if passed:
            level = SafetyLevel.SAFE
            recommendation = "Proceed with execution"
            self._gate_passes += 1
        elif avg_health < self.config.min_average_health:
            level = SafetyLevel.CRITICAL
            recommendation = "BLOCK: Critical safety violation — generate emergency fallback"
            self._gate_blocks += 1
        else:
            level = SafetyLevel.WARNING
            recommendation = "CAUTION: Safety warnings present — consider fallback"
            self._gate_blocks += 1

        result = SafetyCheckResult(
            level=level,
            passed=passed,
            dimension_scores=dim_scores,
            violations=violations,
            recommendation=recommendation,
        )

        self._history.append({
            'level': level.value,
            'passed': passed,
            'n_violations': len(violations),
            'avg_health': avg_health,
            'timestamp': time.time(),
        })

        return result

    def should_block(self, result: SafetyCheckResult) -> bool:
        return not result.passed

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_checks': self._gate_checks,
            'total_blocks': self._gate_blocks,
            'total_passes': self._gate_passes,
            'block_rate': self._gate_blocks / self._gate_checks if self._gate_checks > 0 else 0.0,
        }


# ═══════════════════════════════════════════════════════════
# 2. UNCERTAINTY QUANTIFICATION
# ═══════════════════════════════════════════════════════════

@dataclass
class UncertaintyEstimate:
    mean: float
    variance: float
    std_error: float
    confidence_interval_95: Tuple[float, float]
    n_samples: int
    effective_confidence: float


class UncertaintyQuantifier:
    """
    Quantifies uncertainty in trajectory utility estimates.

    Tracks per-trajectory:
      - Sample count (how many times evaluated)
      - Running mean and variance (Welford's algorithm)
      - Standard error of the mean
      - 95% confidence interval

    Confidence-weighted utility:
      U_eff = U_raw - λ * (σ / √n)

    where λ controls risk aversion.
    """

    def __init__(self, risk_aversion: float = 0.5,
                 z_score_95: float = 1.96,
                 max_trajectories: int = 1000):
        self.risk_aversion = risk_aversion
        self.z_score_95 = z_score_95
        self.max_trajectories = max_trajectories
        self._trajectory_stats: Dict[str, Dict[str, float]] = {}
        self._access_order: OrderedDict = OrderedDict()
        self._total_estimates = 0

    def observe(self, trajectory_id: str, utility: float) -> None:
        self._total_estimates += 1

        if trajectory_id in self._trajectory_stats:
            self._access_order.move_to_end(trajectory_id)
        else:
            if len(self._trajectory_stats) >= self.max_trajectories:
                oldest, _ = self._access_order.popitem(last=False)
                del self._trajectory_stats[oldest]
            self._trajectory_stats[trajectory_id] = {
                'n': 0, 'mean': 0.0, 'M2': 0.0,
            }
            self._access_order[trajectory_id] = None

        stats = self._trajectory_stats[trajectory_id]
        stats['n'] += 1
        n = stats['n']
        delta = utility - stats['mean']
        stats['mean'] += delta / n
        delta2 = utility - stats['mean']
        stats['M2'] += delta * delta2

    def estimate(self, trajectory_id: str) -> UncertaintyEstimate:
        if trajectory_id not in self._trajectory_stats:
            return UncertaintyEstimate(
                mean=0.0, variance=1.0, std_error=1.0,
                confidence_interval_95=(-1.96, 1.96),
                n_samples=0, effective_confidence=0.0,
            )

        stats = self._trajectory_stats[trajectory_id]
        n = stats['n']
        mean = stats['mean']

        if n < 2:
            variance = 1.0
        else:
            variance = stats['M2'] / (n - 1)

        std_error = np.sqrt(variance / n) if n > 0 else 1.0
        ci_lower = mean - self.z_score_95 * std_error
        ci_upper = mean + self.z_score_95 * std_error

        ci_width = ci_upper - ci_lower
        effective_confidence = max(0.0, 1.0 - ci_width / 4.0)

        return UncertaintyEstimate(
            mean=mean,
            variance=variance,
            std_error=std_error,
            confidence_interval_95=(ci_lower, ci_upper),
            n_samples=n,
            effective_confidence=effective_confidence,
        )

    def confidence_weighted_utility(self, trajectory_id: str,
                                    raw_utility: float) -> float:
        est = self.estimate(trajectory_id)
        penalty = self.risk_aversion * est.std_error
        return raw_utility - penalty

    def batch_confidence_weighted(self, trajectory_ids: List[str],
                                  raw_utilities: List[float]) -> List[float]:
        return [
            self.confidence_weighted_utility(tid, util)
            for tid, util in zip(trajectory_ids, raw_utilities)
        ]

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_estimates': self._total_estimates,
            'tracked_trajectories': len(self._trajectory_stats),
            'risk_aversion': self.risk_aversion,
        }


# ═══════════════════════════════════════════════════════════
# 3. MULTI-OBJECTIVE SELECTION
# ═══════════════════════════════════════════════════════════

@dataclass
class ParetoFront:
    trajectories: List[Any]
    front_indices: List[int]
    n_total: int
    n_pareto: int
    dominance_matrix: Optional[np.ndarray] = None


class MultiObjectiveSelector:
    """
    Pareto-optimal trajectory selection across 6 health dimensions.

    Instead of collapsing H(M,K,T,E,A,R) into a scalar, finds trajectories
    that are NOT dominated by any other trajectory.

    Pareto dominance: F_i dominates F_j iff:
      ∀k: H_k(F_i) ≥ H_k(F_j)  AND  ∃k: H_k(F_i) > H_k(F_j)

    The Pareto front is the set of non-dominated trajectories.
    """

    def __init__(self, dim_names: Optional[List[str]] = None,
                 preference_weights: Optional[np.ndarray] = None):
        self.dim_names = dim_names or list(HEALTH_DIMENSIONS)
        if preference_weights is not None:
            self.preference_weights = preference_weights / np.sum(preference_weights)
        else:
            self.preference_weights = np.ones(len(self.dim_names)) / len(self.dim_names)
        self._selection_count = 0

    def find_pareto_front(self, health_vectors: List[np.ndarray]) -> ParetoFront:
        n = len(health_vectors)
        if n == 0:
            return ParetoFront([], [], 0, 0)

        is_dominated = [False] * n
        for i in range(n):
            for j in range(n):
                if i == j or is_dominated[j]:
                    continue
                if self._dominates(health_vectors[j], health_vectors[i]):
                    is_dominated[i] = True
                    break

        front_indices = [i for i in range(n) if not is_dominated[i]]

        return ParetoFront(
            trajectories=None,
            front_indices=front_indices,
            n_total=n,
            n_pareto=len(front_indices),
        )

    def _dominates(self, a: np.ndarray, b: np.ndarray) -> bool:
        better_or_equal = np.all(a >= b)
        strictly_better = np.any(a > b)
        return better_or_equal and strictly_better

    def scalarize(self, health_vector: np.ndarray,
                  weights: Optional[np.ndarray] = None) -> float:
        w = weights if weights is not None else self.preference_weights
        hv = np.array(health_vector[:len(w)])
        return float(np.dot(w, hv))

    def select_from_pareto(self, health_vectors: List[np.ndarray],
                           trajectory_ids: List[str],
                           utilities: Optional[List[float]] = None,
                           precomputed_front: Optional[ParetoFront] = None) -> int:
        if not health_vectors:
            return 0

        front = precomputed_front if precomputed_front is not None else self.find_pareto_front(health_vectors)

        if not front.front_indices:
            best = int(np.argmax([self.scalarize(hv) for hv in health_vectors]))
            self._selection_count += 1
            return best

        if len(front.front_indices) == 1:
            self._selection_count += 1
            return front.front_indices[0]

        pareto_utilities = []
        for idx in front.front_indices:
            if utilities is not None and idx < len(utilities):
                pareto_utilities.append((utilities[idx], idx))
            else:
                pareto_utilities.append((self.scalarize(health_vectors[idx]), idx))

        pareto_utilities.sort(key=lambda x: x[0], reverse=True)
        self._selection_count += 1
        return pareto_utilities[0][1]

    def rank_trajectories(self, health_vectors: List[np.ndarray],
                           utilities: Optional[List[float]] = None) -> List[int]:
        if not health_vectors:
            return []

        scores = []
        for i, hv in enumerate(health_vectors):
            score = self.scalarize(hv)
            if utilities is not None and i < len(utilities):
                score = 0.5 * score + 0.5 * utilities[i]
            scores.append((score, i))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [idx for _, idx in scores]

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_selections': self._selection_count,
            'n_dimensions': len(self.dim_names),
            'preference_weights': self.preference_weights.tolist(),
        }
