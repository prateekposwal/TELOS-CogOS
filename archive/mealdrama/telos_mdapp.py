"""
TELOS + MD-App v2 — Diet profiles, regional cuisines, meal discovery.

Usage:
    PYTHONPATH=. python3 telos_mdapp.py
    PYTHONPATH=. python3 telos_mdapp.py --diet eggetarian --region north_indian --region south_indian
    PYTHONPATH=. python3 telos_mdapp.py --snapshot /tmp/md_snapshot.json
"""

import numpy as np
import logging
import json
import sys
import os
import argparse

logging.basicConfig(level=logging.WARNING)

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.streams.inquiry_stream import InquiryStream
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.adapters.mealdrama_adapter import MealDramaSim, MealDramaAdpt, GOAL_STATE, suggest_next_dishes
from telos.adapters.meal_library import DIET_TYPES, REGIONS, get_dishes

DIET_LABELS = {
    "vegetarian": "🥬 Vegetarian",
    "eggetarian": "🥚 Eggetarian",
    "non_veg": "🍗 Non-Veg",
    "vegan": "🌱 Vegan",
    "jain": "🌸 Jain",
}

REGION_LABELS = {
    "north_indian": "North Indian",
    "south_indian": "South Indian",
    "italian": "Italian",
    "mexican": "Mexican",
    "east_asian": "East Asian",
    "middle_eastern": "Middle Eastern",
}

DEFAULT_SNAPSHOT = {
    "tray_library": {
        "breakfast": [{"id": "aloo-paratha", "name": "Aloo Paratha"}],
        "lunch": [{"id": "rajma-chawal", "name": "Rajma Chawal"}],
        "dinner": [{"id": "dal-makhani", "name": "Dal Makhani"}],
        "snacks": [],
    },
    "plan_days": {
        "2026-07-22": {
            "breakfast": [{"meal_id": "aloo-paratha"}],
            "lunch": [{"meal_id": "rajma-chawal"}],
            "dinner": [{"meal_id": "dal-makhani"}],
        }
    },
    "pantry_staples": ["Rice", "Dal", "Onions", "Tomatoes", "Spices", "Oil"],
    "health_goal": "balanced",
    "cook_contact": "+911234567890",
    "planned_slots": ["Breakfast", "Lunch", "Dinner", "Snacks"],
}


def load_snapshot(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    print(f"Snapshot not found at {path}, using defaults")
    return DEFAULT_SNAPSHOT


def print_state_analysis(state: np.ndarray, snapshot: dict, diet: str):
    labels = [
        ("Meal Count", f"{state[0]*100:.0f}%", "📊"),
        ("Tray Size", f"{state[1]*100:.0f}%", "🍽️"),
        ("Pantry Coverage", f"{state[3]*100:.0f}%", "🥦"),
        ("Plate Balance", f"{state[4]*100:.0f}%", "⚖️"),
        ("Plan Completion", f"{state[8]*100:.0f}%", "📅"),
        ("Slot Diversity", f"{state[9]*100:.0f}%", "🎯"),
        ("Diet Match", f"{state[10]*100:.0f}%", "✅"),
        ("Discoverability", f"{state[11]*100:.0f}%", "🔍"),
        ("Region Diversity", f"{state[12]*100:.0f}%", "🌍"),
    ]
    diet_label = DIET_LABELS.get(diet, diet)
    print(f"\n{'='*55}")
    print(f"  📋  MEAL PLAN ANALYSIS  [{diet_label}]")
    print(f"{'='*55}")
    for label, value, icon in labels:
        bar = "█" * int(float(value.strip('%')) / 10) + "░" * (10 - int(float(value.strip('%')) / 10))
        print(f"  {icon} {label:20s} {bar} {value}")
    print(f"{'='*55}")

    issues = []
    for slot in ["breakfast", "lunch", "dinner", "snacks"]:
        dishes = snapshot.get("tray_library", {}).get(slot, [])
        if len(dishes) < 2:
            issues.append(f"  {slot.capitalize():10s} has {len(dishes)} dish(es) — add more for variety")

    if state[10] < 0.6:
        issues.append(f"  Diet compatibility is low ({state[10]*100:.0f}%) — some tray dishes may not match your {diet_label} diet")

    if state[11] < 0.5:
        issues.append(f"  Low discovery score ({state[11]*100:.0f}%) — many diet-compatible dishes not in your tray yet")

    if state[12] < 0.3:
        issues.append(f"  Low region diversity — try dishes from other cuisines")

    if not snapshot.get("health_goal"):
        issues.append("  No health goal set — enable in Profile for personalized suggestions")

    if not snapshot.get("pantry_staples") or len(snapshot["pantry_staples"]) < 5:
        issues.append("  Pantry is thin — add staples for better ingredient tracking")

    if issues:
        print(f"\n🔍  ISSUES FOUND ({len(issues)})")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅  No critical issues detected.")
    print()


def suggest_for_slots(snapshot: dict, diet: str, preferred_regions: list,
                       slot: str, count: int = 3) -> list:
    tray = snapshot.get("tray_library", {})
    suggestions = suggest_next_dishes(tray, diet, preferred_regions, count=10)
    slot_suggestions = [d for d in suggestions if slot in d["slots"]]
    return slot_suggestions[:count]


def main():
    parser = argparse.ArgumentParser(description="TELOS + MealDrama")
    parser.add_argument("--snapshot", type=str, help="Path to snapshot JSON")
    parser.add_argument("--diet", type=str, default="vegetarian", choices=DIET_TYPES, help="Diet profile")
    parser.add_argument("--region", type=str, action="append", dest="regions", choices=REGIONS, help="Preferred regions")
    args = parser.parse_args()

    snapshot = load_snapshot(args.snapshot) if args.snapshot else DEFAULT_SNAPSHOT
    diet = args.diet
    preferred_regions = args.regions or []

    print(f"\n🧠 TELOS + MealDrama: Analyzing your meal plan...\n")

    sim = MealDramaSim(
        tray_library=snapshot.get("tray_library"),
        plan_days=snapshot.get("plan_days"),
        pantry_staples=snapshot.get("pantry_staples"),
        health_goal=snapshot.get("health_goal"),
        cook_contact=snapshot.get("cook_contact"),
        planned_slots=snapshot.get("planned_slots"),
        diet_profile=diet,
        preferred_regions=preferred_regions,
    )

    from telos.adapters.mealdrama_adapter import _extract_features
    state = _extract_features(
        snapshot.get("tray_library", {}),
        snapshot.get("plan_days", {}),
        snapshot.get("pantry_staples", []),
        snapshot.get("health_goal"),
        snapshot.get("cook_contact"),
        snapshot.get("planned_slots"),
        diet_profile=diet,
        preferred_regions=preferred_regions,
    )

    print_state_analysis(state, snapshot, diet)

    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=MealDramaAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=14, n_worlds=10, horizon=5,
    ))
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)
    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
    pipeline.register_stream(InquiryStream(skill_lib))
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))

    result = pipeline.execute(state, user_name="MD-App")
    trace = result.decision_trace

    if trace:
        intent = trace.selected_intent.intent_type if trace.selected_intent else "none"
        status = "APPROVED" if not (result.council_blocked or result.firewall_blocked) else "BLOCKED"
        top_futures = [round(o.get("score", 0), 3) for o in trace.strategic_options[:3]] if trace.strategic_options else []

        print("🔮  TELOS COUNCIL VERDICT")
        print(f"  Intent:       {intent}")
        print(f"  Status:       {status}")
        print(f"  DI:           {trace.decision_integrity:.3f}")
        print(f"  MD:           {trace.mission_drift:.3f}")
        print(f"  Alternatives: {len(trace.strategic_options)} futures evaluated")
        if top_futures:
            print(f"  Top scores:   {top_futures}")
        if result.council_blocked:
            print(f"  Blocked by:   {trace.blocking_validator}")

    # ── Diet-aware dish suggestions ──
    print(f"\n🍽️  SUGGESTED DISHES FOR YOUR DIET ({DIET_LABELS.get(diet, diet)})")
    if preferred_regions:
        region_names = [REGION_LABELS.get(r, r) for r in preferred_regions]
        print(f"   Preferred cuisines: {', '.join(region_names)}")

    for slot in ["breakfast", "lunch", "dinner", "snacks"]:
        suggestions = suggest_for_slots(snapshot, diet, preferred_regions, slot, count=3)
        if suggestions:
            names = [f"{d['name']} ({REGION_LABELS.get(d['region'], d['region'])})" for d in suggestions]
            print(f"\n   {slot.capitalize()}:")
            for n in names:
                print(f"     • {n}")
        else:
            print(f"\n   {slot.capitalize()}:")
            print(f"     No new suggestions — tray is well stocked!")

    print(f"\n💡  TELOS RECOMMENDATIONS")
    recs = []
    if state[10] < 0.8:
        recs.append(f"  1. Improve diet match by adding dishes compatible with your {DIET_LABELS.get(diet, diet)} profile")
    if state[11] < 0.6:
        recs.append(f"  2. Explore more dishes — many diet-compatible options not in your tray yet")
    if state[12] < 0.3:
        recs.append(f"  3. Try a new cuisine to diversify your meal rotation")
    if len(snapshot.get("tray_library", {}).get("breakfast", [])) < 3:
        recs.append(f"  4. Add 2-3 more breakfast dishes for better loop rotation")
    if not snapshot.get("health_goal"):
        recs.append(f"  5. Set a health goal for personalized plate balance scores")
    if state[3] < 0.6:
        recs.append(f"  6. Stock the pantry — ingredient tracking improves with more staples")

    for r in recs:
        print(f"  {r}")
    print()


if __name__ == "__main__":
    main()
