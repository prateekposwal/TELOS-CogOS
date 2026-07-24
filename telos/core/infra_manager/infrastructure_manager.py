"""
Infrastructure Manager — Meta-Cognitive Orchestrator

The InfraManager is the "Meta-Runtime." It observes the Pipeline's
execution and adjusts the system's cognitive parameters — stream
calibrations, failure policies, risk tolerance — without ever
modifying Pipeline logic.

This is the self-modifying loop:
  1. Pipeline executes a decision cycle
  2. InfraManager observes the result
  3. StreamCalibrator updates stream influence weights
  4. FailureLedger records failures as structural knowledge
  5. AuditController tracks infrastructure health trends
  6. MissionPolicy adjusts risk/exploration based on trends
  7. MaintenanceCostTracker records attention-related costs

The Pipeline remains architecturally invariant. Only the
InfraManager's calibrations change — the Pipeline reads them.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Dict, List, Callable, Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from telos.core.runtime import PipelineResult

from telos.core.infra_manager.stream_calibrator import StreamCalibrator
from telos.core.infra_manager.failure_ledger import FailureLedger
from telos.core.infra_manager.mission_policy import MissionPolicyManager, MissionPolicy
from telos.core.infra_manager.audit_controller import AuditController
from telos.core.infra_manager.health_manager import SystemHealthManager
from telos.core.infra_manager.knowledge_manager import KnowledgeManager
from telos.core.identity.system_self import SystemSelf
from telos.core.resource.gradient import ResourceGradientTracker

logger = logging.getLogger('telos_infra')


class MutationGuard:
    """Per-cycle rate limiter for InfrastructureManager self-modification.
    
    Prevents any single observe() call from making large, runaway changes
    to cognitive parameters by capping total delta per parameter per cycle.
    """
    
    MAX_DELTA_PER_CYCLE = {
        'risk_tolerance': 0.05,
        'exploration_budget': 0.05,
        'influence_weight': 0.1,
        'ambition_level': 0.1,
        'drift_tolerance': 1.0,
        'maintenance_bias': 0.1,
        'recovery_urgency': 0.1,
    }
    
    def __init__(self):
        self._cycle_deltas: Dict[str, float] = {}
        self._cycle_number: int = 0
        self._blocked_changes: int = 0
    
    def begin_cycle(self, cycle_number: int) -> None:
        self._cycle_number = cycle_number
        self._cycle_deltas = {}
    
    def check(self, param: str, proposed_delta: float) -> bool:
        current = self._cycle_deltas.get(param, 0.0)
        new_total = current + proposed_delta
        cap = self.MAX_DELTA_PER_CYCLE.get(param, 0.05)
        if abs(new_total) > cap:
            logger.warning(
                f"MutationGuard BLOCKED: {param} would drift {new_total:.3f} "
                f"(cap={cap}) in cycle {self._cycle_number}"
            )
            self._blocked_changes += 1
            return False
        self._cycle_deltas[param] = new_total
        return True


@dataclass
class MaintenanceCostTracker:
    """Tracks the ratio of maintenance vs recovery costs over time.

    Axiom 5.1 (Maintenance Cost vs Recovery Cost):
      - Maintenance costs: resources spent on upkeep, calibration, prevention
      - Recovery costs: resources spent on fixing failures after they occur
      - Early correction (maintenance) is cheaper than late recovery

    The tracker provides:
      - Rolling ratio of maintenance to total cost
      - Trend detection (is the system investing enough in maintenance?)
      - Alerting when recovery costs dominate
    """

    window_size: int = 20

    def __post_init__(self):
        self._maintenance_costs: List[float] = []
        self._recovery_costs: List[float] = []
        self._cycle_count: int = 0
        self._decay_rate: float = 0.1

    def record_maintenance(self, cost: float) -> None:
        """Record a maintenance cost (upkeep, calibration, prevention)."""
        self._cycle_count += 1
        self._apply_decay()
        self._maintenance_costs.append(max(0.0, cost))
        self._trim()

    def record_recovery(self, cost: float) -> None:
        """Record a recovery cost (failure repair, rework, catch-up)."""
        self._cycle_count += 1
        self._apply_decay()
        self._recovery_costs.append(max(0.0, cost))
        self._trim()

    def _apply_decay(self) -> None:
        """Decay older costs by 10% per cycle so recent events weigh more."""
        for i in range(len(self._maintenance_costs)):
            self._maintenance_costs[i] *= (1.0 - self._decay_rate)
        for i in range(len(self._recovery_costs)):
            self._recovery_costs[i] *= (1.0 - self._decay_rate)

    def _trim(self) -> None:
        """Keep rolling window bounded."""
        max_len = self.window_size * 2
        if len(self._maintenance_costs) > max_len:
            self._maintenance_costs = self._maintenance_costs[-self.window_size:]
        if len(self._recovery_costs) > max_len:
            self._recovery_costs = self._recovery_costs[-self.window_size:]

    @property
    def total_maintenance(self) -> float:
        return sum(self._maintenance_costs)

    @property
    def total_recovery(self) -> float:
        return sum(self._recovery_costs)

    @property
    def total_cost(self) -> float:
        return self.total_maintenance + self.total_recovery

    @property
    def maintenance_ratio(self) -> float:
        """Fraction of total cost spent on maintenance.

        Higher is better: it means the system is investing in prevention
        rather than paying for recovery after failures.
        """
        total = self.total_cost
        if total == 0:
            return 0.5  # neutral default
        return self.total_maintenance / total

    @property
    def recovery_ratio(self) -> float:
        """Fraction of total cost spent on recovery.

        Lower is better: high recovery ratio means the system is
        firefighting rather than preventing.
        """
        total = self.total_cost
        if total == 0:
            return 0.5
        return self.total_recovery / total

    @property
    def cost_efficiency(self) -> float:
        """Maintenance / Recovery ratio. Values > 1.0 mean proactive > reactive."""
        if self.total_recovery == 0:
            return 2.0 if self.total_maintenance > 0 else 1.0
        return self.total_maintenance / self.total_recovery

    @property
    def trend(self) -> str:
        """Human-readable assessment of cost management trend."""
        if self._cycle_count < 3:
            return "insufficient_data"
        recent_m = sum(self._maintenance_costs[-3:]) / max(len(self._maintenance_costs[-3:]), 1)
        recent_r = sum(self._recovery_costs[-3:]) / max(len(self._recovery_costs[-3:]), 1)
        if recent_m > recent_r * 1.5:
            return "healthy — maintenance dominates, proactive posture"
        elif recent_r > recent_m * 2:
            return "critical — recovery dominates, firefighting mode"
        elif recent_m > recent_r:
            return "stable — slight maintenance advantage"
        else:
            return "deteriorating — recovery costs rising"

    @property
    def stats(self) -> Dict:
        return {
            "total_maintenance": self.total_maintenance,
            "total_recovery": self.total_recovery,
            "total_cost": self.total_cost,
            "maintenance_ratio": self.maintenance_ratio,
            "recovery_ratio": self.recovery_ratio,
            "cost_efficiency": self.cost_efficiency,
            "trend": self.trend,
            "cycles_recorded": self._cycle_count,
            "recent_maintenance": self._maintenance_costs[-5:] if self._maintenance_costs else [],
            "recent_recovery": self._recovery_costs[-5:] if self._recovery_costs else [],
        }


class InfrastructureManager:
    """The Meta-Cognitive Layer — observes, calibrates, and governs.

    Usage:
        infra = InfrastructureManager()
        infra.set_mission("high_stakes")

        for state in states:
            result = pipeline.execute(state)
            infra.observe(result, total_streams=len(pipeline.streams))

        report = infra.generate_report()
        print(report.health_score)
    """

    def __init__(self, domain: str = "gridworld"):
        self._domain = domain
        self._mutation_guard = MutationGuard()
        self.calibrator = StreamCalibrator()
        self.failures = FailureLedger()
        self.policy = MissionPolicyManager()
        self.audit = AuditController()
        self._total_streams: int = 0
        self._council_block_listeners: List[Callable[[Dict], None]] = []
        self._escalation_count: int = 0
        # Lambda1.x: SystemSelf — persistent cognitive identity
        self.system_self = SystemSelf()
        # KnowledgeManager — consultation, recording, perception feedback
        self.knowledge_mgr = KnowledgeManager(self.policy, self.system_self, domain=self._domain)
        # SystemHealthManager — recovery, degradation, adaptive horizon
        self.health = SystemHealthManager(self.policy, self.audit, self.failures, domain=self._domain)
        # MaintenanceCostTracker — Law of Attention cost tracking
        self.cost_tracker = MaintenanceCostTracker()
        # P4: Resource gradient tracker
        self.resource_gradient = ResourceGradientTracker()
        self._last_resource_reallocation: Optional[Dict[str, float]] = None

        # Phase 3: Register infrastructure components for maturity tracking
        self.audit.register_component("stream_calibrator")
        self.audit.register_component("failure_ledger")
        self.audit.register_component("mission_policy")
        self.audit.register_component("audit_controller")
        self.audit.register_component("health_manager")
        self.audit.register_component("knowledge_manager")
        self.audit.register_component("cost_tracker")

    def search_knowledge(self, domain: str, top_k: int = 5) -> List[Any]:
        """Search the knowledge graph for proven solutions in a domain."""
        return self.knowledge_mgr.search_knowledge(domain, top_k)

    def consult_knowledge(self, domain: str, cycle: int = 0) -> Dict:
        """Consult KnowledgeGraph before the Pipeline executes."""
        return self.knowledge_mgr.consult_knowledge(domain, cycle)

    @property
    def adaptive_horizon(self) -> Optional[int]:
        return self.health.adaptive_horizon

    @adaptive_horizon.setter
    def adaptive_horizon(self, value: Optional[int]) -> None:
        self.health.adaptive_horizon = value

    def on_council_block(self, callback: Callable[[Dict], None]) -> None:
        """Register a callback invoked when the Council blocks an action."""
        self._council_block_listeners.append(callback)

    def on_recovery_event(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked on recovery mode transitions."""
        self.health.on_recovery_event(callback)

    @property
    def knowledge(self) -> 'KnowledgeGraph':
        """Backward-compat access to the KnowledgeGraph."""
        return self.knowledge_mgr.knowledge

    def record_maintenance_cost(self, cost: float) -> None:
        """Record a maintenance (preventive) cost for attention tracking."""
        self.cost_tracker.record_maintenance(cost)

    def record_recovery_cost(self, cost: float) -> None:
        """Record a recovery (failure repair) cost for attention tracking."""
        self.cost_tracker.record_recovery(cost)

    def observe(self, result: Any, total_streams: int = 0) -> None:
        """Process a PipelineResult through all infrastructure components.

        This is the self-modification entry point. Called after each
        pipeline.execute().

        Based on observations, the InfraManager may:
        - Adjust stream influence weights (Calibrator)
        - Record failures (Kintsugi Ledger)
        - Adjust risk tolerance based on failure rate (Policy)
        - Enter/exit Recovery Mode (Axiom 3.1)
        - Adjust simulation horizon (adaptive horizon)
        - Record escalations as structural knowledge
        - Track maintenance vs recovery costs (Axiom 5.1)
        """
        if result is None:
            return
        self._total_streams = max(self._total_streams, total_streams)

        # MutationGuard: track per-cycle parameter change budget
        cycle_num = getattr(result, 'decision_trace', None) and result.decision_trace.cycle_id or 0
        self._mutation_guard.begin_cycle(cycle_num)

        # Phase 3: Increment component cycle counters
        for component in self.audit._component_maturities.values():
            component.cycles_active += 1

        self.calibrator.observe(result)
        failure = self.failures.observe(result)

        # Phase 0: Feed ExperienceMap from selected stream
        trace = result.decision_trace if hasattr(result, 'decision_trace') else None
        if trace and trace.selected_intent:
            stream_name = trace.selected_intent.metadata.get('stream', '') if trace.selected_intent.metadata else ''
            if stream_name:
                context = str(trace.world_state_snapshot.tolist() if hasattr(trace, 'world_state_snapshot') and trace.world_state_snapshot is not None else '')
                self.calibrator.update_experience_map(stream_name, context, trace.selected_intent.confidence)

        # P2.5: Detect additional failure modes
        trace = result.decision_trace if hasattr(result, 'decision_trace') else None
        if failure is None and trace:
            # budget_starvation: health_score < 0.3 indicates budget nearly exhausted
            # Clamp health_score to [0, 1] to avoid false positives from carryover
            hs = max(0.0, min(1.0, result.health_score))
            if hs < 0.3:
                from telos.core.infra_manager.failure_ledger import FailureRecord
                failure = FailureRecord(
                    failure_id=f"budget_{trace.cycle_id}",
                    cycle=trace.cycle_id,
                    timestamp=time.time(),
                    failure_type="budget_starvation",
                    severity=0.6,
                    root_cause="resource_exhaustion",
                    decision_integrity=trace.decision_integrity,
                    mission_drift=trace.mission_drift,
                    metadata={"health_score": result.health_score},
                )
                self.failures.record_direct(failure)
            # simulation_timeout: worlds_generated == 0 but streams were activated
            elif result.worlds_generated == 0 and trace.stream_activations:
                any_activated = any(
                    sa.activated for sa in trace.stream_activations
                    if hasattr(sa, 'activated')
                )
                if any_activated:
                    from telos.core.infra_manager.failure_ledger import FailureRecord
                    failure = FailureRecord(
                        failure_id=f"sim_timeout_{trace.cycle_id}",
                        cycle=trace.cycle_id,
                        timestamp=time.time(),
                        failure_type="simulation_timeout",
                        severity=0.5,
                        root_cause="simulation_failure",
                        decision_integrity=trace.decision_integrity,
                        mission_drift=trace.mission_drift,
                        metadata={"worlds_generated": result.worlds_generated},
                    )
                    self.failures.record_direct(failure)

        # Λ2.3 — Record escalations as failures for Kintsugi visibility
        trace = result.decision_trace
        if trace and getattr(trace, 'escalation_requested', False):
            self._escalation_count += 1
            if not failure:
                from telos.core.infra_manager.failure_ledger import FailureRecord
                failure = FailureRecord(
                    failure_id=f"esc_{self._escalation_count}",
                    cycle=trace.cycle_id,
                    timestamp=time.time(),
                    failure_type="escalation",
                    severity=min(0.5, 0.2 + self._escalation_count * 0.05),
                    root_cause="unresolved_uncertainty",
                    decision_integrity=trace.decision_integrity,
                    mission_drift=trace.mission_drift,
                    metadata={
                        "reason": trace.escalation_reason,
                        "escalation_count": self._escalation_count,
                    },
                )
                self.failures.record_direct(failure)

        # Λ2.2 — Fire council block callbacks when the Council blocks action
        if result.council_blocked and hasattr(result, 'decision_trace') and result.decision_trace:
            block_info = {
                "blocking_validator": result.decision_trace.blocking_validator,
                "signals": result.decision_trace.council_signals,
                "di": result.decision_trace.decision_integrity,
                "md": result.decision_trace.mission_drift,
            }
            for cb in self._council_block_listeners:
                try:
                    cb(block_info)
                except Exception as e:
                    logger.warning(f"on_council_block callback failed: {e}")
        self.audit.observe(result)

        # Set B: Apply council-block penalty to stream calibrations
        if result.council_blocked or (trace and not getattr(trace, 'council_validated', True)):
            self.calibrator.apply_council_block_penalty()

        # Delegate health monitoring to SystemHealthManager
        failure = self.health.observe(result, failure, trace)

        # ── Maintenance/Recovery Cost Tracking ──
        # When a failure occurs, it's a recovery cost
        # When no failure and DI > 0.8, it's maintenance (preventive)
        # Action-loop blocks are governance events, not system failures
        if failure is not None and getattr(failure, 'blocked_by', '') != 'action_loop':
            self.cost_tracker.record_recovery(failure.severity * 1.0)
        elif trace and trace.decision_integrity > 0.8:
            self.cost_tracker.record_maintenance(0.1)
        elif trace:
            self.cost_tracker.record_maintenance(0.5)

        # Adaptive policy adjustment based on recent failures
        if failure is not None:
            recent = self.failures.get_recent_failures(n=5)
            recent_failures = len(recent)
            if recent_failures >= 3 and self._mutation_guard.check('risk_tolerance', -0.1):
                self.policy.adjust_risk_tolerance(-0.1)
                logger.info("InfraManager: reduced risk tolerance due to recent failures")

        # Increase exploration after stable periods
        if self.audit.stats.get("cycles_observed", 0) > 5:
            recent_di = self.audit.stats.get("di_trend", 1.0)
            recent_md = self.audit.stats.get("md_trend", 0.0)
            if recent_di > 0.9 and recent_md < 1.0 and self._mutation_guard.check('exploration_budget', 0.05):
                self.policy.adjust_exploration_budget(0.05)

        # Delegate knowledge recording to KnowledgeManager
        failure = self.knowledge_mgr.observe(result, failure, trace)

        # Phase 0: Adjust risk tolerance based on stream uncertainties
        uncertainties = self.calibrator.get_stream_uncertainties()
        self.policy.adjust_risk_by_uncertainty(uncertainties)

        # Phase 3: Gate risk by infrastructure readiness
        readiness = self.audit.infra_readiness_score()
        self.policy.set_readiness_gate(readiness)

        # A2: Wire mood into risk tolerance — SystemSelf.get_risk_adjustment() applied
        mood_adj = self.system_self.get_risk_adjustment()
        if abs(mood_adj) > 0.01 and self._mutation_guard.check('risk_tolerance', mood_adj * 0.3):
            self.policy.adjust_risk_tolerance(
                mood_adj * 0.3,
                reason=f"mood:{self.system_self.mood}",
                caller="system_self",
            )

        # C2: Wire mood into exploration budget
        explore_adj = self.system_self.get_exploration_adjustment()
        if abs(explore_adj) > 0.01 and self._mutation_guard.check('exploration_budget', explore_adj * 0.3):
            self.policy.adjust_exploration_budget(
                explore_adj * 0.3,
                reason=f"mood:{self.system_self.mood}",
                caller="system_self",
            )


        # P4: Resource gradient computation and reallocation
        if trace is not None and hasattr(trace, "resource_budgets") and trace.resource_budgets:
            try:
                commitment_opt = getattr(self, "_commitment_optimizer", None)
                # If not directly accessible, try via pipeline
                if commitment_opt is None:
                    commitment_opt = getattr(trace, "_commitment_optimizer", None)
                
                gradients = self.resource_gradient.compute_gradients(
                    commitment_opt,
                    trace.resource_budgets,
                )
                
                # Reallocate if we have meaningful gradients
                if any(abs(v) > 0.01 for v in gradients.values()):
                    reallocated = self.resource_gradient.reallocate(
                        trace.resource_budgets,
                        gradients,
                        step_size=0.05,
                    )
                    # Store reallocation for downstream use
                    self._last_resource_reallocation = reallocated
            except Exception as e:
                logger.debug(f"Resource gradient computation failed: {e}")

        # Phase 2: Kintsugi — integrate failures into identity and repair
        if failure is not None:
            markers = self.failures.integrate_into_identity(failure)
            self.system_self.observe(
                result.decision_integrity, result.mission_drift,
                result.council_blocked or result.firewall_blocked,
                identity_markers_to_add=markers,
                cycle_number=trace.cycle_id if trace else 0,
            )
            self._kintsugi_repair()

            # Set B: Consume identity markers — map to policy adjustments
            if markers:
                self.policy.apply_identity_markers(markers)
        else:
            self.system_self.observe(
                result.decision_integrity, result.mission_drift,
                result.council_blocked or result.firewall_blocked,
                cycle_number=trace.cycle_id if trace else 0,
            )

    def enter_recovery(self) -> None:
        """Enter recovery mode: tighten risk tolerance, reduce exploration, shorten horizon."""
        self.health.enter_recovery()

    def exit_recovery(self) -> None:
        """Exit recovery mode: restore pre-recovery parameters and horizon."""
        self.health.exit_recovery()

    def set_mission(self, mission_name: str,
                     risk_tolerance: float = 0.3,
                     exploration_budget: float = 0.3,
                     ambition_level: float = 0.5,
                     drift_tolerance: float = 5.0) -> None:
        """Set a new mission policy."""
        self.policy.set_policy(MissionPolicy(
            mission_name=mission_name,
            risk_tolerance=risk_tolerance,
            exploration_budget=exploration_budget,
            ambition_level=ambition_level,
            drift_tolerance=drift_tolerance,
        ))

    def _kintsugi_repair(self) -> None:
        """Kintsugi: perform structural repair based on recent failures.
        
        Real structural actions (not just logs):
          1. 3+ budget_starvation → reduce n_worlds
          2. 3+ simulation_timeout → reduce horizon
          3. 3+ high-severity failures → tighten risk + circuit break
          4. Every 5 failures → increase resilience
          5. Track repair_effective flag
        """
        total = self.failures.total_failures
        recent = self.failures.get_recent_failures(n=10)
        recent_severity = sum(f.severity for f in recent) / max(len(recent), 1)
        recent_failures = len(recent)
        by_type = self.failures.stats.get("by_type", {})

        # Budget starvation → reduce n_worlds
        budget_starvations = by_type.get("budget_starvation", 0)
        if budget_starvations >= 3:
            old_horizon = self.health.adaptive_horizon
            new_horizon = max(3, (old_horizon or 8) - 1)
            self.health.adaptive_horizon = new_horizon
            logger.info(
                f"Kintsugi: {budget_starvations} budget_starvations "
                f"— horizon {old_horizon} → {new_horizon}"
            )

        # Simulation timeout → reduce horizon further
        sim_timeouts = by_type.get("simulation_timeout", 0)
        if sim_timeouts >= 3:
            old_horizon = self.health.adaptive_horizon
            new_horizon = max(2, (old_horizon or 8) - 2)
            self.health.adaptive_horizon = new_horizon
            logger.info(
                f"Kintsugi: {sim_timeouts} simulation_timeouts "
                f"— horizon {old_horizon} → {new_horizon}"
            )

        # High-severity failures → tighten risk + circuit break failing streams
        if recent_failures >= 3 and recent_severity > 0.5:
            old_risk = self.policy.current.risk_tolerance
            if self._mutation_guard.check('risk_tolerance', -0.1):
                self.policy.adjust_risk_tolerance(-0.1, reason="kintsugi_high_severity")

            # Circuit break: if a specific failure type dominates, reduce its stream weight
            from telos.core.infra_manager.failure_ledger import FailureRecord
            type_counts: Dict[str, int] = {}
            for f in recent:
                type_counts[f.failure_type] = type_counts.get(f.failure_type, 0) + 1
            worst_type = max(type_counts, key=type_counts.get) if type_counts else None
            if worst_type and type_counts.get(worst_type, 0) >= 3:
                # Map failure type to stream name for circuit breaking
                type_stream_map = {
                    "council_block": "PlanningStream",
                    "high_drift": "PlanningStream",
                    "simulation_timeout": "PlanningStream",
                    "budget_starvation": "MemoryStream",
                    "low_integrity": "PerceptionStream",
                }
                stream_name = type_stream_map.get(worst_type)
                if stream_name:
                    cal = self.calibrator.get_calibration(stream_name)
                    if cal and cal.council_blocks > 0:
                        block_rate = cal.council_blocks / max(cal.total_calls, 1)
                        if block_rate > 0.3:
                            old_weight = cal.influence_weight
                            halved = old_weight * 0.5
                            cal.influence_weight = halved
                            logger.info(
                                f"Kintsugi circuit break: {stream_name} "
                                f"({worst_type} ×{type_counts[worst_type]}) "
                                f"— weight {old_weight:.2f} → {halved:.2f}"
                            )

            logger.info(
                f"Kintsugi: repair triggered — {recent_failures} recent failures "
                f"(avg severity={recent_severity:.2f}). risk {old_risk:.2f} → "
                f"{self.policy.current.risk_tolerance:.2f}, horizon adjusted"
            )

        if total > 5 and total % 5 == 0:
            self.system_self.state.resilience = min(1.0, self.system_self.state.resilience + 0.05)
            logger.info(
                f"Kintsugi: resilience increased to {self.system_self.state.resilience:.2f} "
                f"after {total} total failures"
            )

        # A3: Resilience decay — decrease after rapid failure streaks
        # Prevents "emotional flatlining" where resilience only ever increases
        if recent_failures >= 3 and len(recent) >= 3:
            # Check if failures are accelerating (severity increasing)
            sevs = [f.severity for f in recent[:3]]
            if len(sevs) >= 2 and sevs[-1] > sevs[0]:
                decay = 0.03 * (sevs[-1] - sevs[0])
                self.system_self.state.resilience = max(0.1, self.system_self.state.resilience - decay)
                logger.info(
                    f"Kintsugi: resilience decayed by {decay:.3f} to "
                    f"{self.system_self.state.resilience:.2f} (accelerating failures)"
                )

    def generate_report(self) -> 'InfrastructureReport':
        """Generate an infrastructure health report."""
        from telos.core.infra_manager.audit_controller import InfrastructureReport
        total = self._total_streams or len(self.calibrator.stats["calibrations"])
        return self.audit.generate_report(
            calibrated_streams=len(self.calibrator.stats["calibrations"]),
            total_streams=total,
        )

    @property
    def stats(self) -> Dict:
        return {
            "calibrator": self.calibrator.stats,
            "failures": self.failures.stats,
            "policy": self.policy.stats,
            "audit": self.audit.stats,
            "health": self.health.stats,
            "knowledge": self.knowledge_mgr.stats,
            "system_self": self.system_self.to_dict() if hasattr(self, 'system_self') else {},
            "cost_tracker": self.cost_tracker.stats,
        }
