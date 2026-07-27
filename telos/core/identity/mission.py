"""Mission entity — Layer 3 of the Identity Cascade.

Identity Core -> Identity Narrative -> Missions -> Projects -> Methods -> Actions
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger('telos_mission')


class MissionLifecycle(str, Enum):
    BIRTH = "birth"
    ACTIVE = "active"
    DORMANT = "dormant"
    COMPLETED = "completed"
    FAILED = "failed"
    SUPERSEDED = "superseded"


@dataclass
class Mission:
    id: str
    name: str
    description: str
    lifecycle: MissionLifecycle = MissionLifecycle.BIRTH
    birth_cycle: int = 0
    completion_cycle: Optional[int] = None
    priority: float = 0.5
    urgency: float = 0.0
    identity_core_alignment: float = 1.0
    project_ids: List[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.lifecycle == MissionLifecycle.ACTIVE

    def complete(self, cycle: int) -> None:
        self.lifecycle = MissionLifecycle.COMPLETED
        self.completion_cycle = cycle

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "lifecycle": self.lifecycle.value,
            "priority": self.priority,
            "urgency": self.urgency,
            "core_alignment": self.identity_core_alignment,
            "project_count": len(self.project_ids),
        }


class MissionPortfolio:
    """Manages all missions. Generates new ones from identity."""

    def __init__(self):
        self._missions: Dict[str, Mission] = {}
        self._generation_count: int = 0

    def create_mission(self, name: str, description: str, cycle: int,
                       priority: float = 0.5, urgency: float = 0.0,
                       core_alignment: float = 1.0) -> Mission:
        mid = f"mission_{int(time.time() * 1000)}_{self._generation_count}"
        self._generation_count += 1
        m = Mission(
            id=mid, name=name, description=description,
            lifecycle=MissionLifecycle.ACTIVE, birth_cycle=cycle,
            priority=priority, urgency=urgency,
            identity_core_alignment=core_alignment,
        )
        self._missions[mid] = m
        logger.info(f"Mission: created '{name}' ({mid})")
        return m

    def get(self, mission_id: str) -> Optional[Mission]:
        return self._missions.get(mission_id)

    def active_missions(self) -> List[Mission]:
        return [m for m in self._missions.values() if m.is_active]

    def all_missions(self) -> List[Mission]:
        return list(self._missions.values())

    def generate_missions_from_narrative(self, narrative_role: str,
                                          cycle: int) -> List[Mission]:
        """Identity Narrative -> generates candidate missions."""
        candidates = []
        if "mathematician" in narrative_role.lower() or "researcher" in narrative_role.lower():
            candidates.append(self.create_mission(
                "advance_knowledge", "Discover and formalize new knowledge",
                cycle, priority=0.8, core_alignment=1.0,
            ))
        if "explorer" in narrative_role.lower() or "agent" in narrative_role.lower():
            candidates.append(self.create_mission(
                "explore_environment", "Map and understand the environment",
                cycle, priority=0.5, core_alignment=0.8,
            ))
        if "teacher" in narrative_role.lower() or "mentor" in narrative_role.lower():
            candidates.append(self.create_mission(
                "share_knowledge", "Communicate findings to others",
                cycle, priority=0.4, core_alignment=0.9,
            ))
        return candidates

    def to_dict(self) -> Dict:
        return {
            "total": len(self._missions),
            "active": len(self.active_missions()),
            "missions": {mid: m.to_dict() for mid, m in self._missions.items()},
        }
