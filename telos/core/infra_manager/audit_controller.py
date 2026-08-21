"""
Audit Controller — Monitors Infrastructure Health.

The AuditController evaluates the maturity of the system's infrastructure
components over time. It does not track "accuracy" — it tracks infrastructure
quality metrics:

  - Stream Calibration Coverage: What fraction of streams are calibrated?
  - Failure Rate: How many cycles end in failure?
  - Decision Integrity Trend: Is DI improving or degrading?
  - Mission Drift Trend: Is MD increasing or stable?

These metrics are the basis for the "Infrastructure-First" evaluation
framework — we measure the system by the health of its infrastructure,
not by task-specific accuracy.
"""

from __future__ import annotations

import time
import numpy as np
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger('telos_infra')


@dataclass
class ComponentMaturity:
    """Maturity score for a single infrastructure component."""
    component_name: str
    cycles_active: int = 0
    calibration_count: int = 0
    coverage_score: float = 0.0
    maturity_score: float = 0.0


@dataclass
class InfrastructureReport:
    """A snapshot of infrastructure health at a point in time."""
    timestamp: float
    total_cycles: int
    failure_rate: float
    avg_decision_integrity: float
    avg_mission_drift: float
    stream_calibration_coverage: float
    governance_block_rate: float
    health_score: float
    infra_readiness_score: float = 0.0
    component_maturities: Dict[str, float] = field(default_factory=dict)


class AuditController:
    """Monitors infrastructure health and generates maturity reports.

    The AuditController evaluates the system not by "accuracy" but by
    the maturity of its infrastructure components. This is the
    "Infrastructure-First" evaluation framework.
    """

    def __init__(self):
        self._di_history: List[float] = []
        self._md_history: List[float] = []
        self._health_history: List[float] = []
        self._cycle_count: int = 0
        self._failure_count: int = 0
        self._governance_block_count: int = 0
        self._component_maturities: Dict[str, ComponentMaturity] = {}

    def register_component(self, name: str) -> ComponentMaturity:
        """Register an infrastructure component for maturity tracking.
            Args:
                name: the name/key of the item
        """
        mat = ComponentMaturity(component_name=name)
        self._component_maturities[name] = mat
        return mat


    def evaluate_component_maturity(self, name: str) -> float:
        """Score a component's maturity based on cycles, coverage, and calibration.
            Args:
                name: the name/key of the item
        """
        mat = self._component_maturities.get(name)
        if not mat:
            return 0.0
        cycle_factor = min(1.0, mat.cycles_active / 100)
        cal_factor = min(1.0, mat.calibration_count / 50)
        cov_factor = mat.coverage_score
        mat.maturity_score = float(np.clip(
            cycle_factor * 0.3 + cal_factor * 0.4 + cov_factor * 0.3, 0.0, 1.0
        ))
        return mat.maturity_score

    def infra_readiness_score(self) -> float:
        """Compute overall infrastructure readiness from all registered components."""
        scores = [self.evaluate_component_maturity(n) for n in self._component_maturities]
        return float(np.mean(scores)) if scores else 0.0

    def observe(self, result: Any) -> None:
        """Record infrastructure metrics from a single decision cycle.
            Args:
                result: the observation result
        """
        self._cycle_count += 1
        trace = result.decision_trace
        if trace is None:
            return

        self._di_history.append(trace.decision_integrity)
        self._md_history.append(trace.mission_drift)
        self._health_history.append(result.health_score)

        if not trace.council_validated or trace.firewall_blocked:
            self._failure_count += 1
        if trace.firewall_blocked:
            self._governance_block_count += 1

    def generate_report(self, calibrated_streams: int = 0,
                         total_streams: int = 0) -> InfrastructureReport:
        """Generate a snapshot of infrastructure health.
            Args:
                calibrated_streams: streams that are calibrated
                total_streams: the total stream count
        """
        avg_di = float(np.mean(self._di_history[-50:])) if self._di_history else 1.0
        avg_md = float(np.mean(self._md_history[-50:])) if self._md_history else 0.0
        avg_health = float(np.mean(self._health_history[-50:])) if self._health_history else 1.0

        failure_rate = self._failure_count / max(self._cycle_count, 1)
        gov_block_rate = self._governance_block_count / max(self._cycle_count, 1)
        cal_coverage = calibrated_streams / max(total_streams, 1)

        # Composite health score
        health_score = float(np.clip(
            0.3 * avg_di +
            0.3 * (1.0 - failure_rate) +
            0.2 * (1.0 - gov_block_rate) +
            0.2 * avg_health,
            0.0, 1.0
        ))

        return InfrastructureReport(
            timestamp=time.time(),
            total_cycles=self._cycle_count,
            failure_rate=failure_rate,
            avg_decision_integrity=avg_di,
            avg_mission_drift=avg_md,
            stream_calibration_coverage=cal_coverage,
            governance_block_rate=gov_block_rate,
            health_score=health_score,
            infra_readiness_score=self.infra_readiness_score(),
            component_maturities={
                n: round(self.evaluate_component_maturity(n), 3)
                for n in self._component_maturities
            },
        )

    def get_di_history(self) -> List[float]:
        """Return a copy of decision-integrity history."""
        return list(self._di_history)

    def get_md_history(self) -> List[float]:
        """Return a copy of mission-drift history."""
        return list(self._md_history)

    @property
    def stats(self) -> Dict:
        return {
            "cycles_observed": self._cycle_count,
            "failures": self._failure_count,
            "governance_blocks": self._governance_block_count,
            "di_trend": float(np.mean(self._di_history[-10:])) if len(self._di_history) >= 10
                        else (float(np.mean(self._di_history)) if self._di_history else 1.0),
            "md_trend": float(np.mean(self._md_history[-10:])) if len(self._md_history) >= 10
                        else (float(np.mean(self._md_history)) if self._md_history else 0.0),
        }
