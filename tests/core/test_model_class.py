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


def test_observational_only_never_fabricates_a_structure():
    # V12 semantics fix: without an intervention, the stateful class must NOT
    # invent a feedback/shared_state structure from association + autocorrelation.
    x, y = _feedback_series()
    r = StatefulModel().represent(x, y)      # no do_xy / do_yx
    assert r["verdict"] == ModelClassVerdict.UNRESOLVED.value
    assert r["structure"] is None


# ── V13: compositional representation ───────────────────────────────────────

def _cycle3(n=600, seed=0, noise=0.3):
    import numpy as np
    rng = np.random.RandomState(seed)
    v = {k: np.zeros(n) for k in ("v0", "v1", "v2")}
    for t in range(1, n):
        v["v0"][t] = 0.5 * v["v0"][t-1] + 0.5 * v["v2"][t-1] + rng.normal(0, noise)
        v["v1"][t] = 0.5 * v["v1"][t-1] + 0.5 * v["v0"][t-1] + rng.normal(0, noise)
        v["v2"][t] = 0.5 * v["v2"][t-1] + 0.5 * v["v1"][t-1] + rng.normal(0, noise)
    return v


def test_three_node_cycle_is_represented_as_depth_three():
    from telos.core.discovery.model_class import discover_structure
    v = _cycle3()
    iv = {("v0", "v1"): 1.0, ("v1", "v2"): 1.0, ("v2", "v0"): 1.0,
          ("v1", "v0"): 0.0, ("v2", "v1"): 0.0, ("v0", "v2"): 0.0}
    st = discover_structure(v, iv)
    comps = st.recurrent_components()
    assert len(comps) == 1 and len(comps[0]) == 3      # depth preserved, not "2"


def test_two_independent_loops_are_two_components():
    import numpy as np
    from telos.core.discovery.model_class import discover_structure
    n, rng = 600, np.random.RandomState(0)
    v = {k: np.zeros(n) for k in ("v0", "v1", "v2", "v3")}
    for t in range(1, n):
        v["v0"][t] = 0.6 * v["v0"][t-1] + 0.5 * v["v1"][t-1] + rng.normal(0, .3)
        v["v1"][t] = 0.6 * v["v1"][t-1] + 0.5 * v["v0"][t-1] + rng.normal(0, .3)
        v["v2"][t] = 0.6 * v["v2"][t-1] + 0.5 * v["v3"][t-1] + rng.normal(0, .3)
        v["v3"][t] = 0.6 * v["v3"][t-1] + 0.5 * v["v2"][t-1] + rng.normal(0, .3)
    iv = {("v0", "v1"): 1.0, ("v1", "v0"): 1.0, ("v2", "v3"): 1.0, ("v3", "v2"): 1.0,
          ("v0", "v2"): 0.0, ("v2", "v0"): 0.0, ("v0", "v3"): 0.0, ("v3", "v0"): 0.0,
          ("v1", "v2"): 0.0, ("v2", "v1"): 0.0, ("v1", "v3"): 0.0, ("v3", "v1"): 0.0}
    comps = discover_structure(v, iv).recurrent_components()
    assert len(comps) == 2 and all(len(c) == 2 for c in comps)


def test_feedback_plus_delay_preserves_both():
    import numpy as np
    from telos.core.discovery.model_class import discover_structure
    n, rng = 600, np.random.RandomState(0)
    v0, v1 = np.zeros(n), np.zeros(n)
    for t in range(2, n):
        v0[t] = 0.6 * v0[t-1] + 0.5 * v1[t-1] + rng.normal(0, .3)   # v1 -> v0 (lag1)
        v1[t] = 0.6 * v1[t-1] + 0.5 * v0[t-2] + rng.normal(0, .3)   # v0 -> v1 (lag2)
    st = discover_structure({"v0": v0, "v1": v1},
                            {("v0", "v1"): 1.0, ("v1", "v0"): 1.0})
    assert len(st.recurrent_edges()) >= 2      # feedback preserved
    assert len(st.temporal_edges()) >= 1       # delay preserved, not collapsed


def test_delay_is_not_recurrent_and_observation_stays_unresolved():
    import numpy as np
    from telos.core.discovery.model_class import discover_structure
    n, rng = 600, np.random.RandomState(0)
    x = rng.normal(0, 1, n)
    y = np.zeros(n)
    for t in range(2, n):
        y[t] = x[t-2] + rng.normal(0, .3)
    # delay: no cycle even with interventions
    st = discover_structure({"v0": x, "v1": y}, {("v0", "v1"): 1.0, ("v1", "v0"): 0.0})
    assert len(st.recurrent_components()) == 0
    # no intervention observed => representable but NOT supported
    st2 = discover_structure({"v0": x, "v1": y}, {("v0", "v1"): None, ("v1", "v0"): None})
    assert st2.confidence == "UNRESOLVED" and st2.required_intervention is not None


# ── R1: explicit bounded-representation semantics ───────────────────────────

def _kcycle_obs(k, n=200, seed=0):
    import numpy as np
    rng = np.random.RandomState(seed)
    V = {f"v{i}": np.zeros(n) for i in range(k)}
    for t in range(1, n):
        for i in range(k):
            V[f"v{i}"][t] = (0.5 * V[f"v{i}"][t-1]
                             + 0.5 * V[f"v{(i-1) % k}"][t-1] + rng.normal(0, .3))
    return V


def test_within_node_bound_represents_normally():
    from telos.core.discovery.model_class import discover_structure
    v = _kcycle_obs(5)
    iv = {(f"v{i}", f"v{(i+1) % 5}"): 1.0 for i in range(5)}
    st = discover_structure(v, iv)
    assert st.bound_exceeded is False
    assert st.representable is True
    assert len(st.nodes) == 5                      # reported == represented


def test_exceeding_node_bound_is_explicit_not_silent():
    from telos.core.discovery.model_class import discover_structure
    for k in (6, 7, 10):
        st = discover_structure(_kcycle_obs(k), {})
        assert st.bound_exceeded is True
        assert st.representable is False
        assert st.nodes == ()                      # no partial graph presented
        assert st.confidence == "UNRESOLVED"       # BOUND_EXCEEDED != epistemic
        assert st.status == "BOUND_EXCEEDED"
        assert st.n_observed == k


def test_three_components_has_no_silent_component_loss():
    from telos.core.discovery.model_class import discover_structure
    v = _kcycle_obs(6)                              # 6 nodes => exceeds bound
    st = discover_structure(v, {})
    assert st.bound_exceeded is True
    assert st.recurrent_components() == ()          # never a truncated (2,2)
