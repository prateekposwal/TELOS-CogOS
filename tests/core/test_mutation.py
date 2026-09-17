"""
MutationGuard (core/infra_manager/mutation.py) — direct unit coverage.

The guard is a security defense: it caps the total per-parameter self-
modification delta per cycle so a single observe() cannot cause runaway drift.
"""
from telos.core.infra_manager.mutation import MutationGuard


def test_within_cap_accumulates_then_blocks():
    g = MutationGuard()
    g.begin_cycle(1)
    assert g.check("risk_tolerance", 0.03) is True
    assert g.check("risk_tolerance", 0.01) is True   # total 0.04 <= 0.05
    assert g.check("risk_tolerance", 0.02) is False  # total 0.06 > 0.05
    assert g._blocked_changes == 1


def test_begin_cycle_resets_accumulators():
    g = MutationGuard()
    g.begin_cycle(1)
    assert g.check("risk_tolerance", 0.04) is True
    g.begin_cycle(2)
    assert g.check("risk_tolerance", 0.04) is True, "new cycle starts clean"


def test_unknown_param_uses_default_cap():
    g = MutationGuard()
    g.begin_cycle(1)
    assert g.check("mystery_param", 0.04) is True
    assert g.check("mystery_param", 0.02) is False


def test_negative_delta_is_magnitude_capped():
    g = MutationGuard()
    g.begin_cycle(1)
    assert g.check("risk_tolerance", -0.04) is True
    assert g.check("risk_tolerance", -0.02) is False, "abs(total) > cap"


def test_params_are_independent_within_a_cycle():
    g = MutationGuard()
    g.begin_cycle(1)
    assert g.check("risk_tolerance", 0.05) is True
    assert g.check("exploration_budget", 0.05) is True
