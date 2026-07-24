"""
Ω Operator — Q* = argmax[ΔJ(Q) - Cost(Q)]

Selects the optimal question to reduce decision-relevant uncertainty.

ΔJ(Q) = expected improvement in trajectory quality if Q is answered
Cost(Q) = computational cost of obtaining the answer

This operator is the core of the InquiryStream's question-generation logic.
It replaces old ad-hoc threshold rules (U > 0.7 → EXPLORE) with a principled
optimization over the question space.
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger('telos_omega')


class OmegaOperator:
    """Ω Operator: Q* = argmax[ΔJ(Q) - Cost(Q)]
    
    Ranks candidate questions by their expected net value in reducing
    decision-relevant uncertainty. A question is worth asking only if
    its Ω value > 0.5 (saturation threshold).
    
    Fixes applied:
      Fix 1: adaptive_cost() — lightweight pre-simulation for true cost estimation
      Fix 2: Question cache — prevents re-asking the same question within TTL cycles
      Fix 4: Multi-axis Ω vector — per-dimension (world, identity, other) omega values
      Fix 6: Smoother cost scaling — avoids division by near-zero in _compute_cost
    """

    def __init__(self):
        self._last_questions: List[Dict] = []
        self._max_history: int = 20
        
        # Fix 2: Question cache — prevent re-asking within TTL
        self._seen_questions: Dict[str, int] = {}  # question_id -> cycle_seen
        self._cache_ttl: int = 5  # cycles before a question can be re-asked
        self._cycle_counter: int = 0
        
        # Fix 4: Multi-axis omega vector from last compute()
        self._last_omega_vector: Dict[str, float] = {
            'world': 0.0,
            'identity': 0.0,
            'other': 0.0,
        }

    def compute(self, tripartite_u: Any, council_signals: List[Dict],
                meta_state: Optional[Dict] = None,
                budget: Optional[Dict] = None,
                sim_engine: Optional[Any] = None) -> Tuple[Optional[Dict], float, Dict[str, float]]:
        """Rank questions by Ω value and return the best one.
        
        Args:
            tripartite_u: TripartiteUncertainty instance with U_W, U_I, U_O
            council_signals: List of council validation signal dicts
            meta_state: Optional meta-cognition state dict
            budget: Optional budget dict with 'remaining_ms' key
            sim_engine: Optional CounterfactualEngine for adaptive cost estimation
            
        Returns:
            Tuple of (best_question_dict_or_None, omega_value, omega_vector)
            where omega_vector = {'world': float, 'identity': float, 'other': float}
        """
        # Fix 2: Increment cycle counter and prune stale cache entries
        self._cycle_counter += 1
        self._prune_cache()
        
        questions = self._generate_questions(tripartite_u, council_signals)
        
        # Fix 2: Filter out recently-seen questions
        questions = [q for q in questions if q['id'] not in self._seen_questions]
        
        budget_dict = budget or {"remaining_ms": 100.0}
        
        best_q = None
        best_val = -float('inf')
        scored = []
        
        for q in questions:
            # Fix 1: Use adaptive cost when sim_engine is available
            dj = self._expected_improvement(q, tripartite_u, council_signals)
            if sim_engine is not None:
                cost = self.adaptive_cost(q, sim_engine, budget_dict)
            else:
                cost = self._compute_cost(q, budget_dict)
            value = dj - cost
            scored.append((q, dj, cost, value))
            if value > best_val:
                best_q, best_val = q, value
        
        # Fix 4: Compute multi-axis omega vector
        omega_vector = self._compute_omega_vector(
            tripartite_u, council_signals, scored, questions
        )
        self._last_omega_vector = omega_vector
        
        # Fix 2: Add the selected question to cache
        if best_q is not None:
            self._seen_questions[best_q['id']] = self._cycle_counter
        
        # Record scored questions for transparency
        self._last_questions = [{
            "id": q.get("id", "unknown"),
            "type": q.get("type", "unknown"),
            "domain": q.get("domain", "unknown"),
            "delta_J": round(dj, 4),
            "cost": round(cost, 4),
            "omega": round(val, 4),
        } for q, dj, cost, val in scored]
        if len(self._last_questions) > self._max_history:
            self._last_questions = self._last_questions[-self._max_history:]
        
        return best_q, best_val, omega_vector

    def _expected_improvement(self, q: Dict, U: Any,
                               council: List[Dict]) -> float:
        """ΔJ(Q) — expected improvement in trajectory quality if Q is answered.
        
        Driven by:
        - U_O (other-agent/council disagreement) — highest weight because
          resolving disagreement directly unblocks pipeline decisions
        - U_W (environmental uncertainty) — understanding the world helps planning
        - Prior from the question itself (how likely is this to be relevant)
        """
        u_o = getattr(U, 'U_O', 0.0)
        u_w = getattr(U, 'U_W', 0.0)
        u_i = getattr(U, 'U_I', 0.0)
        
        # Disagreement bonus: if council has blocking signals, amplify
        disagreement_bonus = 0.0
        if council:
            passed_vals = [s.get('passed', True) for s in council]
            if passed_vals:
                block_ratio = sum(1 for p in passed_vals if not p) / len(passed_vals)
                disagreement_bonus = block_ratio * 0.3
        
        return (
            0.4 * u_o +          # Council disagreement drives inquiry most
            0.3 * u_w +          # Environmental uncertainty
            0.1 * u_i +          # Identity uncertainty
            0.2 * q.get('prior', 0.5) +  # Prior relevance of this question
            disagreement_bonus
        )

    # Fix 6: Smoother cost scaling — avoids division by near-zero
    def _compute_cost(self, q: Dict, budget: Dict) -> float:
        """Cost(Q) — computational cost of answering Q.
        
        Smooth scaling: est / (1 + remaining) avoids division by near-zero.
        """
        est = q.get('estimated_horizon', 3) * q.get('estimated_worlds', 5) * 0.5
        remaining = budget.get('remaining_ms', 100)
        return est / (1 + remaining)

    # Fix 1: Adaptive Question Cost — lightweight pre-simulation
    def adaptive_cost(self, question: Dict, sim_engine: Any,
                      budget: Dict) -> float:
        """Lightweight pre-simulation to estimate true cost of answering Q.
        
        Runs 2-3 worlds with horizon=2 to measure actual operations count,
        then scales by domain complexity.
        
        Falls back to hardcoded _compute_cost() if sim_engine is unavailable
        or the pre-simulation fails.
        
        Args:
            question: Question dict with 'estimated_horizon', 'estimated_worlds', 'domain'
            sim_engine: CounterfactualEngine instance for running pre-sim
            budget: Budget dict with 'remaining_ms' key
            
        Returns:
            Estimated cost for answering the question (float)
        """
        if sim_engine is None:
            return self._compute_cost(question, budget)
        
        try:
            n_worlds = min(question.get('estimated_worlds', 5), 3)
            horizon = min(question.get('estimated_horizon', 3), 2)
            
            # Domain complexity factor — harder domains cost more
            domain_complexity = {
                'world': 1.5,
                'identity': 1.2,
                'council': 1.8,
                'action': 1.0,
            }.get(question.get('domain', 'action'), 1.0)
            
            # Use last known state if available, otherwise zero vector
            dummy_state = getattr(sim_engine, '_last_state', None)
            if dummy_state is None:
                import numpy as np
                dummy_state = np.zeros(6)
            
            # Run lightweight pre-simulation
            start = time.time()
            worlds = sim_engine.generate_worlds(
                dummy_state, horizon=horizon, n_worlds=n_worlds
            )
            elapsed_ms = (time.time() - start) * 1000.0
            
            # Count actual operations
            actual_ops = len(worlds) if worlds else n_worlds * horizon
            estimated_ops = n_worlds * horizon * domain_complexity
            
            # Blend measured and estimated cost
            if elapsed_ms > 0:
                measured_cost = elapsed_ms / 100.0  # normalize to ~0-1 range
            else:
                measured_cost = estimated_ops / 50.0
            
            remaining = max(budget.get('remaining_ms', 100), 1)
            return min(1.0, measured_cost * domain_complexity / remaining)
        except Exception as e:
            logger.debug(
                f"Adaptive cost estimation failed: {e}, "
                f"falling back to hardcoded"
            )
            return self._compute_cost(question, budget)

    # Fix 4: Compute multi-axis omega vector
    def _compute_omega_vector(self, U: Any, council: List[Dict],
                               scored: List[Tuple],
                               questions: List[Dict]) -> Dict[str, float]:
        """Compute per-dimension omega values.
        
        Formulas:
          Ω_W = 0.5 * U_W + 0.3 * prior_world - cost_W
          Ω_I = 0.5 * U_I + 0.3 * prior_identity - cost_I
          Ω_O = 0.6 * U_O + 0.2 * council_disagreement - cost_O
        
        Returns:
            Dict with keys 'world', 'identity', 'other'
        """
        u_w = getattr(U, 'U_W', 0.0)
        u_i = getattr(U, 'U_I', 0.0)
        u_o = getattr(U, 'U_O', 0.0)
        
        # Compute average prior per domain
        def _avg_prior(domain: str) -> float:
            domain_qs = [q for q in questions if q.get('domain') == domain]
            if not domain_qs:
                return 0.0
            return sum(q.get('prior', 0.0) for q in domain_qs) / len(domain_qs)
        
        prior_w = _avg_prior('world')
        prior_i = _avg_prior('identity')
        prior_o = _avg_prior('council')
        
        # Compute average cost per domain from scored questions
        def _avg_cost(domain: str) -> float:
            domain_scored = [s for s in scored if s[0].get('domain') == domain]
            if not domain_scored:
                return 0.0
            return sum(s[2] for s in domain_scored) / len(domain_scored)
        
        cost_W = _avg_cost('world')
        cost_I = _avg_cost('identity')
        cost_O = _avg_cost('council')
        
        # Council disagreement ratio
        council_disagreement = 0.0
        if council:
            passed_vals = [s.get('passed', True) for s in council]
            if passed_vals:
                council_disagreement = (
                    sum(1 for p in passed_vals if not p) / len(passed_vals)
                )
        
        return {
            'world': 0.5 * u_w + 0.3 * prior_w - cost_W,
            'identity': 0.5 * u_i + 0.3 * prior_i - cost_I,
            'other': 0.6 * u_o + 0.2 * council_disagreement - cost_O,
        }

    def _generate_questions(self, U: Any, council: List[Dict]) -> List[Dict]:
        """Generate candidate questions from uncertainty dimensions.
        
        Each question is a dict with:
        - id: unique identifier
        - type: question type (explore, recalibrate, investigate, proceed)
        - domain: what aspect of uncertainty it targets (world, identity, council, action)
        - prior: how relevant this question is given current uncertainty levels
        - estimated_horizon: how many simulation steps to answer
        - estimated_worlds: how many parallel futures needed
        """
        u_w = getattr(U, 'U_W', 0.0)
        u_i = getattr(U, 'U_I', 0.0)
        u_o = getattr(U, 'U_O', 0.0)
        
        questions = []
        
        # Question: explore the terrain (high environmental uncertainty)
        if u_w > 0.3:
            questions.append({
                'id': 'explore_terrain',
                'type': 'explore',
                'domain': 'world',
                'prior': u_w,
                'estimated_horizon': 5,
                'estimated_worlds': 10,
            })
        
        # Question: recalibrate identity (high identity uncertainty)
        if u_i > 0.3:
            questions.append({
                'id': 'recalibrate_identity',
                'type': 'recalibrate',
                'domain': 'identity',
                'prior': u_i,
                'estimated_horizon': 3,
                'estimated_worlds': 5,
            })
        
        # Question: resolve council disagreement (high other-agent uncertainty)
        if u_o > 0.3:
            questions.append({
                'id': 'resolve_disagreement',
                'type': 'investigate',
                'domain': 'council',
                'prior': u_o,
                'estimated_horizon': 4,
                'estimated_worlds': 8,
            })
        
        # Fallback: check if any council signal indicates a specific blocker
        if council:
            blockers = [s for s in council if not s.get('passed', True)]
            if blockers:
                questions.append({
                    'id': f'address_blocker_{blockers[0].get("validator_name", "unknown")}',
                    'type': 'investigate',
                    'domain': 'council',
                    'prior': 0.7,
                    'estimated_horizon': 3,
                    'estimated_worlds': 6,
                })
        
        # Default navigation question (always available, low prior)
        questions.append({
            'id': 'default_navigate',
            'type': 'proceed',
            'domain': 'action',
            'prior': 0.3,
            'estimated_horizon': 2,
            'estimated_worlds': 3,
        })
        
        return questions

    # Fix 2: Cache management
    def reset_cache(self) -> None:
        """Reset the question cache, allowing all questions to be re-asked."""
        self._seen_questions.clear()
        logger.debug("OmegaOperator question cache reset")

    def _prune_cache(self) -> None:
        """Remove stale entries from question cache (older than TTL cycles)."""
        stale = [
            qid for qid, cycle in self._seen_questions.items()
            if self._cycle_counter - cycle > self._cache_ttl
        ]
        for qid in stale:
            del self._seen_questions[qid]
        if stale:
            logger.debug(
                f"Pruned {len(stale)} stale question(s) from cache: {stale}"
            )

    @property
    def last_questions(self) -> List[Dict]:
        """Return the most recently scored question set (for transparency)."""
        return list(self._last_questions)

    @property
    def last_omega_vector(self) -> Dict[str, float]:
        """Return the most recent multi-axis omega vector."""
        return dict(self._last_omega_vector)

    @property
    def seen_questions(self) -> Dict[str, int]:
        """Return the current question cache (question_id -> cycle_seen)."""
        return dict(self._seen_questions)
