"""
MD-App DomainAdapter v2 — Maps MealDrama app state into TELOS's World model.

Supports diet profiles (vegetarian, eggetarian, non-veg, vegan, jain),
regional cuisines (North Indian, South Indian, Italian, Mexican, etc.),
and meal discovery scoring.
"""

from typing import Dict, List, Optional, Any
import numpy as np

from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR
from telos.adapters.meal_library import (
    MEAL_LIBRARY, DIET_TYPES, REGIONS, SLOTS,
    get_dishes, diet_tag, compute_diet_compatibility,
    compute_search_quality, compute_region_diversity,
)

STATE_DIM = 14
GOAL_STATE = np.array([1.0, 1.0, 1.0, 1.0, 0.8, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])


def _extract_features(
    tray_library: Dict[str, List[Any]],
    plan_days: Dict[str, Any],
    pantry_staples: List[str],
    health_goal: Optional[str] = None,
    cook_contact: Optional[str] = None,
    planned_slots: Optional[List[str]] = None,
    diet_profile: Optional[str] = None,
    preferred_regions: Optional[List[str]] = None,
) -> np.ndarray:
    total_meals = sum(
        len(day.get("breakfast", []) + day.get("lunch", []) + day.get("dinner", []) + day.get("snacks", []))
        for day in plan_days.values()
    ) if plan_days else 0

    total_tray = sum(len(v) for v in (tray_library or {}).values())

    slots = planned_slots or ["Breakfast", "Lunch", "Dinner"]
    dishes_per_slot = [len((tray_library or {}).get(s.lower(), [])) for s in slots]
    filled_slots = sum(1 for c in dishes_per_slot if c > 0)
    slot_diversity = filled_slots / max(len(slots), 1)

    ingredient_coverage = 0.5
    if pantry_staples and total_meals > 0:
        ingredient_coverage = min(1.0, len(pantry_staples) / max(total_meals * 3, 1))

    is_healthy = 1.0 if health_goal else 0.0
    has_cook = 1.0 if cook_contact else 0.0
    completion = min(1.0, total_meals / max(len(slots) * 7, 1)) if total_meals > 0 else 0.0
    diet_profile_str = diet_profile or "vegetarian"

    diet_compat = compute_diet_compatibility(tray_library, diet_profile_str)
    search_quality = compute_search_quality(tray_library, diet_profile_str)
    region_div = compute_region_diversity(tray_library)

    dishes_per_slot_normalized = min(total_tray / 15, 1.0)

    return np.array([
        min(total_meals / 20, 1.0),
        dishes_per_slot_normalized,
        min(len(pantry_staples or []) / 10, 1.0),
        ingredient_coverage,
        0.5,
        completion * 7,
        is_healthy,
        has_cook,
        completion,
        slot_diversity,
        diet_compat,
        search_quality,
        region_div,
        1.0 if preferred_regions else 0.0,
    ], dtype=float)


def suggest_next_dishes(tray_library: Dict[str, List], diet: str,
                         preferred_regions: Optional[List[str]] = None,
                         count: int = 5) -> List[Dict]:
    diet_key = diet_tag(diet)

    tray_ids = set()
    for dishes in tray_library.values():
        for d in dishes:
            dish_id = d["id"] if isinstance(d, dict) else d
            tray_ids.add(dish_id)

    candidates = [d for d in MEAL_LIBRARY if d["id"] not in tray_ids and diet_key in d["diet"]]
    if preferred_regions:
        region_candidates = [d for d in candidates if d["region"] in preferred_regions]
        if region_candidates:
            candidates = region_candidates + [d for d in candidates if d not in region_candidates]

    return candidates[:count]


class MealDramaSim(DomainSimulator):
    def __init__(
        self,
        tray_library: Optional[Dict[str, List[Any]]] = None,
        plan_days: Optional[Dict[str, Any]] = None,
        pantry_staples: Optional[List[str]] = None,
        health_goal: Optional[str] = None,
        cook_contact: Optional[str] = None,
        planned_slots: Optional[List[str]] = None,
        diet_profile: Optional[str] = None,
        preferred_regions: Optional[List[str]] = None,
    ):
        self.tray_library = tray_library or {}
        self.plan_days = plan_days or {}
        self.pantry_staples = pantry_staples or []
        self.health_goal = health_goal
        self.cook_contact = cook_contact
        self.planned_slots = planned_slots or ["Breakfast", "Lunch", "Dinner"]
        self.diet_profile = diet_profile or "vegetarian"
        self.preferred_regions = preferred_regions

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        return [
            np.array([0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
            np.array([0, 0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
            np.array([0, 0, 0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
            np.array([0, 0, 0, 0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
            np.array([0, 0, 0, 0, 0, 0.1, 0, 0, 0, 0, 0, 0, 0, 0]),
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 0.1, 0, 0, 0, 0, 0]),
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.1, 0, 0, 0]),
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.1, 0, 0]),
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.1, 0]),
        ]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        return np.clip(state + action, 0.0, 1.0)

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        futures = []
        s = state.copy()
        for _ in range(horizon):
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
                "diet_compatibility": float(state[10]),
                "search_quality": float(state[11]),
                "region_diversity": float(state[12]),
            },
            metadata={
                "health_goal": self.health_goal or "none",
                "has_cook": bool(self.cook_contact),
                "planned_slots": self.planned_slots,
                "diet_profile": self.diet_profile,
                "preferred_regions": self.preferred_regions or [],
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
                "diet_match": float(state[10]),
                "discoverability": float(state[11]),
            },
            risks=float(1.0 - min(state[3], state[10])),
        )


class MealDramaAdpt(DomainAdapter):
    def forward(self, x: Any) -> Any:
        return x

    def inverse(self, x: Any) -> Any:
        return x

    def intent_to_action(self, intent: IntentIR, state: np.ndarray,
                          mission_dir: np.ndarray) -> np.ndarray:
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        diff = GOAL_STATE[:len(state)] - state
        return np.sign(diff + np.random.randn(len(state)) * 0.1).astype(float) * 0.1

    @property
    def name(self) -> str:
        return "mealdrama"
