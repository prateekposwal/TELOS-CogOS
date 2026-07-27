"""Cost tracker — maintenance and recovery cost tracking."""
import numpy as np
from dataclasses import dataclass
from typing import Dict, List
import logging
logger = logging.getLogger("telos_infrastructure")

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
