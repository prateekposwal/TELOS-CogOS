"""
TELOS Negative Search & Guided Space Contraction

Implements four core architectural extensions:
1. NetiNetiPruningEngine - Negative Search (iterative elimination)
2. ForestSearchRouter - Guided Search (mission-filtered space reduction)
3. StableRegionMonitor - Stable Operating Region supervision
4. ModerationOptimizer - Resource-constrained multi-objective optimization

Core principle: Shift from brute-force generation to iterative space contraction.
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
import time
import hashlib


@dataclass
class PruningResult:
    surviving_candidates: List[np.ndarray]
    eliminated_count: int
    initial_count: int
    pruning_ratio: float
    elimination_details: List[Dict] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class NetiNetiPruningEngine:
    """Negative Search Architecture: iterative elimination before inference.

    C_{k+1} = C_k \\ R_k

    Eliminates candidates violating mission invariants, norm bounds,
    value bounds, or numerical stability.
    """

    def __init__(self, alignment_threshold=0.3, norm_bounds=(0.1, 10.0),
                 value_bounds=(-5.0, 5.0), max_history=1000):
        self.alignment_threshold = alignment_threshold
        self.norm_bounds = norm_bounds
        self.value_bounds = value_bounds
        self._elimination_history = deque(maxlen=max_history)
        self._total_pruned = 0
        self._total_seen = 0

    def prune_candidates(self, candidates: List[np.ndarray], mission_vector: np.ndarray,
                          context: Optional[Dict] = None) -> PruningResult:
        if not candidates:
            return PruningResult([], 0, 0, 0.0)

        self._total_seen += len(candidates)
        surviving = []
        eliminated_details = []

        for i, cand in enumerate(candidates):
            reason = self._check_candidate(cand, mission_vector, context)
            if reason is None:
                surviving.append(cand)
            else:
                self._total_pruned += 1
                detail = {
                    'index': i, 'reason': reason,
                    'norm': float(np.linalg.norm(cand)),
                    'alignment': float(self._compute_alignment(cand, mission_vector)),
                }
                eliminated_details.append(detail)
                self._elimination_history.append({
                    **detail, 'timestamp': time.time(),
                    'candidate_hash': hashlib.md5(cand.tobytes()).hexdigest()[:8],
                })

        n = len(candidates)
        eliminated = n - len(surviving)
        return PruningResult(surviving, eliminated, n,
                             eliminated / n if n else 0.0, eliminated_details)

    def _check_candidate(self, candidate: np.ndarray, mission_vector: np.ndarray,
                          context: Optional[Dict] = None) -> Optional[str]:
        alignment = self._compute_alignment(candidate, mission_vector)
        if alignment < self.alignment_threshold:
            return f"misalignment: {alignment:.4f} < {self.alignment_threshold}"

        norm = np.linalg.norm(candidate)
        if norm < self.norm_bounds[0] or norm > self.norm_bounds[1]:
            return f"norm_out_of_bounds: {norm:.4f}"

        min_v, max_v = np.min(candidate), np.max(candidate)
        if min_v < self.value_bounds[0] or max_v > self.value_bounds[1]:
            return f"value_out_of_bounds: [{min_v:.4f}, {max_v:.4f}]"

        if np.any(np.isnan(candidate)) or np.any(np.isinf(candidate)):
            return "numerical_instability"

        if context:
            if 'forbidden_patterns' in context:
                for pat in context['forbidden_patterns']:
                    if np.allclose(candidate, pat, atol=0.1):
                        return "forbidden_pattern_match"
            if 'max_complexity' in context:
                c = float(np.sum(np.abs(candidate)))
                if c > context['max_complexity']:
                    return f"complexity_exceeded: {c:.4f}"

        return None

    def _compute_alignment(self, candidate: np.ndarray, mission_vector: np.ndarray) -> float:
        cn = np.linalg.norm(candidate)
        mn = np.linalg.norm(mission_vector)
        if cn < 1e-9 or mn < 1e-9:
            return 0.0
        return float(np.dot(candidate, mission_vector) / (cn * mn))

    def get_statistics(self):
        return {
            'total_seen': self._total_seen,
            'total_pruned': self._total_pruned,
            'pruning_rate': self._total_pruned / self._total_seen if self._total_seen else 0.0,
            'history_size': len(self._elimination_history),
            'alignment_threshold': self.alignment_threshold,
        }

    def get_elimination_history(self, n: int = 10) -> List[Dict]:
        return list(self._elimination_history)[-n:]


@dataclass
class SearchResult:
    active_modules: List[str]
    eliminated_modules: List[str]
    relevance_scores: Dict[str, float]
    original_space_size: int
    reduced_space_size: int
    compression_ratio: float


class ForestSearchRouter:
    """Guided Search: S -> S_M via mission filter, |S_M| << |S|."""

    def __init__(self, mission_vector: np.ndarray, relevance_threshold: float = 0.2,
                 dynamic_threshold: bool = True) -> None:
        self.mission_vector = mission_vector / (np.linalg.norm(mission_vector) + 1e-9)
        self.base_threshold = relevance_threshold
        self.relevance_threshold = relevance_threshold
        self.dynamic_threshold = dynamic_threshold
        self._module_registry = {}
        self._query_history = deque(maxlen=100)
        self._access_counts = {}

    def register_module(self, name: str, embedding: np.ndarray) -> None:
        self._module_registry[name] = embedding / (np.linalg.norm(embedding) + 1e-9)
        if name not in self._access_counts:
            self._access_counts[name] = 0

    def register_modules(self, modules: Dict[str, np.ndarray]) -> None:
        for name, emb in modules.items():
            self.register_module(name, emb)

    def restrict_search_space(self, query_embedding: Optional[np.ndarray] = None,
                                theta: Optional[float] = None,
                                top_k: Optional[int] = None) -> SearchResult:
        threshold = theta if theta is not None else self.relevance_threshold

        if query_embedding is not None:
            qn = query_embedding / (np.linalg.norm(query_embedding) + 1e-9)
            effective = 0.7 * self.mission_vector + 0.3 * qn
            effective = effective / (np.linalg.norm(effective) + 1e-9)
        else:
            effective = self.mission_vector

        scores = {}
        for name, emb in self._module_registry.items():
            scores[name] = float(np.dot(emb, effective))

        sorted_mods = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        active, eliminated = [], []
        for name, rel in sorted_mods:
            if rel >= threshold and (top_k is None or len(active) < top_k):
                active.append(name)
                self._access_counts[name] = self._access_counts.get(name, 0) + 1
            else:
                eliminated.append(name)

        if self.dynamic_threshold and self._module_registry:
            self._adapt_threshold(scores)

        self._query_history.append({
            'timestamp': time.time(), 'n_active': len(active),
            'n_eliminated': len(eliminated), 'threshold': threshold,
        })

        orig = len(self._module_registry)
        reduced = len(active)
        return SearchResult(active, eliminated, scores, orig, reduced,
                           1.0 - (reduced / orig if orig else 0.0))

    def _adapt_threshold(self, scores: Dict[str, float]) -> None:
        vals = sorted(scores.values(), reverse=True)
        target = int(len(vals) * 0.3)
        if target < len(vals):
            std = np.std(vals)
            self.relevance_threshold = max(
                self.base_threshold * 0.5, vals[target] - 0.5 * std)

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_modules': len(self._module_registry),
            'total_queries': len(self._query_history),
            'current_threshold': self.relevance_threshold,
            'module_access_counts': dict(self._access_counts),
        }


@dataclass
class StabilityState:
    identity_entropy: float
    mission_drift: float
    attention_focus: float
    is_stable: bool
    violations: List[str]
    composite_score: float = 0.0
    timestamp: float = field(default_factory=time.time)


class StableRegionMonitor:
    """Monitors H_I, D, A to keep agent in stable operating region."""

    def __init__(self, max_entropy=0.75, max_drift=0.5, min_attention=0.3,
                 entropy_weight=0.4, drift_weight=0.4, attention_weight=0.2):
        self.max_entropy = max_entropy
        self.max_drift = max_drift
        self.min_attention = min_attention
        self.entropy_weight = entropy_weight
        self.drift_weight = drift_weight
        self.attention_weight = attention_weight
        self._history = deque(maxlen=1000)
        self._violation_count = 0
        self._stable_steps = 0
        self._total_steps = 0

    def evaluate_stability(self, identity_entropy: float, mission_drift: float,
                            attention_focus: float = 0.5) -> StabilityState:
        self._total_steps += 1
        violations = []

        if identity_entropy > self.max_entropy:
            violations.append(f"entropy: {identity_entropy:.4f} > {self.max_entropy}")
        if mission_drift > self.max_drift:
            violations.append(f"drift: {mission_drift:.4f} > {self.max_drift}")
        if attention_focus < self.min_attention:
            violations.append(f"attention: {attention_focus:.4f} < {self.min_attention}")

        is_stable = len(violations) == 0
        if is_stable:
            self._stable_steps += 1
        else:
            self._violation_count += 1

        e_s = max(0, 1.0 - identity_entropy / self.max_entropy) if self.max_entropy > 0 else 1.0
        d_s = max(0, 1.0 - mission_drift / self.max_drift) if self.max_drift > 0 else 1.0
        a_s = min(1.0, attention_focus / self.min_attention) if self.min_attention > 0 else 1.0
        composite = self.entropy_weight * e_s + self.drift_weight * d_s + self.attention_weight * a_s

        state = StabilityState(identity_entropy, mission_drift, attention_focus,
                              is_stable, violations, composite)
        self._history.append({'state': state, 'timestamp': time.time()})
        return state

    def compute_correction_vector(self, current_identity: np.ndarray,
                                    mission_vector: np.ndarray) -> np.ndarray:
        mn = mission_vector / (np.linalg.norm(mission_vector) + 1e-9)
        cn = current_identity / (np.linalg.norm(current_identity) + 1e-9)
        proj = np.dot(cn, mn) * mn
        drift_mag = np.linalg.norm(cn - proj)
        damping = min(1.0, drift_mag / self.max_drift)
        return 0.5 * damping * (proj - cn)

    def get_stability_ratio(self) -> float:
        return self._stable_steps / self._total_steps if self._total_steps else 1.0

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_steps': self._total_steps,
            'stable_steps': self._stable_steps,
            'violation_count': self._violation_count,
            'stability_ratio': self.get_stability_ratio(),
        }


@dataclass
class ModerationState:
    objective_value: float
    reward: float
    energy_penalty: float
    stress_penalty: float
    memory_penalty: float
    identity_penalty: float
    timestamp: float = field(default_factory=time.time)


class ModerationOptimizer:
    """J = Q - lambda_E*E(t) - lambda_S*S(t) - lambda_M*M(t) - lambda_I*H_I"""

    def __init__(self, lambda_e=0.1, lambda_s=0.15, lambda_m=0.1, lambda_i=0.2):
        self.lambda_e = lambda_e
        self.lambda_s = lambda_s
        self.lambda_m = lambda_m
        self.lambda_i = lambda_i
        self._history = deque(maxlen=1000)
        self._total_evaluations = 0

    def compute_objective(self, reward: float, energy: float = 100.0,
                           stress: float = 0.0, memory_usage: float = 0.0,
                           identity_entropy: float = 0.0) -> float:
        self._total_evaluations += 1
        e_pen = self.lambda_e * (100.0 - energy) / 100.0
        s_pen = self.lambda_s * stress
        m_pen = self.lambda_m * memory_usage
        i_pen = self.lambda_i * identity_entropy

        j = reward - e_pen - s_pen - m_pen - i_pen

        state = ModerationState(j, reward, e_pen, s_pen, m_pen, i_pen)
        self._history.append(state)
        return j

    def get_optimization_history(self, n: int = 10) -> List[ModerationState]:
        return list(self._history)[-n:]

    def get_statistics(self) -> Dict[str, Any]:
        if not self._history:
            return {'total_evaluations': 0}
        vals = [s.objective_value for s in self._history]
        return {
            'total_evaluations': self._total_evaluations,
            'mean_objective': float(np.mean(vals)),
            'min_objective': float(np.min(vals)),
            'max_objective': float(np.max(vals)),
        }


# ═══════════════════════════════════════════════════════════
# 5. UNIFIED NEGATIVE SEARCH RUNTIME
# ═══════════════════════════════════════════════════════════

class NegativeSearchRuntime:
    """Unified runtime integrating all four components."""

    def __init__(self, mission_vector: np.ndarray, alignment_threshold: float = 0.3,
                 module_registry: Optional[Dict[str, np.ndarray]] = None,
                 max_entropy: float = 0.75, max_drift: float = 0.5) -> None:
        self.mission_vector = mission_vector / (np.linalg.norm(mission_vector) + 1e-9)

        self.pruner = NetiNetiPruningEngine(alignment_threshold=alignment_threshold)
        self.router = ForestSearchRouter(self.mission_vector)
        self.stability = StableRegionMonitor(max_entropy=max_entropy, max_drift=max_drift)
        self.optimizer = ModerationOptimizer()

        if module_registry:
            self.router.register_modules(module_registry)

        self._step_count = 0
        self._total_pruned = 0
        self._total_pruning_input = 0

    def process_candidates(self, candidates: List[np.ndarray],
                            context: Optional[Dict] = None) -> PruningResult:
        self._step_count += 1
        result = self.pruner.prune_candidates(candidates, self.mission_vector, context)
        self._total_pruned += result.eliminated_count
        self._total_pruning_input += result.initial_count
        return result

    def select_modules(self, query_embedding: Optional[np.ndarray] = None,
                        theta: Optional[float] = None) -> SearchResult:
        return self.router.restrict_search_space(query_embedding, theta)

    def check_stability(self, identity_entropy: float, mission_drift: float,
                         attention_focus: float = 0.5) -> Tuple[StabilityState, Optional[np.ndarray]]:
        state = self.stability.evaluate_stability(identity_entropy, mission_drift, attention_focus)
        if not state.is_stable:
            return state, self.stability.compute_correction_vector(
                np.random.randn(len(self.mission_vector)), self.mission_vector)
        return state, None

    def optimize(self, reward: float, energy: float = 100.0, stress: float = 0.0,
                  memory: float = 0.0, entropy: float = 0.0) -> float:
        return self.optimizer.compute_objective(reward, energy, stress, memory, entropy)

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'step_count': self._step_count,
            'pruner': self.pruner.get_statistics(),
            'router': self.router.get_statistics(),
            'stability': self.stability.get_statistics(),
            'optimizer': self.optimizer.get_statistics(),
            'overall_pruning_rate': self._total_pruned / self._total_pruning_input if self._total_pruning_input else 0.0,
        }

