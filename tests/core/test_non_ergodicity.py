"""
Non-ergodicity theorem — executable witness.

A self-referential evidence system that counts governance suppression as
approach-failure is non-ergodic (absorbing trap). Separating suppression from
evidence restores ergodicity. These tests pin both regimes, abstractly and on
the real MemoryAdvisor/FailureLedger path.
"""
from telos.core.governance.recovery_types import GOVERNANCE_SUPPRESSION_REASONS
from telos.core.verifier.non_ergodicity import simulate, run_regime, analyze


def test_canonical_suppression_set_is_nonempty():
    assert "governance_intervention" in GOVERNANCE_SUPPRESSION_REASONS


def test_misattributed_regime_is_non_ergodic():
    r = simulate(separate_suppression=False, cycles=200)
    assert r["non_ergodic"] is True
    assert r["escaped"] is None


def test_separated_regime_escapes_in_bounded_cycles():
    r = simulate(separate_suppression=True, cycles=200)
    assert r["non_ergodic"] is False
    assert isinstance(r["escaped"], int) and r["escaped"] > 0


def test_real_misattributed_approach_never_escapes():
    assert run_regime(separate_suppression=False, cycles=50) is None


def test_real_separated_approach_escapes():
    assert run_regime(separate_suppression=True, cycles=50) == 1


def test_analyze_contrast():
    rep = analyze(cycles=50)
    assert rep["misattributed"]["real_escape_cycle"] is None
    assert rep["separated"]["real_escape_cycle"] is not None
    assert rep["misattributed"]["abstract"]["non_ergodic"] is True
    assert rep["separated"]["abstract"]["non_ergodic"] is False
