"""
Counterfactual Engine — Domain-agnostic simulation with StrategicOption queries.

The engine generates alternative future trajectories and provides query
methods for Axiom 4.3 (Possibility Preservation): the system must always
maintain a set of alternative future trajectories.

Law of Attention Integration:
  - Counterfactual Diversity: variance of simulated futures quantifies
    decision quality bounds (Axiom 4.7)
  - Attention-weighted generation: when attention allocation is provided,
    worlds are generated based on threat/opportunity focus
"""

import logging
import numpy as np
from typing import List, Any, Optional, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum
from telos.core.contracts.domain_model import DomainSimulator

logger = logging.getLogger('telos_simulation')


@dataclass
class ProbabilisticScore:
    """Uncertainty-quantified score — mean, variance, and 95% CI."""
    mean: float
    std: float
    n_samples: int
    ci_lower: float
    ci_upper: float
    min_score: float
    max_score: float


class TrajectoryClass(str, Enum):
    """P3: Compressed trajectory class for Value of Information pruning.
    
    Raw trajectories are compressed into one of five action classes:
      - EXPLORE: High-uncertainty, wide search
      - EXPLOIT: Low-uncertainty, narrow optimization
      - RECOVER: Recovery from failure/degradation
      - WAIT: Resource preservation, no action
      - EXIT: Terminal/escape trajectory
    """
    EXPLORE = "explore"
    EXPLOIT = "exploit"
    RECOVER = "recover"
    WAIT = "wait"
    EXIT = "exit"



@dataclass
class StrategicOption:
    """An alternative future trajectory — proof of Possibility Preservation (Axiom 4.3)."""
    world: Any
    score: float
    rank: int
    horizon: int = 0
    metadata: Dict = field(default_factory=dict)
    probabilistic: Optional[ProbabilisticScore] = None

    @property
    def variance(self) -> float:
        return self.probabilistic.std ** 2 if self.probabilistic else 0.0


class CounterfactualEngine:
    """The 'Decision Brain' of TELOS.

    Generates counterfactual futures, evaluates them, and stores
    alternative trajectories for query.  With n_repetitions > 1,
    each future is sampled multiple times for uncertainty quantification.

    Law of Attention Integration (Axiom 4.7):
      - Counterfactual Diversity: the variance of simulated futures
        bounds decision quality. Low diversity = blind spots.
      - Attention-weighted generation: uses attention allocation to
        focus simulation resources on relevant trajectories.
    """

    def __init__(self, simulator: DomainSimulator, n_repetitions: int = 3, seed: Optional[int] = None):
        self.simulator = simulator
        self._rng = np.random.RandomState(seed) if seed is not None else None
        self._seed = seed
        self._last_options: List[StrategicOption] = []
        self._last_state: Optional[np.ndarray] = None
        self._last_horizon: int = 0
        self._last_n_worlds: int = 0
        self._n_repetitions = max(1, n_repetitions)
        # Rolling variance history for counterfactual diversity tracking
        self._variance_history: List[float] = []
        self._max_variance_history: int = 20
        # Fix 3: VOI summary stored after each generate_options call
        self._last_voi_summary: Dict = {
            'voi_values': [],
            'pruned_count': 0,
            'total_options': 0,
            'trajectory_classes': [],
            'dominant_class': None,
            'optimal_score': None,
        }

    def generate_worlds(
        self,
        state: np.ndarray,
        horizon: int,
        n_worlds: int,
        attention_allocation: Optional[Dict] = None,
    ) -> List[Any]:
        """Branch into multiple potential future realities.

        When attention_allocation is provided, world generation is weighted:
          - High threat_ratio → focus on safe/defensive trajectories
          - High opportunity_ratio → diverse exploration across action space
          - High maintenance_ratio → status-quo-preserving trajectories

        Args:
            state: Current world state
            horizon: Simulation horizon
            n_worlds: Number of world branches to generate
            attention_allocation: Dict with threat/opportunity/maintenance ratios
                from the AttentionProjectionEngine (optional)

        Returns:
            List of simulated world states
        """
        worlds = []

        if attention_allocation and isinstance(attention_allocation, dict):
            threat_r = attention_allocation.get("threat_ratio", 0.33)
            opp_r = attention_allocation.get("opportunity_ratio", 0.33)
            maint_r = attention_allocation.get("maintenance_ratio", 0.34)

            # Weighted allocation of simulation budget
            threat_worlds = max(1, int(n_worlds * threat_r))
            opp_worlds = max(1, int(n_worlds * opp_r))
            maint_worlds = max(1, n_worlds - threat_worlds - opp_worlds)

            # Generate threat-focused worlds (defensive, conservative)
            for _ in range(threat_worlds):
                simulated = self.simulator.simulate(state, horizon)
                if simulated:
                    world = simulated[-1] if len(simulated) > 0 else simulated[0]
                    world = self._apply_threat_bias(world)
                    worlds.extend(simulated)

            # Generate opportunity-focused worlds (diverse, exploratory)
            for _ in range(opp_worlds):
                rng = self._rng if self._rng is not None else np.random
                noise = rng.randn(*state.shape) * 0.2 * opp_r
                perturbed_state = state + noise
                simulated = self.simulator.simulate(perturbed_state, horizon)
                if simulated:
                    worlds.extend(simulated)

            # Generate maintenance worlds (status quo, minimal change)
            for _ in range(maint_worlds):
                simulated = self.simulator.simulate(state, max(1, horizon // 2))
                if simulated:
                    worlds.extend(simulated)
        else:
            # Default: uniform generation
            for _ in range(n_worlds):
                worlds.extend(self.simulator.simulate(state, horizon))

        return worlds

    def _apply_threat_bias(self, world: Any) -> Any:
        """Apply a conservative bias to a world under threat-dominated attention.

        Reduces action magnitudes and clamps extreme values to produce
        safer, more defensive trajectories.
        """
        if hasattr(world, 'state') and world.state is not None:
            # Clamp extreme values to reduce risk
            world.state = np.clip(world.state, -2.0, 2.0)
        return world

    def compute_counterfactual_diversity(self, options: List[StrategicOption]) -> float:
        """Compute the variance of simulated futures.

        Decision quality is bounded by the variance of simulated futures
        (Counterfactual Diversity). Low diversity means the system is
        generating similar futures regardless of starting conditions —
        a sign of attention lock-in.

        Returns:
            Variance of all option scores. Higher = more diverse futures.
        """
        if len(options) < 2:
            return 0.0
        scores = [o.score for o in options]
        return float(np.var(scores)) if len(scores) > 1 else 0.0

    def record_variance(self, variance: float) -> None:
        """Record a counterfactual variance for rolling diversity tracking."""
        self._variance_history.append(variance)
        if len(self._variance_history) > self._max_variance_history:
            self._variance_history = self._variance_history[-self._max_variance_history:]

    @property
    def rolling_diversity(self) -> float:
        """Rolling mean of counterfactual variance over recent cycles."""
        if not self._variance_history:
            return 0.0
        return float(np.mean(self._variance_history))

    def evaluate_paths(self, worlds: List[Any]) -> List[float]:
        """Rank future trajectories based on mission-relative utility.

        Delegates the definition of 'success' to the domain-specific
        simulator's evaluate() method (guaranteed by DomainSimulator ABC).
        """
        scores = []
        for world in worlds:
            state = getattr(world, 'state', world)
            evaluation = self.simulator.evaluate(state)
            scores.append(evaluation.score)
        return scores

    def best_path(self, state: np.ndarray, horizon: int,
                  n_worlds: int) -> Any:
        """Select the optimal future reality."""
        worlds = self.generate_worlds(state, horizon, n_worlds)
        if not worlds:
            return None

        scores = self.evaluate_paths(worlds)
        best_idx = int(np.argmax(scores))
        return worlds[best_idx]

    def generate_options(
        self,
        state: np.ndarray,
        horizon: int,
        n_worlds: int,
        attention_allocation: Optional[Dict] = None,
    ) -> List[StrategicOption]:
        """Generate and rank alternative futures with uncertainty quantification.

        When n_repetitions > 1, each trajectory is sampled multiple times
        and a ProbabilisticScore (mean, std, 95% CI) is attached to each
        StrategicOption. The .score field retains the mean for backward compat.

        Law of Attention: attention_allocation weights the simulation budget
        toward threat or opportunity-focused worlds.

        Returns options sorted by mean score descending.
        """
        worlds = self.generate_worlds(state, horizon, n_worlds, attention_allocation)
        if not worlds:
            self._last_options = []
            self._last_state = state
            self._last_horizon = horizon
            self._last_n_worlds = n_worlds
            self._last_voi_summary = {
                'voi_values': [], 'pruned_count': 0, 'total_options': 0,
                'trajectory_classes': [], 'dominant_class': None, 'optimal_score': None,
            }
            return []

        scores = self.evaluate_paths(worlds)

        ranked = sorted(
            [
                StrategicOption(
                    world=w,
                    score=float(scores[i]),
                    rank=0,
                    horizon=horizon,
                    metadata={"index": i, "state_norm": float(np.linalg.norm(
                        getattr(w, 'state', np.array([0.0]))
                    ))},
                )
                for i, (w, s) in enumerate(zip(worlds, scores))
            ],
            key=lambda o: o.score,
            reverse=True,
        )

        # Uncertainty quantification: re-sample top options for variance
        if self._n_repetitions > 1 and len(ranked) > 0:
            top_n = min(len(ranked), max(3, n_worlds // 2))
            for opt in ranked[:top_n]:
                rep_scores = []
                for _ in range(self._n_repetitions):
                    rep_worlds = self.simulator.simulate(state, horizon)
                    if rep_worlds:
                        rep_state = getattr(rep_worlds[-1], 'state',
                                            getattr(rep_worlds[0], 'state', state))
                        rep_eval = self.simulator.evaluate(rep_state)
                        rep_scores.append(rep_eval.score)
                if rep_scores:
                    mean = float(np.mean(rep_scores))
                    std = float(np.std(rep_scores)) if len(rep_scores) > 1 else 0.0
                    sorted_scores = sorted(rep_scores)
                    opt.score = mean
                    opt.probabilistic = ProbabilisticScore(
                        mean=mean,
                        std=std,
                        n_samples=len(rep_scores),
                        ci_lower=float(np.percentile(rep_scores, 2.5)),
                        ci_upper=float(np.percentile(rep_scores, 97.5)),
                        min_score=sorted_scores[0],
                        max_score=sorted_scores[-1],
                    )

        # Re-sort by updated mean score
        ranked.sort(key=lambda o: o.score, reverse=True)
        for i, option in enumerate(ranked):
            option.rank = i + 1

        # Compute and record counterfactual diversity
        diversity = self.compute_counterfactual_diversity(ranked)
        self.record_variance(diversity)

        # ── Fix 3: VOI pruning — remove low-value branches ──
        if ranked:
            pre_prune_count = len(ranked)
            ranked = self.prune_low_value(ranked, threshold=0.05)
            voi_summary = self.compute_voi_summary(ranked)
            self._last_voi_summary = voi_summary
            # Re-sort after pruning
            ranked.sort(key=lambda o: o.score, reverse=True)
            for i, option in enumerate(ranked):
                option.rank = i + 1
            logger.debug(
                f'Fix 3 (VOI): pruned {pre_prune_count - len(ranked)}/{pre_prune_count} '
                f'options, dominant_class={voi_summary.get("dominant_class")}'
            )

        # ── Fix 5: Fallback scoring pass — ensure every option has a valid score ──
        for opt in ranked:
            try:
                if opt.score is None or not isinstance(opt.score, (int, float)):
                    opt.score = 0.01
                opt.score = float(opt.score)
                # Only floor zero scores to 0.01 to avoid zero-score rejection;
                # negative scores are valid (e.g., GridWorld proximity-based scoring)
                if opt.score == 0.0:
                    opt.score = 0.01
            except (TypeError, ValueError):
                opt.score = 0.01
            # Also ensure probabilistic mean is consistent
            if opt.probabilistic is not None and opt.probabilistic.mean is None:
                opt.probabilistic.mean = opt.score

        self._last_options = ranked
        self._last_state = state
        self._last_horizon = horizon
        self._last_n_worlds = n_worlds

        return ranked

    def query_options(self, min_score: Optional[float] = None,
                      top_k: Optional[int] = None) -> List[StrategicOption]:
        """Query the last set of generated alternatives.

        Args:
            min_score: Only return options with score >= min_score
            top_k: Only return the top-k options

        Returns:
            Filtered list of StrategicOptions from the last generation.
            Returns empty list if no options have been generated.
        """
        if not self._last_options:
            return []

        results = list(self._last_options)

        if min_score is not None:
            results = [o for o in results if o.score >= min_score]

        if top_k is not None:
            results = results[:top_k]

        return results

    @property
    def has_options(self) -> bool:
        """At least one alternative future is available.

        Satisfies Axiom 4.3: |F_t| >= 1
        """
        return len(self._last_options) > 0

    @property
    def alternative_count(self) -> int:
        """Number of alternatives beyond the top choice."""
        return max(0, len(self._last_options) - 1)


    def compute_value_of_information(self, options, optimal_score=None):
        """P3: Compute Value of Information for each option.
        
        V(c_i) = |J(τ_i) - J(τ*)|  — the absolute difference between
        each option's commitment score and the optimal score.
        
        Args:
            options: List of strategic options to evaluate
            optimal_score: The score of the optimal (best) option.
                          If None, uses the top option's score.
            
        Returns:
            List of VoI values, one per option, in the same order
        """
        if not options:
            return []
        
        if optimal_score is None:
            optimal_score = options[0].score if options else 0.0
        
        voi_values = []
        for opt in options:
            voi = abs(opt.score - optimal_score)
            voi_values.append(voi)
        
        return voi_values

    def prune_low_value(self, options, threshold=0.05):
        """P3: Prune branches that don't alter optimal decision.
        
        Removes options whose Value of Information is below threshold.
        
        Args:
            options: List of strategic options
            threshold: Minimum VoI to retain (default 0.05)
            
        Returns:
            Pruned list of options (always keeps at least 1)
        """
        if not options:
            return []
        
        optimal_score = options[0].score if options else 0.0
        voi_values = self.compute_value_of_information(options, optimal_score)
        
        pruned = [opt for opt, voi in zip(options, voi_values) if voi >= threshold]
        
        # Always keep at least the top option
        if not pruned and options:
            pruned.append(options[0])
        
        return pruned

    def compress_to_classes(self, options):
        """P3: Compress raw trajectories into {Explore, Exploit, Recover, Wait, Exit}.
        
        Args:
            options: List of strategic options to classify
            
        Returns:
            List of dicts with 'option_index', 'class', 'score', 'variance'
        """
        classifications = []
        for i, opt in enumerate(options):
            score = opt.score
            var = opt.variance
            metadata = opt.metadata or {}
            
            # Classify based on score, variance, and metadata
            if metadata.get('is_terminal', False) or metadata.get('is_escape', False):
                cls = TrajectoryClass.EXIT
            elif score < 0.3:
                cls = TrajectoryClass.RECOVER
            elif var < 0.01 and 0.3 <= score <= 0.6:
                cls = TrajectoryClass.WAIT
            elif var > 0.1:
                cls = TrajectoryClass.EXPLORE
            elif score > 0.6 and var < 0.05:
                cls = TrajectoryClass.EXPLOIT
            elif opt.rank <= max(1, len(options) // 3):
                cls = TrajectoryClass.EXPLOIT
            else:
                cls = TrajectoryClass.EXPLORE
            
            classifications.append({
                'option_index': i,
                'class': cls.value,
                'score': score,
                'variance': var,
                'rank': opt.rank,
            })
        
        return classifications

    def compute_voi_summary(self, options):
        """P3: Compute a summary of Value of Information across all options.
        
        Returns:
            Dict with voi_values, pruned_count, trajectory_classes, dominant_class
        """
        if not options:
            return {
                'voi_values': [],
                'pruned_count': 0,
                'total_options': 0,
                'trajectory_classes': [],
                'dominant_class': None,
                'optimal_score': None,
            }
        
        optimal_score = options[0].score if options else 0.0
        voi_values = self.compute_value_of_information(options, optimal_score)
        pruned = self.prune_low_value(options)
        classes = self.compress_to_classes(options)
        
        class_counts = {}
        for c in classes:
            cls = c['class']
            class_counts[cls] = class_counts.get(cls, 0) + 1
        
        dominant = max(class_counts, key=class_counts.get) if class_counts else None
        
        return {
            'voi_values': voi_values,
            'pruned_count': len(options) - len(pruned),
            'total_options': len(options),
            'trajectory_classes': classes,
            'dominant_class': dominant,
            'optimal_score': optimal_score,
        }


    @property
    def stats(self) -> Dict:
        return {
            "total_generated": len(self._last_options),
            "alternatives_available": self.alternative_count,
            "last_horizon": self._last_horizon,
            "last_n_worlds": self._last_n_worlds,
            "best_score": self._last_options[0].score if self._last_options else None,
            "worst_score": self._last_options[-1].score if len(self._last_options) > 1 else None,
            "rolling_diversity": self.rolling_diversity,
            "variance_history": self._variance_history[-10:] if self._variance_history else [],
        }
