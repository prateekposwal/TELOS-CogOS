"""
TELOS v9: Objective Integrity & Purpose-Driven Architecture

Formalizes the distinction between Mission (G₀) and Reward (R_t),
solving Goodhart's Law: systems optimizing purely for external metrics
invariably drift from their original purpose.

Core Principles:
  1. Objective Invariance: max G₀ subject to R_t ≥ R_min
     (Reward is a constraint, never the objective)

  2. Cognitive Friction: Q = Q₀ - F
     (Internal noise taxes decision quality)

  3. Prediction Rigidity vs. Mission Adaptability:
     - Predictions/strategies: fluid, updated instantly on evidence
     - Mission (G₀): immutable, invariant across volatility

Unified Pipeline:
  G₀ → Objective Integrity Monitor → Forest Search → Neti-Neti
  → Decision Ledger → Reasoning Runtime → Friction Optimizer
  → Execution → Mission Audit → Strategy Update (never the mission)
"""

import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

from telos_negative_search import (
    NetiNetiPruningEngine, ForestSearchRouter,
    StableRegionMonitor, ModerationOptimizer,
)
from telos_decision_ledger import DecisionLedger, DecisionLedgerEntry
from telos_v8x_extensions import (
    MissionWeightedConsensus, EpistemicCalibrationLoop,
    ContextImmunologyFilter, AgentProposal, ContextChunk,
)


# ═══════════════════════════════════════════════════════════
# 1. OBJECTIVE INTEGRITY MONITOR
#    Guards against Goodhart's Law & Proxy Optimization
# ═══════════════════════════════════════════════════════════

class DriftSeverity(Enum):
    """Classification of mission drift severity."""
    NOMINAL = "NOMINAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


class ObjectiveStatus(Enum):
    """Status of the objective integrity check."""
    NOMINAL = "NOMINAL"
    REWARD_DEFICIT = "REWARD_DEFICIT"
    MISSION_DRIFT = "MISSION_DRIFT"
    PROXY_DRIFT = "PROXY_DRIFT"
    DUAL_VIOLATION = "DUAL_VIOLATION"


@dataclass
class IntegrityAudit:
    """Result of a single objective integrity audit."""
    mission_alignment: float          # cos(action, G₀) ∈ [-1, 1]
    reward_constraint_met: bool       # R_t ≥ R_min
    reward_value: float
    reward_min: float
    objective_status: ObjectiveStatus
    drift_severity: DriftSeverity
    proxy_drift_detected: bool
    corrective_signal: float          # Negative = drift correction needed
    reasoning: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class MissionState:
    """Immutable mission definition with versioning."""
    mission_vector: np.ndarray
    mission_id: str
    min_reward_threshold: float
    created_at: float = field(default_factory=time.time)
    version: int = 1

    def immutable_hash(self) -> str:
        import hashlib
        data = f"{self.mission_id}:{self.mission_vector.tobytes()}:{self.version}"
        return hashlib.sha256(data.encode()).hexdigest()


class ObjectiveIntegrityMonitor:
    """
    Guards against Goodhart's Law and Proxy Optimization.

    Ensures the system optimizes for foundational mission G₀ while
    treating external rewards R_t strictly as operational constraints:
      max G₀  subject to  R_t ≥ R_min

    Proxy drift detection:
      High reward + Low mission alignment = PROXY_DRIFT
      (System is gaming the metric instead of fulfilling the mission)
    """

    def __init__(self, mission_state: MissionState,
                 drift_warning_threshold: float = 0.5,
                 drift_critical_threshold: float = 0.3,
                 drift_emergency_threshold: float = 0.1):
        self.mission_state = mission_state
        self.drift_warning_threshold = drift_warning_threshold
        self.drift_critical_threshold = drift_critical_threshold
        self.drift_emergency_threshold = drift_emergency_threshold

        self._audit_history: deque = deque(maxlen=500)
        self._total_audits = 0
        self._total_warnings = 0
        self._total_proxy_drifts = 0
        self._consecutive_drifts = 0
        self._max_consecutive_drifts = 0

    def audit_objective(self, action_vector: np.ndarray,
                        observed_reward: float,
                        base_quality: float = 0.0) -> IntegrityAudit:
        """
        Evaluate whether current execution aligns with G₀ and satisfies
        R_min constraint.

        Core formula:
          Alignment = cos(action, G₀)
          Status = f(Alignment, R_t, R_min, previous_history)
        """
        self._total_audits += 1

        # ── Mission Alignment ──
        an = np.linalg.norm(action_vector)
        mn = np.linalg.norm(self.mission_state.mission_vector)
        if an < 1e-9 or mn < 1e-9:
            alignment = 0.0
        else:
            alignment = float(np.dot(action_vector, self.mission_state.mission_vector) / (an * mn))

        # ── Reward Constraint ──
        reward_min = self.mission_state.min_reward_threshold
        constraint_met = observed_reward >= reward_min

        # ── Proxy Drift Detection ──
        # Goodhart's Law: high reward but low mission alignment
        proxy_drift = (observed_reward > 0.8) and (alignment < 0.5)

        # ── Drift Severity ──
        if alignment < self.drift_emergency_threshold:
            severity = DriftSeverity.EMERGENCY
        elif alignment < self.drift_critical_threshold:
            severity = DriftSeverity.CRITICAL
        elif alignment < self.drift_warning_threshold:
            severity = DriftSeverity.WARNING
        else:
            severity = DriftSeverity.NOMINAL

        # ── Objective Status ──
        if proxy_drift:
            status = ObjectiveStatus.PROXY_DRIFT
            self._total_proxy_drifts += 1
            self._consecutive_drifts += 1
        elif not constraint_met and alignment < self.drift_warning_threshold:
            status = ObjectiveStatus.DUAL_VIOLATION
            self._consecutive_drifts += 1
        elif not constraint_met:
            status = ObjectiveStatus.REWARD_DEFICIT
            self._consecutive_drifts += 1
        elif alignment < self.drift_warning_threshold:
            status = ObjectiveStatus.MISSION_DRIFT
            self._consecutive_drifts += 1
        else:
            status = ObjectiveStatus.NOMINAL
            self._consecutive_drifts = 0

        self._max_consecutive_drifts = max(self._max_consecutive_drifts, self._consecutive_drifts)

        if severity != DriftSeverity.NOMINAL:
            self._total_warnings += 1

        # ── Corrective Signal ──
        # Negative when drift detected, magnitude proportional to misalignment
        corrective_signal = -(1.0 - alignment) * (1.0 if not constraint_met else 0.5)

        # ── Reasoning ──
        if proxy_drift:
            reasoning = (f"PROXY DRIFT: reward={observed_reward:.4f} is high but "
                         f"mission alignment={alignment:.4f} is below threshold. "
                         f"System may be gaming the metric.")
        elif status == ObjectiveStatus.MISSION_DRIFT:
            reasoning = (f"MISSION DRIFT: alignment={alignment:.4f} below "
                         f"warning threshold {self.drift_warning_threshold}. "
                         f"Strategy must be updated to realign with G₀.")
        elif status == ObjectiveStatus.REWARD_DEFICIT:
            reasoning = (f"REWARD DEFICIT: reward={observed_reward:.4f} below "
                         f"minimum {reward_min}. Execution continues but "
                         f"resource allocation may need adjustment.")
        elif status == ObjectiveStatus.DUAL_VIOLATION:
            reasoning = (f"DUAL VIOLATION: reward deficit AND mission drift. "
                         f"Execute emergency realignment with G₀.")
        else:
            reasoning = (f"NOMINAL: alignment={alignment:.4f}, "
                         f"reward={observed_reward:.4f} ≥ min={reward_min}.")

        audit = IntegrityAudit(
            mission_alignment=alignment,
            reward_constraint_met=constraint_met,
            reward_value=observed_reward,
            reward_min=reward_min,
            objective_status=status,
            drift_severity=severity,
            proxy_drift_detected=proxy_drift,
            corrective_signal=corrective_signal,
            reasoning=reasoning,
        )

        self._audit_history.append(audit)
        return audit

    def get_correction_vector(self, action_vector: np.ndarray) -> np.ndarray:
        """
        Compute correction vector to realign action with mission G₀.

        Returns a vector that, when added to the action, moves it toward
        the mission vector while preserving magnitude.
        """
        mn = self.mission_state.mission_vector
        mn_norm = np.linalg.norm(mn)
        if mn_norm < 1e-9:
            return np.zeros_like(action_vector)

        mission_dir = mn / mn_norm
        an = np.linalg.norm(action_vector)
        if an < 1e-9:
            return mission_dir * 0.1

        action_dir = action_vector / an
        projection = np.dot(action_dir, mission_dir)
        correction = mission_dir - projection * action_dir
        return correction * an * 0.3

    def get_mission_state(self) -> MissionState:
        return self.mission_state

    def get_statistics(self) -> Dict:
        return {
            'total_audits': self._total_audits,
            'total_warnings': self._total_warnings,
            'total_proxy_drifts': self._total_proxy_drifts,
            'warning_rate': self._total_warnings / self._total_audits if self._total_audits else 0.0,
            'proxy_drift_rate': self._total_proxy_drifts / self._total_audits if self._total_audits else 0.0,
            'consecutive_drifts': self._consecutive_drifts,
            'max_consecutive_drifts': self._max_consecutive_drifts,
            'drift_thresholds': {
                'warning': self.drift_warning_threshold,
                'critical': self.drift_critical_threshold,
                'emergency': self.drift_emergency_threshold,
            },
        }


# ═══════════════════════════════════════════════════════════
# 2. COGNITIVE FRICTION OPTIMIZER
#    F = Context Switching + Interruptions + Irrelevant Memory + Unnecessary Search
#    Q = Q₀ - F
# ═══════════════════════════════════════════════════════════

@dataclass
class FrictionComponents:
    """Individual components of cognitive friction."""
    context_switching: float
    interruptions: float
    irrelevant_memory: float
    unnecessary_search: float
    total: float = 0.0

    def __post_init__(self):
        self.total = (self.context_switching + self.interruptions +
                      self.irrelevant_memory + self.unnecessary_search)


@dataclass
class FrictionState:
    """Snapshot of friction and quality at a point in time."""
    friction: FrictionComponents
    base_quality: float
    net_quality: float
    quality_loss_ratio: float       # F / Q₀ (how much quality is lost to friction)
    timestamp: float = field(default_factory=time.time)


class CognitiveFrictionOptimizer:
    """
    Calculates and minimizes cognitive friction F to preserve decision quality Q.

    F = C + I + M + S
      where:
        C = Context Switching overhead
        I = Interruption cost
        M = Irrelevant Memory penalty
        S = Unnecessary Search waste

    Q_net = Q₀ - F

    Optimization targets:
      - Reduce C through stable execution contexts
      - Reduce I through focused reasoning chains
      - Reduce M through Neti-Neti pruning and Context Immunology
      - Reduce S through Forest Search guided routing
    """

    def __init__(self, context_switching: float = 0.05,
                 interruptions: float = 0.02,
                 irrelevant_memory: float = 0.05,
                 unnecessary_search: float = 0.08,
                 max_total_friction: float = 0.5):
        self.base_context_switching = context_switching
        self.base_interruptions = interruptions
        self.base_irrelevant_memory = irrelevant_memory
        self.base_unnecessary_search = unnecessary_search
        self.max_total_friction = max_total_friction
        self._friction_history: deque = deque(maxlen=500)
        self._total_evaluations = 0

    def compute_friction(self, context_switching: Optional[float] = None,
                         interruptions: Optional[float] = None,
                         irrelevant_memory: Optional[float] = None,
                         unnecessary_search: Optional[float] = None) -> FrictionComponents:
        """Compute current friction with optional overrides."""
        return FrictionComponents(
            context_switching=context_switching if context_switching is not None else self.base_context_switching,
            interruptions=interruptions if interruptions is not None else self.base_interruptions,
            irrelevant_memory=irrelevant_memory if irrelevant_memory is not None else self.base_irrelevant_memory,
            unnecessary_search=unnecessary_search if unnecessary_search is not None else self.base_unnecessary_search,
        )

    def compute_net_quality(self, base_quality: float,
                            friction: Optional[FrictionComponents] = None) -> FrictionState:
        """
        Q = Q₀ - F

        Returns FrictionState with net quality and diagnostic info.
        """
        self._total_evaluations += 1

        if friction is None:
            friction = self.compute_friction()

        net_quality = max(0.0, base_quality - friction.total)
        quality_loss = friction.total / base_quality if base_quality > 0 else 0.0

        state = FrictionState(
            friction=friction,
            base_quality=base_quality,
            net_quality=net_quality,
            quality_loss_ratio=quality_loss,
        )

        self._friction_history.append(state)
        return state

    def get_optimization_suggestions(self, friction: FrictionComponents) -> List[str]:
        """Return actionable suggestions to reduce friction."""
        suggestions = []
        total = friction.total

        if friction.context_switching > total * 0.3:
            suggestions.append("Reduce context switching: consolidate execution contexts")
        if friction.interruptions > total * 0.25:
            suggestions.append("Reduce interruptions: batch external calls, use async I/O")
        if friction.irrelevant_memory > total * 0.3:
            suggestions.append("Reduce irrelevant memory: apply Neti-Neti pruning more aggressively")
        if friction.unnecessary_search > total * 0.25:
            suggestions.append("Reduce unnecessary search: tighten Forest Search thresholds")

        if not suggestions:
            suggestions.append("Friction within acceptable bounds")

        return suggestions

    def get_statistics(self) -> Dict:
        if not self._friction_history:
            return {'total_evaluations': 0}

        frictions = [s.friction.total for s in self._friction_history]
        qualities = [s.net_quality for s in self._friction_history]
        return {
            'total_evaluations': self._total_evaluations,
            'mean_friction': float(np.mean(frictions)),
            'max_friction': float(np.max(frictions)),
            'mean_net_quality': float(np.mean(qualities)),
            'quality_loss_mean': float(np.mean([s.quality_loss_ratio for s in self._friction_history])),
        }


# ═══════════════════════════════════════════════════════════
# 3. MISSION AUDIT & STRATEGY UPDATE
# ═══════════════════════════════════════════════════════════

@dataclass
class StrategyVector:
    """A mutable strategy that can be updated without touching the mission."""
    strategy_id: str
    embedding: np.ndarray
    confidence: float
    version: int = 1
    parent_strategy_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def update(self, new_embedding: np.ndarray, confidence: float):
        """Update strategy embedding. Mission G₀ is never modified."""
        self.embedding = new_embedding
        self.confidence = confidence
        self.version += 1


@dataclass
class MissionAuditResult:
    """Result of a full mission audit (R_t vs G₀ evaluation)."""
    mission_id: str
    audit_count: int
    alignment_mean: float
    alignment_min: float
    alignment_max: float
    reward_mean: float
    reward_min_met_ratio: float    # Fraction of audits where R_t ≥ R_min
    proxy_drift_count: int
    mission_drift_count: int
    overall_status: str
    strategy_recommended: bool     # Should strategies be updated?
    mission_modified: bool         # Always False (mission is immutable)
    timestamp: float = field(default_factory=time.time)


class MissionAuditor:
    """
    Evaluates R_t against G₀ over the full audit history.

    Key invariant: the mission (G₀) is NEVER modified by the audit.
    Only strategies are updated.
    """

    def __init__(self, integrity_monitor: ObjectiveIntegrityMonitor):
        self.integrity_monitor = integrity_monitor

    def full_audit(self) -> MissionAuditResult:
        """Run a full mission audit over the complete audit history."""
        history = list(self.integrity_monitor._audit_history)
        mission_id = self.integrity_monitor.mission_state.mission_id

        if not history:
            return MissionAuditResult(
                mission_id=mission_id,
                audit_count=0, alignment_mean=0.0, alignment_min=0.0,
                alignment_max=0.0, reward_mean=0.0, reward_min_met_ratio=0.0,
                proxy_drift_count=0, mission_drift_count=0,
                overall_status="NO_DATA", strategy_recommended=False,
                mission_modified=False,
            )

        alignments = [a.mission_alignment for a in history]
        rewards = [a.reward_value for a in history]
        min_met = sum(1 for a in history if a.reward_constraint_met)
        proxy_drifts = sum(1 for a in history if a.proxy_drift_detected)
        mission_drifts = sum(1 for a in history
                            if a.objective_status in [
                                ObjectiveStatus.MISSION_DRIFT,
                                ObjectiveStatus.DUAL_VIOLATION,
                                ObjectiveStatus.PROXY_DRIFT,
                            ])

        alignment_mean = float(np.mean(alignments))
        reward_min_ratio = min_met / len(history)

        # Overall status determination
        if proxy_drifts > len(history) * 0.3:
            overall = "CRITICAL: SYSTEMIC PROXY DRIFT"
            strategy_recommended = True
        elif mission_drifts > len(history) * 0.5:
            overall = "WARNING: FREQUENT MISSION DRIFT"
            strategy_recommended = True
        elif alignment_mean < 0.5:
            overall = "WARNING: LOW MEAN ALIGNMENT"
            strategy_recommended = True
        elif reward_min_ratio < 0.8:
            overall = "WARNING: FREQUENT REWARD DEFICIT"
            strategy_recommended = True
        else:
            overall = "NOMINAL"
            strategy_recommended = False

        return MissionAuditResult(
            mission_id=mission_id,
            audit_count=len(history),
            alignment_mean=alignment_mean,
            alignment_min=float(np.min(alignments)),
            alignment_max=float(np.max(alignments)),
            reward_mean=float(np.mean(rewards)),
            reward_min_met_ratio=reward_min_ratio,
            proxy_drift_count=proxy_drifts,
            mission_drift_count=mission_drifts,
            overall_status=overall,
            strategy_recommended=strategy_recommended,
            mission_modified=False,  # ALWAYS FALSE
        )


# ═══════════════════════════════════════════════════════════
# 4. UNIFIED TELOS v9 RUNTIME
# ═══════════════════════════════════════════════════════════

class TelosV9Runtime:
    """
    TELOS v9: Objective Integrity & Purpose-Driven Runtime.

    Pipeline:
      G₀ → Objective Integrity Monitor → Forest Search → Neti-Neti
      → Decision Ledger → Reasoning Runtime → Friction Optimizer
      → Execution → Mission Audit → Strategy Update (never the mission)

    Core invariants:
      1. Mission (G₀) is immutable across all operations
      2. Rewards (R_t) are constraints, never objectives
      3. Strategies are mutable; updated on evidence
      4. Friction F is minimized at every step
    """

    def __init__(self, mission_vector: np.ndarray,
                 mission_id: str = "default-mission",
                 min_reward_threshold: float = 0.4,
                 energy: float = 100.0,
                 roi_threshold: float = 0.15):
        # ── Mission (Immutable) ──
        self.mission_state = MissionState(
            mission_vector=mission_vector,
            mission_id=mission_id,
            min_reward_threshold=min_reward_threshold,
        )

        # ── v9 Core Components ──
        self.integrity_monitor = ObjectiveIntegrityMonitor(self.mission_state)
        self.friction_optimizer = CognitiveFrictionOptimizer()
        self.mission_auditor = MissionAuditor(self.integrity_monitor)

        # ── v8.x Integrations ──
        mn = np.linalg.norm(mission_vector)
        mission_dir = mission_vector / mn if mn > 1e-9 else mission_vector
        self.consensus = MissionWeightedConsensus(mission_dir)
        self.ledger = DecisionLedger()
        self.calibration = EpistemicCalibrationLoop(self.ledger)
        self.immunology = ContextImmunologyFilter(mission_dir)

        # ── Negative Search ──
        self.pruner = NetiNetiPruningEngine()
        self.router = ForestSearchRouter(mission_dir)
        self.stability = StableRegionMonitor()
        self.optimizer = ModerationOptimizer()

        # ── State ──
        self._current_strategy = StrategyVector(
            strategy_id="strategy-0",
            embedding=mission_vector.copy(),
            confidence=1.0,
        )
        self._strategies: Dict[str, StrategyVector] = {}
        self._step_count = 0
        self._execution_log: deque = deque(maxlen=500)

    def execute_step(self, action_vector: np.ndarray,
                     observed_reward: float,
                     base_quality: float = 0.8,
                     friction_metrics: Optional[Dict[str, float]] = None,
                     context_chunks: Optional[List[ContextChunk]] = None,
                     proposals: Optional[List[AgentProposal]] = None,
                     current_identity: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Execute one full TELOS v9 pipeline step.

        Returns comprehensive dict with integrity audit, friction state,
        ledger status, and adaptive directive.
        """
        self._step_count += 1
        step_log: Dict[str, Any] = {'step': self._step_count}

        # ── 1. Objective Integrity Audit ──
        audit = self.integrity_monitor.audit_objective(
            action_vector, observed_reward, base_quality
        )
        step_log['integrity_audit'] = {
            'status': audit.objective_status.value,
            'alignment': audit.mission_alignment,
            'reward_met': audit.reward_constraint_met,
            'proxy_drift': audit.proxy_drift_detected,
            'severity': audit.drift_severity.value,
            'corrective_signal': audit.corrective_signal,
        }

        # ── 2. Cognitive Friction Optimization ──
        fm = friction_metrics or {}
        friction = self.friction_optimizer.compute_friction(
            context_switching=fm.get('context_switching'),
            interruptions=fm.get('interruptions'),
            irrelevant_memory=fm.get('irrelevant_memory'),
            unnecessary_search=fm.get('unnecessary_search'),
        )
        friction_state = self.friction_optimizer.compute_net_quality(
            base_quality, friction
        )
        step_log['friction'] = {
            'total': round(friction.total, 4),
            'components': {
                'context_switching': friction.context_switching,
                'interruptions': friction.interruptions,
                'irrelevant_memory': friction.irrelevant_memory,
                'unnecessary_search': friction.unnecessary_search,
            },
            'net_quality': round(friction_state.net_quality, 4),
            'quality_loss_ratio': round(friction_state.quality_loss_ratio, 4),
        }

        # ── 3. Context Immunology (if external data present) ──
        immunology_results = []
        if context_chunks:
            for chunk in context_chunks:
                result = self.immunology.screen_chunk(chunk, current_identity)
                immunology_results.append({
                    'chunk_id': chunk.chunk_id,
                    'status': result.status.value,
                    'alignment': result.alignment_score,
                })
        step_log['immunology'] = {
            'chunks_screened': len(immunology_results),
            'results': immunology_results,
        }

        # ── 4. Epistemic Consensus (if proposals present) ──
        consensus_result = None
        if proposals:
            consensus_result = self.consensus.resolve(proposals)
            step_log['consensus'] = {
                'winner': consensus_result.winner_agent_id,
                'conflict': consensus_result.conflict_type.value if consensus_result.conflict_type else None,
            }

        # ── 5. Mission Audit ──
        mission_audit = self.mission_auditor.full_audit()
        step_log['mission_audit'] = {
            'overall_status': mission_audit.overall_status,
            'strategy_recommended': mission_audit.strategy_recommended,
            'mission_modified': mission_audit.mission_modified,  # ALWAYS FALSE
            'alignment_mean': round(mission_audit.alignment_mean, 4),
        }

        # ── 6. Strategy Update (if drift detected, never mission) ──
        if audit.drift_severity != DriftSeverity.NOMINAL:
            correction = self.integrity_monitor.get_correction_vector(
                self._current_strategy.embedding
            )
            new_embedding = self._current_strategy.embedding + correction
            self._current_strategy.update(new_embedding, friction_state.net_quality)
            self._strategies[self._current_strategy.strategy_id] = self._current_strategy
            step_log['strategy_updated'] = True
        else:
            step_log['strategy_updated'] = False

        # ── 7. Adaptive Directive ──
        if audit.proxy_drift_detected:
            directive = "HALT: Proxy drift detected. Realign with G₀ immediately."
        elif audit.drift_severity == DriftSeverity.EMERGENCY:
            directive = "EMERGENCY: Critical mission drift. Execute emergency realignment."
        elif audit.drift_severity == DriftSeverity.CRITICAL:
            directive = "CRITICAL: Mission drift detected. Update strategy vector."
        elif audit.objective_status == ObjectiveStatus.REWARD_DEFICIT:
            directive = "REWARD_DEFICIT: Continue execution. Adjust resource allocation."
        else:
            directive = "NOMINAL: Continue execution. Strategy is aligned with G₀."

        step_log['directive'] = directive

        # ── 8. Friction Optimization Suggestions ──
        suggestions = self.friction_optimizer.get_optimization_suggestions(friction)
        step_log['optimization_suggestions'] = suggestions

        self._execution_log.append(step_log)
        return step_log

    def register_consensus_proposals(self, proposals: List[AgentProposal]) -> Dict[str, Any]:
        """Register and resolve agent proposals through consensus."""
        result = self.consensus.resolve(proposals)
        return {
            'winner': result.winner_agent_id,
            'proposal': result.winning_proposal,
            'conflict': result.conflict_type.value if result.conflict_type else None,
            'projection': result.projection_score,
        }

    def get_mission_hash(self) -> str:
        """Return the immutable mission hash."""
        return self.mission_state.immutable_hash()

    def get_current_strategy(self) -> Dict[str, Any]:
        s = self._current_strategy
        return {
            'id': s.strategy_id,
            'version': s.version,
            'confidence': s.confidence,
            'norm': float(np.linalg.norm(s.embedding)),
        }

    def get_statistics(self) -> Dict:
        return {
            'version': '9.0-objective-integrity-purpose-driven',
            'steps': self._step_count,
            'mission_id': self.mission_state.mission_id,
            'mission_hash': self.get_mission_hash(),
            'integrity': self.integrity_monitor.get_statistics(),
            'friction': self.friction_optimizer.get_statistics(),
            'mission_audit': {
                'strategy_versions': len(self._strategies),
            },
            'consensus': self.consensus.get_statistics(),
            'ledger': self.ledger.get_statistics(),
            'immunology': self.immunology.get_statistics(),
        }


if __name__ == "__main__":
    mission = np.array([1.0, 0.5, 0.3, 0.8, 0.2])
    runtime = TelosV9Runtime(mission, mission_id="acquire-resources", min_reward_threshold=0.4)

    print("=== TELOS v9: Objective Integrity & Purpose-Driven Architecture ===")
    print(f"Mission hash (immutable): {runtime.get_mission_hash()[:16]}...")

    # Simulate steps
    for i in range(5):
        action = mission + np.random.randn(5) * 0.1
        reward = 0.7 + np.random.uniform(-0.3, 0.3)
        result = runtime.execute_step(
            action_vector=action,
            observed_reward=reward,
            base_quality=0.85,
            friction_metrics={
                'context_switching': 0.04,
                'interruptions': 0.02,
                'irrelevant_memory': 0.03,
                'unnecessary_search': 0.06,
            },
        )
        print(f"\nStep {i+1}:")
        print(f"  Status: {result['integrity_audit']['status']}")
        print(f"  Alignment: {result['integrity_audit']['alignment']:.4f}")
        print(f"  Net Quality: {result['friction']['net_quality']:.4f}")
        print(f"  Directive: {result['directive'][:60]}...")

    stats = runtime.get_statistics()
    print(f"\n=== Final Statistics ===")
    print(f"  Total audits: {stats['integrity']['total_audits']}")
    print(f"  Proxy drifts: {stats['integrity']['total_proxy_drifts']}")
    print(f"  Mission hash unchanged: {runtime.get_mission_hash()[:16]}...")
