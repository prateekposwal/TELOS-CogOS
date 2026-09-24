"""
CausalPlanner (V7) — planner-aware VoI grounded in the real causal stack.

V6 proved lookahead over a hand-authored transition tree. V7 builds the SAME
planner model from the REAL machinery:

    candidate hypotheses (DomainSimulator each)  ─┐
    immediate VoI  ← CanonicalExperimentSelector ←─┤  (CounterfactualEngine)
    successors     ← the hypotheses' own predicted outcomes (their model)
                                                   ┘
    → PlannerAwareSelector (GREEDY | PLANNER_AWARE, depth only)

There is NO second valuation mechanism: immediate values come from the canonical
selector; only the DEPTH of planning differs between modes.

Epistemic integrity: `plan()` is pure — it reads an immutable snapshot and never
mutates actual state. Hypothetical observations update a LOCAL belief only.
Callers commit to actual state (RealityGapTracker/Evidence/TheoryBuilder/
KnowledgeGraph) exclusively in `execute_actual`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from telos.core.discovery.experiment_selection import (
    CanonicalExperimentSelector, Hypothesis,
)
from telos.core.discovery.planner import PlannerAwareSelector, PlannerMode, Plan


def _round(v: float) -> float:
    return round(float(v), 4)


def _key(survivors, observed) -> str:
    """Stable key for a planner state (surviving hyps + observed tokens)."""
    obs = ",".join(f"{e}:{_round(o)}" for (e, o) in sorted(observed))
    return "|".join(survivors) + "#" + obs


class CausalPlanner:
    """Plans over real hypotheses using the canonical immediate VoI.

    Args:
        selector: the canonical experiment selector (immediate VoI).
        gamma: future discount.
        max_model_depth: cap on the model's horizon (bounds the state space).
    """

    def __init__(self, selector: CanonicalExperimentSelector, gamma: float = 1.0,
                 max_model_depth: int = 4):
        self.selector = selector
        self.gamma = float(gamma)
        self.max_model_depth = max_model_depth

    # ── Real immediate values (canonical) ────────────────────────────────────

    def immediate_values(self, state, hypotheses: List[Any]) -> Dict[str, float]:
        """Per-hypothesis decision sensitivity from the canonical selector.

        Args:
            state: current state.
            hypotheses: candidate hypotheses (id/simulator/uncertainty/cost).

        Returns:
            {hypothesis_id: canonical sensitivity} (UNKNOWN hypotheses omitted).
        """
        hyps = [Hypothesis(h.id, h.simulator, h.uncertainty, h.cost) for h in hypotheses]
        opts = self.selector.evaluate(state, hyps)
        return {o.hypothesis_id: float(o.sensitivity or 0.0)
                for o in opts if o.status == "VALUED"}

    # ── Build the model from the hypotheses' OWN predictions ─────────────────

    def build_model(self, state, hypotheses: List[Any]) -> Dict[str, Dict[str, Any]]:
        """Construct the planner model from the real hypotheses.

        A state is the set of SURVIVING hypotheses. Testing experiment `e`
        yields, for each distinct predicted diagnostic, the successor set of
        hypotheses consistent with that observation — the agent's own belief
        update, NOT ground truth.

        Args:
            state: current state.
            hypotheses: candidate hypotheses (id/predicts/cost/...).

        Returns:
            A planner model dict (states → experiments/transitions/obs_prob).
        """
        imm = self.immediate_values(state, hypotheses)
        cost = {h.id: float(h.cost) for h in hypotheses}
        predicts = {h.id: dict(h.predicts) for h in hypotheses}
        # candidate generation is EVIDENCE-GATED: a hypothesis is only testable
        # once an observation puts it on the table (its `unlocked_by` token).
        unlocked = {h.id: getattr(h, "unlocked_by", None) for h in hypotheses}
        start = (tuple(sorted(h.id for h in hypotheses)), frozenset())

        model: Dict[str, Dict[str, Any]] = {}
        seen = {start}
        frontier = [start]
        depth = 0
        while frontier and depth < self.max_model_depth:
            depth += 1
            nxt = []
            for S, obs in frontier:
                key = _key(S, obs)
                if key in model:
                    continue
                exps: Dict[str, Any] = {}
                trans: Dict[Any, str] = {}
                probs: Dict[Any, float] = {}
                for e in S:
                    if unlocked.get(e) is not None and unlocked[e] not in obs:
                        continue                     # not yet on the table
                    exps[e] = {"cost": cost[e], "imm": imm.get(e, 0.0)}
                    for o in sorted({_round(predicts[h].get(e, 0.0)) for h in S}):
                        succ_h = tuple(h for h in S
                                       if _round(predicts[h].get(e, 0.0)) == o)
                        succ = (succ_h, obs | frozenset({(e, o)}))
                        trans[(e, o)] = _key(succ_h, succ[1])
                        probs[(e, o)] = len(succ_h) / len(S)
                        if succ not in seen:
                            seen.add(succ)
                            nxt.append(succ)
                model[key] = {"experiments": exps, "transitions": trans, "obs_prob": probs}
            frontier = nxt
        return model

    # ── Plan (pure) ──────────────────────────────────────────────────────────

    def plan(self, state, hypotheses: List[Any], *, mode: PlannerMode = PlannerMode.PLANNER_AWARE,
             horizon: int = 1, cost_budget: float = 1e9,
             count_budget: int = 10) -> Plan:
        """Select an experiment (pure; never mutates actual state).

        Args:
            state: current state.
            hypotheses: candidate hypotheses.
            mode: GREEDY or PLANNER_AWARE.
            horizon: plan depth (ignored in GREEDY).
            cost_budget: cost cap.
            count_budget: experiment-count cap.

        Returns:
            The Plan (experiment + expected value + per-experiment values).
        """
        model = self.build_model(state, hypotheses)
        full = _key(tuple(sorted(h.id for h in hypotheses)), frozenset())
        sel = PlannerAwareSelector(model, gamma=self.gamma)
        return sel.select(full, mode=mode, horizon=horizon,
                          cost_budget=cost_budget, count_budget=count_budget)
