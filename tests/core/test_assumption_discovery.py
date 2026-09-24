"""
Assumption-discovery tests — endogenous candidate assumptions from transitions.

Verifies: control-structure recovery (edges + sign), the information-value
ranking, test execution (support/contradict → status), evidence-gated promotion,
and that declared assumptions are never merged with or promoted from discovered.
"""

import numpy as np
import pytest

from telos.core.discovery import AssumptionDiscoverer
from telos.world.evidence import ValidationStatus


def _transitions(M, n=400, seed=0):
    rng = np.random.RandomState(seed)
    M = np.array(M, float)
    s = np.zeros(2)
    out = []
    for _ in range(n):
        a = rng.uniform(-1, 1, 2)
        ns = s + M @ a
        out.append((s.copy(), a.copy(), ns.copy(), -float(np.linalg.norm(ns)), False))
        s = ns
    return out


def test_recovers_control_edges_and_signs():
    # hidden: a0 -> -s1, a1 -> +s0
    M = [[0.0, 1.0], [-1.0, 0.0]]
    d = AssumptionDiscoverer()
    found = d.discover(_transitions(M))
    edges = {(a.state_dim, a.action_dim): a.sign for a in found}
    assert edges.get((1, 0)) == -1     # a0 -> -s1
    assert edges.get((0, 1)) == +1     # a1 -> +s0


def test_no_spurious_edges_on_zero_map():
    d = AssumptionDiscoverer()
    found = d.discover(_transitions([[0.0, 0.0], [0.0, 0.0]]))
    assert found == []


def test_info_value_ranks_by_relevance_uncertainty_falsifiability_cost():
    d = AssumptionDiscoverer()
    found = d.discover(_transitions([[0.0, 1.0], [-1.0, 0.0]]))
    for a in found:
        a.decision_relevance = 0.9; a.uncertainty = 0.5; a.falsifiability = 1.0
    vals = [a.info_value(test_cost=1.0) for a in found]
    assert all(v == pytest.approx(0.45) for v in vals)
    # a costlier test is worth less
    assert found[0].info_value(test_cost=10.0) < found[0].info_value(test_cost=1.0)


def test_run_test_supports_and_falsifies():
    M = np.array([[0.0, 1.0], [-1.0, 0.0]])
    step = lambda s, a: (s + M @ a, 0.0, False)
    d = AssumptionDiscoverer()
    d.discover(_transitions(M))
    # the true relation is supported
    a_true = next(a for a in d.discovered if (a.state_dim, a.action_dim) == (1, 0))
    res = d.run_test(a_true, step, np.zeros(2))
    assert res["supported"] is True
    assert a_true.evidence.validation_status in (ValidationStatus.MEASURED,
                                                 ValidationStatus.VALIDATED)
    # a wrong-sign relation is falsified against the real dynamics
    a_false = next(a for a in d.discovered if (a.state_dim, a.action_dim) == (1, 0))
    a_false.sign = +1  # deliberately wrong
    res2 = d.run_test(a_false, step, np.zeros(2))
    assert res2["supported"] is False
    assert a_false.evidence.validation_status == ValidationStatus.FALSIFIED


def test_promotion_requires_evidence_and_never_touches_declared():
    M = np.array([[0.0, 1.0], [-1.0, 0.0]])
    step = lambda s, a: (s + M @ a, 0.0, False)
    d = AssumptionDiscoverer(declared=["a human-declared premise"])
    d.discover(_transitions(M))
    assert len(d.declared_assumptions()) == 1
    # one supporting observation is not enough
    a = d.discovered[0]
    d.run_test(a, step, np.zeros(2))
    assert d.promote(min_support=2) == []
    # a second support promotes the DISCOVERED assumption only
    d.run_test(a, step, np.zeros(2))
    promoted = d.promote(min_support=2)
    assert a in promoted
    assert d.declared_assumptions()[0].provenance == "declared"
    assert all(x.provenance == "discovered" for x in promoted)


def test_control_matrix_shape():
    M = [[0.0, 1.0], [-1.0, 0.0]]
    d = AssumptionDiscoverer()
    d.discover(_transitions(M))
    Mh = d.control_matrix()
    assert Mh.shape == (2, 2)
    assert Mh[1, 0] == -1 and Mh[0, 1] == 1
