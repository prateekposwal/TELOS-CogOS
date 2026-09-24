"""
HypothesisGenerator tests (V8): generation from unexplained residuals.

Falsifiers: a significant repeatable lag generates CANDIDATE hypotheses (never
believed); noise and lagless correlation generate NOTHING; two candidates are
discriminated by an experiment (one eliminated); the generator never emits a
hidden variable name.
"""

import numpy as np

from telos.core.discovery.hypothesis_generation import HypothesisGenerator
from telos.world.evidence import ValidationStatus


def _lagged(n=500, seed=0, lag=2):
    rng = np.random.RandomState(seed)
    x = rng.normal(0, 1, n)
    y = np.zeros(n)
    y[lag:] = x[:-lag] + rng.normal(0, 0.2, n - lag)
    return x, y


def test_lagged_residual_generates_candidates_not_beliefs():
    x, y = _lagged()
    gen = HypothesisGenerator()
    assert gen.residual(x, y) == 2
    cands = gen.generate("X", "Y", x, y)
    assert len(cands) == 2
    assert all(c.evidence.validation_status == ValidationStatus.UNVALIDATED for c in cands)
    assert all(c.provenance == "generated" for c in cands)


def test_noise_does_not_generate():
    rng = np.random.RandomState(1)
    x, y = rng.normal(0, 1, 500), rng.normal(0, 1, 500)
    gen = HypothesisGenerator()
    assert gen.residual(x, y) is None
    assert gen.generate("A", "B", x, y) == []


def test_lagless_correlation_does_not_generate():
    rng = np.random.RandomState(2)
    x = rng.normal(0, 1, 500)
    y = 0.2 * x + rng.normal(0, 1, 500)     # contemporaneous corr, no lag structure
    gen = HypothesisGenerator()
    assert gen.generate("A", "B", x, y) == []


def test_discrimination_eliminates_one_candidate():
    x, y = _lagged()
    gen = HypothesisGenerator()
    cands = gen.generate("X", "Y", x, y)
    med = next(c for c in cands if c.mechanism == "mediated")
    direct = next(c for c in cands if c.mechanism == "delayed_direct")
    # hidden world is mediated -> an intermediate signal is present
    res = gen.discriminate(cands, observed_intermediate=True)
    assert res["resolved"] is True
    assert res["survivor"]["mechanism"] == "mediated"
    assert direct.statement in res["falsified"]


def test_generator_emits_no_hidden_name():
    x, y = _lagged()
    gen = HypothesisGenerator()
    cands = gen.generate("X", "Y", x, y)     # the hidden mediator is "M"
    emitted = {v for c in cands for v in c.proposed_variables}
    assert emitted <= {"X", "Y"}
    assert "M" not in emitted
