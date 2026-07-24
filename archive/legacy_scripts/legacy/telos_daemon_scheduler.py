"""
TELOS v14: Event-Triggered Async Daemon Scheduler (ETADS)

Replaces synchronous maintenance daemons with event-driven
background execution. Daemons fire on telemetry anomalies,
run in background threads, and results are synchronized at
safe pipeline boundaries.

Key invariant: execute_step() never waits for daemon completion.

Architecture:
  Telemetry → Trigger Evaluator → Budget Allocator → Dispatch
                                                          │
  execute_step() ◀── Sync Results ◀── Result Queue ◀──────┘
       │
       └── continue decision engine (no wait)
"""

import time
import threading
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
from collections import deque
from enum import Enum


# ═══════════════════════════════════════════════════════════
# 1. DAEMON TYPES & STATES
# ═══════════════════════════════════════════════════════════

class DaemonType(Enum):
    HEALTH_AUDIT      = "health_audit"
    STATE_COMPRESSION = "state_compression"
    RESOURCE_ROTATION = "resource_rotation"
    PRE_SYNC          = "pre_sync"
    NUTRITION_SCAN    = "nutrition_scan"
    KNOWLEDGE_PRUNE   = "knowledge_prune"
    SOR_RECOVERY      = "SOR_recovery"
    HEALTH_OPTIMIZE   = "health_optimize"


class DaemonPriority(Enum):
    LOW      = 0
    NORMAL   = 1
    HIGH     = 2
    CRITICAL = 3


class DaemonState(Enum):
    IDLE      = "idle"
    TRIGGERED = "triggered"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


# ═══════════════════════════════════════════════════════════
# 2. TELEMETRY & TRIGGER SYSTEM
# ═══════════════════════════════════════════════════════════

@dataclass
class TelemetrySnapshot:
    """Immutable snapshot of runtime telemetry."""
    mission_integrity: float = 1.0
    knowledge_quality: float = 1.0
    energy_efficiency: float = 1.0
    trust_merit: float = 1.0
    attention_focus: float = 1.0
    recovery_capacity: float = 1.0
    system_health: float = 1.0
    decision_entropy: float = 0.0
    mission_drift: float = 0.0
    merit_flow: float = 1.0
    working_memory_entries: int = 0
    knowledge_graph_nodes: int = 0
    knowledge_graph_edges: int = 0
    active_modules: int = 0
    step_count: int = 0
    time_since_last_audit_ms: float = 0.0
    time_since_last_compression_ms: float = 0.0
    sor_within: bool = True
    sor_violation_count: int = 0
    sor_weakest_dimension: str = ""
    sor_weakest_value: float = 1.0


@dataclass
class TriggerCondition:
    """A single trigger rule evaluated against telemetry."""
    daemon_type: DaemonType
    priority: DaemonPriority
    condition_name: str
    metric_name: str
    operator: str
    threshold: float
    cooldown_steps: int = 5
    max_fires_per_episode: int = 50

    def evaluate(self, telemetry: TelemetrySnapshot,
                 last_fire_step: int,
                 fire_count: int) -> Tuple[bool, float]:
        if fire_count >= self.max_fires_per_episode:
            return False, 0.0
        if telemetry.step_count - last_fire_step < self.cooldown_steps:
            return False, 0.0
        current_value = getattr(telemetry, self.metric_name, 0.0)
        ops = {
            "lt": lambda v, t: v < t,
            "gt": lambda v, t: v > t,
            "gte": lambda v, t: v >= t,
            "lte": lambda v, t: v <= t,
            "eq": lambda v, t: v == t,
        }
        op_fn = ops.get(self.operator, lambda v, t: False)
        return op_fn(current_value, self.threshold), current_value


DEFAULT_TRIGGER_RULES: List[TriggerCondition] = [
    TriggerCondition(
        DaemonType.HEALTH_AUDIT, DaemonPriority.HIGH,
        "health_degraded", "system_health", "lt", 0.6,
        cooldown_steps=3, max_fires_per_episode=30,
    ),
    TriggerCondition(
        DaemonType.HEALTH_AUDIT, DaemonPriority.NORMAL,
        "entropy_spike", "decision_entropy", "gt", 0.7,
        cooldown_steps=5, max_fires_per_episode=20,
    ),
    TriggerCondition(
        DaemonType.STATE_COMPRESSION, DaemonPriority.HIGH,
        "memory_pressure", "working_memory_entries", "gt", 400.0,
        cooldown_steps=10, max_fires_per_episode=15,
    ),
    TriggerCondition(
        DaemonType.RESOURCE_ROTATION, DaemonPriority.NORMAL,
        "module_overheat", "active_modules", "gt", 6.0,
        cooldown_steps=8, max_fires_per_episode=20,
    ),
    TriggerCondition(
        DaemonType.PRE_SYNC, DaemonPriority.LOW,
        "step_boundary", "step_count", "eq", 0.0,
        cooldown_steps=10, max_fires_per_episode=100,
    ),
    TriggerCondition(
        DaemonType.NUTRITION_SCAN, DaemonPriority.NORMAL,
        "merit_degradation", "merit_flow", "lt", 0.4,
        cooldown_steps=5, max_fires_per_episode=25,
    ),
    TriggerCondition(
        DaemonType.KNOWLEDGE_PRUNE, DaemonPriority.LOW,
        "graph_overflow", "knowledge_graph_nodes", "gt", 500.0,
        cooldown_steps=15, max_fires_per_episode=10,
    ),
    TriggerCondition(
        DaemonType.SOR_RECOVERY, DaemonPriority.CRITICAL,
        "sor_breach", "sor_within", "eq", 0.0,
        cooldown_steps=0, max_fires_per_episode=100,
    ),
    TriggerCondition(
        DaemonType.HEALTH_OPTIMIZE, DaemonPriority.LOW,
        "periodic_optimize", "step_count", "eq", 0.0,
        cooldown_steps=20, max_fires_per_episode=50,
    ),
]


# ═══════════════════════════════════════════════════════════
# 3. DAEMON REQUEST & RESULT
# ═══════════════════════════════════════════════════════════

@dataclass
class DaemonRequest:
    """Read-only snapshot passed to a daemon handler."""
    daemon_type: DaemonType
    priority: DaemonPriority
    request_id: int
    step: int
    timestamp: float
    health_state: Dict[str, float] = field(default_factory=dict)
    execution_log_snapshot: List[Dict] = field(default_factory=list)
    knowledge_graph_snapshot: Dict = field(default_factory=dict)
    mission_vector: Any = None
    sor_violations: List[Dict] = field(default_factory=list)
    nutrition_score: float = 0.0
    compression_ratio: float = 1.0
    max_duration_ms: float = 50.0


@dataclass
class DaemonResult:
    """Immutable result from a daemon."""
    request_id: int
    daemon_type: DaemonType
    success: bool
    duration_ms: float
    step: int
    audit_result: Optional[Dict] = None
    compression_result: Optional[Dict] = None
    rotation_result: Optional[Dict] = None
    sync_result: Optional[Dict] = None
    nutrition_result: Optional[Dict] = None
    prune_result: Optional[Dict] = None
    recovery_result: Optional[Dict] = None
    optimize_result: Optional[Dict] = None
    recommendations: List[str] = field(default_factory=list)
    emergency: bool = False


# ═══════════════════════════════════════════════════════════
# 4. BUDGET ALLOCATION
# ═══════════════════════════════════════════════════════════

@dataclass
class DaemonBudget:
    """Per-cycle compute budget for daemon execution."""
    total_budget_ms: float = 10.0
    remaining_ms: float = 10.0
    allocated_daemons: List[DaemonType] = field(default_factory=list)
    deferred_daemons: List[DaemonType] = field(default_factory=list)

    def allocate(self, triggered: List[Tuple[DaemonType, DaemonPriority]],
                 cost_fn: Callable[[DaemonType], float]) -> Tuple[
                     List[DaemonType], List[DaemonType]]:
        self.remaining_ms = self.total_budget_ms
        self.allocated_daemons = []
        self.deferred_daemons = []
        sorted_t = sorted(triggered, key=lambda x: x[1].value, reverse=True)
        normals = [t for t in sorted_t if t[1] == DaemonPriority.NORMAL]
        normal_count = max(len(normals), 1)
        for daemon_type, priority in sorted_t:
            cost = cost_fn(daemon_type)
            if priority == DaemonPriority.CRITICAL:
                self.allocated_daemons.append(daemon_type)
                self.remaining_ms = max(0.0, self.remaining_ms - cost)
            elif priority == DaemonPriority.HIGH:
                if cost <= self.remaining_ms * 0.6:
                    self.allocated_daemons.append(daemon_type)
                    self.remaining_ms -= cost
                else:
                    self.deferred_daemons.append(daemon_type)
            elif priority == DaemonPriority.NORMAL:
                fair_share = self.remaining_ms / normal_count
                if cost <= fair_share:
                    self.allocated_daemons.append(daemon_type)
                    self.remaining_ms -= cost
                else:
                    self.deferred_daemons.append(daemon_type)
            else:
                if self.remaining_ms > self.total_budget_ms * 0.3:
                    if cost <= self.remaining_ms * 0.3:
                        self.allocated_daemons.append(daemon_type)
                        self.remaining_ms -= cost
                    else:
                        self.deferred_daemons.append(daemon_type)
                else:
                    self.deferred_daemons.append(daemon_type)
        return self.allocated_daemons, self.deferred_daemons


# ═══════════════════════════════════════════════════════════
# 5. PENDING RESULTS
# ═══════════════════════════════════════════════════════════

@dataclass
class PendingDaemonResults:
    """Accumulated daemon results waiting to be applied."""
    results: List[DaemonResult] = field(default_factory=list)
    emergency_count: int = 0
    total_duration_ms: float = 0.0

    def has_emergency(self) -> bool:
        return self.emergency_count > 0

    def clear(self):
        self.results.clear()
        self.emergency_count = 0
        self.total_duration_ms = 0.0


# ═══════════════════════════════════════════════════════════
# 6. EXECUTOR STATISTICS
# ═══════════════════════════════════════════════════════════

@dataclass
class ExecutorStatistics:
    total_steps_processed: int = 0
    total_daemons_dispatched: int = 0
    total_daemons_completed: int = 0
    total_daemons_failed: int = 0
    total_daemons_dropped: int = 0
    total_sync_cycles: int = 0
    total_sync_duration_ms: float = 0.0
    avg_sync_duration_ms: float = 0.0
    daemon_fire_counts: Dict[str, int] = field(default_factory=dict)
    last_sync_step: int = 0
    emergency_count: int = 0
    degraded_steps: int = 0


# ═══════════════════════════════════════════════════════════
# 7. ASYNC DAEMON EXECUTOR
# ═══════════════════════════════════════════════════════════

class AsyncDaemonExecutor:
    """
    Event-Triggered Async Daemon Scheduler (ETADS).

    Evaluates telemetry triggers, dispatches daemons to background
    threads, and synchronizes results at safe pipeline boundaries.

    Thread safety:
      - Dispatch queue protected by threading.Condition
      - Result queue protected by threading.Lock
      - Runtime state mutations only in sync_pending_results()
    """

    def __init__(self,
                 trigger_rules: Optional[List[TriggerCondition]] = None,
                 daemon_budget_ms: float = 10.0,
                 pool_size: int = 2,
                 queue_size: int = 8,
                 sync_interval: int = 5,
                 step_boundary_modulus: int = 10,
                 optimize_interval: int = 20):
        self.trigger_rules = trigger_rules or DEFAULT_TRIGGER_RULES
        self.budget = DaemonBudget(total_budget_ms=daemon_budget_ms)
        self.pool_size = pool_size
        self.queue_size = queue_size
        self.sync_interval = sync_interval
        self.step_boundary_modulus = step_boundary_modulus
        self.optimize_interval = optimize_interval

        self._daemon_states: Dict[DaemonType, DaemonState] = {
            dt: DaemonState.IDLE for dt in DaemonType
        }
        self._last_fire_step: Dict[DaemonType, int] = {
            dt: -1000 for dt in DaemonType
        }
        self._fire_counts: Dict[DaemonType, int] = {
            dt: 0 for dt in DaemonType
        }
        self._request_counter: int = 0

        self._dispatch_queue: deque = deque(maxlen=queue_size)
        self._result_queue: deque = deque(maxlen=64)
        self._dispatch_lock = threading.Condition()
        self._result_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self._workers: List[threading.Thread] = []
        self._stop_event = threading.Event()
        self._daemon_registry: Dict[DaemonType, Callable] = {}

        self._stats = ExecutorStatistics()
        self._emergency_window: deque = deque(maxlen=100)
        self._degraded_until_step: int = 0

    def register_daemon(self, daemon_type: DaemonType,
                        handler: Callable[[DaemonRequest], DaemonResult]):
        self._daemon_registry[daemon_type] = handler

    def start(self):
        self._stop_event.clear()
        for i in range(self.pool_size):
            t = threading.Thread(
                target=self._worker_loop, args=(i,),
                daemon=True, name=f"telos-daemon-{i}",
            )
            t.start()
            self._workers.append(t)

    def shutdown(self, timeout_ms: float = 100):
        self._stop_event.set()
        with self._dispatch_lock:
            self._dispatch_lock.notify_all()
        deadline = time.time() + timeout_ms / 1000.0
        for t in self._workers:
            remaining = deadline - time.time()
            t.join(timeout=max(remaining, 0.01))
        self._workers.clear()

    def dispatch(self, telemetry: TelemetrySnapshot,
                 runtime_snapshot: Optional[Dict] = None) -> int:
        triggered: List[Tuple[DaemonType, DaemonPriority]] = []
        for rule in self.trigger_rules:
            if rule.condition_name == "step_boundary":
                if (telemetry.step_count > 0 and
                        telemetry.step_count % self.step_boundary_modulus == 0):
                    triggered.append((rule.daemon_type, rule.priority))
                continue
            if rule.condition_name == "periodic_optimize":
                if (telemetry.step_count > 0 and
                        telemetry.step_count % self.optimize_interval == 0):
                    triggered.append((rule.daemon_type, rule.priority))
                continue
            last_step = self._last_fire_step.get(rule.daemon_type, -1000)
            fires = self._fire_counts.get(rule.daemon_type, 0)
            is_triggered, _ = rule.evaluate(telemetry, last_step, fires)
            if is_triggered:
                triggered.append((rule.daemon_type, rule.priority))

        allocated, deferred = self.budget.allocate(
            triggered, self._estimate_cost
        )

        dispatched_count = 0
        for daemon_type in allocated:
            request = self._create_request(
                daemon_type, telemetry, runtime_snapshot or {},
            )
            if len(self._dispatch_queue) < self.queue_size:
                self._dispatch_queue.append(request)
                with self._state_lock:
                    self._daemon_states[daemon_type] = DaemonState.TRIGGERED
                self._last_fire_step[daemon_type] = telemetry.step_count
                self._fire_counts[daemon_type] += 1
                dispatched_count += 1
                with self._dispatch_lock:
                    self._dispatch_lock.notify()
            else:
                self._stats.total_daemons_dropped += 1

        self._stats.total_daemons_dispatched += dispatched_count
        return dispatched_count

    def sync_pending_results(self,
                             runtime_context: Any = None) -> PendingDaemonResults:
        pending = PendingDaemonResults()
        with self._result_lock:
            while self._result_queue:
                result = self._result_queue.popleft()
                pending.results.append(result)
                pending.total_duration_ms += result.duration_ms
                if result.emergency:
                    pending.emergency_count += 1
                self._stats.total_daemons_completed += 1

        self._stats.total_sync_cycles += 1
        self._stats.total_sync_duration_ms += pending.total_duration_ms
        if pending.results:
            self._stats.avg_sync_duration_ms = (
                self._stats.total_sync_duration_ms /
                self._stats.total_sync_cycles
            )
        self._stats.last_sync_step = getattr(
            runtime_context, '_step_count', 0
        )
        return pending

    def _worker_loop(self, worker_id: int):
        while not self._stop_event.is_set():
            request = None
            with self._dispatch_lock:
                if not self._dispatch_queue:
                    self._dispatch_lock.wait(timeout=0.05)
            if self._dispatch_queue:
                try:
                    request = self._dispatch_queue.popleft()
                except IndexError:
                    continue
            if request is None:
                continue

            with self._state_lock:
                self._daemon_states[request.daemon_type] = DaemonState.RUNNING
            start_time = time.time()
            try:
                handler = self._daemon_registry.get(request.daemon_type)
                if handler is None:
                    result = DaemonResult(
                        request_id=request.request_id,
                        daemon_type=request.daemon_type,
                        success=False,
                        duration_ms=0.0,
                        step=request.step,
                        recommendations=[
                            f"No handler for {request.daemon_type.value}"
                        ],
                    )
                else:
                    result = handler(request)
                    result.duration_ms = (time.time() - start_time) * 1000
                with self._state_lock:
                    self._daemon_states[request.daemon_type] = DaemonState.COMPLETED
            except Exception as e:
                result = DaemonResult(
                    request_id=request.request_id,
                    daemon_type=request.daemon_type,
                    success=False,
                    duration_ms=(time.time() - start_time) * 1000,
                    step=request.step,
                    recommendations=[f"Failed: {str(e)[:100]}"],
                )
                with self._state_lock:
                    self._daemon_states[request.daemon_type] = DaemonState.FAILED
                self._stats.total_daemons_failed += 1

            with self._result_lock:
                self._result_queue.append(result)

    def _create_request(self, daemon_type: DaemonType,
                        telemetry: TelemetrySnapshot,
                        runtime_snapshot: Dict) -> DaemonRequest:
        self._request_counter += 1
        return DaemonRequest(
            daemon_type=daemon_type,
            priority=DaemonPriority.NORMAL,
            request_id=self._request_counter,
            step=telemetry.step_count,
            timestamp=time.time(),
            health_state={
                'mission_integrity': telemetry.mission_integrity,
                'knowledge_quality': telemetry.knowledge_quality,
                'energy_efficiency': telemetry.energy_efficiency,
                'trust_merit': telemetry.trust_merit,
                'attention_focus': telemetry.attention_focus,
                'recovery_capacity': telemetry.recovery_capacity,
            },
            knowledge_graph_snapshot={
                'total_nodes': telemetry.knowledge_graph_nodes,
                'total_edges': telemetry.knowledge_graph_edges,
            },
            nutrition_score=telemetry.merit_flow,
            max_duration_ms=self.budget.total_budget_ms / max(
                len(self.budget.allocated_daemons), 1
            ),
        )

    def _estimate_cost(self, daemon_type: DaemonType) -> float:
        costs = {
            DaemonType.HEALTH_AUDIT: 1.5,
            DaemonType.STATE_COMPRESSION: 4.0,
            DaemonType.RESOURCE_ROTATION: 0.8,
            DaemonType.PRE_SYNC: 2.0,
            DaemonType.NUTRITION_SCAN: 1.0,
            DaemonType.KNOWLEDGE_PRUNE: 1.5,
            DaemonType.SOR_RECOVERY: 3.0,
            DaemonType.HEALTH_OPTIMIZE: 0.5,
        }
        return costs.get(daemon_type, 1.0)

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_steps_processed': self._stats.total_steps_processed,
            'total_daemons_dispatched': self._stats.total_daemons_dispatched,
            'total_daemons_completed': self._stats.total_daemons_completed,
            'total_daemons_failed': self._stats.total_daemons_failed,
            'total_daemons_dropped': self._stats.total_daemons_dropped,
            'total_sync_cycles': self._stats.total_sync_cycles,
            'avg_sync_duration_ms': round(self._stats.avg_sync_duration_ms, 4),
            'daemon_fire_counts': {
                k.value: v for k, v in self._fire_counts.items()
            },
            'daemon_states': {
                k.value: v.value for k, v in self._get_safe_daemon_states().items()
            },
            'queue_depth': len(self._dispatch_queue),
            'result_depth': len(self._result_queue),
            'last_sync_step': self._stats.last_sync_step,
            'emergency_count': self._stats.emergency_count,
            'degraded_steps': self._stats.degraded_steps,
        }

    def _get_safe_daemon_states(self) -> Dict[DaemonType, DaemonState]:
        with self._state_lock:
            return dict(self._daemon_states)

    def get_daemon_state(self, daemon_type: DaemonType) -> DaemonState:
        with self._state_lock:
            return self._daemon_states.get(daemon_type, DaemonState.IDLE)

    def reset_circuit_breakers(self):
        for dt in DaemonType:
            self._fire_counts[dt] = 0
        with self._state_lock:
            for dt in DaemonType:
                self._daemon_states[dt] = DaemonState.IDLE
        self._emergency_window.clear()
        self._degraded_until_step = 0
