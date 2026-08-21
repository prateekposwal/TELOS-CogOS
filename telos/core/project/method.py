"""Methods layer — Layer 5 of the Identity Cascade.

Identity Core -> Identity Narrative -> Missions -> Projects -> Methods -> Actions

Methods are explicit entities with lifecycles matching the Wiles story:
Iwasawa -> FAIL -> Galois -> SUCCESS
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger('telos_method')


class MethodLifecycle(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    FAILED = "failed"
    ABANDONED = "abandoned"
    SUCCESSFUL = "successful"


@dataclass
class Method:
    id: str
    name: str
    project_id: str
    description: str = ""
    lifecycle: MethodLifecycle = MethodLifecycle.PROPOSED
    birth_cycle: int = 0
    last_used_cycle: int = 0
    attempts: int = 0
    successes: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / max(self.attempts, 1)

    def record_attempt(self, cycle: int, succeeded: bool) -> None:
        self.attempts += 1
        self.last_used_cycle = cycle
        if succeeded:
            self.successes += 1
        if self.success_rate >= 0.7 and self.attempts >= 3:
            self.lifecycle = MethodLifecycle.SUCCESSFUL
        elif self.attempts >= 5 and self.success_rate < 0.3:
            self.lifecycle = MethodLifecycle.FAILED

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "project_id": self.project_id,
            "lifecycle": self.lifecycle.value,
            "success_rate": self.success_rate,
            "attempts": self.attempts,
        }


class MethodRegistry:
    """Registry of all methods across projects."""

    def __init__(self):
        self._methods: Dict[str, Method] = {}
        self._count: int = 0

    def register(self, name: str, project_id: str, cycle: int,
                 description: str = "") -> Method:
        mid = f"method_{int(time.time() * 1000)}_{self._count}"
        self._count += 1
        m = Method(id=mid, name=name, project_id=project_id,
                   description=description, birth_cycle=cycle,
                   lifecycle=MethodLifecycle.ACTIVE)
        self._methods[mid] = m
        logger.info(f"Method: registered '{name}' ({mid}) for project {project_id}")
        return m

    def get(self, method_id: str) -> Optional[Method]:
        return self._methods.get(method_id)


    def active_methods(self) -> List[Method]:
        return [m for m in self._methods.values()
                if m.lifecycle == MethodLifecycle.ACTIVE]

    def failed_methods(self) -> List[Method]:
        return [m for m in self._methods.values()
                if m.lifecycle == MethodLifecycle.FAILED]

    def parsimony_score(self) -> float:
        active = self.active_methods()
        if not active:
            return 0.5
        return min(1.0, sum(1.0 / (1.0 + len(m.name)) for m in active) / len(active))

    def to_dict(self) -> Dict:
        return {
            "total": len(self._methods),
            "active": len(self.active_methods()),
            "failed": len(self.failed_methods()),
            "parsimony": self.parsimony_score(),
        }
