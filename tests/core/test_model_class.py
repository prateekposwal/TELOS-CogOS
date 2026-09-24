"""
Model-class assessment tests (V10): domain-agnostic, vocabulary-free verdicts.

Distinguishes SUFFICIENT / ADDITIONAL_STRUCTURE_REQUIRED / UNRESOLVED /
MODEL_CLASS_INSUFFICIENT using only generic primitives (correlation, lag,
intervention effects). No `mediated`/`common_cause` vocabulary.
"""

import numpy as np

from telos.core.discovery.model_class import (
    assess, ModelClassVerdict, AcyclicModel, StatefulModel,
)


def _confounded(n=500, seed=0):
    rng = np.random.RandomState(seed)
    h = rng.normal(0, 1, n)
    return h + rng.normal(0, 0.3, n), h + rng.normal(0, 0.3, n)


def _noise(n=500, seed=1):
    rng = np.random.RandomState(seed)
    return rng.normal(0, 1, n), rng.normal(0, 1, n)


def _delayed(n=500, seed=2, lag=2):
    rng = np.random.RandomState(seed)
    x = rng.normal(0, 1, n); y = np.zeros(n)
    y[lag:] = x[:-lag] + rng.normal(0, 0.2, n - lag)
    return x, y


def test_bidirectional_is_model_class_insufficient():
    x, y = _confounded()
    r = assess(x, y, do_xy=1.2, do_yx=1.2)     # both directions move -> X<->Y
    assert r["verdict"] == ModelClassVerdict.MODEL_CLASS_INSUFFICIENT


def test_confounded_needs_additional_structure_not_noise():
    x, y = _confounded()
    r = assess(x, y, do_xy=0.0, do_yx=0.0)     # association, no intervention effect
    assert r["verdict"] == ModelClassVerdict.ADDITIONAL_STRUCTURE_REQUIRED


def test_direct_causal_is_sufficient():
    x, y = _confounded()
    r = assess(x, y, do_xy=1.0, do_yx=0.0)     # x -> y
    assert r["verdict"] == ModelClassVerdict.SUFFICIENT


def test_noise_is_unresolved_not_insufficient():
    x, y = _noise()
    r = assess(x, y)                            # not tested -> unresolved
    assert r["verdict"] == ModelClassVerdict.UNRESOLVED


def test_delayed_direct_needs_no_latent_unless_intermediate_seen():
    x, y = _delayed()
    assert assess(x, y)["verdict"] == ModelClassVerdict.SUFFICIENT
    assert assess(x, y, intermediate=True)["verdict"] == ModelClassVerdict.ADDITIONAL_STRUCTURE_REQUIRED


def test_unresolved_and_model_class_insufficient_are_distinct():
    # ambiguous direction -> UNRESOLVED (witness gap)
    x, y = _confounded()
    assert assess(x, y, do_xy=None, do_yx=None)["verdict"] == ModelClassVerdict.UNRESOLVED
    # bidirectional -> MODEL_CLASS_INSUFFICIENT (class failure)
    assert assess(x, y, do_xy=1.0, do_yx=1.0)["verdict"] == ModelClassVerdict.MODEL_CLASS_INSUFFICIENT


# ── V11: stateful / feedback model class ─────────────────────────────────────

def _feedback_series(n=500, seed=0):
    rng = np.random.RandomState(seed)
    x = np.zeros(n); y = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.6 * x[t - 1] + 0.6 * y[t - 1] + rng.normal(0, 0.3)
        y[t] = 0.6 * y[t - 1] + 0.6 * x[t - 1] + rng.normal(0, 0.3)
    return x, y


def _shared_state_series(n=500, seed=0):
    rng = np.random.RandomState(seed)
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = 0.95 * s[t - 1] + rng.normal(0, 0.3)
    return s + rng.normal(0, 0.2, n), s + rng.normal(0, 0.2, n)


def test_acyclic_flags_feedback_but_stateful_represents_it():
    x, y = _feedback_series()
    ev = {"do_xy": 1.0, "do_yx": 1.0}
    a = AcyclicModel().represent(x, y, **ev)
    s = StatefulModel().represent(x, y, **ev)
    assert a["verdict"] == ModelClassVerdict.MODEL_CLASS_INSUFFICIENT.value
    assert s["structure"] == "feedback" and s["status"] == "UNVALIDATED"


def test_delay_is_not_feedback():
    x, y = _delayed()
    s = StatefulModel().represent(x, y, do_xy=0.9, do_yx=0.0)
    assert s["structure"] != "feedback"
    assert s["verdict"] == ModelClassVerdict.SUFFICIENT.value


def test_shared_hidden_state_is_not_feedback():
    x, y = _shared_state_series()
    s = StatefulModel().represent(x, y, do_xy=0.0, do_yx=0.0)
    assert s["structure"] == "shared_state"
    assert s["structure"] != "feedback"


def test_feedback_is_falsified_when_the_intervention_nulls():
    x, y = _feedback_series()
    s = StatefulModel()
    rep = s.represent(x, y, do_xy=1.0, do_yx=1.0)
    assert s.falsify(rep, {"do_xy": 0.0, "do_yx": 0.0}) is True


def test_model_class_insufficient_is_preserved_not_absorbed():
    x, y = _feedback_series()
    # the acyclic verdict is authoritative for the acyclic class
    assert AcyclicModel().represent(x, y, do_xy=1.0, do_yx=1.0)["verdict"] == \
        ModelClassVerdict.MODEL_CLASS_INSUFFICIENT.value
