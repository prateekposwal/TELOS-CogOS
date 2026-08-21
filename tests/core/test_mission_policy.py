"""
Contract tests for telos/core/infra_manager/mission_policy.py — MissionPolicy.

Configures risk/exploration/ambition parameters and provides dynamic
adjustment with an audit trail. Tests assert REAL behavior of the source:
clamping, halving, readiness gating, uncertainty adjustment, UCB, and the
parameter budget drift guard.
"""

import numpy as np

from telos.core.infra_manager.mission_policy import (
    MissionPolicyManager, MissionPolicy, PolicyChangeLog, ParameterBudget,
)


def test_default_policy_values():
    ppm = MissionPolicyManager()
    assert ppm.current.mission_name == "default"
    assert ppm.current.risk_tolerance == 0.3
    assert ppm.current.exploration_budget == 0.3
    assert ppm.current.ambition_level == 0.5
    assert ppm.current.drift_tolerance == 5.0
    assert ppm.current.recovery_mode is False


def test_set_policy_records_history_and_changes():
    ppm = MissionPolicyManager()
    ppm.set_policy(MissionPolicy("high_stakes", risk_tolerance=0.1,
                                 exploration_budget=0.2))
    assert ppm.current.mission_name == "high_stakes"
    assert ppm.current.risk_tolerance == 0.1
    assert len(ppm._policy_history) == 1


def test_adjust_risk_tolerance_clamps_to_upper():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5))
    ppm.adjust_risk_tolerance(10.0)
    assert ppm.current.risk_tolerance == 1.0
    assert ppm.firewall_di_threshold == 0.0


def test_adjust_risk_tolerance_clamps_to_lower():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5))
    ppm.adjust_risk_tolerance(-10.0)
    assert ppm.current.risk_tolerance == 0.0


def test_adjust_risk_no_change_when_same():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=1.0))
    ppm.adjust_risk_tolerance(10.0)  # already 1.0, no change
    assert ppm.current.risk_tolerance == 1.0
    assert ppm._change_log.stats["total_changes"] == 0


def test_adjust_exploration_budget():
    ppm = MissionPolicyManager(MissionPolicy(exploration_budget=0.3))
    ppm.adjust_exploration_budget(0.1)
    assert abs(ppm.current.exploration_budget - 0.4) < 1e-9


def test_firewall_di_threshold_derivation():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.2))
    assert ppm.firewall_di_threshold == 0.8


def test_check_halving_at_interval():
    ppm = MissionPolicyManager(MissionPolicy(exploration_budget=0.8))
    ppm.exploration_halving_cycles = 10
    ppm.check_halving(9)
    assert ppm.current.exploration_budget == 0.8  # not due
    ppm.check_halving(10)
    assert ppm.current.exploration_budget == 0.4
    assert ppm.halving_count == 1


def test_check_halving_zero_cycle_noop():
    ppm = MissionPolicyManager()
    ppm.check_halving(0)
    assert ppm.halving_count == 0


def test_set_readiness_gate_low():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5,
                                             exploration_budget=0.5))
    ppm.set_readiness_gate(0.1)
    assert ppm.current.risk_tolerance == 0.2
    assert ppm.current.exploration_budget == 0.15


def test_set_readiness_gate_medium():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5,
                                             exploration_budget=0.5))
    ppm.set_readiness_gate(0.4)
    assert ppm.current.risk_tolerance == 0.3
    assert ppm.current.exploration_budget == 0.25


def test_set_readiness_gate_high_no_forced_cap():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5,
                                             exploration_budget=0.5))
    ppm.set_readiness_gate(0.9)
    assert ppm.current.risk_tolerance == 0.5
    assert ppm.current.exploration_budget == 0.5


def test_adjust_risk_by_uncertainty_empty_noop():
    ppm = MissionPolicyManager()
    ppm.adjust_risk_by_uncertainty({})
    assert ppm.current.risk_tolerance == 0.3


def test_adjust_risk_by_uncertainty_tightens():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.8))
    ppm.adjust_risk_by_uncertainty({"a": 1.0})
    # target = 0.8 * (1 - 0.5) = 0.4 ; delta = -0.4
    assert abs(ppm.current.risk_tolerance - 0.4) < 1e-9


def test_apply_identity_markers_mapping():
    ppm = MissionPolicyManager(MissionPolicy(risk_tolerance=0.5,
                                             exploration_budget=0.5))
    before_risk = ppm.current.risk_tolerance
    before_exp = ppm.current.exploration_budget
    ppm.apply_identity_markers({"learning_governance", "breaking_patterns"})
    assert ppm.current.risk_tolerance < before_risk
    assert ppm.current.exploration_budget > before_exp


def test_record_and_bonus_never_tried():
    ppm = MissionPolicyManager()
    assert ppm.exploration_bonus("never") == 1.0


def test_record_outcome_updates_ucb():
    ppm = MissionPolicyManager()
    ppm.record_outcome("nav", "move", 0.8)
    ppm.record_outcome("nav", "move", 0.6)
    assert ppm._domain_pulls["nav"] == 2
    assert abs(ppm._domain_rewards["nav"] - 1.4) < 1e-9
    bonus = ppm.exploration_bonus("nav")
    assert 0.0 <= bonus <= 1.0


def test_stats_shape():
    ppm = MissionPolicyManager()
    stats = ppm.stats
    for key in ["mission", "risk_tolerance", "exploration_budget",
                "ambition_level", "drift_tolerance", "firewall_di_threshold",
                "policy_changes", "change_log", "method", "ucb_domains"]:
        assert key in stats
    assert stats["method"] == "ucb_thompson_dual"


def test_parameter_budget_blocks_excessive_drift():
    genesis = MissionPolicy(risk_tolerance=0.3)
    pb = ParameterBudget(genesis)
    assert pb.check_drift("risk_tolerance", 0.9) is True  # drift 0.6 < 0.7
    assert pb.check_drift("risk_tolerance", 1.5) is False  # drift 1.2 > 0.7


def test_curiosity_modulation_records_change():
    ppm = MissionPolicyManager(MissionPolicy(exploration_budget=0.5))
    ppm.apply_curiosity_modulation(1.0)  # no-op
    assert ppm._change_log.stats["total_changes"] == 0
    ppm.apply_curiosity_modulation(1.5)
    assert ppm._change_log.stats["total_changes"] == 1


def test_policy_change_log_caps():
    log = PolicyChangeLog()
    for i in range(12):
        log.record("risk_tolerance", 0.1, 0.2, reason=f"r{i}")
    assert len(log._changes) == 12
    assert len(log.recent) == 10
