"""
Consolidated cognitive-health gate — the four-instrument verdict.

`evaluate` must pass on a healthy baseline and fail on any regressed metric.
`collect` must run all four audits and return every check value.
"""
from telos.tools.cognitive_health import CHECKS, checks_for, collect, evaluate


def _healthy():
    return {
        "action_emission_rate": 0.89,
        "noop_rate": 0.11,
        "episodes_completed": 16,
        "mean_di": 1.0,
        "model_fidelity_mean": 1.0,
        "low_integrity_blocks": 0,
        "evidence_validator_dissent": 0,
        "capability_defers": 0,
        "risk_tolerance_at_floor": 0,
        "unlabeled_policy_changes": 0,
    }


def test_healthy_baseline_passes_all_checks():
    rows = evaluate(_healthy())
    assert len(rows) == len(CHECKS)
    assert all(r["passed"] for r in rows)


def test_each_regression_fails_the_gate():
    # Each check, when regressed, must flip to FAIL.
    regressions = {
        "action_emission_rate": 0.10,
        "noop_rate": 0.90,
        "episodes_completed": 0,
        "mean_di": 0.30,
        "model_fidelity_mean": 0.40,
        "low_integrity_blocks": 40,
        "evidence_validator_dissent": 40,
        "capability_defers": 92,
        "risk_tolerance_at_floor": 35,
        "unlabeled_policy_changes": 335,
    }
    for key, bad in regressions.items():
        measured = _healthy()
        measured[key] = bad
        rows = {r["check"]: r["passed"] for r in evaluate(measured)}
        assert rows[key] is False, f"{key} regression not caught"


def test_collect_returns_all_measured_keys():
    data = collect(3)  # tiny run — just proves the four audits wire up
    for name, _p, _op, _t in CHECKS:
        assert name in data["measured"]
    assert set(data["reports"]) == {"act_gate", "council_gate", "policy", "selection"}
