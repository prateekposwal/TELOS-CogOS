"""
Curiosity exploration vector (A/B knob) — gated, default off.

Default 0.0 = control: `curiosity_explore` intents carry no `action_vector`, so
a preferred-vector adapter (GridAdpt) falls back to the goal-directed A* step.
At probability >0 the injected intent carries a seeded exploratory vector.
"""
import tempfile

from telos.tools.theorem_audit import _build
from telos.tools.bench_loop import drive


def _curiosity_counts(prob, cycles=40):
    """Count selected curiosity_explore intents and how many carry a vector.

    Args:
        prob: `curiosity_explore_probability`.
        cycles: number of cycles.

    Returns:
        (n_curiosity, n_with_vector) tuple.
    """
    workdir = tempfile.mkdtemp(prefix="telos_cv_test_")
    pipe, _ = _build(workdir)
    pipe.config.curiosity_explore_probability = prob
    n_cur = n_vec = 0
    for step in drive(pipe, cycles, user_name="cv-test"):
        t = step["trace"]
        si = getattr(t, "selected_intent", None) if t else None
        if si is not None and si.intent_type == "curiosity_explore":
            n_cur += 1
            if (si.params or {}).get("action_vector") is not None:
                n_vec += 1
    return n_cur, n_vec


def test_default_control_never_attaches_a_vector():
    n_cur, n_vec = _curiosity_counts(0.0)
    assert n_vec == 0, "control must not attach exploration vectors"


def test_probability_one_attaches_a_vector_to_every_curiosity_intent():
    n_cur, n_vec = _curiosity_counts(1.0)
    assert n_cur > 0, "test needs at least one curiosity_explore selection"
    assert n_vec == n_cur
