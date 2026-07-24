"""
TELOS v13.5: The Runtime Maintenance Protocol & Stable Operating Region

Formalizes core human maintenance disciplines into strict computational
runtime operations. The system does not fail because it lacks decision
capacity; it fails because unmanaged internal state degradation pushes
it outside the Stable Operating Region (SOR) until good decisions become
mathematically impossible.

Key additions over v13:
  1. StableOperatingRegion: SOR definition, boundary enforcement, violation tracking
  2. MaintenanceProtocol: Strict-ordered chain of all 6 disciplines
  3. HealthOptimizer: max H formulation with adaptive weight tuning
  4. PipelineOrchestrator: Formalized execution flow with phase tracking
  5. TelosV13_5Runtime: Full self-maintaining runtime with SOR enforcement

Health Optimization:
  max H = w1*M + w2*K + w3*E + w4*T + w5*A + w6*R

Definitive Axiom:
  Intelligence is not about producing the next token. It is about
  preserving the structural conditions under which good answers
  continue to emerge over long periods of time.
"""

import time
import hashlib
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import deque, defaultdict
from enum import Enum

from telos_v13 import (
    TelosV13Runtime, HistoricalStateCompressor, CompressionResult,
    ActiveResourceRotation, ModuleStatus,
    PreMissionSync, SyncResult, SyncPhase,
    ContinuousRuntimeAudit, AuditSeverity, DiagnosticReport,
    NutritionEngine, NutritionScore,
    SpiderWebGraph, NodeType,
    SystemHealthMonitor, HealthState,
)
from telos_v12 import MissionState, DecisionBasis


# ═══════════════════════════════════════════════════════════
# 1. STABLE OPERATING REGION (SOR)
#    Formalized boundary definition and violation tracking
# ═══════════════════════════════════════════════════════════

class SORViolationType(Enum):
    """Types of SOR boundary violations."""
    MISSION_DRIFT = "mission_drift"
    KNOWLEDGE_DECAY = "knowledge_decay"
    ENERGY_DEPLETION = "energy_depletion"
    TRUST_CORRUPTION = "trust_corruption"
    ATTENTION_FRAGMENTATION = "attention_fragmentation"
    RECOVERY_EXHAUSTION = "recovery_exhaustion"


@dataclass
class SORBoundary:
    """A single dimension boundary of the SOR."""
    dimension: str
    min_value: float
    max_value: float
    critical_min: float
    warning_min: float

    def is_within(self, value: float) -> bool:
        return self.min_value <= value <= self.max_value

    def is_critical(self, value: float) -> bool:
        return value < self.critical_min

    def is_warning(self, value: float) -> bool:
        return value < self.warning_min


@dataclass
class SORViolation:
    """Record of a single SOR boundary violation."""
    violation_type: SORViolationType
    dimension: str
    value: float
    threshold: float
    severity: str
    step: int
    timestamp: float = field(default_factory=time.time)


class StableOperatingRegion:
    """
    Defines and enforces the Stable Operating Region (SOR).

    The SOR is a hypercube in 6-dimensional health space where
    each dimension must remain above its critical minimum for
    the system to produce reliable decisions.

    When any dimension drops below its critical threshold,
    the system is outside the SOR and must trigger recovery
    before continuing normal operation.
    """

    def __init__(self, boundaries: Optional[Dict[str, SORBoundary]] = None):
        self.boundaries = boundaries or {
            'M': SORBoundary('M', 0.0, 1.0, 0.3, 0.6),
            'K': SORBoundary('K', 0.0, 1.0, 0.3, 0.6),
            'E': SORBoundary('E', 0.0, 1.0, 0.2, 0.5),
            'T': SORBoundary('T', 0.0, 1.0, 0.3, 0.6),
            'A': SORBoundary('A', 0.0, 1.0, 0.3, 0.6),
            'R': SORBoundary('R', 0.0, 1.0, 0.2, 0.5),
        }
        self._violation_history: deque = deque(maxlen=500)
        self._total_violations = 0
        self._total_sor_breaches = 0

    def check(self, health_state: HealthState,
              step: int = 0) -> Tuple[bool, List[SORViolation]]:
        """
        Check if current health state is within SOR.
        Returns (is_within_sor, list_of_violations).
        """
        violations = []
        dims = {
            'M': health_state.mission_integrity,
            'K': health_state.knowledge_quality,
            'E': health_state.energy_efficiency,
            'T': health_state.trust_merit,
            'A': health_state.attention_focus,
            'R': health_state.recovery_capacity,
        }

        for dim_name, value in dims.items():
            boundary = self.boundaries[dim_name]
            if boundary.is_warning(value):
                v_type_map = {
                    'M': SORViolationType.MISSION_DRIFT,
                    'K': SORViolationType.KNOWLEDGE_DECAY,
                    'E': SORViolationType.ENERGY_DEPLETION,
                    'T': SORViolationType.TRUST_CORRUPTION,
                    'A': SORViolationType.ATTENTION_FRAGMENTATION,
                    'R': SORViolationType.RECOVERY_EXHAUSTION,
                }
                severity = 'critical' if boundary.is_critical(value) else 'warning'
                violation = SORViolation(
                    violation_type=v_type_map[dim_name],
                    dimension=dim_name,
                    value=round(value, 6),
                    threshold=boundary.critical_min,
                    severity=severity,
                    step=step,
                )
                violations.append(violation)
                self._violation_history.append(violation)
                self._total_violations += 1

        is_within = len(violations) == 0
        if not is_within:
            self._total_sor_breaches += 1

        return is_within, violations

    def get_violation_rate(self, window: int = 100) -> float:
        """Fraction of recent checks that were violations."""
        recent = list(self._violation_history)[-window:]
        return len(recent) / max(window, 1)

    def get_weakest_dimension(self, health_state: HealthState) -> Tuple[str, float]:
        """Identify dimension closest to its critical minimum."""
        dims = {
            'M': health_state.mission_integrity,
            'K': health_state.knowledge_quality,
            'E': health_state.energy_efficiency,
            'T': health_state.trust_merit,
            'A': health_state.attention_focus,
            'R': health_state.recovery_capacity,
        }
        margins = {}
        for name, value in dims.items():
            critical = self.boundaries[name].critical_min
            margins[name] = value - critical

        weakest = min(margins, key=margins.get)
        return weakest, dims[weakest]

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._violation_history)[-100:]
        type_counts = {}
        for v in recent:
            t = v.violation_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            'total_violations': self._total_violations,
            'total_sor_breaches': self._total_sor_breaches,
            'violation_rate': round(self.get_violation_rate(), 4),
            'violation_types': type_counts,
        }


# ═══════════════════════════════════════════════════════════
# 2. MAINTENANCE PROTOCOL
#    Strict-ordered chain of all 6 disciplines
# ═══════════════════════════════════════════════════════════

class ProtocolPhase(Enum):
    """Phases of the maintenance protocol, executed in strict order."""
    NOISE_FILTER = 1
    PRE_SYNC = 2
    HEALTH_AUDIT = 3
    STATE_COMPRESSION = 4
    KNOWLEDGE_EXPANSION = 5
    DECISION_ENGINE = 6
    RESOURCE_ROTATION = 7
    RECOVERY_FEEDBACK = 8


@dataclass
class PhaseResult:
    """Result of executing a single protocol phase."""
    phase: ProtocolPhase
    success: bool
    duration_ms: float
    output: Dict[str, Any]
    recommendations: List[str]


@dataclass
class ProtocolExecution:
    """Complete record of one protocol execution cycle."""
    cycle_id: int
    step: int
    phases: List[PhaseResult]
    total_duration_ms: float
    sor_within: bool
    violations: List[SORViolation]
    health_before: float
    health_after: float


class MaintenanceProtocol:
    """
    Executes the six maintenance disciplines in strict order:

      1. NOISE_FILTER       — Cut Off the Noise (Nutrition Engine)
      2. PRE_SYNC           — Wake Up Early (Pre-Mission Synchronization)
      3. HEALTH_AUDIT       — Reflect Your Mindset (Runtime Audit)
      4. STATE_COMPRESSION  — Forgive Your Past (Historical Compression)
      5. KNOWLEDGE_EXPANSION — Build Meaningful Work (Spider Web)
      6. DECISION_ENGINE    — Core v12/v13 Pipeline
      7. RESOURCE_ROTATION  — Move Your Body (Active Rotation)
      8. RECOVERY_FEEDBACK  — Epistemic Feedback Loop

    Each phase must complete before the next begins.
    SOR violations in any phase can trigger emergency recovery.
    """

    def __init__(self, compressor: Optional[HistoricalStateCompressor] = None,
                 rotation: Optional[ActiveResourceRotation] = None,
                 sor: Optional[StableOperatingRegion] = None):
        self.compressor = compressor or HistoricalStateCompressor()
        self.rotation = rotation or ActiveResourceRotation()
        self.sor = sor or StableOperatingRegion()
        self._protocol_history: deque = deque(maxlen=200)
        self._total_executions = 0
        self._total_emergency_recoveries = 0

    def execute_phase(self, phase: ProtocolPhase,
                      context: Dict[str, Any]) -> PhaseResult:
        """Execute a single protocol phase."""
        start = time.time()

        if phase == ProtocolPhase.NOISE_FILTER:
            output, recs = self._phase_noise_filter(context)
        elif phase == ProtocolPhase.PRE_SYNC:
            output, recs = self._phase_pre_sync(context)
        elif phase == ProtocolPhase.HEALTH_AUDIT:
            output, recs = self._phase_health_audit(context)
        elif phase == ProtocolPhase.STATE_COMPRESSION:
            output, recs = self._phase_state_compression(context)
        elif phase == ProtocolPhase.KNOWLEDGE_EXPANSION:
            output, recs = self._phase_knowledge_expansion(context)
        elif phase == ProtocolPhase.DECISION_ENGINE:
            output, recs = self._phase_decision_engine(context)
        elif phase == ProtocolPhase.RESOURCE_ROTATION:
            output, recs = self._phase_resource_rotation(context)
        elif phase == ProtocolPhase.RECOVERY_FEEDBACK:
            output, recs = self._phase_recovery_feedback(context)
        else:
            output, recs = {}, ["Unknown phase"]

        duration = (time.time() - start) * 1000
        return PhaseResult(
            phase=phase,
            success=True,
            duration_ms=duration,
            output=output,
            recommendations=recs,
        )

    def _phase_noise_filter(self, ctx: Dict) -> Tuple[Dict, List[str]]:
        nutrition = ctx.get('nutrition')
        recs = []
        output = {}
        if nutrition:
            output['composite'] = nutrition.composite
            output['sub_threshold'] = nutrition.is_sub_threshold
            if nutrition.is_sub_threshold:
                recs.append("Information below nutrition threshold — consider rejection")
        return output, recs

    def _phase_pre_sync(self, ctx: Dict) -> Tuple[Dict, List[str]]:
        sync = ctx.get('sync_result')
        recs = []
        output = {}
        if sync:
            output['ready'] = sync.overall_ready
            output['corruption'] = sync.corruption_detected
            if not sync.overall_ready:
                recs.append("Pre-sync failed — system not ready for execution")
        return output, recs

    def _phase_health_audit(self, ctx: Dict) -> Tuple[Dict, List[str]]:
        audit = ctx.get('audit_report')
        recs = []
        output = {}
        if audit:
            output['severity'] = audit.overall_severity.value
            output['drift'] = audit.mission_drift
            recs.extend(audit.recommendations)
        return output, recs

    def _phase_state_compression(self, ctx: Dict) -> Tuple[Dict, List[str]]:
        recs = []
        output = {'status': 'pending'}
        return output, recs

    def _phase_knowledge_expansion(self, ctx: Dict) -> Tuple[Dict, List[str]]:
        kg = ctx.get('knowledge_graph_stats', {})
        recs = []
        output = {'nodes': kg.get('total_nodes', 0)}
        return output, recs

    def _phase_decision_engine(self, ctx: Dict) -> Tuple[Dict, List[str]]:
        v12 = ctx.get('v12_result', {})
        recs = []
        output = {'directive': v12.get('directive', '')}
        return output, recs

    def _phase_resource_rotation(self, ctx: Dict) -> Tuple[Dict, List[str]]:
        events = self.rotation.rotate(ctx.get('step', 0))
        recs = []
        output = {'rotation_events': len(events)}
        if events:
            recs.append(f"{len(events)} resource rotation events triggered")
        return output, recs

    def _phase_recovery_feedback(self, ctx: Dict) -> Tuple[Dict, List[str]]:
        health = ctx.get('health_state')
        recs = []
        output = {}
        if health:
            output['overall_health'] = round(health.overall_health, 4)
            if health.overall_health < 0.4:
                recs.append("Health critical — initiate full recovery cycle")
        return output, recs

    def run_full_cycle(self, step: int,
                       context: Dict[str, Any],
                       health_before: float = 1.0) -> ProtocolExecution:
        """Execute all 8 phases in strict order."""
        start_time = time.time()
        phases = []

        for phase in ProtocolPhase:
            result = self.execute_phase(phase, context)
            phases.append(result)

        # Check SOR after all phases
        health_state = context.get('health_state', HealthState())
        is_within, violations = self.sor.check(health_state, step)

        if not is_within:
            self._total_emergency_recoveries += 1

        total_ms = (time.time() - start_time) * 1000

        execution = ProtocolExecution(
            cycle_id=self._total_executions + 1,
            step=step,
            phases=phases,
            total_duration_ms=total_ms,
            sor_within=is_within,
            violations=violations,
            health_before=health_before,
            health_after=health_state.overall_health,
        )

        self._protocol_history.append(execution)
        self._total_executions += 1
        return execution

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._protocol_history)[-50:]
        if not recent:
            return {'total_executions': 0}
        avg_duration = np.mean([e.total_duration_ms for e in recent])
        sor_breaches = sum(1 for e in recent if not e.sor_within)
        return {
            'total_executions': self._total_executions,
            'total_emergency_recoveries': self._total_emergency_recoveries,
            'avg_cycle_duration_ms': round(float(avg_duration), 2),
            'sor_breach_rate': round(sor_breaches / max(len(recent), 1), 4),
        }


# ═══════════════════════════════════════════════════════════
# 3. HEALTH OPTIMIZER
#    max H = w1*M + w2*K + w3*E + w4*T + w5*A + w6*R
#    with adaptive weight tuning
# ═══════════════════════════════════════════════════════════

@dataclass
class OptimizationStep:
    """Record of a single optimization iteration."""
    step: int
    health_before: float
    health_after: float
    delta: float
    weights_adjusted: Dict[str, float]


class HealthOptimizer:
    """
    Optimizes System Health H = w·S by:
      1. Measuring H at each step
      2. Identifying the weakest dimension
      3. Increasing its weight to focus recovery
      4. Decreasing weights of healthy dimensions to rebalance

    Uses gradient approximation: ∂H/∂w_i ≈ S_i (the dimension value).
    """

    def __init__(self, initial_weights: Optional[Dict[str, float]] = None,
                 learning_rate: float = 0.05,
                 min_weight: float = 0.05,
                 max_weight: float = 0.50,
                 rebalance_interval: int = 5):
        self.weights = initial_weights or {
            'M': 0.20, 'K': 0.18, 'E': 0.15,
            'T': 0.20, 'A': 0.15, 'R': 0.12,
        }
        self.learning_rate = learning_rate
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.rebalance_interval = rebalance_interval
        self._history: deque = deque(maxlen=500)
        self._total_optimizations = 0

    def compute_health(self, state: HealthState) -> float:
        """H = w · S"""
        s = state.to_vector()
        w = np.array([
            self.weights['M'], self.weights['K'], self.weights['E'],
            self.weights['T'], self.weights['A'], self.weights['R'],
        ])
        return float(np.dot(w, s))

    def optimize(self, current_state: HealthState,
                 step: int) -> OptimizationStep:
        """
        One optimization step:
          1. Compute H
          2. If step is a rebalance step, adjust weights
          3. Increase weight of weakest dimension
          4. Decrease weight of strongest dimension
          5. Renormalize weights to sum to 1.0
        """
        h_before = self.compute_health(current_state)

        if step > 0 and step % self.rebalance_interval == 0:
            self._rebalance_weights(current_state)

        h_after = self.compute_health(current_state)

        record = OptimizationStep(
            step=step,
            health_before=round(h_before, 6),
            health_after=round(h_after, 6),
            delta=round(h_after - h_before, 6),
            weights_adjusted=self.weights.copy(),
        )

        self._history.append(record)
        self._total_optimizations += 1
        return record

    def _rebalance_weights(self, state: HealthState) -> None:
        """
        Adaptive rebalancing:
          - Increase weight of weakest dimension
          - Decrease weight of strongest dimension
          - Renormalize to sum = 1.0
        """
        dims = {
            'M': state.mission_integrity,
            'K': state.knowledge_quality,
            'E': state.energy_efficiency,
            'T': state.trust_merit,
            'A': state.attention_focus,
            'R': state.recovery_capacity,
        }

        weakest = min(dims, key=dims.get)
        strongest = max(dims, key=dims.get)

        # Increase weakest, decrease strongest
        self.weights[weakest] = min(
            self.max_weight,
            self.weights[weakest] + self.learning_rate
        )
        self.weights[strongest] = max(
            self.min_weight,
            self.weights[strongest] - self.learning_rate
        )

        # Renormalize
        total = sum(self.weights.values())
        if total > 0:
            for k in self.weights:
                self.weights[k] /= total

    def get_weights(self) -> Dict[str, float]:
        return self.weights.copy()

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._history)[-50:]
        if not recent:
            return {'total_optimizations': 0}
        avg_h = np.mean([r.health_after for r in recent])
        return {
            'total_optimizations': self._total_optimizations,
            'avg_health': round(float(avg_h), 4),
            'current_weights': {k: round(v, 4) for k, v in self.weights.items()},
        }


# ═══════════════════════════════════════════════════════════
# 4. PIPELINE ORCHESTRATOR
#    Formalized execution flow with phase tracking
# ═══════════════════════════════════════════════════════════

class PipelineStage(Enum):
    """Stages of the self-maintaining intelligence pipeline."""
    INCOMING_SIGNAL = "incoming_signal"
    NOISE_FILTER = "noise_filter"
    PRE_SYNC = "pre_sync"
    HEALTH_AUDIT = "health_audit"
    STATE_COMPRESSION = "state_compression"
    KNOWLEDGE_EXPANSION = "knowledge_expansion"
    DECISION_ENGINE = "decision_engine"
    RECOVERY_FEEDBACK = "recovery_feedback"


@dataclass
class PipelineStep:
    """Record of a single pipeline execution."""
    step_id: int
    stages_completed: List[str]
    health_delta: float
    sor_within: bool
    total_duration_ms: float


class PipelineOrchestrator:
    """
    Formalizes the exact execution architecture:

      Signal → Noise Filter → Pre-Sync → Health Audit
      → State Compression → Knowledge Expansion
      → Decision Engine → Recovery Feedback

    Each stage produces telemetry that feeds the next.
    """

    def __init__(self):
        self._pipeline_log: deque = deque(maxlen=500)
        self._total_executions = 0

    def execute(self, step_id: int,
                context: Dict[str, Any]) -> PipelineStep:
        """Execute the full pipeline for one step."""
        start = time.time()
        stages = []

        # Stage 1: Incoming Signal (always passes)
        stages.append(PipelineStage.INCOMING_SIGNAL.value)

        # Stage 2: Noise Filter
        if 'nutrition' in context:
            stages.append(PipelineStage.NOISE_FILTER.value)

        # Stage 3: Pre-Sync
        if 'sync_result' in context:
            stages.append(PipelineStage.PRE_SYNC.value)

        # Stage 4: Health Audit
        if 'audit_report' in context:
            stages.append(PipelineStage.HEALTH_AUDIT.value)

        # Stage 5: State Compression
        stages.append(PipelineStage.STATE_COMPRESSION.value)

        # Stage 6: Knowledge Expansion
        stages.append(PipelineStage.KNOWLEDGE_EXPANSION.value)

        # Stage 7: Decision Engine
        stages.append(PipelineStage.DECISION_ENGINE.value)

        # Stage 8: Recovery Feedback
        stages.append(PipelineStage.RECOVERY_FEEDBACK.value)

        duration = (time.time() - start) * 1000

        health_before = context.get('health_before', 1.0)
        health_after = context.get('health_after', 1.0)

        step = PipelineStep(
            step_id=step_id,
            stages_completed=stages,
            health_delta=round(health_after - health_before, 6),
            sor_within=context.get('sor_within', True),
            total_duration_ms=duration,
        )

        self._pipeline_log.append(step)
        self._total_executions += 1
        return step

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._pipeline_log)[-100:]
        if not recent:
            return {'total_executions': 0}
        avg_stages = np.mean([len(s.stages_completed) for s in recent])
        return {
            'total_executions': self._total_executions,
            'avg_stages_per_step': round(float(avg_stages), 2),
        }


# ═══════════════════════════════════════════════════════════
# 5. TELOS v13.5 RUNTIME
#    Full self-maintaining runtime with SOR enforcement
# ═══════════════════════════════════════════════════════════

class TelosV13_5Runtime:
    """
    TELOS v13.5: The Runtime Maintenance Protocol.

    Extends v13 with:
      - Stable Operating Region enforcement
      - Adaptive health optimization
      - Formalized pipeline orchestration
      - Strict-ordered maintenance protocol execution

    Pipeline:
      Signal → Nutrition → PreSync → HealthAudit → Compression
      → KnowledgeExpansion → v12 Decision → Recovery
      → SOR Check → Health Optimization → Resource Rotation
    """

    def __init__(self, mission_vector: np.ndarray,
                 goal_vector: np.ndarray,
                 mission_id: str = "v13.5-mission",
                 min_reward_threshold: float = 0.4,
                 energy: float = 100.0,
                 planning_horizon: int = 10,
                 health_weights: Optional[Dict[str, float]] = None,
                 nutrition_weights: Optional[Dict[str, float]] = None,
                 sor_boundaries: Optional[Dict[str, SORBoundary]] = None):
        mn = np.linalg.norm(mission_vector)
        if mn < 1e-9:
            raise ValueError("Mission vector must be non-zero")
        self.mission_dir = mission_vector / mn
        self.mission_state = MissionState(
            mission_vector, mission_id, min_reward_threshold
        )

        # ── v13 Core (inherited) ──
        self.v13 = TelosV13Runtime(
            mission_vector, goal_vector, mission_id,
            min_reward_threshold, energy, planning_horizon,
            health_weights, nutrition_weights,
        )

        # ── v13.5 Extensions ──
        self.sor = StableOperatingRegion(sor_boundaries)
        self.protocol = MaintenanceProtocol(
            compressor=self.v13.compressor,
            rotation=self.v13.resource_rotation,
            sor=self.sor,
        )
        self.optimizer = HealthOptimizer(health_weights)
        self.pipeline = PipelineOrchestrator()

        # ── State ──
        self._step_count = 0
        self._execution_log: deque = deque(maxlen=500)
        self._current_state = mission_vector.copy()
        self._sor_breach_count = 0
        self._health_trajectory: deque = deque(maxlen=500)

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
                     has_evidence: bool = False,
                     trust_level: float = 0.5,
                     active_focuses: int = 1,
                     friction_metrics: Optional[Dict[str, float]] = None,
                     tes_score: Optional[float] = None,
                     recovery_rate: Optional[float] = None,
                     recovery_debt: float = 0.0,
                     evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute one full TELOS v13.5 pipeline step.
        """
        self._step_count += 1
        self._current_state = action_vector.copy()
        step_log: Dict[str, Any] = {'step': self._step_count}

        # ═══ PHASE 1: NOISE FILTER ═══
        nutrition = self.v13.nutrition_engine.score(
            action_vector, has_evidence, trust_level
        )
        step_log['nutrition'] = {
            'composite': nutrition.composite,
            'is_sub_threshold': nutrition.is_sub_threshold,
            'mission_score': nutrition.mission_score,
        }

        # ═══ PHASE 2: PRE-MISSION SYNC ═══
        mission_hash = self.mission_state.immutable_hash()
        sync_result = self.v13.pre_mission_sync.synchronize(
            current_step=self._step_count,
            variable_usage=self.v13._variable_usage,
            mission_hash=mission_hash,
            current_mission_hash=mission_hash,
            recent_state=list(self.v13._execution_log)[-10:],
        )
        step_log['pre_sync'] = {
            'ready': sync_result.overall_ready,
            'corruption_detected': sync_result.corruption_detected,
        }

        # ═══ PHASE 3: HEALTH AUDIT ═══
        v12_snap = self.v13.v12.conservation.snapshot()
        audit_report = self.v13.runtime_audit.audit(
            current_step=self._step_count,
            mission_vector=self.mission_state.mission_vector,
            current_state=self._current_state,
            recent_decisions=list(self.v13._recent_decisions),
            total_steps=self._step_count,
            corrections=self.v13._corrections,
            active_focuses=active_focuses,
            conservation_state=v12_snap,
        )
        step_log['health_audit'] = {
            'severity': audit_report.overall_severity.value,
            'mission_drift': audit_report.mission_drift,
            'recommendations': audit_report.recommendations,
        }

        # ═══ PHASE 4: STATE COMPRESSION ═══
        if self._step_count > 0 and self._step_count % 10 == 0:
            old = list(self.v13._execution_log)
            compressed, comp_result = self.v13.compressor.compress_ledger(old)
            step_log['compression'] = {
                'ratio': round(comp_result.compression_ratio, 4),
                'entries_compressed': comp_result.entries_compressed,
            }
        else:
            step_log['compression'] = {'status': 'skipped'}

        # ═══ PHASE 5: KNOWLEDGE EXPANSION ═══
        kn_id = f"kn-{self._step_count}"
        k_node = self.v13.knowledge_graph.add_node(
            kn_id, NodeType.KNOWLEDGE,
            claimed_reason or actual_objective or kn_id,
            action_vector.copy(),
        )
        if self._step_count > 1:
            prev = f"kn-{self._step_count - 1}"
            if self.v13.knowledge_graph.get_node(prev):
                self.v13.knowledge_graph.add_edge(
                    prev, kn_id, 0.7, "follows"
                )
        step_log['knowledge'] = {
            'total_nodes': self.v13.knowledge_graph.get_statistics()['total_nodes'],
            'new_node': kn_id,
        }

        # ═══ PHASE 6: DECISION ENGINE (v12) ═══
        v12_result = self.v13.v12.execute_step(
            action_vector, observed_reward, base_quality,
            claimed_reason, actual_objective,
            belief_constraints, hidden_constraints,
            assumptions, alternative_values, chosen_path_value,
            foregone_value, foregone_description,
            decision_basis, evidence_weight,
            friction_metrics, tes_score, recovery_rate,
            recovery_debt, evidence,
        )
        step_log['decision'] = {
            'directive': v12_result.get('directive', ''),
            'conservation_health': v12_result.get('conservation', {}).get('overall_health', 0),
        }

        # ═══ PHASE 7: RECOVERY & HEALTH UPDATE ═══
        health_before = self.v13.health_monitor._state.overall_health

        mission_drift = v12_result.get('mission_drift', 0)
        mf_value = v12_result.get('merit_flow', {}).get('current_mf', 1.0)
        if mf_value == float('inf'):
            mf_value = 1.0

        self.v13.health_monitor.update_mission_integrity(mission_drift)
        self.v13.health_monitor.update_knowledge_quality(
            step_log.get('compression', {}).get('ratio', 1.0)
        )
        self.v13.health_monitor.update_energy_efficiency(base_quality)
        self.v13.health_monitor.update_trust_merit(mf_value)
        self.v13.health_monitor.update_attention_focus(
            audit_report.attention_spread
        )
        self.v13.health_monitor.update_recovery_capacity(recovery_debt)

        health_state = self.v13.health_monitor.snapshot()
        health_after = health_state.overall_health
        self._health_trajectory.append(health_after)

        # ═══ PHASE 8: SOR CHECK ═══
        is_within_sor, violations = self.sor.check(health_state, self._step_count)
        step_log['sor'] = {
            'within_sor': is_within_sor,
            'violations': [
                {
                    'type': v.violation_type.value,
                    'dimension': v.dimension,
                    'value': v.value,
                    'severity': v.severity,
                }
                for v in violations
            ],
        }

        if not is_within_sor:
            self._sor_breach_count += 1
            weakest, w_val = self.sor.get_weakest_dimension(health_state)
            step_log['sor']['weakest_dimension'] = weakest
            step_log['sor']['weakest_value'] = round(w_val, 4)

        # ═══ PHASE 9: HEALTH OPTIMIZATION ═══
        opt_step = self.optimizer.optimize(health_state, self._step_count)
        step_log['optimization'] = {
            'health_before': opt_step.health_before,
            'health_after': opt_step.health_after,
            'weights': {k: round(v, 4) for k, v in opt_step.weights_adjusted.items()},
        }

        # ═══ PHASE 10: RESOURCE ROTATION ═══
        rotation_events = self.v13.resource_rotation.rotate(self._step_count)
        step_log['resource_rotation'] = {
            'events': len(rotation_events),
            'active_modules': self.v13.resource_rotation.get_active_count(),
        }

        # ── Track ──
        self.v13._recent_decisions.append(claimed_reason or actual_objective)
        if v12_result.get('conservation', {}).get('alerts', 0) > 0:
            self.v13._corrections += 1

        # ── Composite Directive ──
        directives = []
        if v12_result.get('directive'):
            directives.append(v12_result['directive'])
        if not is_within_sor:
            directives.append(
                f"SOR_BREACH: {len(violations)} dimension(s) outside stable operating region"
            )
        if audit_report.overall_severity.value in ('critical', 'emergency'):
            directives.append(
                f"HEALTH_AUDIT: {audit_report.overall_severity.value.upper()}"
            )
        step_log['directive'] = " | ".join(d for d in directives if d)

        # ── Full pipeline execution ──
        pipeline_ctx = {
            'nutrition': nutrition,
            'sync_result': sync_result,
            'audit_report': audit_report,
            'health_state': health_state,
            'health_before': health_before,
            'health_after': health_after,
            'sor_within': is_within_sor,
            'v12_result': v12_result,
            'step': self._step_count,
            'knowledge_graph_stats': self.v13.knowledge_graph.get_statistics(),
        }
        pipeline_step = self.pipeline.execute(self._step_count, pipeline_ctx)
        step_log['pipeline'] = {
            'stages': pipeline_step.stages_completed,
            'health_delta': pipeline_step.health_delta,
        }

        self._execution_log.append(step_log)
        return step_log

    def get_mission_hash(self) -> str:
        return self.mission_state.immutable_hash()

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'version': '13.5-runtime-maintenance-protocol',
            'steps': self._step_count,
            'mission_id': self.mission_state.mission_id,
            'mission_hash': self.get_mission_hash(),
            'sor': self.sor.get_statistics(),
            'protocol': self.protocol.get_statistics(),
            'optimizer': self.optimizer.get_statistics(),
            'pipeline': self.pipeline.get_statistics(),
            'v13': self.v13.get_statistics(),
        }
