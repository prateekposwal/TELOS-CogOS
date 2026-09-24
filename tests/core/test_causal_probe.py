"""
CausalProbe tests — the epistemic ladder (Phase 2) + intervention-based direction.

Verifies: correlation is NOT promotion to causation (confounding/latent), reverse
direction is resolved, nonlinear effects are found by intervention, noisy effects
are found by significance, and truly-independent pairs stay UNRESOLVED.
"""

import numpy as np

from telos.core.discovery import CausalProbe, CausalStatus


class MiniWorld:
    """A tiny SCM: variables in topological order; fns(var, assigns, rng, n)."""

    def __init__(self, variables, order, fns):
        self.variables = variables
        self.order = order
        self.fns = fns

    def sample(self, n, do=None, rng=None):
        rng = rng or np.random.RandomState()
        do = do or {}
        d = {}
        for v in self.order:
            if v in do:
                d[v] = np.full(n, float(do[v]))
            elif v in self.fns:
                d[v] = self.fns[v](d, rng, n)
            else:
                d[v] = rng.normal(0, 1, n)
        return {v: d[v] for v in self.variables}


def _nz(rng, n, sd=0.3):
    return rng.normal(0, sd, n)


def test_direct_causality_resolved():
    w = MiniWorld(["X", "Y"], ["X", "Y"], {"Y": lambda d, r, n: d["X"] + _nz(r, n)})
    r = CausalProbe(seed=1).classify(w, "X", "Y")
    assert r.status == CausalStatus.SUPPORTED_CAUSAL_RELATION
    assert (r.cause, r.effect) == ("X", "Y")


def test_reverse_causality_direction_resolved():
    w = MiniWorld(["X", "Y"], ["Y", "X"], {"X": lambda d, r, n: d["Y"] + _nz(r, n)})
    r = CausalProbe(seed=1).classify(w, "X", "Y")   # query X->Y, truth is Y->X
    assert r.status == CausalStatus.SUPPORTED_CAUSAL_RELATION
    assert (r.cause, r.effect) == ("Y", "X")        # direction corrected


def test_confounding_is_correlation_not_causation():
    w = MiniWorld(["X", "Y", "Z"], ["Z", "X", "Y"],
                  {"X": lambda d, r, n: d["Z"] + _nz(r, n),
                   "Y": lambda d, r, n: d["Z"] + _nz(r, n)})
    probe = CausalProbe(seed=2)
    assert probe.classify(w, "X", "Y").status == CausalStatus.OBSERVED_CORRELATION
    assert probe.classify(w, "Z", "Y").status == CausalStatus.SUPPORTED_CAUSAL_RELATION


def test_latent_confounder_is_correlation_not_causation():
    w = MiniWorld(["X", "Y"], ["L", "X", "Y"],
                  {"X": lambda d, r, n: d["L"] + _nz(r, n),
                   "Y": lambda d, r, n: d["L"] + _nz(r, n)})
    # L is latent (on the order list but not observed)
    w.order = ["L", "X", "Y"]
    r = CausalProbe(seed=3).classify(w, "X", "Y")
    assert r.status == CausalStatus.OBSERVED_CORRELATION


def test_nonlinear_found_by_intervention_despite_zero_correlation():
    w = MiniWorld(["X", "Y"], ["X", "Y"],
                  {"X": lambda d, r, n: r.uniform(-1, 1, n),
                   "Y": lambda d, r, n: d["X"] ** 2 + _nz(r, n)})
    r = CausalProbe(seed=4).classify(w, "X", "Y")
    assert r.status == CausalStatus.SUPPORTED_CAUSAL_RELATION
    assert r.observed_correlation < 0.2          # observation ~ uncorrelated


def test_noisy_effect_found_by_significance():
    w = MiniWorld(["X", "Y"], ["X", "Y"],
                  {"Y": lambda d, r, n: d["X"] + r.normal(0, 3.0, n)})
    r = CausalProbe(seed=5).classify(w, "X", "Y")
    assert r.status == CausalStatus.SUPPORTED_CAUSAL_RELATION


def test_independent_pair_is_unresolved():
    w = MiniWorld(["X", "Y"], ["X", "Y"], {})    # independent normals
    r = CausalProbe(seed=6).classify(w, "X", "Y")
    assert r.status == CausalStatus.UNRESOLVED_RELATION


def test_decision_sensitivity_high_for_real_cause():
    w = MiniWorld(["X", "Y"], ["X", "Y"], {"Y": lambda d, r, n: d["X"] + _nz(r, n)})
    probe = CausalProbe(seed=7)
    rel = probe.classify(w, "X", "Y")
    assert probe.decision_sensitivity(w, rel, "Y") > 0.0
