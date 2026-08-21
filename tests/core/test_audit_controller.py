"""
Contract tests for telos/core/infra_manager/audit_controller.py — AuditController.

The AuditController tracks infrastructure maturity and emits health reports.
These tests assert the REAL behavior of the source: component registration,
maturity scoring, composite health-score math, and history accessors.
"""

import numpy as np

from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace
from telos.intent_ir import IntentIR
from telos.core.infra_manager.audit_controller import AuditController, ComponentMaturity, InfrastructureReport


def _trace(cycle, di, md, council_validated=True, firewall_blocked=False, blocking=None):
    return DecisionTrace(
        cycle_id=cycle, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("test"),
        selected_action=np.array([0.1]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.9, council_validated=council_validated,
        decision_integrity=di, mission_drift=md,
        firewall_blocked=firewall_blocked, blocking_validator=blocking,
    )


def _result(trace, health=0.9):
    return PipelineResult(None, health, PipelinePhase.COMPLETE, decision_trace=trace)


def test_register_component_returns_maturity_object():
    ac = AuditController()
    mat = ac.register_component("hw")
    assert isinstance(mat, ComponentMaturity)
    assert mat.component_name == "hw"
    assert "hw" in ac._component_maturities


def test_evaluate_component_maturity_unknown_returns_zero():
    ac = AuditController()
    assert ac.evaluate_component_maturity("missing") == 0.0


def test_maturity_scoring_weights_cycles_coverage_calibration():
    ac = AuditController()
    mat = ac.register_component("comp")
    mat.cycles_active = 100
    mat.calibration_count = 50
    mat.coverage_score = 1.0
    # cycle_factor=1.0, cal_factor=1.0, cov=1.0 -> 0.3+0.4+0.3 = 1.0
    assert ac.evaluate_component_maturity("comp") == 1.0


def test_maturity_scoring_saturates():
    ac = AuditController()
    mat = ac.register_component("comp")
    mat.cycles_active = 1000
    mat.calibration_count = 500
    mat.coverage_score = 1.5  # not clamped on input; np.clip result to [0,1]
    score = ac.evaluate_component_maturity("comp")
    assert 0.0 <= score <= 1.0
    assert score == 1.0


def test_infra_readiness_no_components_zero():
    ac = AuditController()
    assert ac.infra_readiness_score() == 0.0


def test_infra_readiness_average_of_components():
    ac = AuditController()
    m1 = ac.register_component("a")
    m1.cycles_active = 100
    m1.calibration_count = 50
    m1.coverage_score = 1.0
    m2 = ac.register_component("b")
    m2.cycles_active = 0
    m2.calibration_count = 0
    m2.coverage_score = 0.0
    # a -> 1.0, b -> 0.0 ; mean = 0.5
    assert ac.infra_readiness_score() == 0.5


def test_observe_with_none_trace_still_counts_cycle():
    ac = AuditController()
    result = PipelineResult(None, 0.9, PipelinePhase.COMPLETE, decision_trace=None)
    ac.observe(result)
    assert ac._cycle_count == 1
    assert ac.get_di_history() == []


def test_observe_appends_histories_and_counts():
    ac = AuditController()
    ac.observe(_result(_trace(1, 0.9, 0.2)))
    ac.observe(_result(_trace(2, 0.8, 0.3)))
    assert ac.get_di_history() == [0.9, 0.8]
    assert ac.get_md_history() == [0.2, 0.3]


def test_observe_counts_failure_and_block():
    ac = AuditController()
    # firewall block counts as failure + governance block
    ac.observe(_result(_trace(1, 0.5, 2.0, firewall_blocked=True, blocking="fw")))
    # not council validated counts as failure
    ac.observe(_result(_trace(2, 0.5, 2.0, council_validated=False)))
    # clean
    ac.observe(_result(_trace(3, 0.9, 0.2)))
    assert ac._cycle_count == 3
    assert ac._failure_count == 2
    assert ac._governance_block_count == 1


def test_generate_report_empty_defaults():
    ac = AuditController()
    report = ac.generate_report()
    assert isinstance(report, InfrastructureReport)
    assert report.total_cycles == 0
    assert report.failure_rate == 0.0
    assert report.governance_block_rate == 0.0
    assert report.avg_decision_integrity == 1.0
    assert report.avg_mission_drift == 0.0
    assert report.health_score == 1.0  # 0.3*1+0.3*1+0.2*1+0.2*1
    assert report.infra_readiness_score == 0.0


def test_generate_report_composite_health_math():
    ac = AuditController()
    # one clean cycle di=1.0 md=0.2 health=0.9
    ac.observe(PipelineResult(None, 0.9, PipelinePhase.COMPLETE,
                              decision_trace=_trace(1, 1.0, 0.2)))
    report = ac.generate_report(calibrated_streams=1, total_streams=2)
    assert report.total_cycles == 1
    assert report.failure_rate == 0.0
    assert report.stream_calibration_coverage == 0.5
    assert abs(report.avg_decision_integrity - 1.0) < 1e-9
    # health = 0.3*1 + 0.3*1 + 0.2*1 + 0.2*0.9 = 0.98 (avg_health is the
    # observed result health 0.9, not 1.0)
    assert abs(report.health_score - 0.98) < 1e-9


def test_generate_report_failure_rate_affects_health():
    ac = AuditController()
    ac.observe(_result(_trace(1, 0.5, 2.0, firewall_blocked=True, blocking="fw")))
    report = ac.generate_report()
    assert report.failure_rate == 1.0
    assert report.governance_block_rate == 1.0
    # health = 0.3*0.5 + 0.3*0 + 0.2*0 + 0.2*0.9 = 0.15+0+0+0.18 = 0.33
    # (avg_health is the observed result health 0.9, not 1.0)
    assert abs(report.health_score - 0.33) < 1e-9


def test_stats_returns_di_and_md_trends():
    ac = AuditController()
    for i in range(12):
        ac.observe(_result(_trace(i, 0.9, 0.2)))
    stats = ac.stats
    assert stats["cycles_observed"] == 12
    assert stats["failures"] == 0
    assert stats["governance_blocks"] == 0
    assert abs(stats["di_trend"] - 0.9) < 1e-9
    assert abs(stats["md_trend"] - 0.2) < 1e-9


def test_stats_empty_defaults():
    ac = AuditController()
    stats = ac.stats
    assert stats["di_trend"] == 1.0
    assert stats["md_trend"] == 0.0
