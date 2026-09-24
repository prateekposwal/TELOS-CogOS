"""
Adaptive experiment-sequence falsifiers (V4).

Proves the loop is genuinely state-dependent: new evidence changes the NEXT
experiment; the sequence is never precomputed; budget/stopping/UNKNOWN cannot be
bypassed; falsified hypotheses are not resurrected.
"""

import numpy as np

from telos.core.contracts.domain_model import DomainSimulator, WorldSpec, EvaluationReport
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.core.simulation import CounterfactualEngine
from telos.core.discovery import CanonicalExperimentSelector
from telos.core.discovery.adaptive import AdaptiveExperimentPlanner, Candidate, StopReason


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


class Broken(Sim):
    name = "broken"
    def __init__(self): super().__init__([[1.0, 0.0], [0.0, 1.0]])
    def simulate(self, s, h): raise RuntimeError("no model")


ID = [[1.0, 0.0], [0.0, 1.0]]
ROT = [[0.0, 1.0], [-1.0, 0.0]]
HALF = [[0.5, 0.0], [0.0, 0.5]]
PRED = {"H1": {"H1": 1.0, "H2": 0.0, "H3": 0.0, "H4": 0.0},
        "H2": {"H1": 0.0, "H2": 1.0, "H3": 0.0, "H4": 0.0},
        "H3": {"H1": 0.0, "H2": 0.0, "H3": 1.0, "H4": 0.0},
        "H4": {"H1": 1.0, "H2": 0.0, "H3": 0.0, "H4": 1.0}}
MODELS = {"H1": ROT, "H2": HALF, "H3": ID, "H4": ROT}


class ObsWorld:
    def __init__(self, truth): self.truth = truth
    def observation(self, exp_id): return PRED[self.truth].get(exp_id, 0.0)


def _planner(ids=("H1", "H2", "H3"), **kw):
    engine = CounterfactualEngine(Sim(ID), n_repetitions=1, seed=0)
    sel = CanonicalExperimentSelector(engine, horizon=4, n_worlds=4)
    cands = [Candidate(c, Sim(MODELS[c]), 0.5, 0.2, PRED[c]) for c in ids]
    return AdaptiveExperimentPlanner(sel, cands, **kw)


def test_same_state_different_observation_different_next():
    refuted = _planner().run(np.array([0.0, 0.0]), ObsWorld("H2"))   # A observed 0
    supported = _planner().run(np.array([0.0, 0.0]), ObsWorld("H1"))  # A observed 1
    assert refuted["sequence"] == ["H1", "H2"]
    assert supported["sequence"] == ["H1"]                        # stops
    assert refuted["sequence"][1:] != supported["sequence"][1:]   # NEXT differs


def test_previously_valuable_experiment_not_executed():
    # H4 is rank 2 at the start, but A's evidence falsifies it -> never run.
    r = _planner(ids=("H1", "H2", "H3", "H4")).run(np.array([0.0, 0.0]), ObsWorld("H2"))
    assert "H4" in [o["hypothesis_id"] for o in
                    sorted(r["steps"][0]["options"], key=lambda o: -(o["value"] or 0))[:2]]
    assert "H4" not in r["sequence"]


def test_budget_is_never_exceeded():
    r = _planner(max_experiments=2, cost_budget=0.3).run(np.array([0.0, 0.0]), ObsWorld("H3"))
    assert r["experiments"] <= 2
    assert r["cost"] <= 0.3 + 1e-9


def test_stops_safely_when_no_value():
    inert = Candidate("inert", Broken(), 0.9, 0.05, {"inert": 0.0})
    engine = CounterfactualEngine(Sim(ID), n_repetitions=1, seed=0)
    p = AdaptiveExperimentPlanner(CanonicalExperimentSelector(engine, 4, 4), [inert])
    r = p.run(np.array([0.0, 0.0]), ObsWorld("H1"))
    assert r["experiments"] == 0
    assert r["stop_reason"] == StopReason.NO_VALUE.value


def test_unknown_is_not_confidence():
    inert = Candidate("inert", Broken(), 0.95, 0.05, {"inert": 0.0})
    engine = CounterfactualEngine(Sim(ID), n_repetitions=1, seed=0)
    p = AdaptiveExperimentPlanner(CanonicalExperimentSelector(engine, 4, 4), [inert])
    choice, options = p.select_next(np.array([0.0, 0.0]))
    assert choice is None
    assert options[0].status == "UNKNOWN" and options[0].value is None


def test_falsified_stays_falsified():
    p = _planner()
    p.observe("H1", 0.0)                          # refutes H1
    assert next(c for c in p.candidates if c.id == "H1").status == "falsified"
    p.observe("H2", 1.0)                          # later evidence
    assert next(c for c in p.candidates if c.id == "H1").status == "falsified"


def test_every_run_terminates_with_a_reason():
    for truth in ("H1", "H2", "H3"):
        r = _planner().run(np.array([0.0, 0.0]), ObsWorld(truth))
        assert r["stop_reason"] is not None
