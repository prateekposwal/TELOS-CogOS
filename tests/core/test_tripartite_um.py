"""
TELOS v6 — Phase 3: U_M (model-fidelity uncertainty) tests.

U_M captures uncertainty about the adequacy/fidelity of the model used to
predict the world. It is a 4th orthogonal dimension alongside U_W/U_I/U_O,
added to the existing TripartiteUncertainty (NOT a replacement, NOT H_I).
"""

import math

from telos.core.uncertainty.tripartite import TripartiteUncertainty


def test_um_default_zero():
    u = TripartiteUncertainty()
    assert u.U_M == 0.0


def test_um_rises_as_fidelity_falls():
    u = TripartiteUncertainty()
    u.update(model_fidelity=0.4)
    assert abs(u.U_M - 0.6) < 1e-9


def test_um_clamped_to_zero_one():
    u = TripartiteUncertainty()
    u.update(model_fidelity=1.3)  # fidelity > 1 clamped
    assert u.U_M == 0.0
    u.update(model_fidelity=-0.5)  # fidelity < 0 clamps to 1
    assert u.U_M == 1.0


def test_um_in_to_dict_and_vector():
    u = TripartiteUncertainty()
    u.update(model_fidelity=0.5)
    d = u.to_dict()
    assert d["U_M"] == 0.5
    assert len(u.vector) == 4
    assert u.vector[3] == 0.5


def test_um_composite_includes_model_dimension():
    # all-zero except U_M=1.0 -> composite=(1/2)=0.5 under 4-dim L2 normalization
    u = TripartiteUncertainty()
    u.update(model_fidelity=0.0)
    assert abs(u.composite - 0.5) < 1e-9


def test_um_dominant_model_when_highest():
    u = TripartiteUncertainty()
    u.update(model_fidelity=0.0)  # U_M = 1.0
    assert u.get_dominant() == "model"


def test_um_reset():
    u = TripartiteUncertainty()
    u.update(model_fidelity=0.2)
    u.reset()
    assert u.U_M == 0.0
    assert u.vector == (0.0, 0.0, 0.0, 0.0)


def test_um_in_compute_from_available():
    u = TripartiteUncertainty.compute_from_available(model_fidelity=0.3)
    assert abs(u.U_M - 0.7) < 1e-9


def test_um_answer_decay_reduces():
    u = TripartiteUncertainty()
    u.update(model_fidelity=0.0)  # U_M = 1.0
    u.record_answer("investigate")
    assert u.U_M < 1.0
    # pre-existing dims still present after our change
    assert hasattr(u, "U_W")
    assert hasattr(u, "U_I")
    assert hasattr(u, "U_O")
