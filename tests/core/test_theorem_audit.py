"""
Falsifiable Theorem Audit — the anti-tautology contract.

Each theorem has a declared null. These tests prove the auditor can actually
FAIL (the null is reachable) as well as pass on a healthy run.
"""
from types import SimpleNamespace

from telos.core.verifier.theorem_audit import (
    run_audit, kintsugi_experiment, check_delayed_causality,
    check_process_over_outcomes, check_computational_conservation,
    check_possibility_preservation, check_emergent_intelligence,
    check_determinism,
)


def _trace(di=0.9, options=2, streams=3, used=10.0, total=100.0):
    acts = [SimpleNamespace(activated=True) for _ in range(streams)]
    return SimpleNamespace(
        decision_integrity=di, mission_drift=0.1,
        strategic_options=[object()] * options,
        stream_activations=acts,
        budget_consumed_ms=used, budget_total_ms=total,
    )


def test_kintsugi_experiment_holds():
    holds, measured = kintsugi_experiment()
    assert holds is True, measured


def test_delayed_causality_holds_and_is_strict():
    cfg = SimpleNamespace(horizon=1, feedback_lag=5)
    holds, measured = check_delayed_causality(cfg)
    assert holds is True and "6" in measured


def test_process_check_fails_on_out_of_range_di():
    assert check_process_over_outcomes([_trace(di=0.5)])[0] is True
    assert check_process_over_outcomes([_trace(di=1.5)])[0] is False


def test_conservation_check_fails_on_overrun():
    assert check_computational_conservation([_trace(used=100, total=100)])[0] is True
    assert check_computational_conservation([_trace(used=200, total=100)])[0] is False


def test_possibility_check_fails_on_zero_options():
    assert check_possibility_preservation([_trace(options=1)])[0] is True
    assert check_possibility_preservation([_trace(options=0)])[0] is False


def test_emergent_check_fails_on_single_stream():
    assert check_emergent_intelligence([_trace(streams=2)])[0] is True
    assert check_emergent_intelligence([_trace(streams=1)])[0] is False


def test_determinism_check():
    assert check_determinism("abc", "abc")[0] is True
    assert check_determinism("abc", "def")[0] is False


def test_run_audit_passes_on_healthy_traces():
    cfg = SimpleNamespace(horizon=5, feedback_lag=0)
    report = run_audit([_trace(), _trace()], cfg, "fp", "fp")
    assert report["passed"] is True
    assert len(report["rows"]) == 7


def test_run_audit_fails_when_a_theorem_is_violated():
    cfg = SimpleNamespace(horizon=5, feedback_lag=0)
    report = run_audit([_trace(options=0)], cfg, "fp", "fp")
    assert report["passed"] is False
    failed = [r["id"] for r in report["rows"] if not r["passed"]]
    assert "T4-possibility" in failed
