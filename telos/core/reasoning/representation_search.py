"""Representation Search — search over representations, not solutions.

Wiles changed from Iwasawa to Galois. That's representation search.
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger('telos_representation_search')


class RepresentationType(str, Enum):
    SYMBOLIC = "symbolic"
    SPATIAL = "spatial"
    TEMPORAL = "temporal"
    GRAPH = "graph"
    STATISTICAL = "statistical"
    ANALOGICAL = "analogical"


@dataclass
class RepresentationCandidate:
    rep_type: RepresentationType
    age: int = 0
    discoveries_produced: int = 0
    total_effort: float = 0.0
    bridge_count: int = 0

    @property
    def productivity(self) -> float:
        return self.discoveries_produced / max(self.total_effort, 0.01)


class RepresentationSearch:
    """Searches the space of representations, not just solutions."""

    def __init__(self):
        self._candidates: Dict[str, RepresentationCandidate] = {}
        self._current: Optional[str] = None
        self._switch_count: int = 0

    def register(self, rep_type: RepresentationType) -> str:
        rid = f"rep_{rep_type.value}"
        self._candidates[rid] = RepresentationCandidate(rep_type=rep_type)
        if self._current is None:
            self._current = rid
        return rid

    def record_discovery(self, rid: str, effort: float = 1.0) -> None:
        c = self._candidates.get(rid)
        if c:
            c.discoveries_produced += 1
            c.total_effort += effort

    def should_switch(self, min_productivity: float = 0.1) -> Optional[str]:
        if not self._current:
            return None
        current = self._candidates.get(self._current)
        if not current or current.productivity >= min_productivity:
            return None
        best = max(self._candidates.values(), key=lambda c: c.productivity)
        if best.productivity > current.productivity * 2:
            return best.rep_type.value
        return None

    def switch_to(self, rid: str) -> bool:
        if rid in self._candidates:
            self._current = rid
            self._switch_count += 1
            logger.info(f"RepresentationSearch: switched to {rid}")
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "current": self._current,
            "switches": self._switch_count,
            "candidates": {
                rid: {"type": c.rep_type.value, "productivity": round(c.productivity, 3),
                      "discoveries": c.discoveries_produced}
                for rid, c in self._candidates.items()
            },
        }
