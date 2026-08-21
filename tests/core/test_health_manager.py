"""
Contract tests for telos/core/infra_manager/health_manager.py — SystemHealthManager.

Handles recovery mode entry/exit (Axiom 3.1), adaptive horizon (Lambda 2.5),
and predictive degradation. These tests assert the REAL in-place policy mutation
behavior and listener notification.
"""

import numpy as np

from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace
from telos.intent_ir import IntentIR
from telos.core.infra_manager.health_manager import SystemHealthManager, DOMAIN_CONFIGS
from telos.core.infra_manager.mission_policy import MissionPolicyManager, MissionPolicy
from telos.core.infra_manager.audit_controller import AuditController
from telos.core.infra_manager.failure_ledger import FailureLedger


def _make(policy=None, audit=None, failures=None, domain="gridworld"):
    return SystemHealthManager(
        policy or MissionPolicyManager(),
        audit or AuditController(),
        failures or FailureLedger(),
        domain=domain,
    )


def _trace(cycle, di, md, **kw):
    return DecisionTrace(
        cycle_id=cycle, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("test"),
        selected_action=np.array([0.1]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.9, decision_integrity=di, mission_drift=md,
        **kw,
    )


def _result(trace):
    return PipelineResult(None, 0.9, PipelinePhase.COMPLETE, decision_trace=trace)


def test_domain_config_present():
    assert "gridworld" in DOMAIN_CONFIGS
    assert DOMAIN_CONFIGS["gridworld"]["base_horizon"] == 3


def test_unknown_domain_falls_back_to_default():
    h = _make(domain="nonexistent")
    assert h._base_horizon == DOMAIN_CONFIGS["default"]["base_horizon"]


def test_initial_state():
    h = _make()
    assert h.adaptive_horizon is None
    assert h.degradation_cycles == 0
    assert h.watchful_mode is False


def test_adaptive_horizon_setter():
    h = _make()
    h.adaptive_horizon = 7
    assert h.adaptive_horizon == 7


def test_enter_recovery_tightens_policy_in_place():
    policy = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5,
                                                exploration_budget=0.5,
                                                ambition_level=0.7,
                                                drift_tolerance=5.0))
    h = _make(policy=policy)
    logs_before = len(policy._policy_history)
    h.enter_recovery()
    assert policy.current.recovery_mode is True
    assert policy.current.risk_tolerance < 0.5
    assert policy.current.exploration_budget < 0.5
    assert policy.current.ambition_level < 0.7
    # no spurious policy_history entries
    assert len(policy._policy_history) == logs_before
    # horizon shortened: base 3 - 1 = 2
    assert h.adaptive_horizon == 2


def test_enter_recovery_does_not_go_below_floor():
    policy = MissionPolicyManager(MissionPolicy(risk_tolerance=0.05,
                                                exploration_budget=0.05,
                                                ambition_level=0.1,
                                                drift_tolerance=1.0))
    h = _make(policy=policy)
    h.enter_recovery()
    assert policy.current.risk_tolerance >= 0.05
    assert policy.current.exploration_budget >= 0.05
    assert policy.current.ambition_level >= 0.1
    assert policy.current.drift_tolerance >= 1.0


def test_exit_recovery_restores_parameters():
    policy = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5,
                                                exploration_budget=0.5,
                                                ambition_level=0.7,
                                                drift_tolerance=5.0))
    h = _make(policy=policy)
    h.enter_recovery()
    h.exit_recovery()
    assert policy.current.recovery_mode is False
    assert abs(policy.current.risk_tolerance - 0.5) < 1e-9
    assert abs(policy.current.exploration_budget - 0.5) < 1e-9
    assert abs(policy.current.ambition_level - 0.7) < 1e-9
    assert h.adaptive_horizon is None


def test_exit_recovery_without_prior_enter_safe():
    h = _make()
    h.exit_recovery()  # should not raise; restores from default MissionPolicy()
    assert h.adaptive_horizon is None
    assert h.policy.current.recovery_mode is False


def test_recovery_listener_fired_on_enter_and_exit():
    h = _make()
    events = []
    h.on_recovery_event(lambda stage: events.append(stage))
    h.enter_recovery()
    h.exit_recovery()
    assert events == ["enter", "exit"]


def test_observe_clean_cycle_returns_failure_unchanged():
    h = _make()
    trace = _trace(1, 0.9, 0.2)
    failure = h.observe(_result(trace), None, trace)
    assert failure is None
    assert h.policy.current.recovery_mode is False


def test_observe_failure_does_not_immediately_enter_recovery():
    # threshold is 3 (gridworld); one failure should not enter recovery
    policy = MissionPolicyManager()
    failures = FailureLedger()
    h = _make(policy=policy, failures=failures)
    for i in range(2):
        trace = _trace(i, 0.2, 2.0, council_validated=False, blocking_validator="RealityValidator")
        rec = failures.observe(_result(trace))
        h.observe(_result(trace), rec, trace)
    assert h.policy.current.recovery_mode is False


def test_enter_recovery_timeout_force_exit():
    policy = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5))
    h = _make(policy=policy)
    h.enter_recovery()
    # simulate max recovery cycles reached
    h._recovery_cycle_count = h._max_recovery_cycles - 1
    trace = _trace(1, 0.9, 0.2)
    h.observe(_result(trace), None, trace)
    assert policy.current.recovery_mode is False


def test_stats_shape():
    h = _make()
    stats = h.stats
    assert stats["degradation_cycles"] == 0
    assert stats["watchful_mode"] is False
    assert stats["adaptive_horizon"] is None
    assert "recovery_listeners" in stats
    assert "council_block_listeners" in stats
