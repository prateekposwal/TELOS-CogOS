"""
Canonical experiment-selection tests (V3).

Proves the ONE authoritative counterfactual-value mechanism: experiment choice
uses CounterfactualEngine.compute_value_of_information, prefers decision-relevant
information over mere uncertainty reduction, and represents unvaluable
hypotheses as UNKNOWN (never zero-value truth).
"""

import numpy as np

from telos.core.contracts.domain_model import DomainSimulator, WorldSpec, EvaluationReport
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.core.simulation import CounterfactualEngine
from telos.core.discovery import CanonicalExperimentSelector, Hypothesis


class Sim(DomainSimulator):
    """next = clip(state + M @ action); the committed plan assumes `plan` (id)."""

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
    def __init__(self): super().__init__(ID)
    def simulate(self, s, h): raise RuntimeError("no world model")
    def transition(self, s, a): raise RuntimeError("unsupported")


ID = [[1.0, 0.0], [0.0, 1.0]]
ROT = [[0.0, 1.0], [-1.0, 0.0]]


def _selector():
    return CanonicalExperimentSelector(CounterfactualEngine(Sim(ID), n_repetitions=1, seed=0),
                                       horizon=4, n_worlds=4)


def test_prefers_decision_relevant_over_uncertain_and_cheap():
    sel = _selector()
    inert = Hypothesis("inert", Sim(ID), uncertainty=0.9, test_cost=0.1)   # high unc, cheap, inert
    decisive = Hypothesis("decisive", Sim(ROT), uncertainty=0.6, test_cost=0.5)  # decisive, costly
    choice = sel.select(np.array([0.0, 0.0]), [inert, decisive])
    assert choice.hypothesis_id == "decisive"          # canonical decision value wins
    # the old uncertainty-only rule would pick the inert one
    old = max([inert, decisive], key=lambda h: h.uncertainty / h.test_cost)
    assert old.id == "inert"
    assert choice.hypothesis_id != old.id


def test_sensitivity_is_from_the_canonical_engine():
    sel = _selector()
    opts = {o.hypothesis_id: o for o in sel.evaluate(
        np.array([0.0, 0.0]), [Hypothesis("inert", Sim(ID)), Hypothesis("decisive", Sim(ROT))])}
    assert opts["inert"].sensitivity == 0.0
    assert opts["decisive"].sensitivity > 0.0


def test_unvaluable_hypothesis_is_unknown_not_zero():
    sel = _selector()
    opt = next(o for o in sel.evaluate(
        np.array([0.0, 0.0]), [Hypothesis("x", Broken(), uncertainty=0.99, test_cost=0.01)]))
    assert opt.status == "UNKNOWN"
    assert opt.value is None            # not a fabricated 0.0
    assert sel.select(np.array([0.0, 0.0]), [Hypothesis("x", Broken())]) is None
