"""Strategic Coherence — does today's action increase P(solve | project)?

Question: Does today's action increase the probability of eventually solving
my highest-value project?

Not: Does today's action maximize utility?
That is the key distinction.
"""

from __future__ import annotations
import math
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger('telos_strategic_coherence')


@dataclass
class CoherenceScore:
    score: float
    action_type: str
    project_id: str
    contribution: str  # direct, exploratory, irrelevant, counterproductive


class StrategicCoherence:
    """Evaluates how an action contributes to project-level goals."""

    def __init__(self):
        self._history: List[Dict] = []
        self._max_history = 200

    def evaluate(self, action_type: str, project_id: str,
                 project_value: float, project_stagnation: int) -> CoherenceScore:
        """Score how well an action serves its project.

        High coherence when:
        - The action directly advances the project (e.g., testing a hypothesis)
        - The project is valuable and not yet stagnant
        - The action explores a new method for a stagnant project

        Low coherence when:
        - The action is irrelevant to the active project
        - The project is already terminated
        - The action repeats a failed method on a stagnant project
        Args:
            action_type: the action_type argument for this call.
            project_id: the project_id argument for this call.
            project_value: the project_value argument for this call.
            project_stagnation: the project_stagnation argument for this call.
        """
        project_dead = project_value <= 0.0

        if action_type in ("propose_theory", "propose_hypothesis", "test_hypothesis"):
            contribution = "direct"
            base = 0.9
        elif action_type in ("curiosity_explore", "inquiry_explore"):
            contribution = "exploratory"
            base = 0.7 if project_stagnation > 5 else 0.4
        elif action_type in ("reflex", "plan_trajectory", "navigate"):
            contribution = "direct" if project_value > 0.3 else "irrelevant"
            base = 0.6 if project_value > 0.3 else 0.2
        elif action_type in ("memory_recall", "memory_miss"):
            contribution = "exploratory"
            base = 0.5
        else:
            contribution = "irrelevant"
            base = 0.3

        if project_dead:
            contribution = "counterproductive"
            base = 0.0

        coherence = base * min(1.0, project_value + 0.2)

        result = CoherenceScore(
            score=coherence,
            action_type=action_type,
            project_id=project_id,
            contribution=contribution,
        )
        self._history.append({
            "cycle": len(self._history),
            "project_id": project_id,
            "action_type": action_type,
            "coherence": coherence,
            "contribution": contribution,
        })
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return result

