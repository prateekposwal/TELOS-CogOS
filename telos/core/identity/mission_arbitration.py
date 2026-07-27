"""Mission Arbitration — resolves conflicts between competing missions.

When multiple missions exist, arbitration selects which gets active projects.
All missions remain in the portfolio. Arbitration happens BEFORE project creation.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from telos.core.identity.mission import Mission, MissionPortfolio

logger = logging.getLogger('telos_mission_arbitration')

WEIGHT_CORE_ALIGNMENT = 0.40
WEIGHT_URGENCY = 0.25
WEIGHT_PRIORITY = 0.20
WEIGHT_INERTIA = 0.15


@dataclass
class ArbitrationVerdict:
    mission_id: str
    score: float
    rank: int
    becomes_active: bool


class MissionArbiter:
    """Arbitrates between competing missions on four axes."""

    def arbitrate(self, portfolio: MissionPortfolio,
                  current_active_id: Optional[str] = None
                  ) -> List[ArbitrationVerdict]:
        missions = portfolio.active_missions()
        if not missions:
            return []

        scored = []
        for m in missions:
            score = (
                WEIGHT_CORE_ALIGNMENT * m.identity_core_alignment +
                WEIGHT_URGENCY * m.urgency +
                WEIGHT_PRIORITY * m.priority +
                WEIGHT_INERTIA * (0.1 if m.id == current_active_id else 0.0)
            )
            scored.append((m.id, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        verdicts = []
        for rank, (mid, score) in enumerate(scored):
            verdicts.append(ArbitrationVerdict(
                mission_id=mid, score=score, rank=rank,
                becomes_active=(rank == 0),
            ))
        return verdicts
