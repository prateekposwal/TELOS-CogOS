"""Project Substrate — Identity → Mission → Project → Decision → Action.

A project owns hypotheses, theories, notebooks, failures, dead ends,
collaborators, representations, history, and unfinished questions.

All cognitive processes (TheoryBuilder, Curiosity, Counterfactual, Memory,
UnknownUnknown) operate INSIDE a project context.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from telos.core.curiosity.drive import CuriosityDrive
    from telos.core.reasoning.theory_builder import TheoryBuilder
    from telos.core.curiosity.unknown_unknown_detector import UnknownUnknownDetector
    from telos.core.reasoning.model_competition import ModelCompetition
    from telos.core.memory.regret_memory import RegretMemory

logger = logging.getLogger('telos_project')


class ProjectLifecycle(str, Enum):
    BIRTH = "birth"
    ACTIVE = "active"
    STALLED = "stalled"
    ARCHIVED = "archived"
    TERMINATED = "terminated"


@dataclass
class NotebookEntry:
    cycle: int
    content: str
    entry_type: str  # hypothesis, dead_end, insight, failure, reflection


@dataclass
class Project:
    id: str
    name: str
    mission_id: str
    parent_project_id: Optional[str] = None
    description: str = ""
    value: float = 0.5
    lifecycle: ProjectLifecycle = ProjectLifecycle.BIRTH
    birth_cycle: int = 0
    last_active_cycle: int = 0
    stagnation_cycles: int = 0
    notebooks: List[NotebookEntry] = field(default_factory=list)
    curiosity_drive: Any = None
    theory_builder: Any = None
    unknown_unknown_detector: Any = None
    model_competition: Any = None
    regret_memory: Any = None

    def set_cognitive_context(self, pipeline) -> None:
        """Wire all cognitive processes into this project context.
            Args:
                pipeline: the pipeline argument for this call.
        """
        self.curiosity_drive = getattr(pipeline, '_curiosity_drive', None)
        self.theory_builder = getattr(pipeline, '_theory_builder', None)
        self.unknown_unknown_detector = getattr(pipeline, '_unknown_unknown_detector', None)
        self.model_competition = getattr(pipeline, '_model_competition', None)
        self.regret_memory = getattr(pipeline, '_regret_memory', None)

    def add_note(self, cycle: int, content: str,
                 entry_type: str = "reflection") -> None:
        self.notebooks.append(NotebookEntry(
            cycle=cycle, content=content, entry_type=entry_type,
        ))

    @property
    def age_cycles(self) -> int:
        return max(0, self.last_active_cycle - self.birth_cycle)

    @property
    def is_active(self) -> bool:
        return self.lifecycle == ProjectLifecycle.ACTIVE

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "mission_id": self.mission_id,
            "lifecycle": self.lifecycle.value,
            "value": self.value,
            "age_cycles": self.age_cycles,
            "stagnation_cycles": self.stagnation_cycles,
            "notebook_entries": len(self.notebooks),
        }


class ProjectPortfolio:
    """Manages a portfolio of active/staged/archived projects."""

    def __init__(self):
        self._projects: Dict[str, Project] = {}
        self._active_project_id: Optional[str] = None

    def create_project(self, project_id: str, name: str, mission_id: str,
                       cycle: int, description: str = "",
                       value: float = 0.5) -> Project:
        p = Project(
            id=project_id, name=name, mission_id=mission_id,
            description=description, value=value,
            lifecycle=ProjectLifecycle.BIRTH,
            birth_cycle=cycle, last_active_cycle=cycle,
        )
        self._projects[project_id] = p
        if self._active_project_id is None:
            self._active_project_id = project_id
        logger.info(f"ProjectPortfolio: created '{name}' ({project_id})")
        return p

    def activate(self, project_id: str, cycle: int) -> bool:
        if project_id not in self._projects:
            return False
        p = self._projects[project_id]
        if p.lifecycle in (ProjectLifecycle.ARCHIVED, ProjectLifecycle.TERMINATED):
            return False
        p.lifecycle = ProjectLifecycle.ACTIVE
        p.last_active_cycle = cycle
        self._active_project_id = project_id
        return True

    def set_lifecycle(self, project_id: str, lifecycle: ProjectLifecycle,
                      cycle: int) -> bool:
        if project_id not in self._projects:
            return False
        p = self._projects[project_id]
        p.lifecycle = lifecycle
        if lifecycle == ProjectLifecycle.ACTIVE:
            p.last_active_cycle = cycle
        logger.info(f"ProjectPortfolio: '{p.name}' → {lifecycle.value}")
        return True



    @property
    def active_project(self) -> Optional[Project]:
        if self._active_project_id is None:
            return None
        p = self._projects.get(self._active_project_id)
        if p is not None and p.is_active:
            return p
        return None

    @property
    def active_projects(self) -> List[Project]:
        return [p for p in self._projects.values() if p.is_active]

    @property
    def project_count(self) -> int:
        return len(self._projects)

    def to_dict(self) -> Dict:
        return {
            "total_projects": self.project_count,
            "active_projects": len(self.active_projects),
            "active_project_id": self._active_project_id,
            "projects": {pid: p.to_dict() for pid, p in self._projects.items()},
        }
