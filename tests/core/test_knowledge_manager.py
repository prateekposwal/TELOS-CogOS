"""
Contract tests for telos/core/infra_manager/knowledge_manager.py — KnowledgeManager.

Handles knowledge consultation, outcome recording, UCB outcomes, identity
updates, and perception feedback. These tests assert the REAL behavior:
consultation throttling, policy adjustment, outcome recording to the
KnowledgeGraph, and linker delegation.
"""

import numpy as np

from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace
from telos.intent_ir import IntentIR
from telos.core.infra_manager.knowledge_manager import KnowledgeManager
from telos.core.infra_manager.mission_policy import MissionPolicyManager, MissionPolicy
from telos.core.identity.system_self import SystemSelf


def _make(domain="gridworld", risk=0.3, exploration=0.3):
    policy = MissionPolicyManager(MissionPolicy(risk_tolerance=risk,
                                                exploration_budget=exploration))
    ss = SystemSelf()
    km = KnowledgeManager(policy, ss, domain=domain)
    return km, policy, ss


def _trace(cycle, di, md, intent="good", council_validated=True):
    return DecisionTrace(
        cycle_id=cycle, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR(intent),
        selected_action=np.array([0.1]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.9, council_validated=council_validated,
        decision_integrity=di, mission_drift=md,
    )


def _result(trace, health=0.9, **kw):
    return PipelineResult(None, health, PipelinePhase.COMPLETE,
                          decision_trace=trace, **kw)


def test_constructs_knowledge_subsystem():
    km, _, _ = _make()
    assert km.knowledge is not None
    assert km.inference is not None
    assert km.recommender is not None
    assert km.recorder is not None
    assert km.linker is not None


def test_domain_scale_gridworld():
    km, _, _ = _make(domain="gridworld")
    assert km._get_domain_scale("risk") == 0.1
    assert km._get_domain_scale("exploration") == 0.1


def test_domain_scale_unknown_falls_back():
    km, _, _ = _make(domain="bogus")
    assert km._get_domain_scale("risk") == 0.05


def test_search_knowledge_empty_starts():
    km, _, _ = _make()
    assert km.search_knowledge("gridworld") == []


def test_consult_throttles_within_3_cycles():
    km, _, _ = _make()
    first = km.consult_knowledge("nav", cycle=0)
    assert first.get("throttled") is None
    second = km.consult_knowledge("nav", cycle=1)
    assert second.get("throttled") is True
    assert second.get("adjust_risk") == 0.0


def test_consult_no_proven_adjusts_risk_down_explore_up():
    km, policy, _ = _make(risk=0.5, exploration=0.3)
    report = km.consult_knowledge("novel_domain_xyz", cycle=0)
    assert report["approach"] is None
    assert report["adjust_risk"] < 0.0  # -0.05 * risk_scale
    assert report["adjust_exploration"] > 0.0
    # policy applied
    assert policy.current.risk_tolerance < 0.5
    assert policy.current.exploration_budget > 0.3


def test_observe_success_records_knowledge_and_policy_outcome():
    km, policy, _ = _make()
    trace = _trace(1, 0.9, 0.2, intent="good")
    result = _result(trace)
    result.domain = "gridworld"
    failure = km.observe(result, None, trace)
    assert failure is None
    assert len(km.knowledge._nodes) == 1  # success recorded
    assert policy._domain_pulls.get("gridworld") == 1


def test_observe_without_trace_ticks_only():
    km, _, _ = _make()
    result = PipelineResult(None, 0.9, PipelinePhase.COMPLETE, decision_trace=None)
    failure = km.observe(result, None, None)
    assert failure is None
    assert len(km.knowledge._nodes) == 0


def test_observe_failure_records_failure_node():
    km, _, _ = _make()
    trace = _trace(1, 0.2, 0.4, intent="bad")
    result = _result(trace)
    result.domain = "gridworld"
    from telos.core.infra_manager.failure_ledger import FailureRecord
    rec = FailureRecord(failure_id="f1", cycle=1, timestamp=1.0,
                        failure_type="low_integrity", severity=0.5,
                        root_cause="epistemic_compromise")
    failure = km.observe(result, rec, trace)
    assert failure is rec
    # low_integrity failure recorded (failure_type tag)
    assert len(km.knowledge._nodes) >= 1


def test_linker_delegation_methods_exist():
    km, _, _ = _make()
    assert km.attach_genealogy is not None
    assert km.link_node_to_theory is not None
    assert km.link_theory_to_scm is not None
    assert km.link_promoted_theory is not None
    assert km.get_connected_structure is not None


def test_link_promoted_theory_returns_zero_when_no_domains():
    km, _, _ = _make()
    class FakeTheory:
        domains = []
    assert km.link_promoted_theory(FakeTheory(), "genealogy_1") == 0


def test_stats_shape():
    km, _, _ = _make()
    stats = km.stats
    for key in ["knowledge_nodes", "last_consultations", "linked_theories",
                "linked_scm_structures", "identity_nodes"]:
        assert key in stats
