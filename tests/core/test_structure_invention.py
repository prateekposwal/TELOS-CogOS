"""
StructureInvention tests (V9): expanding the hypothesis SPACE under bounded search.

Falsifiers: three hidden worlds are distinguished; a latent is introduced ONLY
when evidence requires it (Occam / complexity penalty); noise and direct/delayed
relations invent nothing; ambiguity stays UNRESOLVED; the hidden name is never
emitted; a test makes the invented variable HYPOTHESIZED (never OBSERVED).
"""

import numpy as np

from telos.core.discovery.structure_invention import (
    StructureInventor, VariableStatus,
)


def _direct_delay(n=500, seed=0, lag=2):
    rng = np.random.RandomState(seed)
    x = rng.normal(0, 1, n); y = np.zeros(n)
    y[lag:] = x[:-lag] + rng.normal(0, 0.2, n - lag)
    return x, y


def _common_cause(n=500, seed=0):
    rng = np.random.RandomState(seed)
    h = rng.normal(0, 1, n)
    return h + rng.normal(0, 0.2, n), h + rng.normal(0, 0.2, n)


def test_three_worlds_are_distinguished():
    inv = StructureInventor()
    xa, ya = _direct_delay()
    xb, yb = _direct_delay()               # same lag; intermediate observed -> mediated
    xc, yc = _common_cause()
    assert inv.infer("X", "Y", xa, ya, intermediate=False).preferred.family == "direct_delay"
    assert inv.infer("X", "Y", xb, yb, intermediate=True).preferred.family == "mediated"
    assert inv.infer("X", "Y", xc, yc, intervention_changes_y=False).preferred.family == "common_cause"


def test_latent_only_when_evidence_requires():
    inv = StructureInventor()
    xa, ya = _direct_delay()
    # no intermediate evidence -> both fit -> simpler (no latent) preferred
    res = inv.infer("X", "Y", xa, ya, intermediate=None)
    assert res.preferred.family == "direct_delay"
    assert res.preferred.introduces_latent is False
    # an observed intermediate -> the extra entity is required, status HYPOTHESIZED
    med = inv.infer("X", "Y", xa, ya, intermediate=True).preferred
    assert med.family == "mediated" and med.introduces_latent is True
    assert med.variable_status == VariableStatus.HYPOTHESIZED


def test_noise_invents_nothing():
    rng = np.random.RandomState(3)
    x, y = rng.normal(0, 1, 500), rng.normal(0, 1, 500)
    assert inv_is_empty(StructureInventor(), x, y)


def inv_is_empty(inv, x, y):
    res = inv.infer("X", "Y", x, y)
    return len(res.candidates) == 0 and res.preferred is None


def test_ambiguity_is_unresolved_no_promotion():
    inv = StructureInventor()
    xc, yc = _common_cause()
    res = inv.infer("X", "Y", xc, yc, intervention_changes_y=None)
    assert res.unresolved is True
    assert res.preferred is None               # nothing promoted


def test_complexity_penalty_prefers_simpler():
    inv = StructureInventor()
    x, y = _direct_delay()
    res = inv.infer("X", "Y", x, y, intermediate=None)
    assert len(res.candidates) == 2
    assert res.preferred.complexity == min(c.complexity for c in res.candidates)
    assert res.preferred.family == "direct_delay"


def test_hidden_name_never_emitted():
    inv = StructureInventor()
    x, y = _direct_delay()
    structures = [c.structure for c in inv.infer("X", "Y", x, y, intermediate=True).candidates]
    assert all("M" not in s for s in structures)     # the hidden mediator is "M" upstream
    assert any("H1" in s for s in structures)        # invented id is opaque
