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


def _ekey(S, observed) -> str:
    """State key that tolerates NON-numeric (categorical/vector) outcomes."""
    return "S" + str(tuple(S)) + "|" + ",".join(sorted(f"{e}:{o}" for (e, o) in observed))


class Experiment:
    """V19.4 — a first-class EXPERIMENT (an action), distinct from a Hypothesis
    (a belief).  Representation only: no VoI, no scoring, no optimization.

    Args:
        id: stable id.
        cost: acquisition cost.
        predict: callable `hypothesis -> outcome` (scalar, categorical, or vector).
        outcome_space: optional declared outcome set (informational).
    """
    def __init__(self, id: str, cost: float = 1.0, predict: Any = None,
                 outcome_space: Any = None):
        self.id = id
        self.cost = float(cost)
        self.predict = predict
        self.outcome_space = outcome_space


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

    # ── V19.4: first-class Experiment (action), separate from Hypothesis ─────

    def build_experiment_model(self, state, hypotheses: List[Any],
                               experiments: List[Any]) -> Dict[str, Dict[str, Any]]:
        """Model where EXPERIMENTS (actions) are distinct from HYPOTHESES (belief).

        Same shape as `build_model`, so the existing `PlannerAwareSelector`
        consumes it unchanged.  An experiment `e` has `e.cost` and
        `e.predict(hypothesis) -> outcome`; an outcome partitions the surviving
        hypotheses.  Outcomes may be scalars OR arbitrary (categorical/vector)
        values — compared by identity, never numerical distance.
        """
        hids = [h.id for h in hypotheses]
        by_id = {h.id: h for h in hypotheses}
        cost = {e.id: float(e.cost) for e in experiments}

        def okey(v: Any) -> Any:
            if isinstance(v, (list, tuple)):
                return tuple(round(float(x), 6) for x in v)
            if isinstance(v, float):
                return round(v, 6)
            return v

        def _numeric(vals) -> bool:
            return all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       for v in vals)

        def imm(S) -> Dict[str, float]:
            out = {}
            for e in experiments:
                vals = [e.predict(by_id[h]) for h in S]
                if _numeric(vals):
                    out[e.id] = max(float(v) for v in vals) - min(float(v) for v in vals)
                elif any(isinstance(v, (list, tuple)) for v in vals) and all(
                        isinstance(x, (int, float)) for v in vals
                        for x in (v if isinstance(v, (list, tuple)) else [v])):
                    m = max(len(v) for v in vals if isinstance(v, (list, tuple)))
                    def vec(v):
                        v = list(v) if isinstance(v, (list, tuple)) else [v]
                        return [float(x) for x in v] + [0.0] * (m - len(v))
                    mat = [vec(v) for v in vals]
                    out[e.id] = max(max(c) - min(c) for c in zip(*mat))
                else:                                   # categorical: by identity
                    out[e.id] = float(len({okey(v) for v in vals}) - 1)
            return out

        start = (tuple(sorted(hids)), frozenset())
        model: Dict[str, Dict[str, Any]] = {}
        seen = {start}
        frontier = [start]
        depth = 0
        while frontier and depth < self.max_model_depth:
            depth += 1
            nxt = []
            for S, obs in frontier:
                key = _ekey(S, obs)
                if key in model:
                    continue
                used = {e_id for (e_id, _o) in obs}
                im = imm(S)
                exps: Dict[str, Any] = {}
                trans: Dict[Any, str] = {}
                probs: Dict[Any, float] = {}
                for e in experiments:
                    if e.id in used:
                        continue                      # never repeat a spent experiment
                    exps[e.id] = {"cost": cost[e.id], "imm": im[e.id]}
                    outcomes = sorted({okey(e.predict(by_id[h])) for h in S},
                                      key=lambda z: str(z))
                    for o in outcomes:
                        succ_h = tuple(h for h in S if okey(e.predict(by_id[h])) == o)
                        succ = (succ_h, obs | frozenset({(e.id, o)}))
                        trans[(e.id, o)] = _ekey(succ_h, succ[1])
                        probs[(e.id, o)] = len(succ_h) / len(S)
                        if succ not in seen:
                            seen.add(succ)
                            nxt.append(succ)
                model[key] = {"experiments": exps, "transitions": trans, "obs_prob": probs}
            frontier = nxt
        return model

    def plan_experiments(self, state, hypotheses: List[Any], experiments: List[Any], *,
                         mode: PlannerMode = PlannerMode.PLANNER_AWARE, horizon: int = 1,
                         cost_budget: float = 1e9, count_budget: int = 10) -> Plan:
        """Plan over EXPERIMENTS using the EXISTING search (unchanged algorithm)."""
        model = self.build_experiment_model(state, hypotheses, experiments)
        full = _ekey(tuple(sorted(h.id for h in hypotheses)), frozenset())
        sel = PlannerAwareSelector(model, gamma=self.gamma)
        return sel.select(full, mode=mode, horizon=horizon,
                          cost_budget=cost_budget, count_budget=count_budget)

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
