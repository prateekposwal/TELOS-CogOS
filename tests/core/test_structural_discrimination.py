"""V14 — structural discrimination in experiment selection.

Verifies the selector can value experiments that DISCRIMINATE between competing
causal structures, separately from V3's canonical decision VoI, with explicit
no-repeat termination.  Uses the same DomainSimulator shape as the planner tests.
"""

import numpy as np

from telos.core.contracts.domain_model import DomainSimulator, WorldSpec, EvaluationReport
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.core.simulation import CounterfactualEngine
from telos.core.discovery.experiment_selection import (
    CanonicalExperimentSelector, Hypothesis,
)


class Sim(DomainSimulator):
    name = "sim"

    def __init__(self, M, goal=(4.0, 4.0)):
        self.M = np.array(M, float); self.goal = np.array(goal, float)

    def initialize(self): pass
    def cleanup(self): pass
    def world_spec(self):
        return WorldSpec(name="sim", state_dim=2, action_dim=2, objectives=["g"],
                         constraints=[], observability="high", capabilities=["simulate"])
    def legal_transitions(self, s): return [np.array([1.0, 0.0])]
    def transition(self, s, a): return np.clip(np.asarray(s, float) + self.M @ a, -6, 6)
    def _policy(self, s):
        d = np.clip(self.goal - np.asarray(s, float), -1, 1)
        return np.clip(np.linalg.lstsq(self.M, d, rcond=None)[0], -1, 1)
    def simulate(self, s, h):
        s = np.asarray(s, float); out = []
        for _ in range(h):
            s = self.transition(s, self._policy(s)); out.append(World(state=s.copy()))
        return out
    def evaluate(self, s):
        return EvaluationReport(objectives={"g": -float(np.linalg.norm(np.asarray(s, float) - self.goal))})
    def terminal(self, s): return False
    def get_facts(self, s): return DomainFacts(resources={}, constraints=[], events=[], metrics={})


ID = [[1.0, 0.0], [0.0, 1.0]]


def _sel():
    return CanonicalExperimentSelector(CounterfactualEngine(Sim(ID), n_repetitions=1, seed=0),
                                       horizon=4, n_worlds=4)


def _hyp(hid, table):
    return Hypothesis(id=hid, simulator=Sim(ID), uncertainty=0.5, test_cost=0.2,
                      structure=hid, predictor=lambda e, t=table: t.get(e))


def test_decisive_falsifier_selects_the_discriminating_experiment():
    # E1 (do_v0): H_feedback == H_persistence_feedback  -> discrimination 0
    # E2 (persist_probe): they differ                    -> discrimination 1
    hs = [_hyp("feedback", {"do_v0": 1.0, "persist_probe": 0.0}),
          _hyp("persistence_feedback", {"do_v0": 1.0, "persist_probe": 1.0})]
    sel = _sel()
    opts = {o.experiment: o.structural_discrimination
            for o in sel.evaluate_structural(np.zeros(2), hs, ["do_v0", "persist_probe"])}
    assert opts["do_v0"] == 0.0
    assert opts["persist_probe"] == 1.0
    choice, reason, _ = sel.select_experiment(np.zeros(2), hs, ["do_v0", "persist_probe"])
    assert choice.experiment == "persist_probe"
    assert reason == "STRUCTURAL_DISCRIMINATION"


def test_identical_predictions_are_zero_discrimination():
    hs = [_hyp("a", {"e": 1.0}), _hyp("b", {"e": 1.0})]
    disc = _sel().structural_discrimination(hs, "e")
    assert disc == 0.0


def test_attempted_experiment_is_never_reselected():
    hs = [_hyp("a", {"e1": 1.0, "e2": 0.0}), _hyp("b", {"e1": 0.0, "e2": 1.0})]
    sel = _sel()
    choice, reason, _ = sel.select_experiment(np.zeros(2), hs, ["e1", "e2"], attempted={"e1"})
    assert choice.experiment == "e2"            # e1 not repeated
    # nothing left -> explicit exhaustion, not a silent default
    c2, r2, _ = sel.select_experiment(np.zeros(2), hs, ["e1", "e2"], attempted={"e1", "e2"})
    assert c2 is None and r2 == "EXHAUSTED"


def test_trajectory_predictions_are_supported():
    # V14b: a temporal probe returns a response TRAJECTORY; the same max-min
    # spread rule applies per step.  Identical trajectories => zero.
    diff = [_hyp("a", {"t": (1.0, 0.0, 0.0)}), _hyp("b", {"t": (0.0, 1.0, 0.0)})]
    assert _sel().structural_discrimination(diff, "t") == 1.0
    same = [_hyp("a", {"t": (1.0, 1.0)}), _hyp("b", {"t": (1.0, 1.0)})]
    assert _sel().structural_discrimination(same, "t") == 0.0


def test_uncertainty_aware_discrimination_is_a_significance_test():
    # When every hypothesis provides a standard error, a distinction is only
    # reported if spread/pooled-SE exceeds z_threshold (default 3).
    def mk(v, se):
        return Hypothesis(id=f"h{v}", simulator=Sim(ID), uncertainty=0.5, test_cost=0.2,
                          structure="s", predictor=lambda e, v=v: v,
                          predictor_se=lambda e, se=se: se)

    sig = [mk(0.648, 0.02), mk(0.782, 0.02)]      # spread 0.134, z ~ 4.7
    assert _sel().structural_discrimination(sig, "e") > 0.1
    non = [mk(0.60, 0.05), mk(0.65, 0.05)]        # spread 0.05, z ~ 0.7
    assert _sel().structural_discrimination(non, "e") == 0.0


def test_finite_df_widens_the_critical_value():
    # spread .5 with se .1 each -> ratio 3.54: passes the normal z=3 reference,
    # but at small df the Welch/Satterthwaite t critical value is larger.
    def mk(v, se, df):
        return Hypothesis(id=f"h{v}", simulator=Sim(ID), uncertainty=0.5, test_cost=0.2,
                          structure="s", predictor=lambda e, v=v: v,
                          predictor_se=lambda e, se=se: se,
                          predictor_df=lambda e, df=df: df)
    large = [mk(0.0, 0.1, 1000), mk(0.5, 0.1, 1000)]     # ~ normal
    assert _sel().structural_discrimination(large, "e") > 0.4
    small = [mk(0.0, 0.1, 2), mk(0.5, 0.1, 2)]           # df ~ 4 -> wider
    assert _sel().structural_discrimination(small, "e") == 0.0


def test_floating_point_noise_is_not_treated_as_significant():
    # Identifiability-challenge finding: a spread of ~1e-16 with SE ~1e-17 gave
    # z ~ 8 -> false STRUCTURAL_DISCRIMINATION.  Numerical noise must not pass.
    def mk(v, se):
        return Hypothesis(id=f"h{v}", simulator=Sim(ID), uncertainty=0.5, test_cost=0.2,
                          structure="s", predictor=lambda e, v=v: v,
                          predictor_se=lambda e, se=se: se)
    hs = [mk(0.5, 1e-17), mk(0.5 + 1e-16, 1e-17)]
    assert _sel().structural_discrimination(hs, "e") == 0.0


def test_v3_decision_selector_is_unchanged():
    # the canonical select() path still works (V3 semantics preserved)
    hs = [_hyp("a", {"e": 1.0}), _hyp("b", {"e": 0.0})]
    opt = _sel().select(np.zeros(2), hs)
    assert opt is not None and opt.status in ("VALUED", "UNKNOWN")
