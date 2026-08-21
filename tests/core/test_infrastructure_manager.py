"""
Contract tests for telos/core/infra_manager/infrastructure_manager.py — InfrastructureManager.

The meta-runtime that observes pipeline results and adjusts cognitive parameters.
These tests assert the REAL wiring: collaborator construction, delegation, and
observe() side effects on policy/audit/knowledge/system_self.
"""

import numpy as np

from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace
from telos.intent_ir import IntentIR
from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
from telos.core.infra_manager.audit_controller import InfrastructureReport


def _trace(cycle, di, md, council_validated=True, firewall_blocked=False,
           blocking_validator=None, health=0.9):
    return DecisionTrace(
        cycle_id=cycle, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("test"),
        selected_action=np.array([0.1]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=health, council_validated=council_validated,
        decision_integrity=di, mission_drift=md,
        firewall_blocked=firewall_blocked,
        blocking_validator=blocking_validator,
    )


def _result(trace, health=0.9, **kw):
    return PipelineResult(None, health, PipelinePhase.COMPLETE,
                          decision_trace=trace, **kw)


def test_constructs_all_collaborators():
    infra = InfrastructureManager()
    assert infra.calibrator is not None
    assert infra.failures is not None
    assert infra.policy is not None
    assert infra.audit is not None
    assert infra.system_self is not None
    assert infra.knowledge_mgr is not None
    assert infra.health is not None
    assert infra.cost_tracker is not None
    assert infra.resource_gradient is not None


def test_registers_components():
    infra = InfrastructureManager()
    names = set(infra.audit._component_maturities.keys())
    for expected in ["stream_calibrator", "failure_ledger", "mission_policy",
                     "audit_controller", "health_manager", "knowledge_manager",
                     "cost_tracker"]:
        assert expected in names


def test_set_mission_creates_policy():
    infra = InfrastructureManager()
    infra.set_mission("high_stakes", risk_tolerance=0.1, exploration_budget=0.2)
    assert infra.policy.current.mission_name == "high_stakes"
    assert infra.policy.current.risk_tolerance == 0.1
    assert infra.policy.current.exploration_budget == 0.2


def test_observe_none_is_safe():
    infra = InfrastructureManager()
    infra.observe(None)
    assert infra.audit.stats["cycles_observed"] == 0


def test_observe_clean_cycle_updates_audit_and_cost():
    infra = InfrastructureManager()
    trace = _trace(1, 0.9, 0.2)
    infra.observe(_result(trace), total_streams=4)
    assert infra.audit.stats["cycles_observed"] == 1
    assert infra._total_streams == 4
    # DI > 0.8 -> maintenance cost recorded
    assert infra.cost_tracker.stats["total_maintenance"] == 0.1
    assert infra.cost_tracker.stats["cycles_recorded"] == 1
    assert infra.cost_tracker.stats["recent_maintenance"] == [0.1]


def test_observe_clean_cycle_records_knowledge():
    infra = InfrastructureManager()
    trace = _trace(1, 0.9, 0.2)
    infra.observe(_result(trace))
    # knowledge_manager.observe records a success node for 'unknown' domain
    assert len(infra.knowledge_mgr.knowledge._nodes) >= 1


def test_observe_budget_starvation_records_failure():
    infra = InfrastructureManager()
    trace = _trace(1, 0.5, 0.5)
    infra.observe(_result(trace, health=0.1), total_streams=5)
    by_type = infra.failures.stats["by_type"]
    assert by_type.get("budget_starvation", 0) == 1


def test_observe_escalation_records_failure():
    infra = InfrastructureManager()
    trace = _trace(1, 0.8, 0.5)
    trace.escalation_requested = True
    trace.escalation_reason = "high uncertainty"
    infra.observe(_result(trace))
    by_type = infra.failures.stats["by_type"]
    assert by_type.get("escalation", 0) == 1
    assert infra._escalation_count == 1


def test_council_block_callback_fired():
    infra = InfrastructureManager()
    received = []
    infra.on_council_block(lambda info: received.append(info))
    trace = _trace(1, 0.2, 2.0, council_validated=False,
                   blocking_validator="RealityValidator")
    infra.observe(_result(trace, council_blocked=True))
    assert len(received) == 1
    assert received[0]["blocking_validator"] == "RealityValidator"


def test_enter_exit_recovery_delegates():
    infra = InfrastructureManager()
    infra.enter_recovery()
    assert infra.policy.current.recovery_mode is True
    assert isinstance(infra.adaptive_horizon, int)
    infra.exit_recovery()
    assert infra.policy.current.recovery_mode is False
    assert infra.adaptive_horizon is None


def test_adaptive_horizon_property():
    infra = InfrastructureManager()
    infra.adaptive_horizon = 5
    assert infra.adaptive_horizon == 5
    assert infra.health.adaptive_horizon == 5


def test_search_and_consult_delegate_to_knowledge_manager():
    infra = InfrastructureManager()
    assert infra.search_knowledge("gridworld") == []
    report = infra.consult_knowledge("gridworld")
    assert "domain" in report
    assert "adjust_risk" in report


def test_knowledge_property_returns_knowledge_graph():
    infra = InfrastructureManager()
    assert infra.knowledge is infra.knowledge_mgr.knowledge


def test_generate_report_returns_infrastructure_report():
    infra = InfrastructureManager()
    report = infra.generate_report()
    assert isinstance(report, InfrastructureReport)
    assert report.total_cycles == 0


def test_stats_shape():
    infra = InfrastructureManager()
    stats = infra.stats
    for key in ["calibrator", "failures", "policy", "audit", "health",
                "knowledge", "system_self", "cost_tracker"]:
        assert key in stats
