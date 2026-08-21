"""
TELOS v7.1 — MealDrama World Validation tests (Session 1 of the v7.1 fix plan).

Property-based assertions locking the four Session-1 fixes:
  - Symptom 1 (legal transitions): a plan is legal ONLY under the triple
    conjunct diet-compatible AND region-preferred AND pantry-feasible
    (legal_meal_plan = analogue of telos_task.legal_cardinal_action).
  - Symptom 2 (honest metrics): plate_balance is DERIVED from real protein /
    calorie macro fields with a provenance stamp; a metric with no support is
    None — never a fabricated 0.5 default. No bare-0.5 plate_balance anywhere.
  - Symptom 4 (deterministic policy): argmax selection is deterministic even
    when the GLOBAL np.random state is poisoned; exploration only behind an
    explicit flag and driven by a private RandomState.
  - no-leakage / no-dead-code (import reachability).

(Symptom 3 — the WhatsApp loop — is Session 2 and is explicitly NOT built here;
 the adapter leaves the outcome_feedback seam for it.)
"""

import ast
import numpy as np

from telos.benchmarks import mealdrama_v71 as B
from telos.adapters.mealdrama_simulator import (
    MealDramaDomainSimulator, MealDramaDomainAdapter, MealPlan,
    legal_meal_plan, protein_macro_balance,
    diet_compatible, region_preferred, pantry_feasible,
)
from archive.mealdrama.meal_library import MEAL_LIBRARY, get_dishes_by_diet

FULL_PANTRY: set = set().union(*[set(d.get("ingredients", [])) for d in MEAL_LIBRARY])


# ─── no-leakage / no-dead-code ─────────────────────────────────────────────────
def test_public_surface_import_reachable():
    """The adapter's public classes + functions are genuinely importable."""
    for name in ("MealDramaDomainSimulator", "MealDramaDomainAdapter",
                 "MealPlan", "legal_meal_plan", "protein_macro_balance",
                 "score_plan"):
        assert name in dir(__import__("telos.adapters.mealdrama_simulator",
                                      fromlist=[name])), f"{name} not reachable"


def test_benchmark_tasks_all_reachable_and_pass():
    runs = B.run_benchmark()
    assert set(runs.keys()) == {"task_legal_motion", "task_honesty",
                                "task_honesty_unsupported", "task_determinism",
                                "task_reachability"}
    for tid, r in runs.items():
        assert r.passed, f"{tid} failed: {r.detail}"


def test_no_dead_archive_adapter_imported():
    """The archived 14-dim adapter must NOT be reachable from the new world."""
    txt = open("telos/adapters/mealdrama_simulator.py").read()
    assert "mealdrama_adapter" not in txt
    assert "_extract_features" not in txt


# ─── Symptom 4: determinism vs global RNG poisoning ────────────────────────────
def test_argmax_determinism_survives_global_rng_poisoning():
    """Selecting a plan must be deterministic regardless of global np.random."""
    sim = MealDramaDomainSimulator(seed=1, diet="vegetarian",
                                   preferred_regions=["north_indian"],
                                   pantry=FULL_PANTRY)
    first = sim.select_plan(explore=False)
    # poison + consume the GLOBAL RNG heavily
    np.random.seed(0)
    np.random.RandomState(1234).randn(5000)
    np.random.rand(100)
    second = sim.select_plan(explore=False)
    assert [d["id"] for d in first.dishes] == [d["id"] for d in second.dishes]


def test_exploration_uses_private_rng_not_global():
    """Exploration is seed-stable via the private RNG (same seed => same plan)."""
    a = MealDramaDomainSimulator(seed=7, diet="vegetarian", pantry=FULL_PANTRY)
    b = MealDramaDomainSimulator(seed=7, diet="vegetarian", pantry=FULL_PANTRY)
    np.random.seed(99)   # corrupt global; must NOT affect private-RNG explore
    plan_a = a.select_plan(explore=True)
    np.random.seed(77)
    plan_b = b.select_plan(explore=True)
    assert [d["id"] for d in plan_a.dishes] == [d["id"] for d in plan_b.dishes]


# ─── Symptom 2: honest, derived metrics ────────────────────────────────────────
def test_plate_balance_is_derived_with_provenance_stamp():
    sim = MealDramaDomainSimulator(seed=2, diet="vegetarian",
                                   preferred_regions=["north_indian"],
                                   pantry=FULL_PANTRY)
    plan = sim.select_plan(explore=False)
    balance = protein_macro_balance(plan)
    assert balance is not None
    assert balance["source"] == "derived"
    assert isinstance(balance["inputs"], list) and balance["inputs"]
    assert isinstance(balance["formula"], str) and "protein" in balance["formula"]
    assert isinstance(balance["value"], float)
    # derived from REAL dish protein/calorie macro fields
    assert all(any(d.get("id") == i for d in plan.dishes)
               for i in balance["inputs"])


def test_unsupported_metric_is_none_not_fabricated():
    """A plan with no calorie support has plate_balance None — never a 0.5."""
    plan = MealPlan(dishes=[{"id": "phantom", "protein": 5.0}], diet="vegetarian")
    assert protein_macro_balance(plan) is None


def test_facts_plate_balance_never_bare_05():
    """get_facts returns plate_balance only as derived-dict or None — never 0.5."""
    sim = MealDramaDomainSimulator(seed=3, diet="vegetarian",
                                   preferred_regions=["north_indian"],
                                   pantry=FULL_PANTRY)
    facts = sim.get_facts(np.array([0.0]))
    pb = facts.metrics["plate_balance"]
    assert pb is None or (isinstance(pb, dict) and pb["source"] == "derived")
    assert not isinstance(pb, float)  # a bare number is a hunting fabrication


def test_protein_macro_balance_has_no_hardcoded_05():
    """AST-level: the derivation function contains no bare 0.5 literal."""
    src = open("telos/adapters/mealdrama_simulator.py").read()
    tree = ast.parse(src)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "protein_macro_balance":
            target = node
            break
    assert target is not None
    for n in ast.walk(target):
        if isinstance(n, ast.Constant) and isinstance(n.value, float):
            assert abs(n.value - 0.5) > 1e-9, (
                "protein_macro_balance hardcodes 0.5")
        if isinstance(n, ast.Constant) and n.value == 0.5:
            raise AssertionError("protein_macro_balance hardcodes 0.5")


# ─── Symptom 1: legal transitions (triple conjunct) ────────────────────────────
def test_legal_plan_rejects_diet_violation():
    """A non-veg dish must never appear in a vegetarian legal plan."""
    dishes = get_dishes_by_diet("non_veg")
    assert dishes, "need at least one non-veg dish to test the violation"
    nv = dishes[0]
    assert diet_compatible(nv, "vegetarian") is False
    # even with full pantry + no region preference, the non-veg dish is rejected
    generator = legal_meal_plan(MEAL_LIBRARY, "vegetarian", [], FULL_PANTRY, capacity=1)
    for plan in generator:
        assert all(diet_compatible(d, "vegetarian") for d in plan.dishes)
    # and the specific non-veg dish alone is not a legal plan (empty)
    assert not list(legal_meal_plan([nv], "vegetarian", [], FULL_PANTRY, capacity=1))


def test_legal_plan_rejects_region_violation():
    """With north_indian preferred, an italian dish is never selected."""
    sim = MealDramaDomainSimulator(seed=4, diet="vegetarian",
                                   preferred_regions=["north_indian"],
                                   pantry=FULL_PANTRY)
    plan = sim.select_plan(explore=False)
    assert plan is not None and plan.dishes
    assert all(d.get("region") == "north_indian" for d in plan.dishes)
    # an italian vegetarian dish is not region-preferred
    italian = next(d for d in MEAL_LIBRARY
                   if d["region"] == "italian" and "veg" in d["diet"])
    assert region_preferred(italian, ["north_indian"]) is False
    assert region_preferred(italian, []) is True  # no preference => accepted


def test_legal_plan_rejects_pantry_violation():
    """A dish whose ingredients are NOT in the pantry is never selected."""
    # pantry with only wheat flour => a dish needing chicken is infeasible
    tiny_pantry = {"Wheat Flour"}
    chicken = next(d for d in MEAL_LIBRARY if d["id"] == "chicken-curry")
    assert pantry_feasible(chicken, tiny_pantry) is False
    assert not list(legal_meal_plan([chicken], "non_veg", [], tiny_pantry, capacity=1))


def test_legal_plan_requires_all_three_conjuncts_simultaneously():
    """Every dish of every legal plan satisfies diet AND region AND pantry."""
    sim = MealDramaDomainSimulator(seed=5, diet="vegetarian",
                                   preferred_regions=["north_indian"],
                                   pantry=FULL_PANTRY)
    for plan in sim.legal_plans():
        for d in plan.dishes:
            assert diet_compatible(d, "vegetarian")
            assert region_preferred(d, ["north_indian"])
            assert pantry_feasible(d, sim.pantry)


# ─── Session-2 seam guard ──────────────────────────────────────────────────────
def test_outcome_feedback_seam_present_but_channel_deferred():
    """The Session-2 seam exists; the WhatsApp channel is NOT built."""
    sim = MealDramaDomainSimulator(seed=6, diet="vegetarian",
                                   preferred_regions=["north_indian"],
                                   pantry=FULL_PANTRY)
    result = sim.outcome_feedback({"score": 2.0}, {"score": 1.8})
    assert result["predicted"] == {"score": 2.0}
    assert result["observed"] == {"score": 1.8}
    assert result["messaging_channel_active"] is False  # Session 2 not built
    # the adapter must not IMPLEMENT a channel: no function/method/class whose
    # name carries 'whatsapp' or 'messaging' (the seams stays a method hook).
    tree = ast.parse(open("telos/adapters/mealdrama_simulator.py").read())
    names = []
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(child.name)
    channely = [n for n in names if "whatsapp" in n.lower() or "messaging" in n.lower()]
    assert channely == [], f"adapter implements a messaging channel: {channely}"


def test_adapter_intent_to_action_deterministic():
    """The adapter maps a compose intent to the same plan index every time."""
    adapter = MealDramaDomainAdapter(seed=11, diet="vegetarian",
                                     preferred_regions=["north_indian"],
                                     pantry=FULL_PANTRY)
    intent = type("Intent", (), {"intent_type": "compose_meal_plan", "params": {}})()
    state = np.array([0.0])
    a = adapter.intent_to_action(intent, state, None)
    b = adapter.intent_to_action(intent, state, None)
    assert np.array_equal(a, b)
    assert a.shape == (1,)
