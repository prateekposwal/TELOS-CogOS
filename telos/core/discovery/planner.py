"""
Planner-aware Value of Information (V6).

V3 gave the canonical IMMEDIATE VoI (CounterfactualEngine.compute_value_of_
information). V6 adds lookahead WITHOUT replacing it: the immediate value of each
experiment is still the canonical value; the planner adds the EXPECTED VALUE OF
THE FUTURE INVESTIGATION it unlocks.

    GREEDY        argmax immediate value
    PLANNER_AWARE argmax [ immediate + γ · E_outcome( future value(H-1) ) ]

Sanity: at horizon 1 the two modes coincide.

The planner never sees truth/graph/utility: it plans over its own MODEL
(experiments, costs, immediate values from the canonical selector, outcome
probabilities and successor states). A hidden world supplies the ACTUAL outcome.

Budget: both an experiment-count cap and a cost cap are enforced during search;
a state with no affordable/available experiment has value 0 (UNRESOLVED) — the
planner is allowed to finish without resolving.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class PlanningObjective(str, Enum):
    """V19.6 — explicit planning objective (the planner does not define 'good').

    DECISION_VALUE          legacy V6/V7: maximize accumulated discrimination
                            (imm + gamma*future); cost is a feasibility gate only.
    MIN_COST_TO_RESOLUTION  resource-optimal: minimize expected acquisition cost
                            to reach a justified terminal (resolved) state.
    """
    DECISION_VALUE = "DECISION_VALUE"
    MIN_COST_TO_RESOLUTION = "MIN_COST_TO_RESOLUTION"


class PlannerMode(str, Enum):
    GREEDY = "GREEDY"
    PLANNER_AWARE = "PLANNER_AWARE"


# A model state:
#   {"experiments": {exp_id: {"cost": float, "imm": float}},
#    "transitions":  {(exp_id, outcome): next_state_id},
#    "obs_prob":     {(exp_id, outcome): probability}}
Model = Dict[str, Dict[str, Any]]


@dataclass
class Plan:
    """A chosen experiment + its expected value under the model."""
    experiment: Optional[str]
    mode: str
    horizon: int
    expected_value: float
    immediate_value: float
    future_value: float
    considered: Dict[str, float] = field(default_factory=dict)


class PlannerAwareSelector:
    """Expectimax over an experiment/outcome model, on top of canonical VoI.

    Args:
        model: the planning model (states/experiments/transitions/obs_prob).
        gamma: discount on future value (1.0 = undiscounted).
    """

    def __init__(self, model: Model, gamma: float = 1.0):
        self.model = model
        self.gamma = float(gamma)
        self._memo: Dict[Tuple, float] = {}

    # ── Core expectimax ──────────────────────────────────────────────────────

    def value(self, state: str, horizon: int, cost_left: float,
              count_left: int) -> float:
        """Expected value of the best experiment(s) from `state`.

        Args:
            state: model state id.
            horizon: remaining lookahead depth.
            cost_left: remaining cost budget.
            count_left: remaining experiment-count budget.

        Returns:
            The expected value (0.0 when nothing affordable/available ⇒ UNRESOLVED).
        """
        if horizon <= 0 or count_left <= 0 or cost_left <= 0:
            return 0.0
        key = (state, horizon, round(cost_left, 4), count_left)
        if key in self._memo:
            return self._memo[key]
        node = self.model.get(state, {})
        exps = node.get("experiments", {})
        if not exps:
            return 0.0
        trans = node.get("transitions", {})
        probs = node.get("obs_prob", {})
        best = 0.0
        for exp, spec in exps.items():
            cost = float(spec.get("cost", 0.0))
            if cost > cost_left + 1e-9:
                continue
            future = 0.0
            for (e, o), nxt in trans.items():
                if e != exp:
                    continue
                p = float(probs.get((exp, o), 0.0))
                future += p * self.value(nxt, horizon - 1, cost_left - cost,
                                         count_left - 1)
            total = float(spec.get("imm", 0.0)) + self.gamma * future
            best = max(best, total)
        self._memo[key] = best
        return best

    def select(self, state: str, *, mode: PlannerMode = PlannerMode.PLANNER_AWARE,
               horizon: int = 1, cost_budget: float = 1e9,
               count_budget: int = 10) -> Plan:
        """Choose an experiment under the given mode/horizon/budget.

        Args:
            state: model state id.
            mode: GREEDY (horizon forced to 1) or PLANNER_AWARE.
            horizon: lookahead depth for PLANNER_AWARE.
            cost_budget: cost cap.
            count_budget: experiment-count cap.

        Returns:
            The Plan (experiment, values, and per-experiment expected values).
        """
        h = 1 if mode == PlannerMode.GREEDY else max(1, horizon)
        node = self.model.get(state, {})
        exps = node.get("experiments", {})
        trans = node.get("transitions", {})
        probs = node.get("obs_prob", {})
        considered: Dict[str, float] = {}
        best_exp, best_total, best_imm, best_fut = None, -1e18, 0.0, 0.0
        for exp, spec in exps.items():
            cost = float(spec.get("cost", 0.0))
            if cost > cost_budget + 1e-9 or count_budget <= 0:
                continue
            imm = float(spec.get("imm", 0.0))
            fut = 0.0
            for (e, o), nxt in trans.items():
                if e != exp:
                    continue
                fut += float(probs.get((exp, o), 0.0)) * self.value(
                    nxt, h - 1, cost_budget - cost, count_budget - 1)
            total = imm + self.gamma * fut
            considered[exp] = round(total, 4)
            if total > best_total:
                best_exp, best_total, best_imm, best_fut = exp, total, imm, fut
        if best_exp is None:
            return Plan(None, mode.value, h, 0.0, 0.0, 0.0, considered)
        return Plan(best_exp, mode.value, h, round(best_total, 4),
                    round(best_imm, 4), round(best_fut, 4), considered)

    # ── V19.6: MIN_COST_TO_RESOLUTION objective (independent of decision value) ─

    def cost_value(self, state: str, horizon: int, cost_left: float,
                   count_left: int) -> float:
        """Minimum expected acquisition cost to reach a RESOLVED state, or inf.

        Resolved states (marked in the model) cost 0.  A branch that cannot be
        resolved within horizon/count/budget is infeasible (inf) — never a silent 0.
        """
        node = self.model.get(state, {})
        if node.get("resolved"):
            return 0.0
        if horizon <= 0 or count_left <= 0 or cost_left <= 0:
            return float("inf")
        key = (state, horizon, round(cost_left, 4), count_left)
        memo = getattr(self, "_cmemo", None)
        if memo is None:
            memo = self._cmemo = {}
        if key in memo:
            return memo[key]
        exps = node.get("experiments", {})
        trans = node.get("transitions", {})
        probs = node.get("obs_prob", {})
        best = float("inf")
        for exp, spec in exps.items():
            cost = float(spec.get("cost", 0.0))
            if cost > cost_left + 1e-9:
                continue
            fut, ok = 0.0, True
            for (e, o), nxt in trans.items():
                if e != exp:
                    continue
                v = self.cost_value(nxt, horizon - 1, cost_left - cost, count_left - 1)
                if v == float("inf"):
                    ok = False
                    break
                fut += float(probs.get((exp, o), 0.0)) * v
            if ok:
                best = min(best, cost + fut)
        memo[key] = best
        return best

    def select_cost(self, state: str, *, horizon: int = 1, cost_budget: float = 1e9,
                    count_budget: int = 10) -> Plan:
        """Select the experiment minimizing expected cost-to-resolution."""
        self._cmemo = {}
        node = self.model.get(state, {})
        exps = node.get("experiments", {})
        trans = node.get("transitions", {})
        probs = node.get("obs_prob", {})
        considered: Dict[str, float] = {}
        best_exp, best_cost = None, float("inf")
        h = max(1, horizon)
        for exp, spec in exps.items():
            cost = float(spec.get("cost", 0.0))
            if cost > cost_budget + 1e-9 or count_budget <= 0:
                continue
            fut, ok = 0.0, True
            for (e, o), nxt in trans.items():
                if e != exp:
                    continue
                v = self.cost_value(nxt, h - 1, cost_budget - cost, count_budget - 1)
                if v == float("inf"):
                    ok = False
                    break
                fut += float(probs.get((exp, o), 0.0)) * v
            if not ok:
                continue
            total = cost + fut
            considered[exp] = round(total, 4)
            if total < best_cost:
                best_exp, best_cost = exp, total
        if best_exp is None:
            return Plan(None, PlanningObjective.MIN_COST_TO_RESOLUTION.value, h,
                        float("inf"), 0.0, 0.0, considered)
        return Plan(best_exp, PlanningObjective.MIN_COST_TO_RESOLUTION.value, h,
                    round(best_cost, 4), 0.0, 0.0, considered)

    def replan(self, state_after_observation: str, **kwargs) -> Plan:
        """Recompute the plan from the observed successor state (no precompute).

        Args:
            state_after_observation: the successor state id the world produced.
            **kwargs: forwarded to `select`.

        Returns:
            A fresh Plan.
        """
        self._memo.clear()
        return self.select(state_after_observation, **kwargs)
