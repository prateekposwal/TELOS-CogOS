"""V19.4 — first-class Experiment (action) vs Hypothesis (belief).

Verifies the representation is separate, cost is independent of hypothesis id,
outcomes may be categorical/vector, successors partition the live hypotheses, and
spent experiments are eliminated.
"""

import numpy as np

from telos.core.contracts.domain_model import WorldSpec, EvaluationReport
from telos.core.simulation import CounterfactualEngine
from telos.core.discovery.experiment_selection import CanonicalExperimentSelector
from telos.core.discovery.causal_planner import CausalPlanner, Experiment
from telos.world.world import World
from telos.world.facts import DomainFacts


class Sim:
    name = "sim"
    def initialize(self): pass
    def cleanup(self): pass
    def world_spec(self):
        return WorldSpec(name="sim", state_dim=2, action_dim=2, objectives=["g"],
                         constraints=[], observability="high", capabilities=["simulate"])
    def legal_transitions(self, s): return [np.array([1.0, 0.0])]
    def transition(self, s, a): return np.asarray(s, float)
    def simulate(self, s, h): return [World(state=np.zeros(2)) for _ in range(h)]
    def evaluate(self, s): return EvaluationReport(objectives={"g": 0.0})
    def terminal(self, s): return False
    def get_facts(self, s): return DomainFacts(resources={}, constraints=[], events=[], metrics={})


class H:
    def __init__(self, hid):
        self.id = hid; self.simulator = Sim(); self.uncertainty = .5
        self.cost = .2; self.predicts = {}; self.unlocked_by = None


HYP = ["H1", "H2", "H3", "H4"]


def _planner():
    sel = CanonicalExperimentSelector(CounterfactualEngine(Sim(), n_repetitions=1, seed=0),
                                      horizon=3, n_worlds=4)
    return CausalPlanner(sel, gamma=1.0, max_model_depth=4)


def _exps(outcomes, cost=1.0):
    return [Experiment(eid, cost=cost, predict=lambda h, eid=eid, o=o: o[HYP.index(h.id)])
            for eid, o in outcomes.items()]


def test_experiment_is_not_a_hypothesis():
    e = Experiment("E1", cost=3.0, predict=lambda h: 0)
    h = H("H1")
    assert e.id == "E1" and e.cost == 3.0
    assert not hasattr(h, "predict")          # hypotheses don't predict experiment outcomes
    assert h.id == "H1" and e.id != h.id


def test_cost_is_independent_of_hypothesis_id():
    model = _planner().build_experiment_model(np.zeros(2), [H(x) for x in HYP],
                                              _exps({"E1": (0, 0, 1, 1), "E9": (0, 1, 0, 1)}, cost=7.0))
    key = "S" + str(tuple(sorted(HYP))) + "|"
    assert model[key]["experiments"]["E1"]["cost"] == 7.0     # experiment cost, not hyp cost 0.2


def test_multiple_experiments_and_successor_partition():
    model = _planner().build_experiment_model(
        np.zeros(2), [H(x) for x in HYP],
        _exps({"E1": (0, 0, 1, 1), "E2": (0, 1, 0, 1)}))
    key = "S" + str(tuple(sorted(HYP))) + "|"
    assert set(model[key]["experiments"]) == {"E1", "E2"}
    # E1 outcomes split into two successors of size 2
    succ = [k for (e, o), k in model[key]["transitions"].items() if e == "E1"]
    sizes = sorted(len(model[s]["experiments"]) and s.split("|")[0].count("H") for s in succ)
    assert sizes == [2, 2]


def test_categorical_outcomes_by_identity():
    model = _planner().build_experiment_model(
        np.zeros(2), [H(x) for x in HYP], _exps({"E1": ("A", "A", "B", "B")}))
    key = "S" + str(tuple(sorted(HYP))) + "|"
    assert list(model[key]["experiments"]) == ["E1"]          # string outcomes accepted


def test_vector_outcomes_by_identity():
    model = _planner().build_experiment_model(
        np.zeros(2), [H(x) for x in HYP],
        _exps({"E1": ((0, 1), (0, 1), (1, 0), (1, 0))}))
    key = "S" + str(tuple(sorted(HYP))) + "|"
    assert list(model[key]["experiments"]) == ["E1"]          # vector outcomes accepted


def test_spent_experiment_is_eliminated():
    model = _planner().build_experiment_model(
        np.zeros(2), [H(x) for x in HYP], _exps({"E1": (0, 0, 1, 1), "E2": (0, 1, 0, 1)}))
    key = "S" + str(tuple(sorted(HYP))) + "|"
    succ = next(k for (e, o), k in model[key]["transitions"].items() if e == "E1")
    assert "E1" not in model[succ]["experiments"]             # never repeated
    assert "E2" in model[succ]["experiments"]


# ── V19.6: explicit planning objective ──────────────────────────────────────
def _exp_env(outcomes):
    return [Experiment(eid, cost=c, predict=lambda h, eid=eid, o=o: o[HYP.index(h.id)])
            for eid, (c, o) in outcomes.items()]


def test_min_cost_objective_picks_cheap_path():
    from telos.core.discovery.planner import PlanningObjective
    env = {"E1": (1, (0, 0, 1, 1)), "E2": (1, (0, 1, 0, 1)), "E3": (10, (0, 1, 2, 3))}
    p = _planner().plan_experiments(np.zeros(2), [H(x) for x in HYP], _exp_env(env),
                                    mode=__import__("telos.core.discovery.planner",
                                                    fromlist=["PlannerMode"]).PlannerMode.PLANNER_AWARE,
                                    horizon=4, objective=PlanningObjective.MIN_COST_TO_RESOLUTION)
    assert p.experiment == "E1"                       # cheap path, not expensive E3


def test_min_cost_objective_picks_cheap_when_partitions_identical():
    from telos.core.discovery.planner import PlanningObjective
    env = {"Echeap": (1, (0, 1, 2, 3)), "Eexpensive": (9, (0, 1, 2, 3))}
    p = _planner().plan_experiments(np.zeros(2), [H(x) for x in HYP], _exp_env(env),
                                    horizon=4, objective=PlanningObjective.MIN_COST_TO_RESOLUTION)
    assert p.experiment == "Echeap"


def test_objectives_separate_selection():
    from telos.core.discovery.planner import PlanningObjective
    env = {"E1": (1, (0, 0, 1, 1)), "E2": (1, (0, 1, 0, 1)), "E3": (10, (0, 1, 2, 3))}
    hs = [H(x) for x in HYP]
    mc = _planner().plan_experiments(np.zeros(2), hs, _exp_env(env), horizon=4,
                                     objective=PlanningObjective.MIN_COST_TO_RESOLUTION)
    dv = _planner().plan_experiments(np.zeros(2), hs, _exp_env(env), horizon=4,
                                     objective=PlanningObjective.DECISION_VALUE)
    assert mc.experiment == "E1"                      # min cost -> cheap path
    assert dv.experiment is not None and dv.experiment != mc.experiment  # objective changes selection
