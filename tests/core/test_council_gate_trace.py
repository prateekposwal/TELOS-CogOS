"""
Council/firewall instrumentation — non-behavioral record of dissent + block.

Captures the dissenting validator(s) and the low_integrity source (applied DI
threshold + domain) so the remaining suppression can be audited.
"""
from types import SimpleNamespace

from telos.core.decision.council_gate_trace import build_council_gate_record


def _signal(name, passed, reason, weight=0.6):
    return SimpleNamespace(validator_name=name, passed=passed, confidence=-0.7,
                           evidence_weight=weight, reason=reason, verdict=None)


def _ctx():
    verdict = SimpleNamespace(
        validated=False, decision_integrity=0.3, evidence_integrity=1.0,
        blocking_validator="EvidenceProvenanceValidator",
        signals=[_signal("EvidenceProvenanceValidator", False, "no-action pattern"),
                 _signal("RealityValidator", True, "ok", weight=0.3)],
    )
    fw = SimpleNamespace(
        passed=False, blocked_by="low_integrity", reason="DI below threshold",
        governance_signals=[{"check": "decision_integrity", "passed": False,
                             "applied_threshold": 0.95, "domain": "gridworld"}],
    )
    return SimpleNamespace(cycle_count=5, verdict=verdict, firewall_verdict=fw)


def test_record_captures_dissent_and_threshold_source():
    rec = build_council_gate_record(_ctx())
    assert rec["cycle"] == 5
    assert rec["dissent_count"] == 1
    assert rec["dissenters"][0]["validator"] == "EvidenceProvenanceValidator"
    assert rec["blocking_validator"] == "EvidenceProvenanceValidator"
    assert rec["firewall_blocked_by"] == "low_integrity"
    assert rec["applied_di_threshold"] == 0.95
    assert rec["di_domain"] == "gridworld"
    assert rec["decision_integrity"] == 0.3


def test_record_tolerates_missing_fields():
    rec = build_council_gate_record(SimpleNamespace(cycle_count=1))
    assert rec["cycle"] == 1
    assert rec["dissenters"] == []
    assert rec["firewall_blocked_by"] is None
    assert rec["applied_di_threshold"] is None
