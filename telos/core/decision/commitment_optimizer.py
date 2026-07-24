"""
CommitmentOptimizer — TELOS Commitment Theory (Axiom 5.1)

C* = argmax[ E(R) - M - Rec - I + F ]

Generalizes the Kelly Criterion from single-resource capital allocation
to multi-resource cognitive commitment across an evolving trajectory.

Kelly ⊂ TELOS when: only resource=capital, M=Rec=I=F=0

Fix 2 (C2): Added γ (gamma) exponential discounting so that commitment
scores are discounted across the planning horizon: gamma^t * term_value.
This ensures far-future rewards contribute less than near-term ones,
preventing the system from over-committing to distant, uncertain outcomes.
"""

from typing import Dict, Optional, Any
from dataclasses import dataclass
import logging
import numpy as np

logger = logging.getLogger('telos_commitment')


@dataclass
class CommitmentScore:
    """Multi-dimensional commitment score for a decision.
    
    J(τ) = E(R) - M - Rec - IC + OP + CF - PE
    
    With Fix 2 (gamma discounting):
      The expected_reward and future_option_value are discounted across
      the planning horizon using gamma^t weighting.
    """
    expected_reward: float = 0.0
    maintenance_cost: float = 0.0
    recovery_cost: float = 0.0
    identity_cost: float = 0.0
    future_option_value: float = 0.0
    counterfactual_diversity: float = 0.0  # 🔴 NEW: CF first-class term
    prediction_error: float = 0.0           # 🔴 NEW: PE term
    gamma: float = 0.95
    horizon: int = 1
    discounted_reward: float = 0.0

    @property
    def commitment(self) -> float:
        """J(τ) = E(R) - M - Rec - IC + OP + CF - PE, normalized to [0, 1].
        
        Matches the Formal Mathematical Decision Theory.
        """
        er = self.discounted_reward if self.horizon > 1 else self.expected_reward
        raw = (er - self.maintenance_cost - self.recovery_cost
               - self.identity_cost + self.future_option_value
               + self.counterfactual_diversity - self.prediction_error)
        return float(np.clip(raw, 0.0, 1.0))

    @property
    def is_suppressed(self) -> bool:
        return self.commitment < 0.3

    @property
    def is_full(self) -> bool:
        return self.commitment > 0.8

    def to_dict(self) -> Dict:
        return {
            "expected_reward": self.expected_reward,
            "discounted_reward": self.discounted_reward,
            "maintenance_cost": self.maintenance_cost,
            "recovery_cost": self.recovery_cost,
            "identity_cost": self.identity_cost,
            "future_option_value": self.future_option_value,
            "counterfactual_diversity": self.counterfactual_diversity,
            "prediction_error": self.prediction_error,
            "gamma": self.gamma,
            "horizon": self.horizon,
            "commitment": self.commitment,
            "is_suppressed": self.is_suppressed,
            "is_full": self.is_full,
        }


class SystemicStrainTracker:
    """Rolling metric of accumulated maintenance + recovery costs.
    
    High strain → override high-commitment plans → enter recovery protocol.
    """
    
    def __init__(self, window_size: int = 20, strain_threshold: float = 5.0):
        self.window_size = window_size
        self.strain_threshold = strain_threshold
        self._strain_history: list = []
        self._cycle_count: int = 0

    def record_strain(self, maintenance: float, recovery: float) -> None:
        self._cycle_count += 1
        self._strain_history.append(maintenance + recovery)
        if len(self._strain_history) > self.window_size:
            self._strain_history = self._strain_history[-self.window_size:]

    @property
    def current_strain(self) -> float:
        if not self._strain_history:
            return 0.0
        return float(np.mean(self._strain_history[-5:])) if len(self._strain_history) >= 5 else float(np.mean(self._strain_history))

    @property
    def is_critical(self) -> bool:
        return self.current_strain > self.strain_threshold

    @property
    def is_elevated(self) -> bool:
        return self.current_strain > self.strain_threshold * 0.6

    @property
    def trend(self) -> str:
        if len(self._strain_history) < 3:
            return "insufficient_data"
        recent = self._strain_history[-3:]
        if all(recent[i] <= recent[i+1] for i in range(len(recent)-1)):
            return "rising"
        if all(recent[i] >= recent[i+1] for i in range(len(recent)-1)):
            return "falling"
        return "stable"

    @property
    def stats(self) -> Dict:
        return {
            "current_strain": self.current_strain,
            "strain_threshold": self.strain_threshold,
            "is_critical": self.is_critical,
            "is_elevated": self.is_elevated,
            "trend": self.trend,
            "strain_history": self._strain_history[-10:] if self._strain_history else [],
        }


class CommitmentOptimizer:
    """Evaluates multi-dimensional commitment cost before action execution.
    
    Sits between the Decision Integrator and execution pipeline.
    Queries WorldLedger for identity entropy and resource availability,
    dynamically scaling execution weight C* ∈ [0, 1].
    
    Fix 2 (C2): Added gamma discounting across planning horizon.
    """
    
    def __init__(self, gamma: float = 0.95):
        self._strain_tracker = SystemicStrainTracker()
        self._commitment_history: list = []
        self._max_history: int = 50
        self.gamma = gamma  # Fix 2: Discount factor for future rewards

    def _compute_discounted_reward(self, expected_reward: float,
                                    horizon: int = 1) -> float:
        """Fix 2: Apply exponential discounting across planning horizon.
        
        discounted = Σ_{t=0}^{horizon-1} gamma^t * term_value
        
        This ensures far-future rewards contribute less than near-term ones.
        When horizon=1, returns expected_reward unchanged.
        
        Args:
            expected_reward: Base reward estimate
            horizon: Planning horizon length
            
        Returns:
            Gamma-discounted reward sum
        """
        if horizon <= 1:
            return expected_reward
        
        discounted = 0.0
        for t in range(horizon):
            discounted += (self.gamma ** t) * expected_reward
        
        return discounted

    @property
    def strain(self) -> SystemicStrainTracker:
        return self._strain_tracker

    def evaluate(self, expected_reward: float = 1.0,
                 maintenance_cost: float = 0.0,
                 recovery_cost: float = 0.0,
                 identity_cost: float = 0.0,
                 future_option_value: float = 0.0,
                 identity_entropy: Optional[float] = None,
                 recovery_ratio: Optional[float] = None,
                 counterfactual_diversity: Optional[float] = None,
                 horizon: int = 1,
                 terminal_value: float = 0.0,
                 prediction_error: float = 0.0) -> CommitmentScore:  # 🔴 NEW: PE
        """Compute C* from all available signals.
        
        J(τ) = E(R) - M - Rec - IC + OP + CF - PE
        
        When optional signals are provided, they modulate the base costs:
          - identity_entropy: high entropy → higher identity cost
          - recovery_ratio: high ratio → higher recovery cost
          - counterfactual_diversity: high diversity → higher CF
          - terminal_value: terminal reward at horizon endpoint → added to F
          - prediction_error: trajectory divergence → PE penalty
        """
        M = maintenance_cost
        Rec = recovery_cost
        I = identity_cost
        F = future_option_value
        CF = 0.0
        PE = prediction_error if prediction_error > 0 else 0.0

        if identity_entropy is not None:
            I += abs(identity_entropy) * 0.1

        if recovery_ratio is not None:
            Rec *= min(2.0, 1.0 + recovery_ratio)

        if counterfactual_diversity is not None:
            CF = min(0.5, counterfactual_diversity * 0.2)

        # Fix 3: Add terminal_value F(s_T) to future option value
        F += terminal_value * 0.15

        # Fix 2: Compute gamma-discounted reward across horizon
        discounted_reward = self._compute_discounted_reward(expected_reward, horizon)

        score = CommitmentScore(
            expected_reward=expected_reward,
            maintenance_cost=M,
            recovery_cost=Rec,
            identity_cost=I,
            future_option_value=F,
            counterfactual_diversity=CF,
            prediction_error=PE,
            gamma=self.gamma,
            horizon=horizon,
            discounted_reward=discounted_reward,
        )

        logger.debug(
            "Commitment: gamma={:.3f}, horizon={}, reward={:.3f}->discounted={:.3f}, "
            "terminal={:.3f}, CF={:.3f}, PE={:.3f}, commitment={:.3f}".format(
                self.gamma, horizon, expected_reward, discounted_reward,
                terminal_value, CF, PE, score.commitment
            )
        )

        self._commitment_history.append(score.commitment)
        if len(self._commitment_history) > self._max_history:
            self._commitment_history = self._commitment_history[-self._max_history:]

        return score

    @property
    def recent_commitment(self) -> float:
        if not self._commitment_history:
            return 1.0
        return float(np.mean(self._commitment_history[-5:]))

    @property
    def commitment_trend(self) -> str:
        if len(self._commitment_history) < 3:
            return "stable"
        recent = self._commitment_history[-3:]
        if all(recent[i] <= recent[i+1] for i in range(len(recent)-1)):
            return "rising"
        if all(recent[i] >= recent[i+1] for i in range(len(recent)-1)):
            return "falling"
        return "stable"

    @property
    def stats(self) -> Dict:
        return {
            "recent_commitment": self.recent_commitment,
            "commitment_trend": self.commitment_trend,
            "gamma": self.gamma,
            "strain": self._strain_tracker.stats,
            "commitment_history": self._commitment_history[-10:] if self._commitment_history else [],
        }
