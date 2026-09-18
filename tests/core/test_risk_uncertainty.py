"""
Symmetric uncertainty→risk — corrects the tighten-only bias.

Under LOW stream uncertainty the policy may now LOOSEN risk (recover); high
uncertainty tightens exactly as before. Enabled by default, env opt-out.
"""
from telos.core.infra_manager.mission_policy import (
    MissionPolicy, MissionPolicyManager, CERTAINTY_MAX,
    _symmetric_uncertainty_enabled,
)


def _ppm(risk=0.3):
    return MissionPolicyManager(MissionPolicy(risk_tolerance=risk))


def test_default_enabled_and_env_opt_out(monkeypatch):
    monkeypatch.delenv("TELOS_RISK_SYMMETRIC_UNCERTAINTY", raising=False)
    assert _symmetric_uncertainty_enabled() is True
    monkeypatch.setenv("TELOS_RISK_SYMMETRIC_UNCERTAINTY", "0")
    assert _symmetric_uncertainty_enabled() is False


def test_low_uncertainty_loosens_risk_when_enabled(monkeypatch):
    monkeypatch.setenv("TELOS_RISK_SYMMETRIC_UNCERTAINTY", "1")
    ppm = _ppm(risk=0.3)
    ppm.adjust_risk_by_uncertainty({"a": 0.02, "b": 0.04})  # avg 0.03 << CERTAINTY_MAX
    assert ppm.current.risk_tolerance > 0.3, "low uncertainty must loosen risk"


def test_opt_out_restores_tighten_only(monkeypatch):
    monkeypatch.setenv("TELOS_RISK_SYMMETRIC_UNCERTAINTY", "0")
    ppm = _ppm(risk=0.3)
    ppm.adjust_risk_by_uncertainty({"a": 0.02, "b": 0.04})
    assert ppm.current.risk_tolerance <= 0.3, "opt-out keeps tighten-only"


def test_high_uncertainty_tightens_identically_in_both_modes(monkeypatch):
    results = []
    for flag in ("0", "1"):
        monkeypatch.setenv("TELOS_RISK_SYMMETRIC_UNCERTAINTY", flag)
        ppm = _ppm(risk=0.3)
        ppm.adjust_risk_by_uncertainty({"a": 0.9, "b": 0.8})  # avg 0.85 > CERTAINTY_MAX
        results.append(round(ppm.current.risk_tolerance, 9))
    assert results[0] == results[1]
    assert results[0] < 0.3
