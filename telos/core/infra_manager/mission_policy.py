"""
Mission Policy — Configures risk/exploration/ambition parameters.

The MissionPolicy defines the strategic posture of the system:
  - Risk Tolerance: How much uncertainty is acceptable?
  - Exploration Budget: How much compute to spend on counterfactuals?
  - Ambition Level: How aggressively to pursue mission objectives?

The Policy is NOT static. The InfraManager can adjust it based on
historical performance — lowering risk tolerance after failures,
or increasing exploration after repeated low-drift cycles.

Λ3.4 (Exploration vs Exploitation): UCB-based exploration engine
balances exploration of unknown options against exploitation of
known-good ones using a verifiable algorithm.
"""

import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any, List
from enum import Enum

logger = logging.getLogger('telos_infra')


@dataclass
class ParameterBudget:
    """Tracks cumulative parameter drift from genesis baseline.
    
    Prevents slow-burn parameter attacks where small deltas compound
    over hundreds of cycles to fully lock or fully open the system.
    """
    genesis_params: Dict[str, float] = field(default_factory=dict)
    cumulative_drift: Dict[str, float] = field(default_factory=dict)
    MAX_CUMULATIVE_DRIFT: float = 0.5

    def __init__(self, genesis: 'MissionPolicy'):
        self.genesis_params = {
            'risk_tolerance': genesis.risk_tolerance,
            'exploration_budget': genesis.exploration_budget,
            'ambition_level': genesis.ambition_level,
            'drift_tolerance': genesis.drift_tolerance,
        }
        self.cumulative_drift = {k: 0.0 for k in self.genesis_params}
        self.MAX_CUMULATIVE_DRIFT = 0.7

    def check_drift(self, param: str, new_value: float) -> bool:
        drift = new_value - self.genesis_params.get(param, new_value)
        if abs(drift) > self.MAX_CUMULATIVE_DRIFT:
            logger.error(
                f"ParameterBudget EXCEEDED: {param} cumulative drift = {drift:.3f} "
                f"(max={self.MAX_CUMULATIVE_DRIFT}). "
                f"Genesis={self.genesis_params.get(param, '?')}, current={new_value:.3f}. BLOCKING."
            )
            return False
        self.cumulative_drift[param] = drift
        return True


@dataclass
class PolicyChange:
    """A single policy change with audit trail."""
    component: str
    old_value: float
    new_value: float
    reason: str
    caller: str
    cycle: int
    timestamp: float
    status: str = "committed"  # proposed, committed, rolled_back


class PolicyChangeLog:
    """Full audit trail of all MissionPolicy changes."""
    MAX_CHANGES: int = 1000
    
    def __init__(self):
        self._changes: List[PolicyChange] = []
    
    def record(self, component: str, old: float, new_val: float,
               reason: str = "", caller: str = "", cycle: int = 0) -> PolicyChange:
        change = PolicyChange(
            component=component, old_value=old, new_value=new_val,
            reason=reason, caller=caller, cycle=cycle,
            timestamp=time.time(),
        )
        self._changes.append(change)
        if len(self._changes) > self.MAX_CHANGES:
            self._changes.pop(0)
        return change
    
    @property
    def recent(self) -> List[PolicyChange]:
        return self._changes[-10:]
    
    @property
    def stats(self) -> Dict:
        return {
            "total_changes": len(self._changes),
            "recent": [
                {"component": c.component, "old": c.old_value, "new": c.new_value,
                 "reason": c.reason, "caller": c.caller, "cycle": c.cycle, "status": c.status}
                for c in self._changes[-5:]
            ],
        }


@dataclass
class MissionPolicy:
    """The strategic posture of the system for a given mission.

    These parameters control how the Pipeline behaves:
      - risk_tolerance: Min DI threshold for the Firewall (0.0=strict, 1.0=loose)
      - exploration_budget: Fraction of compute to allocate to simulation
      - ambition_level: How aggressively to weight mission-aligned intents
      - drift_tolerance: Max MD before the Council auto-blocks
      - recovery_mode: When True, Pipeline operates in reduced-scope recovery
    """
    mission_name: str = "default"
    risk_tolerance: float = 0.3
    exploration_budget: float = 0.3
    ambition_level: float = 0.5
    drift_tolerance: float = 5.0
    recovery_mode: bool = False
    metadata: Dict = field(default_factory=dict)


class MissionPolicyManager:
    """Manages the active mission policy and supports dynamic adjustments.

    The PolicyManager allows the InfraManager to:
      - Switch policies when the mission changes
      - Adjust parameters based on historical performance
      - Enforce policy boundaries (cannot set risk_tolerance > 1.0)

    Λ3.4 (Exploration vs Exploitation): UCB-based exploration engine
    tracks domain-level pulls and rewards to compute exploration bonuses.
    """

    def __init__(self, initial_policy: Optional[MissionPolicy] = None):
        self._current = initial_policy or MissionPolicy()
        self._parameter_budget = ParameterBudget(self._current)
        self._change_log = PolicyChangeLog()
        self._policy_history: list = []
        # Λ3.4: UCB exploration tracking
        # Bitcoin-inspired exploration budget halving
        self.exploration_halving_cycles: int = 100
        self.halving_count: int = 0
        self._domain_pulls: Dict[str, int] = {}
        self._domain_rewards: Dict[str, float] = {}

    def set_policy(self, policy: MissionPolicy) -> None:
        """Replace the current policy and reset budget anchor."""
        self._policy_history.append({
            "previous": self._current,
            "new": policy,
            "timestamp": time.time(),
        })
        self._current = policy
        self._parameter_budget = ParameterBudget(policy)
        logger.info(f"MissionPolicy: set to '{policy.mission_name}' "
                     f"(risk={policy.risk_tolerance}, explore={policy.exploration_budget})")

    def adjust_risk_tolerance(self, delta: float, reason: str = "", caller: str = "", cycle: int = 0) -> None:
        """Adjust risk tolerance within [0.0, 1.0]."""
        new_val = max(0.0, min(1.0, self._current.risk_tolerance + delta))
        self._parameter_budget.check_drift('risk_tolerance', new_val)
        if new_val != self._current.risk_tolerance:
            old = self._current.risk_tolerance
            self._current.risk_tolerance = new_val
            self._change_log.record('risk_tolerance', old, new_val, reason, caller, cycle)
            logger.info(f"MissionPolicy: risk_tolerance {old:.2f} → {new_val:.2f} ({reason})")

    def check_halving(self, cycle_count: int) -> None:
        """Check if exploration budget should be halved (Bitcoin-inspired).

        Every exploration_halving_cycles cycles, the exploration budget
        is halved. This mirrors Bitcoin block reward halving and
        ensures the system transitions from exploration to exploitation
        over time.

        Args:
            cycle_count: Current pipeline cycle number.
        """
        if cycle_count > 0 and cycle_count % self.exploration_halving_cycles == 0:
            old_budget = self._current.exploration_budget
            new_budget = old_budget * 0.5
            self._current.exploration_budget = new_budget
            self.halving_count += 1
            self._change_log.record(
                "exploration_budget", old_budget, new_budget,
                reason=f"halving #{self.halving_count} at cycle {cycle_count}",
                caller="check_halving",
                cycle=cycle_count,
            )
            logger.info(
                f"Exploration budget halved to {new_budget:.3f}"
                f" (halving #{self.halving_count}, cycle {cycle_count})"
            )

    def set_readiness_gate(self, infra_readiness: float) -> None:
        """Gate risk tolerance by infrastructure readiness.
        
        Low infra maturity → conservative posture:
          - readiness < 0.3: cap risk at 0.2, exploration at 0.15
          - readiness < 0.5: cap risk at 0.3, exploration at 0.25
          - readiness >= 0.5: no forced cap
        """
        old_risk = self._current.risk_tolerance
        old_explore = self._current.exploration_budget
        if infra_readiness < 0.3:
            self._current.risk_tolerance = min(self._current.risk_tolerance, 0.2)
            self._current.exploration_budget = min(self._current.exploration_budget, 0.15)
        elif infra_readiness < 0.5:
            self._current.risk_tolerance = min(self._current.risk_tolerance, 0.3)
            self._current.exploration_budget = min(self._current.exploration_budget, 0.25)
        if old_risk != self._current.risk_tolerance or old_explore != self._current.exploration_budget:
            logger.info(
                f"Readiness gate: infra maturity {infra_readiness:.2f} — "
                f"risk {old_risk:.2f} → {self._current.risk_tolerance:.2f}, "
                f"explore {old_explore:.2f} → {self._current.exploration_budget:.2f}"
            )

    def adjust_risk_by_uncertainty(self, stream_uncertainties: Dict[str, float]) -> None:
        """Tighten risk tolerance when streams have high uncertainty."""
        if not stream_uncertainties:
            return
        avg_uncertainty = sum(stream_uncertainties.values()) / max(len(stream_uncertainties), 1)
        target_risk = self._current.risk_tolerance * (1.0 - 0.5 * avg_uncertainty)
        delta = target_risk - self._current.risk_tolerance
        if abs(delta) > 0.01:
            self.adjust_risk_tolerance(delta)

    def adjust_exploration_budget(self, delta: float, reason: str = "", caller: str = "", cycle: int = 0) -> None:
        """Adjust exploration budget within [0.0, 1.0]."""
        new_val = max(0.0, min(1.0, self._current.exploration_budget + delta))
        self._parameter_budget.check_drift('exploration_budget', new_val)
        if new_val != self._current.exploration_budget:
            old = self._current.exploration_budget
            self._current.exploration_budget = new_val
            self._change_log.record('exploration_budget', old, new_val, reason, caller, cycle)
            logger.info(f"MissionPolicy: exploration_budget {old:.2f} → {new_val:.2f} ({reason})")

    def apply_identity_markers(self, markers: set) -> None:
        """Map identity markers to policy parameter adjustments.
        
        Identity markers from Kintsugi failure integration influence how
        the system balances risk and exploration:
          - learning_governance → lower risk tolerance (being cautious)
          - breaking_patterns → higher exploration (trying new things)
          - conserving_resources → lower exploration (saving compute)
          - calibrating_prediction → higher risk tolerance (learning needs room)
        """
        for marker in markers:
            if marker == "learning_governance":
                self.adjust_risk_tolerance(-0.03, reason=f"identity:{marker}")
            elif marker == "breaking_patterns":
                self.adjust_exploration_budget(0.03, reason=f"identity:{marker}")
            elif marker == "conserving_resources":
                self.adjust_exploration_budget(-0.03, reason=f"identity:{marker}")
            elif marker == "calibrating_prediction":
                self.adjust_risk_tolerance(0.02, reason=f"identity:{marker}")

    # ── Λ3.4 UCB + Thompson Sampling Exploration Engine ─────────────────

    def record_outcome(self, domain: str, approach: str, di_score: float) -> None:
        """Record the outcome of exploring a domain/approach.

        Increments pull count and updates cumulative reward for the domain.
        This feeds both UCB and Thompson sampling exploration.

        Args:
            domain: The domain that was explored (e.g., 'grid', 'navigation')
            approach: The specific approach tried (e.g., 'move', 'perceive')
            di_score: Decision integrity score from the trace [0.0, 1.0]
        """
        self._domain_pulls[domain] = self._domain_pulls.get(domain, 0) + 1
        current = self._domain_rewards.get(domain, 0.0)
        self._domain_rewards[domain] = current + di_score
        logger.debug(f"UCB: recorded outcome for '{domain}/{approach}' — DI={di_score:.3f} (pulls={self._domain_pulls[domain]})")

    def exploration_bonus(self, domain: str) -> float:
        """Compute UCB exploration bonus for a domain.

        Uses the formula: bonus = mean_reward + sqrt(2 * ln(total_pulls) / n_pulls)

        Returns:
            A value in [0.0, 1.0] representing the exploration-adjusted score.
            Never-tried domains get maximum bonus (1.0).
        """
        n = self._domain_pulls.get(domain, 0)
        if n == 0:
            return 1.0  # never tried → maximum bonus
        total = sum(self._domain_pulls.values())
        mean = self._domain_rewards.get(domain, 0.0) / n
        bonus = math.sqrt(2 * math.log(total + 1) / n)
        return min(1.0, mean + bonus)

    def thompson_sample(self, domain: str) -> float:
        """Compute Thompson sampling score for a domain.

        Uses a Beta(alpha, beta) posterior where:
          alpha = total_reward + 1    (pseudo-count prior)
          beta  = pulls - total_reward + 1

        Samples from the posterior for Bayesian explore/exploit.
        Never-tried domains sample from Beta(1, 1) = Uniform(0, 1).

        Returns:
            A value in [0.0, 1.0] — a single Thompson sample.
            Higher = more likely to be optimal under current beliefs.
        """
        n = self._domain_pulls.get(domain, 0)
        total_reward = self._domain_rewards.get(domain, 0.0)
        alpha = total_reward + 1.0
        beta = float(n) - total_reward + 1.0
        return float(random.betavariate(alpha, beta))

    @property
    def current(self) -> MissionPolicy:
        return self._current

    @property
    def firewall_di_threshold(self) -> float:
        """Derive Firewall DI threshold from risk tolerance.

        Low risk tolerance → high DI threshold (strict)
        High risk tolerance → low DI threshold (permissive)
        """
        return 1.0 - self._current.risk_tolerance

    @property
    def stats(self) -> Dict:
        return {
            "mission": self._current.mission_name,
            "risk_tolerance": self._current.risk_tolerance,
            "exploration_budget": self._current.exploration_budget,
            "ambition_level": self._current.ambition_level,
            "drift_tolerance": self._current.drift_tolerance,
            "firewall_di_threshold": self.firewall_di_threshold,
            "policy_changes": len(self._policy_history),
            "change_log": self._change_log.stats,
            "method": "ucb_thompson_dual",
            "ucb_domains": len(self._domain_pulls),
            "ucb_pulls": dict(self._domain_pulls),
            "ucb_rewards": {d: round(r, 3) for d, r in self._domain_rewards.items()},
            "thompson_alphas": {d: round(self._domain_rewards.get(d, 0.0) + 1.0, 3) for d in self._domain_pulls},
            "thompson_betas": {d: round(max(1.0, float(self._domain_pulls[d]) - self._domain_rewards.get(d, 0.0) + 1.0), 3) for d in self._domain_pulls},
        }
