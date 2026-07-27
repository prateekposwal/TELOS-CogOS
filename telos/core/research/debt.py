"""Research Debt — ignored contradictions, temporary workarounds, future complexity."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger('telos_research_debt')


@dataclass
class DebtEntry:
    description: str
    severity: float
    cycle_incurred: int
    resolved: bool = False


class ResearchDebtTracker:
    """Tracks accumulating research debt."""

    def __init__(self):
        self._entries: List[DebtEntry] = []

    def incur(self, description: str, severity: float, cycle: int) -> None:
        self._entries.append(DebtEntry(description, severity, cycle))
        logger.warning(f"ResearchDebt: incurred '{description}' (severity={severity:.2f})")

    def resolve(self, description: str) -> bool:
        for e in self._entries:
            if e.description == description and not e.resolved:
                e.resolved = True
                logger.info(f"ResearchDebt: resolved '{description}'")
                return True
        return False

    @property
    def total_debt(self) -> float:
        return sum(e.severity for e in self._entries if not e.resolved)

    @property
    def debt_entries(self) -> List[DebtEntry]:
        return [e for e in self._entries if not e.resolved]

    def to_dict(self) -> dict:
        return {
            "total_debt": round(self.total_debt, 3),
            "open_entries": len(self.debt_entries),
            "total_incurred": len(self._entries),
        }
