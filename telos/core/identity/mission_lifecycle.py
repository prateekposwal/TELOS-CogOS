"""Mission Lifecycle Engine — handles mission death, completion, and rebirth.

Mission Complete -> Reflection -> Identity -> Generate New Mission -> New Projects
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Dict, Optional

from telos.core.identity.mission import Mission, MissionPortfolio, MissionLifecycle
from telos.core.identity.system_self import IdentityCore, IdentityNarrative

logger = logging.getLogger('telos_mission_lifecycle')


@dataclass
class LifecycleTransition:
    old_mission_id: str
    old_status: str
    new_mission_id: Optional[str]
    new_status: str
    narrative_updated: bool


class MissionLifecycleEngine:
    """Handles mission completion, death, and rebirth."""

    def detect_completion(self, mission: Mission, all_projects_completed: bool,
                          cycle: int) -> Optional[LifecycleTransition]:
        if all_projects_completed:
            mission.complete(cycle)
            logger.info(f"MissionLifecycle: '{mission.name}' COMPLETED at cycle {cycle}")
            return LifecycleTransition(
                old_mission_id=mission.id,
                old_status="active",
                new_mission_id=None,
                new_status="completed",
                narrative_updated=False,
            )
        return None

    def execute_mission_death(self, mission: Mission, cycle: int,
                               portfolio: MissionPortfolio,
                               narrative: IdentityNarrative) -> Optional[LifecycleTransition]:
        if mission.lifecycle not in (MissionLifecycle.COMPLETED, MissionLifecycle.FAILED):
            return None

        narrative.record_completed_mission(mission.name)
        narrative.add_marker(f"veteran_of_{mission.name.replace(' ', '_')}")

        new_missions = portfolio.generate_missions_from_narrative(narrative.role, cycle)
        chosen_id = new_missions[0].id if new_missions else None

        logger.info(f"MissionLifecycle: '{mission.name}' -> rebirth -> "
                    f"new mission count: {len(new_missions)}")
        return LifecycleTransition(
            old_mission_id=mission.id,
            old_status=mission.lifecycle.value,
            new_mission_id=chosen_id,
            new_status="rebirth",
            narrative_updated=True,
        )

    def mark_failed(self, mission: Mission, cycle: int,
                    reason: str = "abandoned") -> None:
        mission.lifecycle = MissionLifecycle.FAILED
        mission.completion_cycle = cycle
        logger.info(f"MissionLifecycle: '{mission.name}' FAILED: {reason}")
