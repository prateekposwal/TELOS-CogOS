"""Discovery Rate — marginal knowledge gain tracking.

Asks not 'Am I right?' but 'Am I still discovering?'
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger('telos_discovery_rate')


@dataclass
class DiscoveryRecord:
    cycle: int
    new_insights: int
    effort: float
    rate: float
    cumulative: int


class DiscoveryRateTracker:
    """Tracks marginal discovery rate across the ecosystem."""

    def __init__(self, window: int = 20):
        self._records: List[DiscoveryRecord] = []
        self._window = window
        self._cumulative_insights: int = 0

    def record(self, cycle: int, new_insights: int, effort: float = 1.0) -> None:
        rate = new_insights / max(effort, 0.01)
        self._records.append(DiscoveryRecord(cycle, new_insights, effort, rate, self._cumulative_insights))
        self._cumulative_insights += new_insights
        if len(self._records) > self._window:
            self._records.pop(0)

    @property
    def marginal_rate(self) -> float:
        if not self._records:
            return 0.0
        recent = self._records[-min(5, len(self._records)):]
        return sum(r.rate for r in recent) / len(recent)

    @property
    def is_discovering(self) -> bool:
        return self.marginal_rate > 0.05

    @property

    def to_dict(self) -> dict:
        return {
            "marginal_rate": round(self.marginal_rate, 4),
            "is_discovering": self.is_discovering,
            "total": self._cumulative_insights,
            "records": len(self._records),
        }
