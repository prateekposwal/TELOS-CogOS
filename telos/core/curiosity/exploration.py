"""Autonomous curiosity-driven exploration — self-directed learning loop.

When curiosity is high and no external task exists, the system generates
its own exploration goals from UnknownUnknownDetector questions.
"""

from __future__ import annotations
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from telos.core.curiosity.drive import CuriosityDrive
from telos.core.curiosity.unknown_unknown_detector import UnknownUnknownDetector

logger = logging.getLogger('telos_exploration')


@dataclass
class ExplorationGoal:
    description: str
    source: str  # curiosity, unknown_unknown, theory_gap
    priority: float
    attempted: bool = False
    succeeded: bool = False


class AutonomousExplorer:
    """Generates self-directed exploration goals when idle."""

    def __init__(self, curiosity: Optional[CuriosityDrive] = None,
                 unknown_unknown: Optional[UnknownUnknownDetector] = None):
        self._curiosity = curiosity
        self._unknown_unknown = unknown_unknown
        self._goals: List[ExplorationGoal] = []
        self._max_goals = 20


    def set_unknown_unknown(self, uud: UnknownUnknownDetector) -> None:
        self._unknown_unknown = uud

    def generate_goals(self, cycle: int) -> List[ExplorationGoal]:
        """Generate exploration goals from curiosity and unknown unknowns.
            Args:
                cycle: the current cycle count
        """
        goals = []

        if self._curiosity and self._curiosity.state.curiosity_level > 0.6:
            goals.append(ExplorationGoal(
                description="explore_high_curiosity_region",
                source="curiosity",
                priority=self._curiosity.state.curiosity_level,
            ))

        if self._unknown_unknown:
            questions = self._unknown_unknown.get_unanswered_questions()
            for q in questions[:3]:
                goals.append(ExplorationGoal(
                    description=f"investigate:{getattr(q, 'question_text', 'unknown')[:50]}",
                    source="unknown_unknown",
                    priority=0.5 + getattr(q, 'residual_magnitude', 0) * 0.3,
                ))

        self._goals.extend(goals)
        if len(self._goals) > self._max_goals:
            self._goals = self._goals[-self._max_goals:]

        return goals

    @property
    def should_explore(self) -> bool:
        if self._curiosity and self._curiosity.state.curiosity_level > 0.6:
            return True
        if self._unknown_unknown and self._unknown_unknown.get_unanswered_questions():
            return True
        return False

    def to_dict(self) -> Dict:
        return {
            "has_goals": len(self._goals) > 0,
            "goal_count": len(self._goals),
            "should_explore": self.should_explore,
        }
