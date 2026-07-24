"""
TELOS + MD-App — TELOS reasons about the MealDrama meal-planning app.

Reads MD-App state (from a snapshot or live store) and runs the TELOS pipeline
to evaluate plan quality, detect gaps, and suggest improvements.

Usage:
    # Analyze a default simulated state:
    PYTHONPATH=. python3 telos_mdapp.py

    # Snapshot mode (save/load MD-App state for TELOS):
    PYTHONPATH=. python3 telos_mdapp.py --snapshot /tmp/md_snapshot.json
"""

import numpy as np
import logging
import json
import sys
import os

logging.basicConfig(level=logging.WARNING)

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.experience_manager import ExperienceManager, ExperienceConfig
from telos.core.simulation import CounterfactualEngine
from telos.adapters.mealdrama_adapter import MealDramaSim, MealDramaAdpt, GOAL_STATE


# ─── Default snapshot: represents a new user who just finished onboarding ─────
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
    "planned_slots": ["Breakfast", "Lunch", "Dinner"],
}


def load_snapshot(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    print(f"Snapshot not found at {path}, using defaults")
    return DEFAULT_SNAPSHOT


def print_state_analysis(state: np.ndarray, snapshot: dict):
    """Human-readable breakdown of the MD-App state vector."""
    labels = [
        ("Meal Count", f"{state[0]*100:.0f}%", "📊"),
        ("Tray Size", f"{state[1]*100:.0f}%", "🍽️"),
        ("Pantry Coverage", f"{state[3]*100:.0f}%", "🥦"),
        ("Plate Balance", f"{state[4]*100:.0f}%", "⚖️"),
        ("Plan Completion", f"{state[8]*100:.0f}%", "📅"),
        ("Slot Diversity", f"{state[9]*100:.0f}%", "🎯"),
    ]
    print("\n" + "=" * 50)
    print("📋  MD-APP STATE ANALYSIS")
    print("=" * 50)
    for label, value, icon in labels:
        bar = "█" * int(float(value.strip('%')) / 10) + "░" * (10 - int(float(value.strip('%')) / 10))
        print(f"  {icon} {label:20s} {bar} {value}")
    print("=" * 50)

    # Issues detection
    issues = []
    if snapshot["tray_library"].get("breakfast", []) and len(snapshot["tray_library"]["breakfast"]) < 3:
        issues.append("🥣 Breakfast has < 3 dishes — add more for loop variety")
    if not snapshot.get("health_goal"):
        issues.append("🎯 No health goal set — enable in Profile for personalized suggestions")
    if not snapshot.get("pantry_staples") or len(snapshot["pantry_staples"]) < 5:
        issues.append("🥦 Pantry is thin — add staples for better ingredient tracking")
    if state[6] < 0.5:
        issues.append("⚕️ Low plate balance score — consider more balanced meals")
    if state[9] < 0.5:
        issues.append("🎯 Low slot diversity — fill empty meal slots with variety")

    if issues:
        print("\n🔍  DETECTED ISSUES")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅  No critical issues detected.")
    print()


def main():
    # Load state
    snapshot_path = None
    if len(sys.argv) > 2 and sys.argv[1] == "--snapshot":
        snapshot_path = sys.argv[2]

    snapshot = load_snapshot(snapshot_path) if snapshot_path else DEFAULT_SNAPSHOT

    print("\n🧠 TELOS + MealDrama: Analyzing your meal plan...\n")

    # Build simulator from snapshot
    sim = MealDramaSim(
        tray_library=snapshot.get("tray_library"),
        plan_days=snapshot.get("plan_days"),
        pantry_staples=snapshot.get("pantry_staples"),
        health_goal=snapshot.get("health_goal"),
        cook_contact=snapshot.get("cook_contact"),
        planned_slots=snapshot.get("planned_slots"),
    )

    # Build initial state from snapshot features
    from telos.adapters.mealdrama_adapter import _extract_features
    state = _extract_features(
        snapshot.get("tray_library", {}),
        snapshot.get("plan_days", {}),
        snapshot.get("pantry_staples", []),
        snapshot.get("health_goal"),
        snapshot.get("cook_contact"),
        snapshot.get("planned_slots"),
    )
    print_state_analysis(state, snapshot)

    # Build pipeline
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=MealDramaAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=10, n_worlds=10, horizon=5,
    ))
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)
    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))

    # Run a TELOS decision cycle
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

    # Simulate one improvement step
    print("\n🔄  Simulating improvement: adding dishes to tray...")
    improved = sim.transition(state, np.array([0.1, 0.1, 0, 0, 0, 0, 0, 0, 0.1, 0.1]))
    print_state_analysis(improved, {
        **snapshot,
        "tray_library": {
            "breakfast": snapshot["tray_library"].get("breakfast", []) + [{"id": "poha"}, {"id": "idli"}],
            "lunch": snapshot["tray_library"].get("lunch", []) + [{"id": "dal-tadka"}, {"id": "bhindi"}],
            "dinner": snapshot["tray_library"].get("dinner", []) + [{"id": "paneer"}, {"id": "roti"}],
            "snacks": [],
        }
    })

    print("💡  TELOS suggests:")
    print("  1. Add 2-3 more dishes per slot for better loop rotation")
    print("  2. Fill empty Snacks slot if you want variety")
    print("  3. Set a health goal for personalized plate balance scores")
    print("  4. Keep pantry stocked — ingredient tracking improves with more staples\n")


if __name__ == "__main__":
    main()
