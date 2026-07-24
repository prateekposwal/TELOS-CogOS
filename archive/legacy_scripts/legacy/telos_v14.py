"""
TELOS v14: ETADS-Integrated Runtime

Wraps TelosV13_5Runtime with the Event-Triggered Async Daemon Scheduler.
Maintenance daemons now run asynchronously in background threads,
with results synchronized at safe pipeline boundaries.

Architecture:
  ┌─────────────────────────────────────────────────────────┐
  │  TelosV14Runtime                                         │
  │  ┌─────────────┐   ┌──────────────┐   ┌──────────────┐ │
  │  │ Telemetry    │──▶│ AsyncDaemon   │──▶│ DaemonResult │ │
  │  │ Builder      │   │ Executor      │   │ Synchronizer│ │
  │  └─────────────┘   └──────────────┘   └──────────────┘ │
  │        │                   │                   │        │
  │        ▼                   ▼                   ▼        │
  │  ┌─────────────────────────────────────────────────────┐│
  │  │              TelosV13_5Runtime                       ││
  │  │  (unmodified core pipeline)                          ││
  │  └─────────────────────────────────────────────────────┘│
  └─────────────────────────────────────────────────────────┘

Key invariants preserved:
  - execute_step() never blocks on daemon completion
  - Mission G₀ is never modified by any daemon
  - Daemon results are applied atomically at sync points
  - ETADS budget prevents runaway daemon execution
"""

import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque

from telos_v13_5 import (
    TelosV13_5Runtime, HealthOptimizer, PipelineOrchestrator,
    StableOperatingRegion, SORBoundary, SORViolation,
    MaintenanceProtocol, ProtocolPhase,
)
from telos_daemon_scheduler import (
    AsyncDaemonExecutor, TelemetrySnapshot, DaemonRequest, DaemonResult,
    DaemonType, DaemonPriority, DaemonState, PendingDaemonResults,
    TriggerCondition, ExecutorStatistics,
)
from telos_v13 import (
    HealthState,
)


# ═══════════════════════════════════════════════════════════
# 1. TELEMETRY BUILDER
#    Constructs TelemetrySnapshot from v13.5 runtime state
# ═══════════════════════════════════════════════════════════

class TelemetryBuilder:
    """
    Builds TelemetrySnapshot from TelosV13_5Runtime's internal state.

    Read-only access to runtime state — never mutates.
    """

    def __init__(self):
        self._last_audit_step: int = -1
        self._last_compression_step: int = -1

    def build(self, runtime: TelosV13_5Runtime) -> TelemetrySnapshot:
        health = runtime.v13.health_monitor.snapshot()
        kg_stats = runtime.v13.knowledge_graph.get_statistics()
        sor_stats = runtime.sor.get_statistics()

        now_ms = time.time() * 1000
        audit_age = now_ms  # approx
        compression_age = now_ms

        sor_within = True
        weakest_dim = ""
        weakest_val = 1.0
        if runtime._sor_breach_count > 0:
            w, wv = runtime.sor.get_weakest_dimension(health)
            sor_within = len(runtime.sor.check(health, runtime._step_count)[1]) == 0
            weakest_dim = w
            weakest_val = wv

        decision_entropy = 0.0
        recent = list(runtime.v13._recent_decisions)
        if recent:
            from collections import Counter
            counts = Counter(recent)
            total = sum(counts.values())
            probs = [c / total for c in counts.values()]
            probs = [p for p in probs if p > 0]
            if probs:
                decision_entropy = -sum(p * np.log2(p) for p in probs)
                max_entropy = np.log2(max(len(counts), 2))
                if max_entropy > 0:
                    decision_entropy /= max_entropy

        mission_drift = 0.0
        if runtime._health_trajectory:
            trajectory = list(runtime._health_trajectory)
            if len(trajectory) >= 2:
                mission_drift = 1.0 - trajectory[-1]

        merit_flow = 1.0
        try:
            v12_snap = runtime.v13.v12.conservation.snapshot()
            merit_flow = v12_snap.get('overall_health', 1.0)
            if merit_flow == float('inf'):
                merit_flow = 1.0
        except Exception:
            pass

        active_modules = runtime.v13.resource_rotation.get_active_count()

        time_since_audit = 0.0
        time_since_compression = 0.0

        return TelemetrySnapshot(
            mission_integrity=health.mission_integrity,
            knowledge_quality=health.knowledge_quality,
            energy_efficiency=health.energy_efficiency,
            trust_merit=health.trust_merit,
            attention_focus=health.attention_focus,
            recovery_capacity=health.recovery_capacity,
            system_health=health.overall_health,
            decision_entropy=decision_entropy,
            mission_drift=mission_drift,
            merit_flow=merit_flow,
            working_memory_entries=kg_stats.get('total_nodes', 0),
            knowledge_graph_nodes=kg_stats.get('total_nodes', 0),
            knowledge_graph_edges=kg_stats.get('total_edges', 0),
            active_modules=active_modules,
            step_count=runtime._step_count,
            time_since_last_audit_ms=time_since_audit,
            time_since_last_compression_ms=time_since_compression,
            sor_within=sor_within,
            sor_violation_count=sor_stats.get('total_violations', 0),
            sor_weakest_dimension=weakest_dim,
            sor_weakest_value=weakest_val,
        )


# ═══════════════════════════════════════════════════════════
# 2. DAEMON HANDLERS
#    Map DaemonType → v13.5 maintenance operations
# ═══════════════════════════════════════════════════════════

class DaemonHandlerRegistry:
    """
    Registers daemon handlers that delegate to v13.5 subsystems.

    Each handler:
      - Receives a DaemonRequest (read-only snapshot)
      - Calls the corresponding v13.5 maintenance operation
      - Returns a DaemonResult with the operation output
    """

    def __init__(self, runtime: TelosV13_5Runtime):
        self._runtime = runtime
        self._handlers: Dict[DaemonType, Any] = {
            DaemonType.HEALTH_AUDIT: self._handle_health_audit,
            DaemonType.STATE_COMPRESSION: self._handle_state_compression,
            DaemonType.RESOURCE_ROTATION: self._handle_resource_rotation,
            DaemonType.PRE_SYNC: self._handle_pre_sync,
            DaemonType.NUTRITION_SCAN: self._handle_nutrition_scan,
            DaemonType.KNOWLEDGE_PRUNE: self._handle_knowledge_prune,
            DaemonType.SOR_RECOVERY: self._handle_sor_recovery,
            DaemonType.HEALTH_OPTIMIZE: self._handle_health_optimize,
        }

    def get_handler(self, daemon_type: DaemonType):
        return self._handlers.get(daemon_type)

    def _handle_health_audit(self, request: DaemonRequest) -> DaemonResult:
        try:
            health = self._runtime.v13.health_monitor.snapshot()
            v12_snap = self._runtime.v13.v12.conservation.snapshot()
            report = self._runtime.v13.runtime_audit.audit(
                current_step=request.step,
                mission_vector=self._runtime.mission_state.mission_vector,
                current_state=self._runtime._current_state,
                recent_decisions=list(self._runtime.v13._recent_decisions),
                total_steps=request.step,
                corrections=self._runtime.v13._corrections,
                active_focuses=request.health_state.get('attention_focus', 1),
                conservation_state=v12_snap,
            )
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.HEALTH_AUDIT,
                success=True,
                duration_ms=0.0,
                step=request.step,
                audit_result={
                    'severity': report.overall_severity.value,
                    'mission_drift': report.mission_drift,
                    'attention_spread': report.attention_spread,
                    'error_rate': report.error_rate,
                },
                recommendations=report.recommendations[:5],
            )
        except Exception as e:
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.HEALTH_AUDIT,
                success=False,
                duration_ms=0.0,
                step=request.step,
                recommendations=[f"Audit failed: {str(e)[:80]}"],
            )

    def _handle_state_compression(self, request: DaemonRequest) -> DaemonResult:
        try:
            old = list(self._runtime.v13._execution_log)
            compressed, result = self._runtime.v13.compressor.compress_ledger(old)
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.STATE_COMPRESSION,
                success=True,
                duration_ms=0.0,
                step=request.step,
                compression_result={
                    'ratio': round(result.compression_ratio, 4),
                    'entries_compressed': result.entries_compressed,
                    'entries_before': result.entries_before,
                },
            )
        except Exception as e:
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.STATE_COMPRESSION,
                success=False,
                duration_ms=0.0,
                step=request.step,
                recommendations=[f"Compression failed: {str(e)[:80]}"],
            )

    def _handle_resource_rotation(self, request: DaemonRequest) -> DaemonResult:
        try:
            events = self._runtime.v13.resource_rotation.rotate(request.step)
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.RESOURCE_ROTATION,
                success=True,
                duration_ms=0.0,
                step=request.step,
                rotation_result={
                    'events': len(events),
                    'active_modules': self._runtime.v13.resource_rotation.get_active_count(),
                },
            )
        except Exception as e:
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.RESOURCE_ROTATION,
                success=False,
                duration_ms=0.0,
                step=request.step,
                recommendations=[f"Rotation failed: {str(e)[:80]}"],
            )

    def _handle_pre_sync(self, request: DaemonRequest) -> DaemonResult:
        try:
            mission_hash = self._runtime.mission_state.immutable_hash()
            sync_result = self._runtime.v13.pre_mission_sync.synchronize(
                current_step=request.step,
                variable_usage=self._runtime.v13._variable_usage,
                mission_hash=mission_hash,
                current_mission_hash=mission_hash,
                recent_state=list(self._runtime.v13._execution_log)[-10:],
            )
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.PRE_SYNC,
                success=True,
                duration_ms=0.0,
                step=request.step,
                sync_result={
                    'ready': sync_result.overall_ready,
                    'corruption': sync_result.corruption_detected,
                    'phases_completed': sync_result.phases_completed,
                },
            )
        except Exception as e:
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.PRE_SYNC,
                success=False,
                duration_ms=0.0,
                step=request.step,
                recommendations=[f"Pre-sync failed: {str(e)[:80]}"],
            )

    def _handle_nutrition_scan(self, request: DaemonRequest) -> DaemonResult:
        try:
            action = self._runtime._current_state
            nutrition = self._runtime.v13.nutrition_engine.score(
                action, True, request.health_state.get('trust_merit', 0.5)
            )
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.NUTRITION_SCAN,
                success=True,
                duration_ms=0.0,
                step=request.step,
                nutrition_result={
                    'composite': nutrition.composite,
                    'sub_threshold': nutrition.is_sub_threshold,
                },
            )
        except Exception as e:
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.NUTRITION_SCAN,
                success=False,
                duration_ms=0.0,
                step=request.step,
                recommendations=[f"Nutrition scan failed: {str(e)[:80]}"],
            )

    def _handle_knowledge_prune(self, request: DaemonRequest) -> DaemonResult:
        try:
            stats = self._runtime.v13.knowledge_graph.get_statistics()
            pruned = 0
            nodes_to_prune = [
                nid for nid, node in self._runtime.v13.knowledge_graph._nodes.items()
                if node.confidence < 0.2 and node.node_id != f"kn-{request.step}"
            ]
            for nid in nodes_to_prune[:10]:
                self._runtime.v13.knowledge_graph._nodes[nid].status = 'pruned'
                pruned += 1
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.KNOWLEDGE_PRUNE,
                success=True,
                duration_ms=0.0,
                step=request.step,
                prune_result={
                    'pruned': pruned,
                    'total_nodes': stats.get('total_nodes', 0),
                },
            )
        except Exception as e:
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.KNOWLEDGE_PRUNE,
                success=False,
                duration_ms=0.0,
                step=request.step,
                recommendations=[f"Prune failed: {str(e)[:80]}"],
            )

    def _handle_sor_recovery(self, request: DaemonRequest) -> DaemonResult:
        try:
            health = self._runtime.v13.health_monitor.snapshot()
            weakest, w_val = self._runtime.sor.get_weakest_dimension(health)
            recommendations = [
                f"SOR_RECOVERY: Weakest dimension is {weakest} at {w_val:.3f}",
                f"Recommend increasing recovery focus on {weakest}",
            ]
            if w_val < 0.3:
                recommendations.append(f"EMERGENCY: {weakest} below critical minimum")
                return DaemonResult(
                    request_id=request.request_id,
                    daemon_type=DaemonType.SOR_RECOVERY,
                    success=True,
                    duration_ms=0.0,
                    step=request.step,
                    recovery_result={
                        'weakest': weakest,
                        'value': w_val,
                        'emergency': True,
                    },
                    recommendations=recommendations,
                    emergency=True,
                )
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.SOR_RECOVERY,
                success=True,
                duration_ms=0.0,
                step=request.step,
                recovery_result={
                    'weakest': weakest,
                    'value': w_val,
                    'emergency': False,
                },
                recommendations=recommendations,
            )
        except Exception as e:
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.SOR_RECOVERY,
                success=False,
                duration_ms=0.0,
                step=request.step,
                recommendations=[f"SOR recovery failed: {str(e)[:80]}"],
            )

    def _handle_health_optimize(self, request: DaemonRequest) -> DaemonResult:
        try:
            health = self._runtime.v13.health_monitor.snapshot()
            opt = self._runtime.optimizer.optimize(health, request.step)
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.HEALTH_OPTIMIZE,
                success=True,
                duration_ms=0.0,
                step=request.step,
                optimize_result={
                    'health_before': opt.health_before,
                    'health_after': opt.health_after,
                    'weights': {k: round(v, 4) for k, v in opt.weights_adjusted.items()},
                },
            )
        except Exception as e:
            return DaemonResult(
                request_id=request.request_id,
                daemon_type=DaemonType.HEALTH_OPTIMIZE,
                success=False,
                duration_ms=0.0,
                step=request.step,
                recommendations=[f"Optimization failed: {str(e)[:80]}"],
            )


# ═══════════════════════════════════════════════════════════
# 3. DAEMON RESULT SYNCHRONIZER
#    Applies completed daemon results back to runtime state
# ═══════════════════════════════════════════════════════════

class DaemonResultSynchronizer:
    """
    Atomically applies pending daemon results to the v13.5 runtime.

    Synchronization is non-blocking and happens at safe pipeline
    boundaries (after decision engine, before next step).

    Results are applied in priority order:
      1. SOR Recovery (emergency first)
      2. Health Audit results
      3. Compression results
      4. Resource rotation results
      5. Everything else
    """

    def __init__(self, runtime: TelosV13_5Runtime):
        self._runtime = runtime
        self._sync_history: deque = deque(maxlen=200)
        self._total_syncs = 0
        self._total_results_applied = 0

    def synchronize(self, pending: PendingDaemonResults) -> Dict[str, Any]:
        applied = 0
        sync_log: Dict[str, Any] = {
            'results_received': len(pending.results),
            'emergency': pending.has_emergency(),
            'applied_types': [],
        }

        sorted_results = self._sort_by_priority(pending.results)

        for result in sorted_results:
            if not result.success:
                continue
            self._apply_result(result)
            applied += 1
            sync_log['applied_types'].append(result.daemon_type.value)

        sync_log['results_applied'] = applied
        sync_log['total_duration_ms'] = round(pending.total_duration_ms, 4)

        self._total_syncs += 1
        self._total_results_applied += applied
        self._sync_history.append(sync_log)

        return sync_log

    def _sort_by_priority(self, results: List[DaemonResult]) -> List[DaemonResult]:
        priority_order = {
            DaemonType.SOR_RECOVERY: 0,
            DaemonType.HEALTH_AUDIT: 1,
            DaemonType.HEALTH_OPTIMIZE: 2,
            DaemonType.STATE_COMPRESSION: 3,
            DaemonType.RESOURCE_ROTATION: 4,
            DaemonType.PRE_SYNC: 5,
            DaemonType.NUTRITION_SCAN: 6,
            DaemonType.KNOWLEDGE_PRUNE: 7,
        }
        return sorted(results, key=lambda r: priority_order.get(r.daemon_type, 99))

    def _apply_result(self, result: DaemonResult) -> None:
        if result.audit_result:
            self._apply_audit_result(result.audit_result)
        if result.compression_result:
            self._apply_compression_result(result.compression_result)
        if result.rotation_result:
            self._apply_rotation_result(result.rotation_result)
        if result.sync_result:
            self._apply_sync_result(result.sync_result)
        if result.recovery_result:
            self._apply_recovery_result(result.recovery_result)
        if result.optimize_result:
            self._apply_optimize_result(result.optimize_result)

    def _apply_audit_result(self, data: Dict) -> None:
        severity = data.get('severity', 'healthy')
        if severity in ('critical', 'emergency'):
            self._runtime.v13._corrections += 1

    def _apply_compression_result(self, data: Dict) -> None:
        pass

    def _apply_rotation_result(self, data: Dict) -> None:
        pass

    def _apply_sync_result(self, data: Dict) -> None:
        corruption = data.get('corruption', False)
        if corruption:
            self._runtime.v13._corrections += 1

    def _apply_recovery_result(self, data: Dict) -> None:
        pass

    def _apply_optimize_result(self, data: Dict) -> None:
        weights = data.get('weights', {})
        if weights:
            self._runtime.optimizer.weights.update(weights)

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._sync_history)[-50:]
        avg_applied = (
            sum(s['results_applied'] for s in recent) / max(len(recent), 1)
            if recent else 0
        )
        return {
            'total_syncs': self._total_syncs,
            'total_results_applied': self._total_results_applied,
            'avg_results_per_sync': round(avg_applied, 2),
        }


# ═══════════════════════════════════════════════════════════
# 4. TELOS v14 RUNTIME
#    ETADS-integrated runtime wrapping v13.5
# ═══════════════════════════════════════════════════════════

class TelosV14Runtime:
    """
    TELOS v14: ETADS-Integrated Runtime.

    Extends v13.5 with asynchronous daemon execution:
      - Daemon dispatch is non-blocking
      - Results synchronized at safe pipeline boundaries
      - Budget-limited daemon execution prevents runaway
      - Three-level circuit breakers prevent daemon storms

    Pipeline per step:
      1. Build TelemetrySnapshot
      2. Dispatch daemons (non-blocking)
      3. Execute v13.5 pipeline (synchronous)
      4. Sync daemon results (atomic)
      5. Return composite directive
    """

    def __init__(self, mission_vector: np.ndarray,
                 goal_vector: np.ndarray,
                 mission_id: str = "v14-mission",
                 min_reward_threshold: float = 0.4,
                 energy: float = 100.0,
                 planning_horizon: int = 10,
                 health_weights: Optional[Dict[str, float]] = None,
                 nutrition_weights: Optional[Dict[str, float]] = None,
                 sor_boundaries: Optional[Dict[str, SORBoundary]] = None,
                 daemon_budget_ms: float = 10.0,
                 pool_size: int = 2,
                 sync_interval: int = 5):
        mn = np.linalg.norm(mission_vector)
        if mn < 1e-9:
            raise ValueError("Mission vector must be non-zero")

        self._v13_5 = TelosV13_5Runtime(
            mission_vector, goal_vector, mission_id,
            min_reward_threshold, energy, planning_horizon,
            health_weights, nutrition_weights, sor_boundaries,
        )

        self.telemetry_builder = TelemetryBuilder()
        self.daemon_registry = DaemonHandlerRegistry(self._v13_5)
        self.result_synchronizer = DaemonResultSynchronizer(self._v13_5)

        self.etads = AsyncDaemonExecutor(
            daemon_budget_ms=daemon_budget_ms,
            pool_size=pool_size,
            sync_interval=sync_interval,
        )

        for daemon_type, handler in self.daemon_registry._handlers.items():
            self.etads.register_daemon(daemon_type, handler)

        self._step_count = 0
        self._execution_log: deque = deque(maxlen=500)
        self._etads_stats_history: deque = deque(maxlen=200)

    def start(self):
        self.etads.start()

    def shutdown(self, timeout_ms: float = 200):
        self.etads.shutdown(timeout_ms)

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
        self._step_count += 1

        telemetry = self.telemetry_builder.build(self._v13_5)
        dispatched = self.etads.dispatch(telemetry)

        step_log = self._v13_5.execute_step(
            action_vector, observed_reward, base_quality,
            claimed_reason, actual_objective,
            belief_constraints, hidden_constraints,
            assumptions, alternative_values, chosen_path_value,
            foregone_value, foregone_description,
            decision_basis, evidence_weight,
            has_evidence, trust_level, active_focuses,
            friction_metrics, tes_score, recovery_rate,
            recovery_debt, evidence,
        )

        pending = self.etads.sync_pending_results(self._v13_5)
        sync_log = self.result_synchronizer.synchronize(pending)

        step_log['etads'] = {
            'daemons_dispatched': dispatched,
            'results_synced': sync_log['results_applied'],
            'emergency': sync_log.get('emergency', False),
            'applied_types': sync_log.get('applied_types', []),
        }

        self._execution_log.append(step_log)
        return step_log

    def get_mission_hash(self) -> str:
        return self._v13_5.get_mission_hash()

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'version': '14-etads-integrated',
            'steps': self._step_count,
            'mission_id': self._v13_5.mission_state.mission_id,
            'mission_hash': self.get_mission_hash(),
            'etads': self.etads.get_statistics(),
            'result_sync': self.result_synchronizer.get_statistics(),
            'v13_5': self._v13_5.get_statistics(),
        }
