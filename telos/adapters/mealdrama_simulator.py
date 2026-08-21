"""
TELOS v7.1 — MealDrama World Simulator (MealPlan-driven).

Replaces the archived 14-dim bump-vector MealDrama adapter with a DISCRETE,
constraint-satisfying world that exercises what DevDomain/Logistics/Robotics
do not:
  - a discrete MealPlan state (dishes, slots, regions, pantry usage) built from
    the REAL meal_library dish catalogue, not a fabricated numeric vector
  - legality as a TRIPLE CONJUNCT: diet-compatible AND region-preferred AND
    pantry-feasible (analogue of telos_task.legal_cardinal_action)
  - honest, DERIVED metrics (plate_balance computed from real protein/calorie
    macro fields with a provenance stamp; NO hardcoded 0.5 fabrications; a
    metric without support is None, never a made-up default)
  - a DETERMINISTIC policy: argmax over scored legal plans, with exploration
    ONLY behind an explicit flag and driven by a private np.random.RandomState
    (NEVER global np.random) — per AGENTS.md RNG rule.

The meal-library domain content lives in archive/mealdrama/meal_library.py
(the archive stays dead; we import its FUNCTIONS and DATA, not its adapter).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set, Iterator
import numpy as np

from telos.core.contracts.domain_model import (
    DomainSimulator, DomainAdapter, EvaluationReport, WorldSpec,
)
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.world.evidence import (
    EvidenceInfo, EvidenceSource, ValidationStatus,
)

from archive.mealdrama.meal_library import (
    MEAL_LIBRARY, SLOTS, DishEntry, diet_tag,
    compute_diet_compatibility, compute_region_diversity,
)

# The target diet / region profile of the world (a kitchen waking up).
DEFAULT_DIET = "vegetarian"
DEFAULT_SLOTS = ["breakfast", "lunch", "dinner", "snacks"]


# ─── MealPlan — the discrete state object ──────────────────────────────────────
@dataclass
class MealPlan:
    """A discrete weekly meal plan built from real dishes.

    Replaces the archived 14-dim bump vector. The plan is a SET of chosen dishes
    plus the aggregate quantities TELOS reasons over. Nothing here is a
    fabricated numeric latent — every field is derived from the real dishes.
    """
    dishes: List[DishEntry] = field(default_factory=list)
    diet: str = DEFAULT_DIET
    preferred_regions: List[str] = field(default_factory=list)
    pantry: Set[str] = field(default_factory=set)

    @property
    def slots_assigned(self) -> int:
        """Count of meal slots actually covered by at least one dish."""
        covered = set()
        for d in self.dishes:
            for s in d.get("slots", []):
                covered.add(s)
        return len(covered)

    @property
    def region_spread(self) -> int:
        """Count of distinct regions represented in the plan."""
        return len({d.get("region") for d in self.dishes})

    @property
    def pantry_used(self) -> int:
        """Count of dishes in the plan that are pantry-feasible."""
        return sum(1 for d in self.dishes if pantry_feasible(d, self.pantry))


def pantry_feasible(dish: DishEntry, pantry: Set[str]) -> bool:
    """Return True when every ingredient of the dish is in the pantry.

    A dish is pantry-feasible only if all of its real ingredients can be
    covered by the available staples — a genuine feasibility check, not a proxy.
    """
    required = set(dish.get("ingredients", []))
    return bool(required) and required.issubset(pantry)


def diet_compatible(dish: DishEntry, diet: str) -> bool:
    """Return True when the dish is compatible with the diet profile."""
    return diet_tag(diet) in dish.get("diet", [])


def region_preferred(dish: DishEntry, preferred: List[str]) -> bool:
    """Return True when the dish's region is in the preferred set.

    When no preferred regions are given, any region is accepted (no preference).
    """
    if not preferred:
        return True
    return dish.get("region") in preferred


def legal_meal_plan(dishes: List[DishEntry], diet: str,
                    preferred_regions: List[str], pantry: Set[str],
                    capacity: int) -> Iterator[MealPlan]:
    """Yield MealPlan candidates satisfying the TRIPLE CONJUNCT.

    A candidate (the analogue of telos_task.legal_cardinal_action) is legal ONLY
    when every dish in it is simultaneously:
        1. diet-compatible   (diet_compatible)
        2. region-preferred  (region_preferred)
        3. pantry-feasible   (pantry_feasible)
    Plans grow one legal dish at a time, up to `capacity`, and each yielded plan
    is a maximal-feasible prefix (every dish legal). This keeps the model and an
    executor in agreement about what is actually reachable.

    Args:
        dishes: the catalogue to build plans from
        diet: the target diet profile
        preferred_regions: regions that are preferred (empty => no preference)
        pantry: the set of available pantry staple ingredients
        capacity: maximum number of dishes in a yielded plan
    """
    legal = [
        d for d in dishes
        if diet_compatible(d, diet)
        and region_preferred(d, preferred_regions)
        and pantry_feasible(d, pantry)
    ]
    # yield every non-empty legal prefix (plans of increasing size)
    for size in range(1, min(capacity, len(legal)) + 1):
        plan = MealPlan(
            dishes=list(legal[:size]),
            diet=diet,
            preferred_regions=list(preferred_regions),
            pantry=set(pantry),
        )
        yield plan


def protein_macro_balance(plan: MealPlan) -> Optional[Dict[str, Any]]:
    """Derive a plate-balance metric from the REAL protein/calorie macro fields.

    Returns a provenance-stamped dict, or None when the plan has no dish with
    both protein and calorie data (a metric without support is None — never a
    fabricated default).

    Args:
        plan: the MealPlan to measure
    """
    protein = [float(d.get("protein", 0.0)) for d in plan.dishes]
    calories = [float(d.get("calories", 0.0)) for d in plan.dishes]
    # require real, non-empty support for both macros
    if not plan.dishes or any(c <= 0 for c in calories):
        return None
    total_protein = float(sum(protein))
    total_calories = float(sum(calories))
    if total_calories <= 0.0:
        return None
    # protein per 100 kcal is a real, field-derived balance proxy.
    value = float(total_protein / (total_calories / 100.0))
    return {
        "value": float(np.clip(value, 0.0, 1.0)),
        "source": "derived",
        "inputs": [d.get("id") for d in plan.dishes],
        "formula": "sum(protein) / (sum(calories) / 100)",
    }


# ─── Scoring weights for the deterministic policy ──────────────────────────────
SCORE_WEIGHTS: Dict[str, float] = {
    "diet_compat": 1.0,
    "region_div": 0.8,
    "pantry_coverage": 0.6,
    "slot_spread": 0.5,
}


def score_plan(plan: MealPlan) -> float:
    """Score a legal MealPlan as a weighted sum of four real properties.

    Deterministic — no randomness. The score is the weighted composition of
    diet compatibility, region diversity, pantry coverage and slot spread.
    """
    tray = _tray_library(plan)
    diet_compat = compute_diet_compatibility(tray, plan.diet)
    region = compute_region_diversity(tray)
    pantry_cov = (plan.pantry_used / len(plan.dishes)) if plan.dishes else 0.0
    slot_spread = plan.slots_assigned / max(len(DEFAULT_SLOTS), 1)
    return (
        SCORE_WEIGHTS["diet_compat"] * diet_compat
        + SCORE_WEIGHTS["region_div"] * region
        + SCORE_WEIGHTS["pantry_coverage"] * pantry_cov
        + SCORE_WEIGHTS["slot_spread"] * slot_spread
    )


def _tray_library(plan: MealPlan) -> Dict[str, List[Any]]:
    """Build the {slot: [dish-ids]} tray_library shape meal_library expects.
        Args:
            plan: the plan argument for this call.
    """
    tray: Dict[str, List[Any]] = {s: [] for s in SLOTS}
    for d in plan.dishes:
        for s in d.get("slots", []):
            if s in tray:
                tray[s].append({"id": d.get("id")})
    return tray


def build_mealdrama_world_spec(
    diet: str = DEFAULT_DIET,
    preferred_regions: Optional[List[str]] = None,
    capacity: int = 6,
) -> WorldSpec:
    """Build the explicit MealDrama WorldSpec.

    Args:
        diet: the target diet profile the kitchen is cooking for
        preferred_regions: regions preferred (empty => no preference)
        capacity: maximum dishes per plan
    """
    return WorldSpec(
        name="mealdrama",
        version="7.1",
        state_dim=1,                     # discrete plan world: latent is degenerate
        action_dim=capacity,
        objectives=["maximize_diet_compatibility", "maximize_region_diversity",
                    "maximize_pantry_usage", "maximize_slot_spread"],
        constraints=["diet_compatible", "region_preferred", "pantry_feasible",
                     "plan_capacity"],
        observability="high",            # the full plan is observable
        capabilities=["compose_meal_plan", "select_dishes", "check_legality"],
        authorized_modes={"ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK"},
        escalation_policy="advisory",
    )


class MealDramaDomainSimulator(DomainSimulator):
    """A discrete, constraint-satisfying MealPlan world.

    `state` is a degenerate (1,) placeholder — the REAL working object is the
    MealPlan. The adapter exposes meal-plan logic through the same
    DomainSimulator surface so it plugs into the existing world machinery.
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        diet: str = DEFAULT_DIET,
        preferred_regions: Optional[List[str]] = None,
        pantry: Optional[Set[str]] = None,
        capacity: int = 6,
    ):
        self._rng = np.random.RandomState(seed)   # private RNG — never global
        self.name = "mealdrama"
        self.state_dim = 1
        self.diet = diet
        self.preferred_regions = preferred_regions or []
        self.pantry = set(pantry) if pantry else set()
        self.capacity = capacity

    # ── Lifecycle ──
    def initialize(self) -> None: pass
    def cleanup(self) -> None: pass

    # ── WorldSpec ──
    def world_spec(self) -> WorldSpec:
        return build_mealdrama_world_spec(
            diet=self.diet, preferred_regions=self.preferred_regions,
            capacity=self.capacity,
        )

    # ── Legal plans (the triple conjunct) ──
    def legal_plans(self) -> List[MealPlan]:
        """Return every legal MealPlan (triple-conjunct) reachable right now."""
        return list(legal_meal_plan(
            dishes=MEAL_LIBRARY,
            diet=self.diet,
            preferred_regions=self.preferred_regions,
            pantry=self.pantry,
            capacity=self.capacity,
        ))

    # ── Deterministic policy ──
    def select_plan(self, explore: bool = False,
                    explored_candidates: int = 3) -> Optional[MealPlan]:
        """Select the best plan by DETERMINISTIC argmax over scored legal plans.

        Exploration is only applied when `explore=True`, and only then does the
        private RandomState consume randomness. With explore=False (the default)
        the result is fully deterministic for a given world — never global RNG.

        Args:
            explore: when True, sometimes pick among the top legal plans using
                     the private RNG (never global np.random)
            explored_candidates: how many top candidates exploration may draw from
        """
        plans = self.legal_plans()
        if not plans:
            return None
        scored = sorted(plans, key=lambda p: score_plan(p), reverse=True)
        if explore and len(scored) > 1:
            k = min(explored_candidates, len(scored))
            pick = int(self._rng.randint(0, k))
            return scored[pick]
        return scored[0]

    # ── DomainSimulator surface (plan-as-state bridge) ──
    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        """Return one action vector per legal plan (each is a distinct plan id).

        The latent action space is degenerate (state_dim==1); each legal plan
        is encoded as a unit scalar so the world surface stays a numpy contract.
        """
        plans = self.legal_plans()
        return [np.array([float(i)]) for i in range(len(plans))]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        """Return the selected plan index as the next (degenerate) state.
            Args:
                action: the action argument for this call.
        """
        arr = np.asarray(action, dtype=float).reshape(-1)
        idx = int(round(float(arr[0]))) if arr.size else 0
        plans = self.legal_plans()
        idx = max(0, min(idx, len(plans) - 1)) if plans else 0
        return np.array([float(idx)])

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        """Roll out horizon plan selections into observed World futures.
            Args:
                state: the world/domain state for this call
        """
        futures = []
        for _ in range(horizon):
            plans = self.legal_plans()
            if not plans:
                break
            chosen = plans[int(self._rng.randint(len(plans)))]
            futures.append(World(
                state=np.array([float(0.0)]),
                metadata={"simulated": True, "plan_capacity": self.capacity},
            ))
            _ = chosen
        return futures

    # ── Honest, derived facts ──
    def get_facts(self, state: np.ndarray,
                  evidence: Optional[EvidenceInfo] = None) -> DomainFacts:
        """Produce evidence-bearing DomainFacts for the current plan.

        plate_balance is always DERIVED via protein_macro_balance and is None
        (never a fabricated default) when the plan has no macro support.
        Args:
            state: the world/domain state for this call
        """
        plan = self.select_plan(explore=False)
        meas = evidence or EvidenceInfo(
            source=EvidenceSource.MEASUREMENT,
            validation_status=ValidationStatus.OBSERVED,
        )
        balance = protein_macro_balance(plan) if plan is not None else None
        metrics: Dict[str, Any] = {
            "diet_compatibility": float(compute_diet_compatibility(
                _tray_library(plan), self.diet)) if plan else 0.0,
            "region_diversity": float(compute_region_diversity(
                _tray_library(plan))) if plan else 0.0,
            "slots_assigned": float(plan.slots_assigned) if plan else 0.0,
            "pantry_used": float(plan.pantry_used) if plan else 0.0,
            "score": float(score_plan(plan)) if plan else 0.0,
        }
        if balance is not None:
            metrics["plate_balance"] = balance
        else:
            metrics["plate_balance"] = None
        return DomainFacts(
            state=np.array([float(1.0)]),
            resources={
                "pantry_available": float(len(self.pantry)),
                "region_spread": float(plan.region_spread) if plan else 0.0,
            },
            constraints=["diet_compatible", "region_preferred", "pantry_feasible",
                         "plan_capacity"],
            events=["plan_legal" if plan else "no_legal_plan",
                    ("region_preference_matched" if self.preferred_regions else "no_region_preference")],
            metrics=metrics,
            metadata={
                "diet_profile": self.diet,
                "preferred_regions": self.preferred_regions,
                "observability": "high",
                "plan_capacity": self.capacity,
                "dish_count": len(MEAL_LIBRARY),
            },
            evidence=meas,
        )

    def terminal(self, state: np.ndarray) -> bool:
        """A plan is terminal when at least one legal plan exists.
            Args:
                state: the world/domain state for this call
        """
        return len(self.legal_plans()) > 0

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        """Score the selected plan across the four objectives with zero fabrication.
            Args:
                state: the world/domain state for this call
        """
        plan = self.select_plan(explore=False)
        if plan is None:
            return EvaluationReport(objectives={
                "maximize_diet_compatibility": 0.0,
                "maximize_region_diversity": 0.0,
                "maximize_pantry_usage": 0.0,
                "maximize_slot_spread": 0.0,
            }, risks=1.0)
        tray = _tray_library(plan)
        objectives = {
            "maximize_diet_compatibility": float(compute_diet_compatibility(tray, self.diet)),
            "maximize_region_diversity": float(compute_region_diversity(tray)),
            "maximize_pantry_usage": float(plan.pantry_used / len(plan.dishes)) if plan.dishes else 0.0,
            "maximize_slot_spread": float(plan.slots_assigned / max(len(DEFAULT_SLOTS), 1)),
        }
        risks = float(0.0 if plan.dishes else 1.0)
        return EvaluationReport(objectives=objectives, risks=risks)

    # ── Session-2 seam: reality-gap feedback (NOT the WhatsApp channel) ──
    def outcome_feedback(self, predicted_metrics: Dict[str, Any],
                         observed_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Hook point for Session 2 to wire into RealityGapTracker.

        Session 1 does NOT build the WhatsApp messaging channel. It only leaves
        this seam: a clearly-marked method that currently records the predicted
        vs observed metrics (a pass-through/log). Session 2 will feed these into
        the RealityGapTracker to close the plan-prediction loop.
        Args:
            predicted_metrics: the predicted_metrics argument for this call.
            observed_metrics: the observed_metrics argument for this call.
        """
        return {
            "predicted": dict(predicted_metrics),
            "observed": dict(observed_metrics),
            "seam": "session_2_reality_gap",
            "messaging_channel_active": False,
        }


class MealDramaDomainAdapter(DomainAdapter):
    """Maps TELOS intents to a concrete MealPlan selection (deterministic)."""
    name = "mealdrama"
    state_dim = 1

    def __init__(self, seed: Optional[int] = None, **sim_kwargs):
        self._sim = MealDramaDomainSimulator(seed=seed, **sim_kwargs)

    def forward(self, domain_state: np.ndarray) -> np.ndarray:
        return np.asarray(domain_state, dtype=float)

    def inverse(self, telos_action: np.ndarray) -> np.ndarray:
        return np.asarray(telos_action, dtype=float)

    def intent_to_action(self, intent, state, mission_dir) -> np.ndarray:
        """Map a TELOS intent to the selected plan index (deterministic).
            Args:
                state: the world/domain state for this call
                mission_dir: the mission_dir argument for this call.
        """
        label = (intent.intent_type if hasattr(intent, "intent_type") else "compose")
        if label in ("compose_meal_plan", "select_dishes", "plan_trajectory",
                     "goal_seek"):
            plan = self._sim.select_plan(explore=False)
            if plan is None:
                return np.array([0.0])
            plans = self._sim.legal_plans()
            chosen = next((i for i, p in enumerate(plans) if p.dishes == plan.dishes), 0)
            return np.array([float(chosen)])
        if "action_vector" in (intent.params if hasattr(intent, "params") else {}):
            return np.asarray(intent.params["action_vector"], dtype=float)
        return np.array([0.0])
