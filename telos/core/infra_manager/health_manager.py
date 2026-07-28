"""
SystemHealthManager — Recovery, Degradation, and Adaptive Horizon Management.

Extracted from InfrastructureManager to reduce god-object complexity.
Handles:
  - Recovery mode entry/exit (Axiom 3.1)
  - Predictive degradation detection (watchful mode)
  - Adaptive simulation horizon (Lambda 2.5)
  - Council block and recovery event listeners
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Dict, List, Callable, Any

from telos.core.infra_manager.mission_policy import MissionPolicyManager, MissionPolicy

logger = logging.getLogger('telos_infra')

# Domain-specific configurations for recovery, degradation, and horizon management
DOMAIN_CONFIGS: Dict[str, Dict[str, int]] = {
    "gridworld": {"failure_threshold": 3, "window": 10, "clean_cycles": 5, "base_horizon": 3},
    "devdomain": {"failure_threshold": 5, "window": 20, "clean_cycles": 8, "base_horizon": 5},
    "default":   {"failure_threshold": 3, "window": 10, "clean_cycles": 5, "base_horizon": 3},
}


class SystemHealthManager:
    """Monitors system health: recovery, degradation, and horizon adaptation.

    Designed to be owned by InfrastructureManager and fed observe() calls
    during the same cycle. The observe() method returns an (possibly updated)
    FailureRecord for downstream consumers.
    """

    def __init__(self, policy: MissionPolicyManager, audit, failures, domain: str = "gridworld"):
        self.policy = policy
        self.audit = audit
        self.failures = failures
        self.domain = domain
        self._domain_config = DOMAIN_CONFIGS.get(domain, DOMAIN_CONFIGS["default"])

        self._clean_since_recovery: int = 0
        self._recovery_cycle_count: int = 0
        self._max_recovery_cycles: int = 20
        self._adaptive_horizon: Optional[int] = None
        self._base_horizon: int = self._domain_config["base_horizon"]
        self._degradation_cycles: int = 0
        self._watchful_mode: bool = False
        self._pre_recovery_policy: Optional[MissionPolicy] = None
        self._recovery_listeners: List[Callable[[str], None]] = []
        self._council_block_listeners: List[Callable[[Dict], None]] = []

    @property
    def adaptive_horizon(self) -> Optional[int]:
        """Overrides PipelineConfig.horizon when set (Lambda 2.5)."""
        return self._adaptive_horizon

    @adaptive_horizon.setter
    def adaptive_horizon(self, value: Optional[int]) -> None:
        self._adaptive_horizon = value

    @property
    def degradation_cycles(self) -> int:
        return self._degradation_cycles

    @property
    def watchful_mode(self) -> bool:
        return self._watchful_mode

    def on_recovery_event(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked on recovery mode transitions."""
        self._recovery_listeners.append(callback)

    def enter_recovery(self) -> None:
        """Enter recovery mode: tighten risk tolerance, reduce exploration, shorten horizon.
        
        Modifies the current policy in-place rather than calling set_policy() to avoid
        creating spurious policy_history entries. The original pre-recovery parameters
        are saved for exit_recovery() to restore.
        """
        self._pre_recovery_policy = MissionPolicy(
            mission_name=self.policy.current.mission_name,
            risk_tolerance=self.policy.current.risk_tolerance,
            exploration_budget=self.policy.current.exploration_budget,
            ambition_level=self.policy.current.ambition_level,
            drift_tolerance=self.policy.current.drift_tolerance,
            recovery_mode=self.policy.current.recovery_mode,
        )
        self.policy._current.risk_tolerance = max(0.05, self.policy.current.risk_tolerance - 0.2)
        self.policy._current.exploration_budget = max(0.05, self.policy.current.exploration_budget - 0.15)
        self.policy._current.ambition_level = max(0.1, self.policy.current.ambition_level - 0.2)
        self.policy._current.drift_tolerance = max(1.0, self.policy.current.drift_tolerance - 2.0)
        self.policy._current.recovery_mode = True
        self._adaptive_horizon = max(2, self._base_horizon - 1)
        self._clean_since_recovery = 0
        self._recovery_cycle_count = 0
        logger.info(f"InfraManager: ENTERED RECOVERY MODE — horizon={self._adaptive_horizon}, all parameters tightened")
        for cb in self._recovery_listeners:
            cb("enter")

    def exit_recovery(self) -> None:
        """Exit recovery mode: restore pre-recovery parameters and horizon.
        
        Restores parameters in-place from the saved _pre_recovery_policy snapshot,
        avoiding set_policy() to keep policy_history clean.
        """
        pre = self._pre_recovery_policy or MissionPolicy()
        self.policy._current.risk_tolerance = pre.risk_tolerance
        self.policy._current.exploration_budget = pre.exploration_budget
        self.policy._current.ambition_level = pre.ambition_level
        self.policy._current.drift_tolerance = pre.drift_tolerance
        self.policy._current.recovery_mode = False
        self._adaptive_horizon = None
        self._clean_since_recovery = 0
        self._recovery_cycle_count = 0
        logger.info("InfraManager: EXITED RECOVERY MODE — parameters and horizon restored")
        for cb in self._recovery_listeners:
            cb("exit")

    def observe(self, result, failure, trace):
        """Process degradation detection, recovery mode, and adaptive horizon.

        Args:
            result: PipelineResult from current cycle.
            failure: FailureRecord or None from upstream detection.
            trace: DecisionTrace or None.

        Returns:
            Possibly updated failure (a synthetic failure may be created
            during degradation escalation).
        """
        # P2.7: Predictive degradation detection
        if self.audit.stats.get("cycles_observed", 0) > 10:
            failure = self._check_degradation(failure, trace)

        # Recovery Mode (Axiom 3.1)
        failure = self._check_recovery(failure)

        # Adaptive Horizon (Lambda 2.5)
        self._adjust_horizon(trace)

        return failure

    def _check_degradation(self, failure, trace):
        """Predictive degradation — enter watchful mode before full recovery."""
        di_history = self.audit.get_di_history()
        md_history = self.audit.get_md_history()
        if len(di_history) < 8:
            return failure

        recent_di = di_history[-5:]
        older_di = di_history[-8:-5]
        di_degrading = (
            len(older_di) >= 3 and len(recent_di) >= 3 and
            all(recent_di[i] < older_di[i] for i in range(min(3, len(older_di), len(recent_di))))
        )

        recent_md = md_history[-5:]
        older_md = md_history[-8:-5]
        md_rising = (
            len(older_md) >= 3 and len(recent_md) >= 3 and
            all(recent_md[i] > older_md[i] for i in range(min(3, len(older_md), len(recent_md))))
        )

        if di_degrading or md_rising:
            self._degradation_cycles += 1
        else:
            self._degradation_cycles = 0
            self._watchful_mode = False

        if self._degradation_cycles >= 5 and not self._watchful_mode and not self.policy.current.recovery_mode:
            self._watchful_mode = True
            self.policy.adjust_risk_tolerance(-0.05)
            logger.warning(
                f"Predictive: DI degrading for {self._degradation_cycles} cycles — "
                f"entering watchful mode (risk_tolerance reduced by 0.05)"
            )

        if self._watchful_mode and self._degradation_cycles >= 8 and not self.policy.current.recovery_mode:
            logger.warning(
                f"Predictive: degradation continued for {self._degradation_cycles} cycles — "
                f"escalating to full recovery"
            )
            if failure is None:
                from telos.core.infra_manager.failure_ledger import FailureRecord
                failure = FailureRecord(
                    failure_id=f"predictive_{trace.cycle_id if trace else 0}",
                    cycle=trace.cycle_id if trace else 0,
                    timestamp=time.time(),
                    failure_type="low_integrity",
                    severity=0.5,
                    root_cause="predictive_degradation",
                    decision_integrity=trace.decision_integrity if trace else 0.5,
                    mission_drift=trace.mission_drift if trace else 0.0,
                )
                self.failures.record_direct(failure)

        return failure

    def _check_recovery(self, failure):
        """Enter or exit recovery mode based on failure rate.
        
        Includes an explicit timeout: if recovery mode has been active for more
        than max_recovery_cycles (default 20), force-exit and reset to nominal.
        This prevents recovery mode from getting permanently stuck.
        """
        if self.policy.current.recovery_mode:
            self._recovery_cycle_count += 1
            # Force-exit recovery if it has been active too long
            if self._recovery_cycle_count >= self._max_recovery_cycles:
                logger.warning(
                    f"InfraManager: RECOVERY TIMEOUT — forced exit after "
                    f"{self._recovery_cycle_count} cycles (max={self._max_recovery_cycles})"
                )
                self.exit_recovery()
                return failure
            
            if failure is None:
                self._clean_since_recovery += 1
                if self._clean_since_recovery >= self._domain_config["clean_cycles"]:
                    self.exit_recovery()
            else:
                self._clean_since_recovery = 0
        else:
            if failure is not None:
                recent = self.failures.get_recent_failures(n=self._domain_config["window"])
                if len(recent) >= self._domain_config["failure_threshold"]:
                    self.enter_recovery()
            self._clean_since_recovery = 0
        return failure

    def _adjust_horizon(self, trace):
        """Adaptive horizon adjustment based on DI/MD trends (Lambda 2.5)."""
        if not trace or self.audit.stats.get("cycles_observed", 0) <= 3:
            return

        recent_di = self.audit.stats.get("di_trend", 1.0)
        recent_md = self.audit.stats.get("md_trend", 0.0)

        if recent_di > 0.85 and recent_md < 0.5:
            new_h = self._base_horizon + 2
            if self._adaptive_horizon is None or self._adaptive_horizon < new_h:
                self._adaptive_horizon = new_h
                logger.debug(f"AdaptiveHorizon: increased to {new_h} (stable)")
        elif recent_di < 0.5 or recent_md > 3.0:
            new_h = max(2, self._base_horizon - 1)
            if self._adaptive_horizon is None or self._adaptive_horizon > new_h:
                self._adaptive_horizon = new_h
                logger.debug(f"AdaptiveHorizon: decreased to {new_h} (unstable)")
        elif self._adaptive_horizon is not None and self._adaptive_horizon != self._base_horizon:
            step = 1 if self._adaptive_horizon < self._base_horizon else -1
            self._adaptive_horizon += step
            logger.debug(f"AdaptiveHorizon: drifted to {self._adaptive_horizon} (baseline)")

        if hasattr(trace, 'reflection') and trace.reflection:
            reflect_horizon = trace.reflection.get("recommended_horizon")
            if reflect_horizon is not None and self._adaptive_horizon != reflect_horizon:
                audit_di = self.audit.stats.get("di_trend", None)
                audit_md = self.audit.stats.get("md_trend", None)
                if audit_di is not None and audit_md is not None:
                    logger.info(
                        f"AdaptiveHorizon: Reflect recommended {reflect_horizon}, "
                        f"Infra using {self._adaptive_horizon} "
                        f"(di_trend={audit_di:.2f}, md_trend={audit_md:.2f})"
                    )
                else:
                    logger.info(
                        f"AdaptiveHorizon: Reflect recommended {reflect_horizon}, "
                        f"Infra using {self._adaptive_horizon}"
                    )

    @property
    def stats(self) -> Dict:
        return {
            "degradation_cycles": self._degradation_cycles,
            "watchful_mode": self._watchful_mode,
            "adaptive_horizon": self._adaptive_horizon,
            "clean_since_recovery": self._clean_since_recovery,
            "recovery_listeners": len(self._recovery_listeners),
            "council_block_listeners": len(self._council_block_listeners),
        }
