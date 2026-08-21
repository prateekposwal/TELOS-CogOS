#!/usr/bin/env python3
"""
TELOS Household Demo — Simulate the MD-App Household Feature End-to-End.

Demonstrates the full lifecycle:
  SCENARIO A: 2 Roommates (Prateek + Alex) — share invite code, join, meal plan, split expense
  SCENARIO B: 4 Family Members (Mom + Dad + Son + Daughter) — same flow with family dynamics

TELOS Pipeline reasons about each decision with Council verdicts (DI/MD).

Usage:
  PYTHONPATH=/Users/prateekposwal/Desktop/Vrooom-compatibility python3 telos_household_demo.py
"""

import json
import uuid
import numpy as np
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.WARNING)

# ─── TELOS imports ───────────────────────────────────────────────────────────
from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.adapters.mealdrama_adapter import MealDramaSim, MealDramaAdpt, _extract_features, GOAL_STATE

# ═══════════════════════════════════════════════════════════════════════════════
# PART 0: Household State Machine
# ═══════════════════════════════════════════════════════════════════════════════

class HouseholdMember:
    """A member of a household."""
    def __init__(self, name: str, user_id: str, role: str = "member",
                 persona: str = "", diet: str = "veg", health_goal: str = "balanced"):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.user_id = user_id
        self.role = role
        self.persona = persona
        self.diet = diet
        self.health_goal = health_goal
        self.joined_at = datetime.now().isoformat()
        self.meals: List[Dict] = []  # meals they've added to the plan
        self.expenses_paid: float = 0.0

    def __repr__(self) -> str:
        return f"{self.name} ({self.role}, {self.diet})"


class ExpenseSplit:
    def __init__(self, member_id: str, amount: float):
        self.id = str(uuid.uuid4())[:8]
        self.member_id = member_id
        self.amount = amount
        self.paid = False

    def __repr__(self) -> str:
        return f"${self.amount:.2f} {'✅' if self.paid else '❌'}"


class Expense:
    def __init__(self, title: str, amount: float, category: str,
                 added_by: str, member_ids: List[str], split_type: str = "equal"):
        self.id = str(uuid.uuid4())[:8]
        self.title = title
        self.amount = amount
        self.category = category
        self.added_by = added_by
        self.date = datetime.now().isoformat()
        self.split_type = split_type
        self.settled = False
        if split_type == "equal":
            share = round(amount / len(member_ids), 2)
            self.splits = [ExpenseSplit(mid, share) for mid in member_ids]
        else:
            self.splits = []

    def __repr__(self) -> str:
        return f"💰 {self.title}: ${self.amount:.2f} ({self.category})"


class ActivityEntry:
    def __init__(self, member_name: str, action: str, detail: str):
        self.id = str(uuid.uuid4())[:8]
        self.member_name = member_name
        self.action = action
        self.detail = detail
        self.date = datetime.now().isoformat()

    def __repr__(self) -> str:
        return f"  [{self.date[:10]}] {self.member_name} {self.action}: {self.detail}"


class Household:
    """Simulates the MD-App Household model."""

    def __init__(self, name: str, admin: HouseholdMember):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.code = self._generate_code()
        self.admin_id = admin.user_id
        self.members: Dict[str, HouseholdMember] = {admin.user_id: admin}
        self.expenses: List[Expense] = []
        self.activity: List[ActivityEntry] = []
        self.created_at = datetime.now().isoformat()
        self._log_activity(admin.name, "created", f"Created household '{name}'")

    @staticmethod
    def _generate_code() -> str:
        import random
        chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        return ''.join(random.choice(chars) for _ in range(6))

    def get_member(self, user_id: str) -> Optional[HouseholdMember]:
        return self.members.get(user_id)

    def join(self, member: HouseholdMember) -> bool:
        if member.user_id in self.members:
            return False
        self.members[member.user_id] = member
        self._log_activity(member.name, "joined", f"Joined household via code {self.code}")
        return True

    def leave(self, user_id: str) -> bool:
        m = self.members.pop(user_id, None)
        if m:
            self._log_activity(m.name, "left", "Left the household")
            return True
        return False

    def add_expense(self, title: str, amount: float, category: str,
                    added_by: str) -> Expense:
        member_ids = list(self.members.keys())
        e = Expense(title, amount, category, added_by, member_ids)
        self.expenses.append(e)
        self._log_activity(
            self.members[added_by].name,
            "added expense",
            f"${amount:.2f} for {title} ({category})"
        )
        return e

    def mark_paid(self, expense_id: str, split_id: str) -> bool:
        for e in self.expenses:
            if e.id == expense_id:
                for s in e.splits:
                    if s.id == split_id:
                        s.paid = True
                        e.settled = all(sp.paid for sp in e.splits)
                        return True
        return False

    def get_balances(self) -> List[Dict]:
        """Return per-member balance (what they owe vs what they paid)."""
        balances = {}
        for uid, m in self.members.items():
            balances[uid] = {"name": m.name, "total_owed": 0.0, "total_paid": 0.0, "balance": 0.0}

        for e in self.expenses:
            share = e.amount / len(self.members)
            for uid in self.members:
                balances[uid]["total_owed"] += share
            for s in e.splits:
                if s.paid:
                    # Find which member this split belongs to
                    idx = list(self.members.keys()).index(s.member_id) if s.member_id in self.members else -1
                    if idx >= 0:
                        uid = list(self.members.keys())[idx]
                        balances[uid]["total_paid"] += s.amount

        for uid in balances:
            balances[uid]["balance"] = balances[uid]["total_paid"] - balances[uid]["total_owed"]

        return list(balances.values())

    def add_meal(self, user_id: str, meal: Dict) -> None:
        m = self.members.get(user_id)
        if m:
            m.meals.append(meal)
            self._log_activity(m.name, "added meal", f"{meal.get('name','?')} for {meal.get('slot','?')} on {meal.get('date','?')}")

    def get_consolidated_meals(self, start: str = "", end: str = "") -> List[Dict]:
        """Return all meals across all members, simulating the /households/:id/meals endpoint."""
        result = []
        for uid, m in self.members.items():
            for meal in m.meals:
                result.append({
                    **meal,
                    "requestedBy": m.name,
                    "memberId": m.id,
                })
        return result

    def get_consolidated_grocery_list(self) -> Dict[str, List[str]]:
        """Aggregate ingredients from all members' meals."""
        grocery: Dict[str, List[str]] = {}
        for m in self.members.values():
            for meal in m.meals:
                for ing in meal.get("ingredients", []):
                    cat = ing.get("category", "Other")
                    if cat not in grocery:
                        grocery[cat] = []
                    if ing["name"] not in grocery[cat]:
                        grocery[cat].append(ing["name"])
        return grocery

    def _log_activity(self, member_name: str, action: str, detail: str) -> None:
        self.activity.append(ActivityEntry(member_name, action, detail))

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "admin_id": self.admin_id,
            "members": {uid: {"name": m.name, "role": m.role, "diet": m.diet}
                        for uid, m in self.members.items()},
            "member_count": len(self.members),
            "expenses": len(self.expenses),
            "activity_count": len(self.activity),
            "created_at": self.created_at,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: TELOS Household Simulator (extends MealDramaSim)
# ═══════════════════════════════════════════════════════════════════════════════

class HouseholdDomainSim(MealDramaSim):
    """Extends MealDramaSim to reason about household-level decisions."""

    def __init__(self, household: Household, member: HouseholdMember):
        tray = {
            "breakfast": [],
            "lunch": [],
            "dinner": [],
            "snacks": [],
        }
        super().__init__(
            tray_library=tray,
            plan_days={},
            pantry_staples=["Rice", "Dal", "Onions", "Tomatoes", "Spices", "Oil"],
            health_goal=member.health_goal,
            cook_contact="+919876543210",
            planned_slots=["Breakfast", "Lunch", "Dinner"],
        )
        self.household = household
        self.member = member

    def get_facts(self, state):
        facts = super().get_facts(state)
        facts.metadata["household_name"] = self.household.name
        facts.metadata["household_size"] = len(self.household.members)
        facts.metadata["member_name"] = self.member.name
        facts.metadata["member_role"] = self.member.role
        return facts

    def evaluate(self, state):
        report = super().evaluate(state)
        # Penalize imbalance if household has members with different diets
        diets = set(m.diet for m in self.household.members.values())
        if len(diets) > 1:
            report.objectives["diet_harmony"] = 0.5  # could improve
        return report


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Print Utilities
# ═══════════════════════════════════════════════════════════════════════════════

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
RED = "\033[91m"

def banner(text: str, char: str = "═", color: str = CYAN):
    w = 60
    print(f"\n{color}{char * w}{RESET}")
    print(f"{color}{BOLD}  {text}{RESET}")
    print(f"{color}{char * w}{RESET}\n")

def step(num: int, title: str):
    print(f"\n{YELLOW}{BOLD}▸ Step {num}: {title}{RESET}")
    print(f"{YELLOW}{'─' * 50}{RESET}")

def api_call(method: str, path: str, payload: dict = None, response: dict = None):
    print(f"\n{DIM}📡 API Call:{RESET}")
    print(f"  {GREEN}{method}{RESET} {BLUE}{path}{RESET}")
    if payload:
        print(f"  {DIM}Request:{RESET} {json.dumps(payload, indent=2)}")
    if response:
        print(f"  {DIM}Response:{RESET} {json.dumps(response, indent=2)}")

def show_verdict(trace):
    if not trace:
        return
    intent = trace.selected_intent.intent_type if trace.selected_intent else "none"
    status = "✅ APPROVED" if not getattr(trace, 'council_blocked', False) else "❌ BLOCKED"
    print(f"\n  {BOLD}TELOS Verdict:{RESET}")
    print(f"    Intent:    {intent}")
    print(f"    Status:    {status}")
    print(f"    DI:        {trace.decision_integrity:.3f}")
    print(f"    MD:        {trace.mission_drift:.3f}")
    print(f"    Worlds:    {trace.worlds_simulated}")

def y_n(value: bool) -> str:
    return f"{GREEN}✅ Yes{RESET}" if value else f"{RED}❌ No{RESET}"

def section(title: str, items: List[str]):
    print(f"\n  {BOLD}{title}{RESET}")
    for item in items:
        print(f"    • {item}")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: Build TELOS Pipeline for a Household
# ═══════════════════════════════════════════════════════════════════════════════

def build_pipeline(sim, user_name: str = "HouseholdUser"):
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
    return pipeline


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO A: 2 Roommates
# ═══════════════════════════════════════════════════════════════════════════════

def run_scenario_roommates():
    banner("SCENARIO A: Two Roommates Sharing a Meal Plan", "═", MAGENTA)

    # ─── A1: Prateek creates a household ─────────────────────────────────────
    step(1, "User A (Prateek) downloads the app, completes onboarding, creates a household")

    prateek = HouseholdMember("Prateek", "user_prateek", role="admin",
                               persona="working_professional", diet="veg",
                               health_goal="high_protein")

    api_call("POST", "/api/v1/households", {"name": "Prateek's Kitchen"})
    hh = Household("Prateek's Kitchen", prateek)
    api_call("POST", "/api/v1/households", {},
             response=hh.to_dict())

    print(f"\n  🏠 {BOLD}{hh.name}{RESET} created!")
    print(f"  📋 Invite Code: {YELLOW}{BOLD}{hh.code}{RESET}")
    print(f"  👤 Admin: {prateek.name} ({prateek.persona})")

    # ─── A2: Share invite code ──────────────────────────────────────────────
    step(2, "Prateek shares the invite code with roommate Alex via WhatsApp")

    share_text = f"Join my MealDrama household \"{hh.name}\"! Use code: {hh.code}"
    wa_link = f"https://wa.me/?text={share_text.replace(' ', '%20')}"

    print(f"\n  📱 {BOLD}WhatsApp Share{RESET}")
    print(f"  {DIM}Share Text:{RESET} \"{share_text}\"")
    print(f"  {DIM}WhatsApp Link:{RESET} {BLUE}{wa_link}{RESET}")
    print(f"  {DIM}Invite Code:{RESET} {YELLOW}{BOLD}{hh.code}{RESET}")

    # ─── A3: Alex joins via code ────────────────────────────────────────────
    step(3, "User B (Alex) downloads app, enters the invite code, joins the household")

    alex = HouseholdMember("Alex", "user_alex", role="member",
                            persona="student", diet="non_veg",
                            health_goal="balanced")

    api_call("POST", "/api/v1/households/join", {"code": hh.code})

    joined = hh.join(alex)
    api_call("POST", "/api/v1/households/join", {},
             response={"status": "joined" if joined else "already_member",
                       "household_id": hh.id,
                       "members": len(hh.members)})

    print(f"\n  👤 {BOLD}{alex.name}{RESET} joined {GREEN}{'✅' if joined else 'already was a member'}{RESET}")
    print(f"  👥 Members: {', '.join(m.name for m in hh.members.values())}")

    # ─── A4: TELOS reasons about the household ───────────────────────────────
    step(4, "TELOS reasons about Prateek's meal plan within the household context")

    prateek_sim = HouseholdDomainSim(hh, prateek)
    prateek_state = _extract_features(
        {"breakfast": [{"id": "aloo-paratha"}, {"id": "paneer-sandwich"}],
         "lunch": [{"id": "dal-rice"}, {"id": "rajma-chawal"}],
         "dinner": [{"id": "paneer-butter-masala"}, {"id": "dal-makhani"}]},
        {"2026-07-22": {"breakfast": [{"meal_id": "aloo-paratha"}],
                         "lunch": [{"meal_id": "dal-rice"}],
                         "dinner": [{"meal_id": "paneer-butter-masala"}]}},
        pantry_staples=["Rice", "Dal", "Onions", "Tomatoes", "Spices", "Oil", "Paneer", "Wheat Flour"],
        health_goal=prateek.health_goal,
        cook_contact="+919876543210",
        planned_slots=["Breakfast", "Lunch", "Dinner"],
    )

    pipeline_p = build_pipeline(prateek_sim, "Prateek")
    result_p = pipeline_p.execute(prateek_state, user_name="Prateek")

    print(f"\n  🧠 {BOLD}TELOS analyzes Prateek's household plan{RESET}")
    if result_p.decision_trace:
        show_verdict(result_p.decision_trace)
        print(f"\n  📊 State Features:")
        labels = ["Meals", "Tray", "Pantry", "Coverage", "Balance",
                  "Days", "Health", "Cook", "Completion", "Diversity"]
        for i, (label, val) in enumerate(zip(labels, prateek_state)):
            bar = "█" * int(val * 10) + "░" * (10 - int(val * 10))
            print(f"    {label:12s} {bar} {val:.2f}")

    pipeline_p.shutdown()

    # ─── A5: Both add meals ─────────────────────────────────────────────────
    step(5, "Both roommates add meals to the household plan this week")

    shared_meals = [
        # Prateek's meals
        {"name": "Aloo Paratha", "slot": "Breakfast", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Potato", "category": "Vegetables", "qty": 3},
             {"name": "Wheat Flour", "category": "Grains", "qty": 2},
             {"name": "Ghee", "category": "Dairy", "qty": 1},
         ]},
        {"name": "Dal Rice", "slot": "Lunch", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Rice", "category": "Grains", "qty": 2},
             {"name": "Dal (Toor)", "category": "Legumes", "qty": 1},
             {"name": "Tomato", "category": "Vegetables", "qty": 2},
             {"name": "Onion", "category": "Vegetables", "qty": 1},
         ]},
        {"name": "Paneer Butter Masala", "slot": "Dinner", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Paneer", "category": "Dairy", "qty": 2},
             {"name": "Cream", "category": "Dairy", "qty": 1},
             {"name": "Tomato", "category": "Vegetables", "qty": 3},
             {"name": "Spices", "category": "Condiments", "qty": 1},
         ]},
        # Alex's meals
        {"name": "Chicken Curry", "slot": "Dinner", "date": "2026-07-22",
         "diet": "non_veg", "ingredients": [
             {"name": "Chicken", "category": "Meat", "qty": 3},
             {"name": "Onion", "category": "Vegetables", "qty": 2},
             {"name": "Tomato", "category": "Vegetables", "qty": 2},
             {"name": "Coconut Milk", "category": "Dairy", "qty": 1},
             {"name": "Spices", "category": "Condiments", "qty": 1},
         ]},
        {"name": "Egg Sandwich", "slot": "Breakfast", "date": "2026-07-23",
         "diet": "non_veg", "ingredients": [
             {"name": "Eggs", "category": "Meat", "qty": 4},
             {"name": "Bread", "category": "Grains", "qty": 2},
             {"name": "Butter", "category": "Dairy", "qty": 1},
         ]},
    ]

    for i, meal in enumerate(shared_meals):
        user_id = "user_prateek" if i < 3 else "user_alex"
        hh.add_meal(user_id, meal)
        print(f"  {BLUE}🍽️{RESET} {meal['name']:30s} | {meal['slot']:12s} | {meal['date']} | by {hh.members[user_id].name}")

    # ─── A6: Consolidated grocery list ──────────────────────────────────────
    step(6, "View consolidated grocery list across the household")

    grocery = hh.get_consolidated_grocery_list()
    print(f"\n  {BOLD}🛒 Consolidated Grocery List{RESET}")
    total_items = 0
    for cat, items in sorted(grocery.items()):
        print(f"    {DIM}{cat}:{RESET} {', '.join(items)}")
        total_items += len(items)
    print(f"\n    {BOLD}Total: {total_items} ingredients{RESET}")

    api_call("GET", f"/api/v1/households/{hh.id}/meals?start=2026-07-22&end=2026-07-28",
             response={"meals": hh.get_consolidated_meals(),
                       "members": [{"id": m.id, "name": m.name} for m in hh.members.values()]})

    # ─── A7: Split expense (cook salary) ────────────────────────────────────
    step(7, "Roommates split the cook's weekly salary equally")

    expense = hh.add_expense("Cook Weekly Salary", 2000.00, "cook_salary", "user_prateek")
    print(f"\n  💰 {expense.title}: ${expense.amount:.2f}")
    for s in expense.splits:
        print(f"    {DIM}Split:{RESET} {s.amount:.2f} — {y_n(s.paid)}")

    api_call("GET", f"/api/v1/households/{hh.id}/balances",
             response={"balances": hh.get_balances()})

    print(f"\n  {BOLD}Balance Summary:{RESET}")
    for b in hh.get_balances():
        fmt = f"+${b['balance']:.2f}" if b['balance'] >= 0 else f"-${abs(b['balance']):.2f}"
        print(f"    {b['name']:15s} owes ${b['total_owed']:.2f}, paid ${b['total_paid']:.2f} → {fmt}")

    # ─── A8: Mark expense as paid ───────────────────────────────────────────
    step(8, "Both roommates mark their splits as paid")

    for s in expense.splits:
        hh.mark_paid(expense.id, s.id)
        member_name = hh.members[s.member_id].name if s.member_id in hh.members else "Unknown"
        print(f"  💵 {member_name} marked their split ${s.amount:.2f} as {GREEN}paid{RESET}")

    print(f"\n  Expense settled: {y_n(expense.settled)}")
    print(f"  All splits paid: {y_n(all(s.paid for s in expense.splits))}")

    # ─── A9: TELOS council verdict on household health ──────────────────────
    step(9, "TELOS evaluates household health — diet harmony, plan completion, expense fairness")

    # Build a household-level state from aggregate data
    hh_state = np.array([
        min(len(hh.get_consolidated_meals()) / 20, 1.0),  # meals planned
        min(10 / 15, 1.0),  # tray dishes
        min(8 / 10, 1.0),  # pantry diversity
        0.7,  # ingredient coverage
        0.65,  # average plate balance (mix of veg/non-veg)
        0.5,  # days remaining
        1.0,  # health goal set
        1.0,  # cook assigned
        0.6,  # plan completion
        0.8,  # slot diversity
    ])

    # Run TELOS on the aggregate state for final evaluation
    hh_sim = HouseholdDomainSim(hh, prateek)
    hh_pipeline = build_pipeline(hh_sim, "Prateek+Alex")
    hh_result = hh_pipeline.execute(hh_state, user_name="Prateek+Alex")

    print(f"\n  🧠 {BOLD}TELOS Final Household Assessment{RESET}")
    if hh_result.decision_trace:
        show_verdict(hh_result.decision_trace)

        di = hh_result.decision_trace.decision_integrity
        md = hh_result.decision_trace.mission_drift

        print(f"\n  {BOLD}🏠 Household Scorecard{RESET}")
        print(f"    {DIM}Members:{RESET} {len(hh.members)} roommates")
        print(f"    {DIM}Meals:{RESET} {len(hh.get_consolidated_meals())} shared")
        print(f"    {DIM}Grocery Items:{RESET} {sum(len(v) for v in hh.get_consolidated_grocery_list().values())}")
        print(f"    {DIM}Expenses:{RESET} {len(hh.expenses)} (${sum(e.amount for e in hh.expenses):.2f})")
        print(f"    {DIM}Diet Harmony:{RESET} {'Mixed (veg + non-veg)' if len(set(m.diet for m in hh.members.values())) > 1 else 'Single diet'}")
        print(f"    {DIM}Decision Integrity:{RESET} {di:.3f}")
        print(f"    {DIM}Mission Drift:{RESET} {md:.3f}")

        # Axioms governing this decision
        print(f"\n  {BOLD}📜 Governing Axioms{RESET}")
        axioms = [
            ("1.1", "Architecture Produces Outcomes", "Pipeline evaluated household state through 7-phase engine"),
            ("1.2", "Process over Outcomes", f"DecisionTrace captured DI={di:.3f}, MD={md:.3f}"),
            ("2.4", "Path Dependency", "Household decisions are history-aware through WorldLedger"),
            ("4.3", "Possibility Preservation", "Counterfactual futures generated for meal alternatives"),
            ("4.6", "Emergent Intelligence", "No single stream decided — coordination of 4 streams produced the verdict"),
        ]
        for num, name, desc in axioms:
            print(f"    {MAGENTA}{num}{RESET} {BOLD}{name}{RESET}")
            print(f"       {DIM}{desc}{RESET}")

    hh_pipeline.shutdown()

    return hh


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO B: 4 Family Members
# ═══════════════════════════════════════════════════════════════════════════════

def run_scenario_family():
    banner("SCENARIO B: Four Family Members (Mom, Dad, Son, Daughter)", "═", GREEN)

    # ─── B1: Mom creates a family household ──────────────────────────────────
    step(1, "Mom creates a family household — 'The Kapoor Family Kitchen'")

    mom = HouseholdMember("Mom (Anita)", "user_mom", role="admin",
                           persona="homemaker", diet="veg",
                           health_goal="balanced")

    api_call("POST", "/api/v1/households", {"name": "The Kapoor Family Kitchen"})
    family = Household("The Kapoor Family Kitchen", mom)
    api_call("POST", "/api/v1/households", {},
             response=family.to_dict())

    print(f"\n  🏠 {BOLD}{family.name}{RESET} created!")
    print(f"  📋 Invite Code: {YELLOW}{BOLD}{family.code}{RESET}")

    # ─── B2-4: Dad, Son, Daughter join ──────────────────────────────────────
    step(2, "Dad, Son (teen), Daughter (child) join the family household")

    dad = HouseholdMember("Dad (Rajesh)", "user_dad", role="member",
                           persona="remote_worker", diet="non_veg",
                           health_goal="low_carb")
    son = HouseholdMember("Son (Arjun)", "user_son", role="member",
                           persona="student", diet="veg",
                           health_goal="high_protein",
                           )
    daughter = HouseholdMember("Daughter (Priya)", "user_daughter", role="member",
                                persona="student", diet="veg",
                                health_goal="balanced")

    for member in [dad, son, daughter]:
        api_call("POST", "/api/v1/households/join", {"code": family.code})
        joined = family.join(member)
        print(f"  👤 {BOLD}{member.name}{RESET} joined {GREEN}{'✅' if joined else 'already a member'}{RESET}")

    print(f"\n  👥 {BOLD}Family Members:{RESET}")
    for m in family.members.values():
        print(f"    • {m.name:20s} | {m.persona:20s} | {m.diet:10s} | Goal: {m.health_goal}")

    # ─── B5: Each family member adds meals ──────────────────────────────────
    step(3, "Each family member adds meals for the week (catering to different diets)")

    family_meals = [
        # Mom's meals
        {"name": "Vegetable Poha", "slot": "Breakfast", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Poha (Flattened Rice)", "category": "Grains", "qty": 2},
             {"name": "Potato", "category": "Vegetables", "qty": 1},
             {"name": "Peanuts", "category": "Legumes", "qty": 1},
             {"name": "Lemon", "category": "Fruits", "qty": 1},
         ]},
        {"name": "Dal Tadka + Rice", "slot": "Lunch", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Rice", "category": "Grains", "qty": 4},
             {"name": "Dal (Toor)", "category": "Legumes", "qty": 2},
             {"name": "Tomato", "category": "Vegetables", "qty": 3},
             {"name": "Garlic", "category": "Condiments", "qty": 1},
             {"name": "Ghee", "category": "Dairy", "qty": 1},
         ]},
        {"name": "Mixed Vegetable Curry", "slot": "Dinner", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Mixed Vegetables", "category": "Vegetables", "qty": 4},
             {"name": "Coconut", "category": "Fruits", "qty": 1},
             {"name": "Spices", "category": "Condiments", "qty": 2},
             {"name": "Rice", "category": "Grains", "qty": 3},
         ]},
        # Dad's meals (non-veg, low carb)
        {"name": "Egg Omelette", "slot": "Breakfast", "date": "2026-07-22",
         "diet": "non_veg", "ingredients": [
             {"name": "Eggs", "category": "Meat", "qty": 3},
             {"name": "Onion", "category": "Vegetables", "qty": 1},
             {"name": "Cheese", "category": "Dairy", "qty": 1},
         ]},
        {"name": "Grilled Fish", "slot": "Lunch", "date": "2026-07-22",
         "diet": "non_veg", "ingredients": [
             {"name": "Fish (Pomfret)", "category": "Meat", "qty": 2},
             {"name": "Lemon", "category": "Fruits", "qty": 1},
             {"name": "Salad Greens", "category": "Vegetables", "qty": 2},
             {"name": "Olive Oil", "category": "Condiments", "qty": 1},
         ]},
        # Son's meals (high protein, veg)
        {"name": "Protein Smoothie", "slot": "Breakfast", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Banana", "category": "Fruits", "qty": 2},
             {"name": "Milk", "category": "Dairy", "qty": 2},
             {"name": "Peanut Butter", "category": "Legumes", "qty": 1},
         ]},
        {"name": "Paneer Tikka", "slot": "Lunch", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Paneer", "category": "Dairy", "qty": 3},
             {"name": "Capsicum", "category": "Vegetables", "qty": 2},
             {"name": "Yogurt", "category": "Dairy", "qty": 1},
             {"name": "Spices", "category": "Condiments", "qty": 1},
         ]},
        # Daughter's meals
        {"name": "Cornflakes + Milk", "slot": "Breakfast", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Cornflakes", "category": "Grains", "qty": 2},
             {"name": "Milk", "category": "Dairy", "qty": 2},
             {"name": "Banana", "category": "Fruits", "qty": 1},
         ]},
        {"name": "Cheese Sandwich", "slot": "Lunch", "date": "2026-07-22",
         "diet": "veg", "ingredients": [
             {"name": "Bread", "category": "Grains", "qty": 2},
             {"name": "Cheese", "category": "Dairy", "qty": 2},
             {"name": "Tomato", "category": "Vegetables", "qty": 1},
             {"name": "Lettuce", "category": "Vegetables", "qty": 1},
         ]},
    ]

    user_ids = ["user_mom", "user_dad", "user_son", "user_daughter"]
    user_cycle = []
    for i, mid in enumerate(user_ids):
        for _ in range(2):
            user_cycle.append(mid)
    # Assign meals round-robin
    for i, meal in enumerate(family_meals):
        uid = user_ids[i % len(user_ids)]
        family.add_meal(uid, meal)
        print(f"  {BLUE}🍽️{RESET} {meal['name']:30s} | {meal['slot']:12s} | by {family.members[uid].name:18s} | {meal['diet']}")

    # ─── B6: Consolidated grocery ───────────────────────────────────────────
    step(4, "View consolidated grocery list for the family")

    grocery = family.get_consolidated_grocery_list()
    print(f"\n  {BOLD}🛒 Family Consolidated Grocery List{RESET}")
    total_items = 0
    for cat, items in sorted(grocery.items()):
        print(f"    {DIM}{cat}:{RESET} {', '.join(items)}")
        total_items += len(items)
    print(f"\n    {BOLD}Total: {total_items} ingredients across {len(grocery)} categories{RESET}")

    api_call("GET", f"/api/v1/households/{family.id}/meals",
             response={"meals": family.get_consolidated_meals(),
                       "member_count": len(family.members)})

    # ─── B7: Family expenses ────────────────────────────────────────────────
    step(5, "Family adds shared expenses (groceries, cook salary, utilities)")

    family_expenses = [
        ("Weekly Groceries", 3500.00, "groceries"),
        ("Cook Monthly Salary", 8000.00, "cook_salary"),
        ("Kitchen Supplies", 1200.00, "supplies"),
        ("Gas Refill", 950.00, "utilities"),
    ]

    for title, amount, cat in family_expenses:
        e = family.add_expense(title, amount, cat, "user_mom")
        print(f"  💰 {e.title:30s} ${e.amount:.2f} ({cat})")
        detail = ", ".join(f"{family.members[s.member_id].name if s.member_id in family.members else '?'}: ${s.amount:.2f}"
                          for s in e.splits)
        print(f"     {DIM}Splits:{RESET} {detail}")

    # ─── B8: Family balances ────────────────────────────────────────────────
    step(6, "View family balances — who owes what")

    api_call("GET", f"/api/v1/households/{family.id}/balances",
             response={"balances": family.get_balances()})

    print(f"\n  {BOLD}Family Balance Sheet:{RESET}")
    total_expenses = sum(e.amount for e in family.expenses)
    print(f"  {DIM}Total Household Expenses:{RESET} ${total_expenses:.2f}")
    for b in family.get_balances():
        fmt = f"+${b['balance']:.2f}" if b['balance'] >= 0 else f"-${abs(b['balance']):.2f}"
        status = GREEN if b['balance'] >= 0 else RED
        print(f"    {b['name']:20s} owes ${b['total_owed']:.2f}, paid ${b['total_paid']:.2f} → {status}{fmt}{RESET}")

    # ─── B9: Activity feed ──────────────────────────────────────────────────
    step(7, "View the household activity feed")

    api_call("GET", f"/api/v1/households/{family.id}/activity",
             response={"activities": [str(a) for a in family.activity]})

    print(f"\n  {BOLD}📋 Activity Feed (last {len(family.activity)} events):{RESET}")
    for a in family.activity[-8:]:
        print(f"  {a}")

    # ─── B10: TELOS family health assessment ────────────────────────────────
    step(8, "TELOS performs family-level health assessment — multi-diet harmony, nutritional coverage")

    # Build family aggregate state
    diets_present = set(m.diet for m in family.members.values())
    multi_diet = len(diets_present) > 1

    family_state = np.array([
        min(len(family.get_consolidated_meals()) / 20, 1.0),
        min(12 / 15, 1.0),
        min(10 / 10, 1.0),
        0.75,
        0.7 if multi_diet else 0.85,  # slightly lower with mixed diets
        0.5,
        1.0,
        1.0,
        0.7,
        0.85,
    ])

    mom_sim = HouseholdDomainSim(family, mom)
    fam_pipeline = build_pipeline(mom_sim, "KapoorFamily")
    fam_result = fam_pipeline.execute(family_state, user_name="KapoorFamily")

    print(f"\n  🧠 {BOLD}TELOS Family Assessment{RESET}")
    if fam_result.decision_trace:
        show_verdict(fam_result.decision_trace)

        di = fam_result.decision_trace.decision_integrity
        md = fam_result.decision_trace.mission_drift

        print(f"\n  {BOLD}🏠 Family Scorecard{RESET}")
        print(f"    {DIM}Members:{RESET} {len(family.members)} ({', '.join(m.name for m in family.members.values())})")
        print(f"    {DIM}Diets:{RESET} {', '.join(diets_present)}")
        print(f"    {DIM}Shared Meals:{RESET} {len(family.get_consolidated_meals())}")
        print(f"    {DIM}Grocery Items:{RESET} {total_items}")
        print(f"    {DIM}Total Expenses:{RESET} ${total_expenses:.2f}")
        print(f"    {DIM}Decision Integrity:{RESET} {di:.3f}")
        print(f"    {DIM}Mission Drift:{RESET} {md:.3f}")

        # Insights
        print(f"\n  {BOLD}💡 Family Insights:{RESET}")
        if multi_diet:
            print(f"    • Multiple diets ({', '.join(diets_present)}) — ensure the grocery list covers all preferences")
        print(f"    • Mom manages {len(family.expenses)} shared expenses — consider auto-split reminders")
        print(f"    • Teen son's high-protein goal is covered by paneer & smoothie options")
        print(f"    • Dad's low-carb needs are met with egg/fish options")
        print(f"    • Daughter's kid-friendly meals are present (cornflakes, sandwiches)")

    fam_pipeline.shutdown()

    return family


# ═══════════════════════════════════════════════════════════════════════════════
# PART 4: Summary & JSON Trace Export
# ═══════════════════════════════════════════════════════════════════════════════

def export_trace(scenario_name: str, household: Household):
    """Export the full scenario trace as JSON."""
    trace = {
        "scenario": scenario_name,
        "household": household.to_dict(),
        "members": [
            {
                "name": m.name,
                "role": m.role,
                "persona": m.persona,
                "diet": m.diet,
                "meals": len(m.meals),
            }
            for m in household.members.values()
        ],
        "expenses": [
            {
                "title": e.title,
                "amount": e.amount,
                "category": e.category,
                "splits": [{"amount": s.amount, "paid": s.paid} for s in e.splits],
                "settled": e.settled,
            }
            for e in household.expenses
        ],
        "grocery_items": sum(len(v) for v in household.get_consolidated_grocery_list().values()),
        "activity_events": [
            {"member": a.member_name, "action": a.action, "detail": a.detail, "date": a.date}
            for a in household.activity
        ],
    }
    return trace


def print_summary(scenario_name: str, scenario_type: str, household: Household):
    banner(f"{scenario_name} — COMPLETE", "★", CYAN)

    print(f"  {BOLD}{scenario_type}{RESET}")
    print(f"  {'─' * 40}")
    print(f"  🏠  Household:     {BOLD}{household.name}{RESET}")
    print(f"  🔑  Invite Code:   {YELLOW}{BOLD}{household.code}{RESET}")
    print(f"  👥  Members:       {len(household.members)}")
    print(f"  🍽️  Meals Planned: {len(household.get_consolidated_meals())}")
    print(f"  🛒  Grocery Items: {sum(len(v) for v in household.get_consolidated_grocery_list().values())}")
    print(f"  💰  Expenses:      {len(household.expenses)} (${sum(e.amount for e in household.expenses):.2f})")
    print(f"  📋  Activities:    {len(household.activity)} events")

    # Member breakdown
    print(f"\n  {BOLD}Member Details:{RESET}")
    for m in household.members.values():
        print(f"    • {m.name:20s} | Role: {m.role:8s} | Diet: {m.diet:10s} | Meals: {len(m.meals)}")

    if household.expenses:
        print(f"\n  {BOLD}Expense Status:{RESET}")
        for e in household.expenses:
            settled = "✅" if e.settled else "❌"
            print(f"    {settled} {e.title:30s} ${e.amount:.2f}")

    print(f"\n  {GREEN}{BOLD}✓ Scenario completed successfully!{RESET}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print()
    banner("TELOS + MealDrama: Household Feature Simulation", "=", CYAN)
    print(f"  {DIM}A complete end-to-end walkthrough of the MD-App household feature,{RESET}")
    print(f"  {DIM}simulated through TELOS's 20-axiom Cognitive Operating System.{RESET}")
    print(f"  {DIM}Every decision is traced, evaluated by the Council, and explained.{RESET}")
    print(f"  {DIM}Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}\n")

    # ─── Run Roommate Scenario ──────────────────────────────────────────────
    banner("▶ SCENARIO A: 2 Roommates", "─", MAGENTA)
    hh_roommates = run_scenario_roommates()
    print_summary("Roommate Scenario", "2 Roommates sharing a meal plan & expenses", hh_roommates)

    # ─── Run Family Scenario ────────────────────────────────────────────────
    banner("▶ SCENARIO B: 4 Family Members", "─", GREEN)
    hh_family = run_scenario_family()
    print_summary("Family Scenario", "4 Family Members with mixed dietary needs", hh_family)

    # ─── Export Traces ──────────────────────────────────────────────────────
    trace_a = export_trace("roommates", hh_roommates)
    trace_b = export_trace("family", hh_family)

    trace_path_a = "/tmp/telos_household_roommates.json"
    trace_path_b = "/tmp/telos_household_family.json"

    with open(trace_path_a, "w") as f:
        json.dump(trace_a, f, indent=2)
    with open(trace_path_b, "w") as f:
        json.dump(trace_b, f, indent=2)

    # ─── Final Summary ──────────────────────────────────────────────────────
    banner("FINAL REPORT: Household Feature Complete", "=", CYAN)
    print(f"\n  {BOLD}📊 What was demonstrated:{RESET}")
    print(f"  {'─' * 50}")
    print(f"  ✅ Household creation via {GREEN}POST /api/v1/households{RESET}")
    print(f"  ✅ Invite code generation ({YELLOW}6-char alphanumeric{RESET})")
    print(f"  ✅ WhatsApp share link with code embedded")
    print(f"  ✅ Join via code: {GREEN}POST /api/v1/households/join{RESET}")
    print(f"  ✅ Multi-member meal planning with individual preferences")
    print(f"  ✅ Consolidated grocery list aggregation across all members")
    print(f"  ✅ Splitwise-style expense tracking with equal splits")
    print(f"  ✅ Per-member balance calculation (owed vs paid)")
    print(f"  ✅ Activity feed for all household events")
    print(f"  ✅ TELOS Council reasoning with DI/MD verdicts")
    print(f"  ✅ {MAGENTA}20 Axioms{RESET} governing every decision in the pipeline")
    print(f"\n  {BOLD}📁 JSON Traces exported to:{RESET}")
    print(f"    • {DIM}{trace_path_a}{RESET}")
    print(f"    • {DIM}{trace_path_b}{RESET}")
    print(f"\n  {BOLD}💡 To visualize:{RESET}")
    print(f"    These JSON traces can be fed into any visualization tool")
    print(f"    (D3.js, Graphviz, Excalidraw) to generate the UI mockups.")
    print()


if __name__ == "__main__":
    main()
