"""
Mission-policy instrumentation — the firewall DI threshold and its up-driver.

Locks the threshold derivation (1 − risk_tolerance) and that labeled policy
mutations surface in the record.
"""
from types import SimpleNamespace

from telos.core.decision.policy_trace import build_policy_trace
from telos.core.infra_manager.mission_policy import MissionPolicy, MissionPolicyManager


def _pipe(ppm):
    return SimpleNamespace(_infra_manager=SimpleNamespace(policy=ppm))


def test_threshold_derived_from_risk_tolerance():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.2))
    rec = build_policy_trace(_pipe(ppm))
    assert rec["available"] is True
    assert abs(rec["firewall_di_threshold"] - 0.8) < 1e-9
    assert abs(rec["risk_tolerance"] - 0.2) < 1e-9


def test_unavailable_without_policy():
    assert build_policy_trace(SimpleNamespace()).get("available") is False


def test_labeled_change_surfaces():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5))
    ppm.adjust_risk_tolerance(-0.05, reason="unit_test", caller="tester")
    rec = build_policy_trace(_pipe(ppm))
    last = rec["recent_changes"][-1]
    assert last["caller"] == "tester"
    assert last["reason"] == "unit_test"
