"""
TELOS v12: The General Theory of Guided Intelligent Systems

Transcends TELOS from a decision algorithm to a General Theory of
Guided Intelligent Systems. Synthesizes systemic case studies in
administrative failure, institutional decay, and structural bottlenecks.

Core Theoretical Principles:
  1. Constraint-First Intelligence: Ω_blockade vs Resource Deficiency
  2. Mission Drift & Reward Drift: D_M = |G_t - G_0|
  3. Merit Flow (MF): Evidence-Supported / Authority-Supported decisions
  4. Reverse Planning: G_T → G_{T-1} → ... → G_0 (optimal control)
  5. Cumulative Opportunity Cost: OC(t) = Σ V_i

System Conservation Principle:
  S = (M, K, T, E, C, R) — six-dimensional state vector
  A healthy system preserves all six dimensions continuously.

Master Pipeline (v12):
  G₀ → Objective Integrity → Decision Truth Engine → Reverse Planning
  → Forest Search → Neti-Neti → Red-Team + Counterfactual
  → Belief Verification → Decision Ledger → System Conservation
  → PCS → Friction Optimizer → Execution → Mission Audit
  → Strategy Update → Sleep → Auto-Tune
"""

import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

from telos_v9 import (
    ObjectiveIntegrityMonitor, MissionState, CognitiveFrictionOptimizer,
    DriftSeverity,
)
from telos_v11 import (
    TelosV11Runtime, DecisionTruthEngine, BeliefVerificationEngine,
    CounterfactualExplorer, NarrativeStatus,
)


# ═══════════════════════════════════════════════════════════
# 1. REVERSE PLANNING ENGINE
#    Optimal Control: Projects backward from G_T to G_0
# ═══════════════════════════════════════════════════════════

class MilestoneStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    ACHIEVED = "achieved"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Milestone:
    """A backward-projected milestone from G_T."""
    milestone_id: str
    target_state: np.ndarray
    deadline_step: int
    description: str
    status: MilestoneStatus = MilestoneStatus.PENDING
    required_actions: List[str] = field(default_factory=list)
    achieved_at: Optional[int] = None
    distance_to_target: float = 0.0
    parent_milestone_id: Optional[str] = None


@dataclass
class PlanningHorizon:
    """Complete backward plan from G_T to G_0."""
    goal_state: np.ndarray
    initial_state: np.ndarray
    horizon_length: int
    milestones: List[Milestone]
    total_distance: float
    created_at: float = field(default_factory=time.time)


@dataclass
class PlanDeviation:
    """Record of deviation between planned and actual trajectory."""
    step: int
    planned_state: np.ndarray
    actual_state: np.ndarray
    deviation_magnitude: float
    closest_milestone_id: Optional[str] = None
    recovery_action: str = ""


class ReversePlanningEngine:
    """
    Optimal Control: Projects backward from desired future state (G_T)
    to current state (G_0), computing intermediate milestones.

    Instead of projecting forward blindly:
      G_T → G_{T-1} → ... → G_0

    This ensures immediate actions strictly serve long-term trajectories.

    The engine maintains a planning horizon and tracks deviations
    between planned and actual trajectories, triggering recovery
    when deviation exceeds a threshold.
    """

    def __init__(self, horizon_length: int = 10,
                 deviation_threshold: float = 0.3,
                 interpolation_power: float = 2.0):
        self.horizon_length = horizon_length
        self.deviation_threshold = deviation_threshold
        self.interpolation_power = interpolation_power
        self._current_plan: Optional[PlanningHorizon] = None
        self._deviation_history: deque = deque(maxlen=200)
        self._total_plans_created = 0
        self._total_deviations_detected = 0

    def create_plan(self, initial_state: np.ndarray,
                    goal_state: np.ndarray,
                    goal_step: int,
                    milestone_descriptions: Optional[List[str]] = None,
                    ) -> PlanningHorizon:
        """
        Create a backward plan from goal_state to initial_state.

        The plan interpolates between G_T and G_0 using the specified
        interpolation power, generating milestones at each step.
        """
        n_dims = len(initial_state)
        n_milestones = min(goal_step, self.horizon_length)

        milestones = []
        for i in range(n_milestones):
            # Backward interpolation: from G_T (step n) to G_0 (step 0)
            t = (i + 1) / n_milestones
            # Apply interpolation power for non-linear spacing
            t_powered = t ** self.interpolation_power
            target = initial_state + (goal_state - initial_state) * t_powered

            desc = (milestone_descriptions[i]
                    if milestone_descriptions and i < len(milestone_descriptions)
                    else f"Milestone {i+1}/{n_milestones}")

            milestone = Milestone(
                milestone_id=f"ms-{i}",
                target_state=target,
                deadline_step=goal_step - n_milestones + i + 1,
                description=desc,
                required_actions=[f"step_towards_ms_{i}"],
            )
            milestones.append(milestone)

        total_distance = float(np.linalg.norm(goal_state - initial_state))

        plan = PlanningHorizon(
            goal_state=goal_state.copy(),
            initial_state=initial_state.copy(),
            horizon_length=n_milestones,
            milestones=milestones,
            total_distance=total_distance,
        )

        self._current_plan = plan
        self._total_plans_created += 1
        return plan

    def evaluate_step(self, current_state: np.ndarray,
                      current_step: int) -> Dict[str, Any]:
        """
        Evaluate the current state against the planned trajectory.
        Returns deviation metrics and recovery recommendations.
        """
        if self._current_plan is None:
            return {
                'has_plan': False,
                'deviation': 0.0,
                'recommendation': 'No active plan. Create a plan first.',
            }

        plan = self._current_plan

        # Find the milestone closest to current step
        closest_ms = None
        min_distance = float('inf')
        for ms in plan.milestones:
            if ms.deadline_step <= current_step:
                dist = float(np.linalg.norm(current_state - ms.target_state))
                if dist < min_distance:
                    min_distance = dist
                    closest_ms = ms

        # Compute overall trajectory deviation
        # Expected state at current step via forward interpolation
        progress = min(1.0, current_step / max(1, plan.milestones[-1].deadline_step
                                                if plan.milestones else 1))
        expected_state = plan.initial_state + (
            plan.goal_state - plan.initial_state
        ) * (progress ** self.interpolation_power)

        deviation = float(np.linalg.norm(current_state - expected_state))
        deviation_ratio = deviation / max(plan.total_distance, 1e-9)

        exceeds = deviation_ratio > self.deviation_threshold

        # Mark achieved milestones
        achieved_count = 0
        for ms in plan.milestones:
            if ms.status == MilestoneStatus.ACHIEVED:
                achieved_count += 1
                continue
            if ms.deadline_step <= current_step:
                dist = float(np.linalg.norm(current_state - ms.target_state))
                ms.distance_to_target = dist
                # Milestone achieved if within 20% of total distance
                if dist < plan.total_distance * 0.2:
                    ms.status = MilestoneStatus.ACHIEVED
                    ms.achieved_at = current_step
                    achieved_count += 1
                else:
                    ms.status = MilestoneStatus.ACTIVE

        if exceeds:
            self._total_deviations_detected += 1

        recovery_action = ""
        if exceeds:
            if closest_ms:
                recovery_action = (
                    f"Deviated from trajectory by {deviation_ratio:.2%}. "
                    f"Redirect towards milestone '{closest_ms.milestone_id}' "
                    f"at deadline step {closest_ms.deadline_step}."
                )
            else:
                recovery_action = (
                    f"Deviated from trajectory by {deviation_ratio:.2%}. "
                    f"No close milestone found. Re-plan recommended."
                )

        record = PlanDeviation(
            step=current_step,
            planned_state=expected_state,
            actual_state=current_state.copy(),
            deviation_magnitude=deviation,
            closest_milestone_id=closest_ms.milestone_id if closest_ms else None,
            recovery_action=recovery_action,
        )
        self._deviation_history.append(record)

        return {
            'has_plan': True,
            'deviation': round(deviation, 6),
            'deviation_ratio': round(deviation_ratio, 6),
            'exceeds_threshold': exceeds,
            'milestones_achieved': achieved_count,
            'milestones_total': len(plan.milestones),
            'closest_milestone': closest_ms.milestone_id if closest_ms else None,
            'recovery_action': recovery_action,
            'progress': round(progress, 4),
        }

    def replan(self, current_state: np.ndarray,
               goal_state: Optional[np.ndarray] = None,
               goal_step: int = 10) -> PlanningHorizon:
        """Create a new plan from the current state."""
        effective_goal = goal_state if goal_state is not None else (
            self._current_plan.goal_state if self._current_plan else current_state
        )
        return self.create_plan(current_state, effective_goal, goal_step)

    def get_statistics(self) -> Dict:
        plan_stats = {}
        if self._current_plan:
            achieved = sum(1 for ms in self._current_plan.milestones
                          if ms.status == MilestoneStatus.ACHIEVED)
            plan_stats = {
                'total_milestones': len(self._current_plan.milestones),
                'achieved': achieved,
                'remaining': len(self._current_plan.milestones) - achieved,
                'total_distance': round(self._current_plan.total_distance, 4),
            }
        return {
            'total_plans_created': self._total_plans_created,
            'total_deviations_detected': self._total_deviations_detected,
            'has_active_plan': self._current_plan is not None,
            'current_plan': plan_stats,
        }


# ═══════════════════════════════════════════════════════════
# 2. MERIT FLOW MONITOR
#    Quantifies institutional health: Evidence vs Authority
# ═══════════════════════════════════════════════════════════

class DecisionBasis(Enum):
    EVIDENCE = "evidence"
    AUTHORITY = "authority"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


@dataclass
class MeritFlowRecord:
    """Record of a single decision's basis (evidence vs authority)."""
    decision_id: str
    basis: DecisionBasis
    evidence_weight: float       # 0 = pure authority, 1 = pure evidence
    authority_weight: float      # 1 - evidence_weight
    decision_summary: str
    timestamp: float = field(default_factory=time.time)


class MeritFlowMonitor:
    """
    Quantifies institutional health via Merit Flow.

    MF = Evidence-Supported Decisions / Authority-Supported Decisions

    As MF → 0, structural corruption increases, leading to
    systemic collapse. A healthy system maintains MF >> 1.

    TELOS enforces that every decision must declare its basis
    (evidence vs authority), and the monitor tracks the running ratio.
    """

    def __init__(self, decay_rate: float = 0.01,
                 corruption_threshold: float = 0.3):
        self.decay_rate = decay_rate
        self.corruption_threshold = corruption_threshold
        self._records: deque = deque(maxlen=1000)
        self._evidence_count = 0
        self._authority_count = 0
        self._hybrid_count = 0
        self._total_decisions = 0
        self._corruption_events = 0

    def record_decision(self, decision_id: str,
                        basis: DecisionBasis,
                        evidence_weight: float = 0.5,
                        decision_summary: str = "") -> MeritFlowRecord:
        """Record a decision's basis for Merit Flow calculation."""
        evidence_weight = max(0.0, min(1.0, evidence_weight))
        authority_weight = 1.0 - evidence_weight

        record = MeritFlowRecord(
            decision_id=decision_id,
            basis=basis,
            evidence_weight=evidence_weight,
            authority_weight=authority_weight,
            decision_summary=decision_summary,
        )
        self._records.append(record)
        self._total_decisions += 1

        if basis == DecisionBasis.EVIDENCE:
            self._evidence_count += 1
        elif basis == DecisionBasis.AUTHORITY:
            self._authority_count += 1
        elif basis == DecisionBasis.HYBRID:
            self._hybrid_count += 1

        return record

    def compute_merit_flow(self) -> float:
        """
        MF = evidence_decisions / authority_decisions.

        Returns a value in [0, +inf). MF > 1 is healthy.
        MF < 1 indicates authority is overriding evidence.
        MF → 0 indicates systemic corruption.
        """
        if self._authority_count == 0:
            return float('inf') if self._evidence_count > 0 else 1.0
        return self._evidence_count / self._authority_count

    def compute_weighted_merit_flow(self) -> float:
        """
        Weighted MF incorporating hybrid decisions and evidence weights.
        """
        total_evidence = sum(r.evidence_weight for r in self._records)
        total_authority = sum(r.authority_weight for r in self._records)

        if total_authority < 1e-9:
            return float('inf') if total_evidence > 0 else 1.0
        return total_evidence / total_authority

    def detect_corruption(self) -> Dict[str, Any]:
        """
        Detect structural corruption: when authority overrides evidence.
        """
        mf = self.compute_merit_flow()
        weighted_mf = self.compute_weighted_merit_flow()

        is_corrupt = mf < self.corruption_threshold
        severity = max(0.0, 1.0 - mf) if mf != float('inf') else 0.0

        if is_corrupt:
            self._corruption_events += 1

        return {
            'merit_flow': round(mf, 4) if mf != float('inf') else float('inf'),
            'weighted_merit_flow': round(weighted_mf, 4) if weighted_mf != float('inf') else float('inf'),
            'is_corrupt': is_corrupt,
            'severity': round(severity, 4),
            'evidence_count': self._evidence_count,
            'authority_count': self._authority_count,
            'hybrid_count': self._hybrid_count,
            'recommendation': (
                "STRUCTURAL CORRUPTION DETECTED: Authority is overriding "
                "evidence. MF below threshold. Immediate audit recommended."
                if is_corrupt else
                "Merit flow within acceptable bounds."
            ),
        }

    def get_trend(self, window: int = 50) -> Dict[str, Any]:
        """Compute Merit Flow trend over recent decisions."""
        recent = list(self._records)[-window:]
        if not recent:
            return {'trend': 'stable', 'slope': 0.0}

        ev_count = sum(1 for r in recent if r.basis == DecisionBasis.EVIDENCE)
        auth_count = sum(1 for r in recent if r.basis == DecisionBasis.AUTHORITY)
        mf_recent = ev_count / max(auth_count, 1)

        # Compare to overall MF
        overall_mf = self.compute_merit_flow()
        if overall_mf == float('inf'):
            slope = 0.0
        else:
            slope = mf_recent - overall_mf

        trend = 'improving' if slope > 0.05 else ('declining' if slope < -0.05 else 'stable')

        return {
            'trend': trend,
            'slope': round(slope, 4),
            'recent_mf': round(mf_recent, 4),
            'overall_mf': round(overall_mf, 4) if overall_mf != float('inf') else float('inf'),
            'window_size': len(recent),
        }

    def get_statistics(self) -> Dict:
        return {
            'total_decisions': self._total_decisions,
            'evidence_count': self._evidence_count,
            'authority_count': self._authority_count,
            'hybrid_count': self._hybrid_count,
            'merit_flow': round(self.compute_merit_flow(), 4),
            'weighted_merit_flow': round(self.compute_weighted_merit_flow(), 4),
            'corruption_events': self._corruption_events,
            'corruption_threshold': self.corruption_threshold,
        }


# ═══════════════════════════════════════════════════════════
# 3. SYSTEM CONSERVATION MONITOR
#    Tracks the six-dimensional state vector S(M,K,T,E,C,R)
# ═══════════════════════════════════════════════════════════

@dataclass
class ConservationState:
    """Snapshot of the six-dimensional conservation vector."""
    mission_integrity: float = 1.0     # M: bounded minimization of D_M
    knowledge_integrity: float = 1.0   # K: prevention of knowledge death
    trust_integrity: float = 1.0       # T: maximization of Merit Flow
    energy_efficiency: float = 1.0     # E: optimized computation via PCS
    capability_growth: float = 1.0     # C: pruning & promotion via Neti-Neti
    recovery_capacity: float = 1.0     # R: maintaining low recovery debt

    @property
    def overall_health(self) -> float:
        """Average across all six dimensions."""
        values = [
            self.mission_integrity,
            self.knowledge_integrity,
            self.trust_integrity,
            self.energy_efficiency,
            self.capability_growth,
            self.recovery_capacity,
        ]
        return float(np.mean(values))

    @property
    def weakest_dimension(self) -> Tuple[str, float]:
        """Identify the dimension with lowest value."""
        dims = {
            'M_mission': self.mission_integrity,
            'K_knowledge': self.knowledge_integrity,
            'T_trust': self.trust_integrity,
            'E_energy': self.energy_efficiency,
            'C_capability': self.capability_growth,
            'R_recovery': self.recovery_capacity,
        }
        weakest = min(dims.items(), key=lambda x: x[1])
        return weakest

    def to_vector(self) -> np.ndarray:
        """Convert to numpy vector for computation."""
        return np.array([
            self.mission_integrity,
            self.knowledge_integrity,
            self.trust_integrity,
            self.energy_efficiency,
            self.capability_growth,
            self.recovery_capacity,
        ])

    @classmethod
    def from_vector(cls, vec: np.ndarray) -> 'ConservationState':
        """Create from numpy vector."""
        vec = np.clip(vec, 0.0, 1.0)
        return cls(
            mission_integrity=float(vec[0]),
            knowledge_integrity=float(vec[1]),
            trust_integrity=float(vec[2]),
            energy_efficiency=float(vec[3]),
            capability_growth=float(vec[4]),
            recovery_capacity=float(vec[5]),
        )


class ConservationSeverity(Enum):
    NOMINAL = "nominal"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    COLLAPSE = "collapse"


class SystemConservationMonitor:
    """
    Monitors the six-dimensional state vector S(M,K,T,E,C,R) to ensure
    the system maintains structural health across all dimensions.

    A healthy, long-lived intelligent system cannot optimize isolated
    task outputs while its internal structure decays.

    The monitor tracks:
      M (Mission Integrity): Bounded minimization of Mission Drift D_M
      K (Knowledge Integrity): Prevention of knowledge death
      T (Trust Integrity): Maximization of Merit Flow MF
      E (Energy/Resource Efficiency): Optimized via PCS and Decision ROI
      C (Capability Growth): Continuous pruning via Neti-Neti
      R (Recovery Capacity): Maintaining low recovery debt
    """

    def __init__(self,
                 mission_weight: float = 1.0,
                 knowledge_weight: float = 1.0,
                 trust_weight: float = 1.0,
                 energy_weight: float = 1.0,
                 capability_weight: float = 1.0,
                 recovery_weight: float = 1.0,
                 degradation_threshold: float = 0.7,
                 critical_threshold: float = 0.4,
                 collapse_threshold: float = 0.2):
        self.weights = {
            'M': mission_weight,
            'K': knowledge_weight,
            'T': trust_weight,
            'E': energy_weight,
            'C': capability_weight,
            'R': recovery_weight,
        }
        self.degradation_threshold = degradation_threshold
        self.critical_threshold = critical_threshold
        self.collapse_threshold = collapse_threshold
        self._state = ConservationState()
        self._state_history: deque = deque(maxlen=500)
        self._alert_history: deque = deque(maxlen=200)
        self._total_alerts = 0

    def update_mission_integrity(self, mission_drift: float,
                                  max_drift: float = 1.0) -> float:
        """Update M: inversely proportional to mission drift."""
        normalized_drift = min(1.0, mission_drift / max(max_drift, 1e-9))
        self._state.mission_integrity = max(0.0, 1.0 - normalized_drift)
        return self._state.mission_integrity

    def update_knowledge_integrity(self, decisions_recorded: int,
                                    decisions_lost: int) -> float:
        """Update K: fraction of knowledge preserved."""
        total = decisions_recorded + decisions_lost
        if total == 0:
            self._state.knowledge_integrity = 1.0
        else:
            self._state.knowledge_integrity = decisions_recorded / total
        return self._state.knowledge_integrity

    def update_trust_integrity(self, merit_flow: float,
                                max_mf: float = 5.0) -> float:
        """Update T: normalized merit flow."""
        if merit_flow == float('inf'):
            self._state.trust_integrity = 1.0
        else:
            self._state.trust_integrity = min(1.0, merit_flow / max_mf)
        return self._state.trust_integrity

    def update_energy_efficiency(self, utilization: float,
                                  target_utilization: float = 0.7) -> float:
        """Update E: how close utilization is to target."""
        deviation = abs(utilization - target_utilization)
        self._state.energy_efficiency = max(0.0, 1.0 - deviation)
        return self._state.energy_efficiency

    def update_capability_growth(self, pruning_ratio: float,
                                  promotion_ratio: float) -> float:
        """Update C: balanced pruning and promotion."""
        # High pruning with low promotion = knowledge death
        # Low pruning with high promotion = noise accumulation
        balance = 1.0 - abs(pruning_ratio - promotion_ratio)
        self._state.capability_growth = max(0.0, balance)
        return self._state.capability_growth

    def update_recovery_capacity(self, recovery_debt: float,
                                  max_debt: float = 1.0) -> float:
        """Update R: inversely proportional to recovery debt."""
        normalized_debt = min(1.0, recovery_debt / max(max_debt, 1e-9))
        self._state.recovery_capacity = max(0.0, 1.0 - normalized_debt)
        return self._state.recovery_capacity

    def snapshot(self) -> ConservationState:
        """Take a snapshot of the current conservation state."""
        state = ConservationState(
            mission_integrity=self._state.mission_integrity,
            knowledge_integrity=self._state.knowledge_integrity,
            trust_integrity=self._state.trust_integrity,
            energy_efficiency=self._state.energy_efficiency,
            capability_growth=self._state.capability_growth,
            recovery_capacity=self._state.recovery_capacity,
        )
        self._state_history.append(state)
        return state

    def classify_severity(self) -> ConservationSeverity:
        """Classify overall system health."""
        health = self._state.overall_health
        if health >= self.degradation_threshold:
            return ConservationSeverity.NOMINAL
        elif health >= self.critical_threshold:
            return ConservationSeverity.DEGRADED
        elif health >= self.collapse_threshold:
            return ConservationSeverity.CRITICAL
        else:
            return ConservationSeverity.COLLAPSE

    def check_alerts(self) -> List[Dict[str, Any]]:
        """Check for conservation violations and generate alerts."""
        alerts = []
        dims = {
            'M_mission': self._state.mission_integrity,
            'K_knowledge': self._state.knowledge_integrity,
            'T_trust': self._state.trust_integrity,
            'E_energy': self._state.energy_efficiency,
            'C_capability': self._state.capability_growth,
            'R_recovery': self._state.recovery_capacity,
        }

        for name, value in dims.items():
            if value < self.collapse_threshold:
                alerts.append({
                    'dimension': name,
                    'value': round(value, 4),
                    'severity': 'COLLAPSE',
                    'message': f"Dimension {name} in collapse state ({value:.2f})",
                })
                self._total_alerts += 1
            elif value < self.critical_threshold:
                alerts.append({
                    'dimension': name,
                    'value': round(value, 4),
                    'severity': 'CRITICAL',
                    'message': f"Dimension {name} critically low ({value:.2f})",
                })
                self._total_alerts += 1
            elif value < self.degradation_threshold:
                alerts.append({
                    'dimension': name,
                    'value': round(value, 4),
                    'severity': 'DEGRADED',
                    'message': f"Dimension {name} degraded ({value:.2f})",
                })
                self._total_alerts += 1

        self._alert_history.extend(alerts)
        return alerts

    def get_state_vector(self) -> ConservationState:
        """Get current conservation state."""
        return ConservationState(
            mission_integrity=self._state.mission_integrity,
            knowledge_integrity=self._state.knowledge_integrity,
            trust_integrity=self._state.trust_integrity,
            energy_efficiency=self._state.energy_efficiency,
            capability_growth=self._state.capability_growth,
            recovery_capacity=self._state.recovery_capacity,
        )

    def get_trajectory(self, window: int = 50) -> Dict[str, Any]:
        """Analyze health trajectory over recent history."""
        recent = list(self._state_history)[-window:]
        if len(recent) < 2:
            return {'trend': 'stable', 'slope': 0.0, 'values': []}

        health_values = [s.overall_health for s in recent]
        slope = (health_values[-1] - health_values[0]) / max(len(health_values) - 1, 1)

        trend = 'improving' if slope > 0.01 else ('declining' if slope < -0.01 else 'stable')

        return {
            'trend': trend,
            'slope': round(slope, 6),
            'current_health': round(health_values[-1], 4),
            'min_health': round(min(health_values), 4),
            'max_health': round(max(health_values), 4),
            'values': [round(v, 4) for v in health_values[-10:]],
        }

    def get_statistics(self) -> Dict:
        return {
            'current_state': {
                'M_mission': round(self._state.mission_integrity, 4),
                'K_knowledge': round(self._state.knowledge_integrity, 4),
                'T_trust': round(self._state.trust_integrity, 4),
                'E_energy': round(self._state.energy_efficiency, 4),
                'C_capability': round(self._state.capability_growth, 4),
                'R_recovery': round(self._state.recovery_capacity, 4),
            },
            'overall_health': round(self._state.overall_health, 4),
            'severity': self.classify_severity().value,
            'weakest_dimension': self._state.weakest_dimension[0],
            'snapshots_taken': len(self._state_history),
            'total_alerts': self._total_alerts,
            'weights': self.weights,
        }


# ═══════════════════════════════════════════════════════════
# 4. CUMULATIVE OPPORTUNITY COST TRACKER
#    OC(t) = Σ V_i — multi-decade compounding value lost
# ═══════════════════════════════════════════════════════════

@dataclass
class OpportunityCostEntry:
    """A single recorded opportunity cost event."""
    step: int
    path_description: str
    foregone_value: float
    cumulative_oc: float
    annualized_rate: float = 0.0


class CumulativeOpportunityCostTracker:
    """
    Tracks cumulative opportunity cost over the system's lifetime.

    OC(t) = Σ_{i=t}^{T} V_i

    Unlike CounterfactualExplorer which computes per-step regret,
    this tracker maintains a lifetime total of all foregone value,
    enabling long-horizon strategic review.
    """

    def __init__(self, discount_rate: float = 0.95):
        self.discount_rate = discount_rate
        self._entries: deque = deque(maxlen=1000)
        self._total_oc = 0.0
        self._total_steps = 0
        self._peak_oc_step = 0
        self._peak_oc_value = 0.0

    def record_opportunity_cost(self, step: int,
                                 path_description: str,
                                 foregone_value: float) -> OpportunityCostEntry:
        """Record a single opportunity cost event."""
        self._total_oc += foregone_value * (self.discount_rate ** self._total_steps)
        self._total_steps += 1

        if self._total_oc > self._peak_oc_value:
            self._peak_oc_value = self._total_oc
            self._peak_oc_step = step

        annualized = (self._total_oc / max(self._total_steps, 1))

        entry = OpportunityCostEntry(
            step=step,
            path_description=path_description,
            foregone_value=foregone_value,
            cumulative_oc=self._total_oc,
            annualized_rate=annualized,
        )
        self._entries.append(entry)
        return entry

    def compute_lifetime_oc(self) -> float:
        """Total lifetime opportunity cost."""
        return self._total_oc

    def compute_recent_oc(self, window: int = 10) -> float:
        """OC over the last N steps."""
        recent = list(self._entries)[-window:]
        return sum(e.foregone_value * self.discount_rate ** max(0, self._total_steps - len(recent) + i)
                   for i, e in enumerate(recent))

    def get_statistics(self) -> Dict:
        return {
            'total_oc': round(self._total_oc, 4),
            'total_steps': self._total_steps,
            'annualized_rate': round(self._total_oc / max(self._total_steps, 1), 4),
            'peak_oc_step': self._peak_oc_step,
            'peak_oc_value': round(self._peak_oc_value, 4),
            'entries_recorded': len(self._entries),
        }


# ═══════════════════════════════════════════════════════════
# 5. UNIFIED TELOS v12 RUNTIME
# ═══════════════════════════════════════════════════════════

class TelosV12Runtime:
    """
    TELOS v12: The General Theory of Guided Intelligent Systems.

    Complete pipeline:
      G₀ → Objective Integrity → Decision Truth Engine → Reverse Planning
      → Forest Search → Neti-Neti → Red-Team + Counterfactual
      → Belief Verification → Decision Ledger → System Conservation
      → PCS → Friction Optimizer → Execution → Mission Audit
      → Strategy Update → Sleep → Auto-Tune

    Core axioms:
      1. Mission (G₀) immutable
      2. Narrative must match optimization (no self-deception)
      3. No surrender without evidence
      4. Counterfactual regret must be quantified
      5. Opportunity cost compounds over time
      6. System health is six-dimensional (M,K,T,E,C,R)
      7. Reverse planning anchors actions to long-term trajectories
      8. Merit Flow must exceed corruption threshold
    """

    def __init__(self, mission_vector: np.ndarray,
                 goal_vector: np.ndarray,
                 mission_id: str = "v12-mission",
                 min_reward_threshold: float = 0.4,
                 energy: float = 100.0,
                 planning_horizon: int = 10):
        mn = np.linalg.norm(mission_vector)
        self.mission_dir = mission_vector / mn if mn > 1e-9 else mission_vector
        self.mission_state = MissionState(
            mission_vector, mission_id, min_reward_threshold
        )

        # ── v11 Core ──
        self.v11 = TelosV11Runtime(
            mission_vector, mission_id, min_reward_threshold, energy
        )

        # ── v12 Extensions ──
        self.reverse_planner = ReversePlanningEngine(
            horizon_length=planning_horizon
        )
        self.merit_flow = MeritFlowMonitor()
        self.conservation = SystemConservationMonitor()
        self.oc_tracker = CumulativeOpportunityCostTracker()

        # ── Create initial reverse plan ──
        self.reverse_planner.create_plan(
            initial_state=mission_vector,
            goal_state=goal_vector,
            goal_step=planning_horizon,
        )

        # ── State ──
        self._step_count = 0
        self._execution_log: deque = deque(maxlen=500)
        self._current_state = mission_vector.copy()

    def execute_step(self, action_vector: np.ndarray,
                     observed_reward: float,
                     base_quality: float = 0.8,
                     claimed_reason: str = "",
                     actual_objective: str = "",
                     belief_constraints: Optional[List[str]] = None,
                     hidden_constraints: Optional[List[str]] = None,
                     assumptions: Optional[List[str]] = None,
                     alternative_values: Optional[List[float]] = None,
                     chosen_path_value: float = 0.0,
                     foregone_value: float = 0.0,
                     foregone_description: str = "",
                     decision_basis: str = "evidence",
                     evidence_weight: float = 0.8,
                     friction_metrics: Optional[Dict[str, float]] = None,
                     tes_score: Optional[float] = None,
                     recovery_rate: Optional[float] = None,
                     recovery_debt: float = 0.0,
                     evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute one full TELOS v12 pipeline step.
        """
        self._step_count += 1
        self._current_state = action_vector.copy()
        step_log: Dict[str, Any] = {'step': self._step_count}

        # ── 1. Mission Drift Detection ──
        mission_drift = float(np.linalg.norm(
            self._current_state - self.mission_state.mission_vector
        ))
        self.conservation.update_mission_integrity(mission_drift)
        step_log['mission_drift'] = round(mission_drift, 6)

        # ── 2. Decision Truth Audit (from v11) ──
        v11_result = self.v11.execute_step(
            action_vector, observed_reward, base_quality,
            claimed_reason, actual_objective,
            belief_constraints, hidden_constraints,
            assumptions, alternative_values, chosen_path_value,
            friction_metrics, tes_score, recovery_rate, evidence,
        )
        step_log['v11_pipeline'] = {
            'truth_status': v11_result.get('truth_audit', {}).get('status', 'N/A'),
            'alignment': v11_result.get('truth_audit', {}).get('alignment_score', 0),
            'net_quality': v11_result.get('v10_pipeline', {}).get('net_quality', 0),
        }

        # ── 3. Reverse Planning Evaluation ──
        plan_result = self.reverse_planner.evaluate_step(
            self._current_state, self._step_count
        )
        step_log['reverse_planning'] = {
            'deviation': plan_result.get('deviation', 0),
            'deviation_ratio': plan_result.get('deviation_ratio', 0),
            'exceeds_threshold': plan_result.get('exceeds_threshold', False),
            'milestones_achieved': plan_result.get('milestones_achieved', 0),
            'progress': plan_result.get('progress', 0),
        }

        # ── 4. Merit Flow ──
        basis_map = {
            'evidence': DecisionBasis.EVIDENCE,
            'authority': DecisionBasis.AUTHORITY,
            'hybrid': DecisionBasis.HYBRID,
        }
        basis = basis_map.get(decision_basis, DecisionBasis.UNKNOWN)
        self.merit_flow.record_decision(
            decision_id=f"step-{self._step_count}",
            basis=basis,
            evidence_weight=evidence_weight,
            decision_summary=claimed_reason or actual_objective,
        )
        mf_check = self.merit_flow.detect_corruption()
        step_log['merit_flow'] = {
            'current_mf': mf_check['merit_flow'],
            'is_corrupt': mf_check['is_corrupt'],
            'severity': mf_check['severity'],
        }

        # ── 5. Cumulative Opportunity Cost ──
        if foregone_value > 0:
            self.oc_tracker.record_opportunity_cost(
                self._step_count, foregone_description, foregone_value
            )
        step_log['cumulative_oc'] = round(
            self.oc_tracker.compute_lifetime_oc(), 4
        )

        # ── 6. System Conservation Update ──
        # Knowledge integrity: assume all decisions recorded
        self.conservation.update_knowledge_integrity(
            self._step_count, 0
        )
        # Trust integrity from merit flow
        self.conservation.update_trust_integrity(mf_check['merit_flow'])
        # Energy efficiency from base quality
        self.conservation.update_energy_efficiency(base_quality)
        # Capability growth: pruning ratio proxy
        prune_ratio = 1.0 - v11_result.get('v10_pipeline', {}).get('alignment', 0.5)
        promo_ratio = v11_result.get('v10_pipeline', {}).get('alignment', 0.5)
        self.conservation.update_capability_growth(prune_ratio, promo_ratio)
        # Recovery capacity
        self.conservation.update_recovery_capacity(recovery_debt)

        conservation_state = self.conservation.snapshot()
        conservation_alerts = self.conservation.check_alerts()

        step_log['conservation'] = {
            'overall_health': round(conservation_state.overall_health, 4),
            'severity': self.conservation.classify_severity().value,
            'weakest_dimension': conservation_state.weakest_dimension[0],
            'weakest_value': round(conservation_state.weakest_dimension[1], 4),
            'alerts': len(conservation_alerts),
        }

        # ── 7. Composite Directive ──
        directives = [v11_result.get('directive', '')]

        if plan_result.get('exceeds_threshold'):
            directives.append(
                f"REVERSE_PLANNING: Trajectory deviation {plan_result.get('deviation_ratio', 0):.2%} "
                f"exceeds threshold — redirect towards milestones"
            )

        if mf_check['is_corrupt']:
            directives.append(
                "MERIT_FLOW: Structural corruption — authority overriding evidence"
            )

        if conservation_state.overall_health < 0.4:
            weakest = conservation_state.weakest_dimension
            directives.append(
                f"CONSERVATION: System health critical ({conservation_state.overall_health:.2f}) "
                f"— weakest dimension: {weakest[0]} ({weakest[1]:.2f})"
            )

        step_log['directive'] = " | ".join(d for d in directives if d)

        self._execution_log.append(step_log)
        return step_log

    def get_mission_hash(self) -> str:
        return self.mission_state.immutable_hash()

    def get_statistics(self) -> Dict:
        return {
            'version': '12.0-general-theory-guided-intelligent-systems',
            'steps': self._step_count,
            'mission_id': self.mission_state.mission_id,
            'mission_hash': self.get_mission_hash(),
            'reverse_planner': self.reverse_planner.get_statistics(),
            'merit_flow': self.merit_flow.get_statistics(),
            'conservation': self.conservation.get_statistics(),
            'opportunity_cost': self.oc_tracker.get_statistics(),
            'v11': self.v11.get_statistics(),
        }


if __name__ == "__main__":
    mission = np.array([1.0, 0.5, 0.3, 0.8, 0.2])
    goal = np.array([0.2, 0.8, 0.6, 0.4, 0.9])
    runtime = TelosV12Runtime(mission, goal, "v12-demo", planning_horizon=8)

    print("=== TELOS v12: General Theory of Guided Intelligent Systems ===")
    print(f"Mission hash (immutable): {runtime.get_mission_hash()[:16]}...")

    # Step 1: Aligned, evidence-based, with opportunity cost
    r1 = runtime.execute_step(
        action_vector=np.array([0.9, 0.5, 0.3, 0.7, 0.2]),
        observed_reward=0.7, base_quality=0.85,
        claimed_reason="Market conditions are favorable",
        actual_objective="Market conditions are favorable for growth",
        alternative_values=[100, 200, 300],
        chosen_path_value=250,
        foregone_value=50,
        foregone_description="Did not pursue alternative path A",
        decision_basis="evidence",
        evidence_weight=0.9,
    )
    print(f"\nStep 1 (Aligned, Evidence-based):")
    print(f"  Mission Drift: {r1['mission_drift']:.4f}")
    print(f"  Conservation Health: {r1['conservation']['overall_health']:.4f}")
    print(f"  Merit Flow: {r1['merit_flow']['current_mf']}")
    print(f"  Cumulative OC: ${r1['cumulative_oc']:.2f}")
    print(f"  Reverse Planning Progress: {r1['reverse_planning']['progress']:.2%}")

    # Step 2: Authority override, with drift
    r2 = runtime.execute_step(
        action_vector=np.array([0.5, 0.8, 0.6, 0.3, 0.7]),
        observed_reward=0.6, base_quality=0.75,
        claimed_reason="Leadership decided",
        actual_objective="Avoid risk at all costs",
        decision_basis="authority",
        evidence_weight=0.2,
        recovery_debt=0.5,
    )
    print(f"\nStep 2 (Authority-based, Drift):")
    print(f"  Mission Drift: {r2['mission_drift']:.4f}")
    print(f"  Conservation Health: {r2['conservation']['overall_health']:.4f}")
    print(f"  Merit Flow: {r2['merit_flow']['current_mf']}")
    print(f"  Severity: {r2['conservation']['severity']}")

    stats = runtime.get_statistics()
    print(f"\n=== Statistics ===")
    print(f"  Version: {stats['version']}")
    print(f"  Steps: {stats['steps']}")
    print(f"  Overall Health: {stats['conservation']['overall_health']:.4f}")
    print(f"  Merit Flow: {stats['merit_flow']['merit_flow']}")
    print(f"  Total OC: ${stats['opportunity_cost']['total_oc']:.2f}")
    print(f"  Plans Created: {stats['reverse_planner']['total_plans_created']}")
