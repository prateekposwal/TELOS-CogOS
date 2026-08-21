"""
Contract tests for telos/core/infra_manager/failure_ledger.py — FailureLedger (Kintsugi).

The ledger records failures with root-cause tagging and integrates them into
identity markers. These tests assert the REAL behavior of the source.
"""

import numpy as np

from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace
from telos.intent_ir import IntentIR
from telos.core.infra_manager.failure_ledger import FailureLedger, FailureRecord


def _trace(cycle, di, md, council_validated=True, firewall_blocked=False, blocking=None,
           semantic_depths=None, firewall_blocked_by=None):
    return DecisionTrace(
        cycle_id=cycle, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("test"),
        selected_action=np.array([0.1]) if not firewall_blocked else None,
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.9, council_validated=council_validated,
        decision_integrity=di, mission_drift=md,
        firewall_blocked=firewall_blocked, blocking_validator=blocking,
        firewall_blocked_by=firewall_blocked_by,
        semantic_depths=semantic_depths or [],
    )


def _result(trace, council_blocked=False, firewall_blocked=False, governance_blocked_by=None):
    return PipelineResult(None, 0.5, PipelinePhase.COMPLETE,
                          decision_trace=trace,
                          council_blocked=council_blocked,
                          firewall_blocked=firewall_blocked,
                          governance_blocked_by=governance_blocked_by)


def test_observe_clean_cycle_is_none():
    ledger = FailureLedger()
    assert ledger.total_failures == 0
    result = _result(_trace(1, 0.9, 0.5))
    assert ledger.observe(result) is None
    assert ledger.total_failures == 0


def test_observe_none_trace_is_none():
    ledger = FailureLedger()
    result = PipelineResult(None, 0.9, PipelinePhase.COMPLETE, decision_trace=None)
    assert ledger.observe(result) is None
    assert ledger.total_failures == 0


def test_council_block_records_failure():
    ledger = FailureLedger()
    blocked_trace = _trace(2, 0.2, 2.0, council_validated=False, blocking="RealityValidator")
    fail = ledger.observe(_result(blocked_trace, council_blocked=True))
    assert fail is not None
    assert fail.failure_type == "council_block"
    assert fail.severity == 0.8
    assert fail.blocked_by == "RealityValidator"
    assert fail.root_cause == "council_rejection"  # RealityValidator not in patterns -> get default
    assert ledger.total_failures == 1


def test_council_block_root_cause_maps_validator():
    ledger = FailureLedger()
    blocked_trace = _trace(2, 0.2, 2.0, council_validated=False, blocking="reality_mismatch")
    fail = ledger.observe(_result(blocked_trace, council_blocked=True))
    assert fail.root_cause == "sensor_divergence"


def test_firewall_block_records_failure():
    ledger = FailureLedger()
    fw_trace = _trace(3, 0.5, 2.0, firewall_blocked=True, firewall_blocked_by="policy")
    fail = ledger.observe(_result(fw_trace, firewall_blocked=True, governance_blocked_by="policy"))
    assert fail is not None
    assert fail.failure_type == "firewall_block"
    assert fail.severity == 0.7
    assert fail.root_cause == "governance_intervention"
    assert fail.blocked_by == "policy"


def test_high_drift_records_failure():
    ledger = FailureLedger()
    drift_trace = _trace(3, 0.9, 6.0)
    fail = ledger.observe(_result(drift_trace))
    assert fail is not None
    assert fail.failure_type == "high_drift"
    assert fail.severity == 0.6  # min(0.6, 6/10)
    assert fail.root_cause == "simulation_divergence"


def test_low_integrity_records_failure():
    ledger = FailureLedger()
    low_trace = _trace(4, 0.2, 0.5)
    fail = ledger.observe(_result(low_trace))
    assert fail is not None
    assert fail.failure_type == "low_integrity"
    assert fail.severity == 0.5
    assert fail.root_cause == "epistemic_compromise"


def test_record_direct_appends():
    ledger = FailureLedger()
    rec = FailureRecord(failure_id="synthetic_1", cycle=9, timestamp=1.0,
                        failure_type="budget_starvation", severity=0.6,
                        root_cause="resource_exhaustion")
    assert ledger.record_direct(rec) is rec
    assert ledger.total_failures == 1
    assert ledger.get_recent_failures() == [rec]


def test_integrate_into_identity_maps_known_type():
    ledger = FailureLedger()
    rec = FailureRecord(failure_id="f1", cycle=1, timestamp=1.0,
                        failure_type="budget_starvation", severity=0.6,
                        root_cause="resource_exhaustion")
    markers = ledger.integrate_into_identity(rec)
    assert markers == {"conserving_resources"}
    assert rec.identity_markers_added == ["conserving_resources"]
    assert rec.repair_outcome == "identity_update"


def test_integrate_into_identity_unknown_type_uses_root_cause():
    ledger = FailureLedger()
    rec = FailureRecord(failure_id="f2", cycle=1, timestamp=1.0,
                        failure_type="weird", severity=0.5,
                        root_cause="mystery")
    markers = ledger.integrate_into_identity(rec)
    assert markers == {"recovering_from_mystery"}


def test_get_failures_by_type():
    ledger = FailureLedger()
    low_trace = _trace(1, 0.2, 0.5)
    ledger.observe(_result(low_trace))  # low_integrity
    drift_trace = _trace(2, 0.9, 6.0)
    ledger.observe(_result(drift_trace))  # high_drift
    assert len(ledger.get_failures_by_type("low_integrity")) == 1
    assert len(ledger.get_failures_by_type("high_drift")) == 1
    assert len(ledger.get_failures_by_type("council_block")) == 0


def test_root_cause_summary():
    ledger = FailureLedger()
    ledger.observe(_result(_trace(1, 0.2, 0.5)))  # low_integrity -> epistemic_compromise
    ledger.observe(_result(_trace(2, 0.9, 6.0)))  # high_drift -> simulation_divergence
    summary = ledger.get_root_cause_summary()
    assert summary.get("epistemic_compromise") == 1
    assert summary.get("simulation_divergence") == 1


def test_max_failures_eviction():
    ledger = FailureLedger(max_failures=2)
    for i in range(10):
        rec = FailureRecord(failure_id=f"f{i}", cycle=i, timestamp=1.0,
                            failure_type="low_integrity", severity=0.5,
                            root_cause="epistemic_compromise")
        ledger.record_direct(rec)
    assert ledger.total_failures == 2
    assert ledger.stats["eviction_count"] == 8


def test_stats_shape():
    ledger = FailureLedger()
    ledger.observe(_result(_trace(1, 0.2, 0.5)))
    stats = ledger.stats
    assert stats["total_failures"] == 1
    assert stats["max_failures"] == 10000
    assert stats["by_type"]["low_integrity"] == 1
    assert "root_causes" in stats
