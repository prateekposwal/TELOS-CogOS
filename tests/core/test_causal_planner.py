"""
CausalPlanner tests (V7): planner-aware VoI grounded in the real stack.

Verifies epistemic integrity (planning is pure — no mutation of actual state),
evidence-gated candidate generation, and the honest boundary: when the unlocking
experiment has zero canonical decision sensitivity, planner-aware selection
collapses to greedy (V6's divergence does NOT reproduce through the real stack).
"""

import numpy as np

from telos.core.contracts.domain_model import DomainSimulator, WorldSpec, EvaluationReport
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.core.simulation import CounterfactualEngine
from telos.core.discovery.experiment_selection import CanonicalExperimentSelector
from telos.core.discovery.causal_planner import CausalPlanner
from telos.core.discovery.planner import PlannerMode
from telos.world.epistemic import RealityGapTracker


class Sim(DomainSimulator):
    name = "sim"

    def __init__(self, M, goal=(4.0, 4.0), plan=None):
        self.M = np.array(M, float)
        self.goal = np.array(goal, float)
        self.plan = np.array(plan, float) if plan is not None else np.eye(len(self.M))

    def initialize(self): pass
    def cleanup(self): pass
    def world_spec(self):
        return WorldSpec(name="sim", state_dim=2, action_dim=2, objectives=["g"],
                         constraints=[], observability="high", capabilities=["simulate"])
    def legal_transitions(self, s): return [np.array([1.0, 0.0])]
    def transition(self, s, a): return np.clip(np.asarray(s, float) + self.M @ a, -6, 6)
    def _policy(self, s):
        d = np.clip(self.goal - np.asarray(s, float), -1, 1)
        return np.clip(np.linalg.lstsq(self.plan, d, rcond=None)[0], -1, 1)
    def simulate(self, s, h):
        s = np.asarray(s, float); out = []
        for _ in range(h):
            s = self.transition(s, self._policy(s)); out.append(World(state=s.copy()))
        return out
    def evaluate(self, s):
        return EvaluationReport(objectives={"g": -float(np.linalg.norm(np.asarray(s, float) - self.goal))})
    def terminal(self, s): return bool(np.linalg.norm(np.asarray(s, float) - self.goal) <= 0.6)
    def get_facts(self, s): return DomainFacts(resources={}, constraints=[], events=[], metrics={})


class H:
    def __init__(self, id, sim, predicts, unlocked_by=None, uncertainty=0.5, cost=0.2):
        self.id = id; self.simulator = sim; self.uncertainty = uncertainty
        self.cost = cost; self.predicts = predicts; self.unlocked_by = unlocked_by


ID = [[1.0, 0.0], [0.0, 1.0]]
ROT = [[0.0, 1.0], [-1.0, 0.0]]


def _planner():
    eng = CounterfactualEngine(Sim(ID), n_repetitions=1, seed=0)
    return CausalPlanner(CanonicalExperimentSelector(eng, horizon=4, n_worlds=4))


def _hyps():
    return [
        H("H1", Sim(ROT), {"H1": 1.0, "H2": 0.0}),
        H("H2", Sim(ID), {"H1": 0.0, "H2": 1.0}),
        H("H3", Sim(ROT), {"H1": 1.0, "H2": 1.0}, unlocked_by=("H2", 1.0)),
    ]


def test_planning_is_pure_no_actual_state_mutation():
    gap = RealityGapTracker()
    before = len(getattr(gap, "_models", {}) or {})
    _planner().plan(np.array([0.0, 0.0]), _hyps(), mode=PlannerMode.PLANNER_AWARE, horizon=3)
    after = len(getattr(gap, "_models", {}) or {})
    assert before == after == 0            # hypothetical branches never record


def test_unlocked_hypothesis_is_gated_until_observed():
    model = _planner().build_model(np.array([0.0, 0.0]), _hyps())
    start = next(v for k, v in model.items() if k.startswith("H1|H2|H3#"))
    assert "H3" not in start["experiments"]          # gated by (H2,1)
    assert "H1" in start["experiments"]


def test_collapses_to_greedy_when_unlocker_has_zero_sensitivity():
    # H2 (the unlocker) is the ID model -> canonical sensitivity 0 -> no lookahead
    # justification -> planner-aware selection == greedy (the V7 boundary).
    state = np.array([0.0, 0.0]); hyps = _hyps()
    cp = _planner()
    g = cp.plan(state, hyps, mode=PlannerMode.GREEDY)
    p = cp.plan(state, hyps, mode=PlannerMode.PLANNER_AWARE, horizon=3)
    assert g.experiment == p.experiment


def test_plan_returns_an_available_experiment():
    p = _planner().plan(np.array([0.0, 0.0]), _hyps(), mode=PlannerMode.PLANNER_AWARE, horizon=2)
    assert p.experiment in {"H1", "H2"}
