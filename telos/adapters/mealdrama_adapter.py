"""
MD-App DomainAdapter — Maps MealDrama app state into TELOS's World model.

Allows TELOS to reason about the MealDrama meal-planning app as a domain:
  - Perceive: tray state, meal plans, pantry ingredients, health scores
  - Simulate: "what if the user adds more dishes?" or "what if a meal is swapped?"
  - Evaluate: plate balance, variety score, ingredient coverage
  - Council: detect stale plans, missing ingredients, unhealthy rotations

Usage:
    from telos.adapters.mealdrama_adapter import MealDramaSim, MealDramaAdpt
    sim = MealDramaSim(tray_library, plan_days, pantry_staples)
    pipeline = TelosV14Pipeline(PipelineConfig(simulator=sim, adapter=MealDramaAdpt()))
"""

from typing import Dict, List, Optional, Any
import numpy as np
import json
import os

from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR

# Feature dimensions for the state vector
# [0]: num_planned_meals (total meals in plan)
# [1]: num_tray_dishes (total dishes in tray library)
# [2]: diet_variety_score (0-1, how many different categories covered)
# [3]: ingredient_coverage (0-1, pantry vs needed ratio)
# [4]: plate_balance_score (0-1, average health score)
# [5]: days_remaining (plan horizon)
# [6]: is_healthy_goal_set (0 or 1)
# [7]: cook_assigned (0 or 1)
# [8]: plan_completion_pct (0-1)
# [9]: slot_diversity (0-1, unique dishes per slot)

STATE_DIM = 10
GOAL_STATE = np.array([1.0, 1.0, 1.0, 1.0, 0.8, 0.5, 1.0, 1.0, 1.0, 1.0])


def _extract_features(
    tray_library: Dict[str, List[Any]],
    plan_days: Dict[str, Any],
    pantry_staples: List[str],
    health_goal: Optional[str] = None,
    cook_contact: Optional[str] = None,
    planned_slots: Optional[List[str]] = None,
) -> np.ndarray:
    """Convert MD-App state into a normalized feature vector."""
    total_meals = sum(
        len(day.get("breakfast", []) + day.get("lunch", []) + day.get("dinner", []) + day.get("snacks", []))
        for day in plan_days.values()
    ) if plan_days else 0

    total_tray = sum(len(v) for v in (tray_library or {}).values())

    slots = planned_slots or ["Breakfast", "Lunch", "Dinner"]
    dishes_per_slot = [len((tray_library or {}).get(s.lower(), [])) for s in slots]
    filled_slots = sum(1 for c in dishes_per_slot if c > 0)
    slot_diversity = filled_slots / max(len(slots), 1)

    ingredient_coverage = 0.5  # default mid-range
    if pantry_staples and total_meals > 0:
        ingredient_coverage = min(1.0, len(pantry_staples) / max(total_meals * 3, 1))

    is_healthy = 1.0 if health_goal else 0.0
    has_cook = 1.0 if cook_contact else 0.0
    completion = min(1.0, total_meals / max(len(slots) * 7, 1)) if total_meals > 0 else 0.0

    return np.array([
        min(total_meals / 20, 1.0),
        min(total_tray / 15, 1.0),
        min(len(pantry_staples or []) / 10, 1.0),
        ingredient_coverage,
        0.5,  # plate_balance — external input needed
        completion * 7,  # days_remaining proxy
        is_healthy,
        has_cook,
        completion,
        slot_diversity,
    ], dtype=float)


class MealDramaSim(DomainSimulator):
    """Simulates MealDrama app state for TELOS reasoning.

    Accepts snapshots of the MD-App state and provides:
      - legal_transitions: what actions TELOS can propose
      - simulate: counterfactual futures after adding/removing meals
      - evaluate: score the quality of the current meal plan
    """

    def __init__(
        self,
        tray_library: Optional[Dict[str, List[Any]]] = None,
        plan_days: Optional[Dict[str, Any]] = None,
        pantry_staples: Optional[List[str]] = None,
        health_goal: Optional[str] = None,
        cook_contact: Optional[str] = None,
        planned_slots: Optional[List[str]] = None,
    ):
        self.tray_library = tray_library or {}
        self.plan_days = plan_days or {}
        self.pantry_staples = pantry_staples or []
        self.health_goal = health_goal
        self.cook_contact = cook_contact
        self.planned_slots = planned_slots or ["Breakfast", "Lunch", "Dinner"]

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        """Possible 'moves' in MD-App space: add dish, swap meal, extend plan, etc."""
        actions = [
            np.array([0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0]),  # add dish to tray
            np.array([0, 0.1, 0, 0, 0, 0, 0, 0, 0, 0]),  # add variety
            np.array([0, 0, 0.1, 0, 0, 0, 0, 0, 0, 0]),  # improve pantry
            np.array([0, 0, 0, 0.1, 0, 0, 0, 0, 0, 0]),  # improve plate balance
            np.array([0, 0, 0, 0, 0, 0.1, 0, 0, 0, 0]),  # extend plan
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 0.1, 0]),  # fill empty slots
        ]
        return actions

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        return np.clip(state + action, 0.0, 1.0)

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        futures = []
        s = state.copy()
        from telos.core.simulation import CounterfactualEngine
        for _ in range(horizon):
            # Apply a random legal transition
            actions = self.legal_transitions(s)
            chosen = actions[int(np.random.randint(len(actions)))]
            s = self.transition(s, chosen)
            futures.append(World(state=s.copy(), metadata={"simulated": True}))
        return futures

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        return DomainFacts(
            state=state.copy(),
            resources={
                "meal_count": float(state[0]),
                "tray_size": float(state[1]),
                "pantry_coverage": float(state[3]),
            },
            constraints=[],
            events=[],
            metrics={
                "plan_completion": float(state[8]),
                "slot_diversity": float(state[9]),
                "plate_balance": float(state[4]),
            },
            metadata={
                "health_goal": self.health_goal or "none",
                "has_cook": bool(self.cook_contact),
                "planned_slots": self.planned_slots,
            },
        )

    def terminal(self, state: np.ndarray) -> bool:
        return bool(np.linalg.norm(GOAL_STATE - state[:len(GOAL_STATE)]) < 0.3)

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        dist = np.linalg.norm(GOAL_STATE - state[:len(GOAL_STATE)])
        return EvaluationReport(
            objectives={
                "plan_quality": float(1.0 - dist / len(GOAL_STATE)),
                "completion": float(state[8]),
                "diversity": float(state[9]),
            },
            risks=float(1.0 - state[3]),  # risk = low pantry coverage
        )


class MealDramaAdpt(DomainAdapter):
    """Converts TELOS intents into MD-App actions."""

    def forward(self, x: Any) -> Any:
        return x

    def inverse(self, x: Any) -> Any:
        return x

    def intent_to_action(self, intent: IntentIR, state: np.ndarray,
                          mission_dir: np.ndarray) -> np.ndarray:
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        # Default: move toward goal state
        diff = GOAL_STATE[:len(state)] - state
        return np.sign(diff + np.random.randn(len(state)) * 0.1).astype(float) * 0.1

    @property
    def name(self) -> str:
        return "mealdrama"
