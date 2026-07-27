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
    method_ids: List[str] = field(default_factory=list)

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

    def spawn_project(self, mission_id: str, project_portfolio,
                      name: str, cycle: int) -> Optional[object]:
        """Mission -> spawns a Project. Connects Layer 3 to Layer 4."""
        mission = self._missions.get(mission_id)
        if not mission or not mission.is_active:
            return None
        project = project_portfolio.create_project(
            project_id=f"proj_{mission_id}_{len(mission.project_ids)}",
            name=name, mission_id=mission_id, cycle=cycle,
        )
        mission.project_ids.append(project.id)
        logger.info(f"Mission '{mission.name}' spawned project '{name}'")
        return project

    def get_project_discoveries(self, mission_id: str,
                                 project_portfolio) -> List[Dict]:
        """Mission Ecology: share discoveries across sibling projects."""
        mission = self._missions.get(mission_id)
        if not mission:
            return []
        results = []
        for pid in mission.project_ids:
            proj = getattr(project_portfolio, '_projects', {}).get(pid)
            if proj:
                for note in proj.notebooks:
                    if note.entry_type in ("insight", "discovery", "finding"):
                        results.append({
                            "project_id": pid,
                            "project_name": proj.name,
                            "cycle": note.cycle,
                            "content": note.content,
                            "type": note.entry_type,
                        })
        return results

    def generate_missions_from_narrative(self, narrative_role: str,
                                          cycle: int,
                                          identity_markers: Optional[set] = None,
                                          curiosity_level: float = 0.0) -> List[Mission]:
        """Identity Narrative + markers -> generates candidate missions.

        Uses a weighted generative model combining role, markers, and curiosity.
        Far beyond 3 if-statements — scores each candidate mission type.
        """
        markers = identity_markers or set()
        candidates = []

        mission_templates = [
            ("advance_knowledge", "Discover and formalize new knowledge", 0.8, 1.0,
             ["mathematician", "researcher", "analyst"],
             ["curious", "scholarly", "analytical"]),
            ("explore_environment", "Map and understand the environment", 0.5, 0.8,
             ["explorer", "agent", "pioneer"],
             ["curious", "bold", "adventurous"]),
            ("share_knowledge", "Communicate findings to others", 0.4, 0.9,
             ["teacher", "mentor", "communicator"],
             ["helpful", "collaborative", "generous"]),
            ("optimize_systems", "Improve existing processes and efficiency", 0.6, 0.7,
             ["engineer", "analyst", "optimizer"],
             ["efficient", "precise", "systematic"]),
            ("build_resilience", "Strengthen the system against failure", 0.5, 0.9,
             ["guardian", "protector", "steward"],
             ["cautious", "careful", "resilient"]),
            ("generate_curiosity", "Follow intrinsic curiosity to explore unknowns", 0.7, 1.0,
             ["agent", "explorer", "scientist"],
             ["curious", "questioning", "uncertain"]),
        ]

        for name, desc, priority, alignment, roles, marker_keywords in mission_templates:
            role_score = 1.0 if any(r in narrative_role.lower() for r in roles) else 0.3
            marker_score = 1.0 if any(m.lower() in markers for m in marker_keywords) else 0.2
            curiosity_boost = 0.3 if "curious" in marker_keywords and curiosity_level > 0.5 else 0.0
            total_score = role_score * 0.4 + marker_score * 0.3 + curiosity_boost

            if total_score > 0.4:
                candidates.append(self.create_mission(
                    name, desc, cycle,
                    priority=priority * total_score,
                    core_alignment=alignment * total_score,
                ))

        return candidates[:4] if len(candidates) > 4 else candidates

    def to_dict(self) -> Dict:
        return {
            "total": len(self._missions),
            "active": len(self.active_missions()),
            "missions": {mid: m.to_dict() for mid, m in self._missions.items()},
        }
