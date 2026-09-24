"""
Planner-aware VoI tests (V6): does the planner value FUTURE information?

Falsifiers: H=1 planner == greedy; the planner diverges from greedy only where a
future experiment is unlocked; a budget trap is avoided; unaffordable decisive
experiments yield UNRESOLVED (never forced confidence); replanning after an
observation changes the next plan; the model carries no ground truth.
"""

from telos.core.discovery.planner import PlannerAwareSelector, PlannerMode


def _state(exps, trans=None, probs=None):
    return {"experiments": exps, "transitions": trans or {}, "obs_prob": probs or {}}


def _unlocking():
    t = {("A", 0): "A0", ("A", 1): "A1", ("B", 0): "B0", ("B", 1): "B1"}
    p = {(e, o): 0.5 for (e, o) in t}
    return {"s0": _state({"A": {"cost": 1, "imm": 4.0}, "B": {"cost": 1, "imm": 3.0}}, t, p),
            "A0": _state({}), "A1": _state({}),
            "B0": _state({"C": {"cost": 1, "imm": 12.0}}), "B1": _state({})}


def _bottleneck():
    t = {("X", 0): "X0", ("X", 1): "X1", ("Z", 0): "Z0", ("Z", 1): "Z1"}
    p = {(e, o): 0.5 for (e, o) in t}
    return {"s0": _state({"X": {"cost": 1, "imm": 0.0}, "Z": {"cost": 1, "imm": 2.0}}, t, p),
            "X0": _state({"Y": {"cost": 1, "imm": 10.0}}), "X1": _state({}),
            "Z0": _state({}), "Z1": _state({})}


def _trap():
    t = {("A", 0): "A0", ("A", 1): "A1", ("B", 0): "B0", ("B", 1): "B1"}
    p = {(e, o): 0.5 for (e, o) in t}
    return {"s0": _state({"A": {"cost": 4, "imm": 5.0}, "B": {"cost": 1, "imm": 1.0}}, t, p),
            "A0": _state({"C": {"cost": 3, "imm": 12.0}}), "A1": _state({}),
            "B0": _state({"C": {"cost": 3, "imm": 12.0}}), "B1": _state({})}


def test_h1_planner_equals_greedy():
    for model in (_unlocking(), _bottleneck(), _trap()):
        sel = PlannerAwareSelector(model)
        g = sel.select("s0", mode=PlannerMode.GREEDY, cost_budget=5.0)
        p1 = sel.select("s0", mode=PlannerMode.PLANNER_AWARE, horizon=1, cost_budget=5.0)
        assert g.experiment == p1.experiment


def test_unlocking_prefers_the_experiment_that_unlocks_the_future():
    sel = PlannerAwareSelector(_unlocking())
    g = sel.select("s0", mode=PlannerMode.GREEDY, cost_budget=5.0)
    p = sel.select("s0", mode=PlannerMode.PLANNER_AWARE, horizon=3, cost_budget=5.0)
    assert g.experiment == "A"          # highest immediate
    assert p.experiment == "B"          # unlocks C
    assert p.expected_value > g.expected_value


def test_bottleneck_values_option_value():
    sel = PlannerAwareSelector(_bottleneck())
    g = sel.select("s0", mode=PlannerMode.GREEDY, cost_budget=5.0)
    p = sel.select("s0", mode=PlannerMode.PLANNER_AWARE, horizon=3, cost_budget=5.0)
    assert g.experiment == "Z"          # immediate 2 > 0
    assert p.experiment == "X"          # gates Y


def test_trap_experiment_avoided_under_budget():
    sel = PlannerAwareSelector(_trap())
    g = sel.select("s0", mode=PlannerMode.GREEDY, cost_budget=5.0)
    p = sel.select("s0", mode=PlannerMode.PLANNER_AWARE, horizon=3, cost_budget=5.0)
    assert g.experiment == "A"          # looks best, consumes budget
    assert p.experiment == "B"          # preserves the decisive C


def test_unaffordable_decisive_experiment_is_unresolved():
    model = {"s0": _state({"C": {"cost": 10, "imm": 20.0}}), "C0": _state({}), "C1": _state({})}
    sel = PlannerAwareSelector(model)
    p = sel.select("s0", mode=PlannerMode.PLANNER_AWARE, horizon=3, cost_budget=5.0)
    assert p.experiment is None         # UNRESOLVED — no forced confidence
    assert p.expected_value == 0.0


def test_replanning_after_observation_changes_the_plan():
    sel = PlannerAwareSelector(_unlocking())
    first = sel.select("s0", mode=PlannerMode.PLANNER_AWARE, horizon=3, cost_budget=5.0)
    assert first.experiment == "B"
    after0 = sel.replan("B0", mode=PlannerMode.PLANNER_AWARE, horizon=3, cost_budget=4.0)
    after1 = sel.replan("B1", mode=PlannerMode.PLANNER_AWARE, horizon=3, cost_budget=4.0)
    assert after0.experiment != after1.experiment   # C vs none


def test_model_carries_no_ground_truth():
    for model in (_unlocking(), _bottleneck(), _trap()):
        keys = set()
        for node in model.values():
            keys |= set(node.keys())
        assert keys <= {"experiments", "transitions", "obs_prob"}
