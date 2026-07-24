"""
PlanningHorizon — Persistent sequence of IntentIR tasks.
"""
from __future__ import annotations
from typing import List, Optional
from telos.intent_ir import IntentIR

class PlanningHorizon:
    """State machine for persistent sequence of intents."""
    def __init__(self):
        self.plan: List[IntentIR] = []
        self._current_index = 0

    def set_plan(self, plan: List[IntentIR]):
        self.plan = plan
        self._current_index = 0

    def get_next_step(self) -> Optional[IntentIR]:
        if self._current_index < len(self.plan):
            step = self.plan[self._current_index]
            self._current_index += 1
            return step
        return None

    @property
    def has_plan(self) -> bool:
        return len(self.plan) > 0 and self._current_index < len(self.plan)
