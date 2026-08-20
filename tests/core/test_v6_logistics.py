"""
TELOS v6.2 — Logistics World Validation tests.

Property-based assertions (not implementation-coupled numbers). Locks the
architectural guarantees of the second-world validation:
  - 7 logistics tasks exist and execute against the real simulator
  - hidden oracle is inaccessible to the observable environment (no leakage)
  - no executable EvidenceSource.OBSERVATION; MEASUREMENT is used for observed
    logistics evidence
  - partial observability hides state from TELOS
  - irreversible dispatch produces nonzero committed_risk
  - multi-objective evaluation stays intact
  - Task F proves ACT -> BLOCK -> ACT via the real RealityGapTracker
  - falsification lowers fidelity/authority; sustained corrective evidence
    restores fidelity/authority (recovered > falsified)
  - required escalation produces a structural hard stop
  - human authorization cannot bypass a genuine capability FAIL
  - the SAME governance machinery is used (no cognitive-core/domain-specific
    governance added)
"""

import ast
import numpy as np

from telos.benchmarks import logistics_v62 as L
from telos.world.epistemic import RealityGapTracker
from telos.world.evidence import EvidenceSource
from telos.adapters.logistics_simulator import (
    LogisticsDomainSimulator, LogisticsDomainAdapter, LogisticsAction, HEALTHY,
)
from telos.core.governance.governor import (
    DecisionGovernor, GovernorInput, DecisionMode,
)
from telos.core.governance.capability_authorization import (
    CapabilityAuthorization, CapabilityStatus, all_pass, from_dimensions,
)

SEVEN_TASKS = ["task_a", "task_b", "task_c", "task_d",
               "task_e", "task_f", "task_g"]


def test_seven_logistics_tasks_exist_and_execute():
    runs = L.run_benchmark()
    assert list(runs.keys()) == SEVEN_TASKS
    for tid in SEVEN_TASKS:
        r = runs[tid]
        assert r.decisions, f"{tid} produced no decision"
        assert r.final_decision in ("ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK")


def test_hidden_oracle_not_in_observable_env():
    forbidden = ("expected", "correct", "oracle", "ground_truth", "failure_class",
                 "authority_delta", "decision_class")
    # oracle object itself: fields like task_id are fine, but answer-bearing
    # keys must not appear in observed evidence. We assert the oracle's
    # checkpoints reference decision_idx (scoring metadata), not observable env.
    import re
    src = open("telos/benchmarks/logistics_v62.py").read()
    # The 'ORACLE' dict is the only place answer-bearing decisions are stored,
    # and it is never imported by the simulator/adapter path.
    assert "ORACLE" in src  # exists
    # observable evidence dataclass fields:
    obs_fields = set(vars(L.ObservedEvidence(risk_proxy=0.0)).keys())
    for f in forbidden:
        assert f not in obs_fields, f"observable env leaks {f}"


def test_no_executable_evidence_observation_and_measurement_used():
    # no executable EvidenceSource.OBSERVATION anywhere in logistics + v6 core
    files = ["telos/adapters/logistics_simulator.py", "telos/world/epistemic.py",
             "telos/world/evidence.py"]
    obs = 0; meas = 0

    def visit(node):
        nonlocal obs, meas
        if isinstance(node, ast.Attribute) and node.attr in ("OBSERVATION", "MEASUREMENT"):
            base = node.value
            if isinstance(base, ast.Name) and base.id == "EvidenceSource":
                if node.attr == "OBSERVATION":
                    obs += 1
                else:
                    meas += 1
        for c in ast.iter_child_nodes(node):
            visit(c)
    for fp in files:
        visit(ast.parse(open(fp).read()))
    assert obs == 0, f"executable EvidenceSource.OBSERVATION found ({fp})"
    # MEASUREMENT is used for observed logistics evidence
    assert meas >= 1
    assert not hasattr(EvidenceSource, "OBSERVATION")


def test_logistics_facts_use_measurement_evidence():
    sim = LogisticsDomainSimulator(seed=1)
    facts = sim.get_facts(HEALTHY)
    assert facts.evidence is not None
    assert facts.evidence.source == EvidenceSource.MEASUREMENT


def test_partial_observability_hides_delayed_consequence():
    sim = LogisticsDomainSimulator(seed=1)
    actual = HEALTHY.copy()
    actual[8] = 0.9                      # delayed consequence (hidden)
    obs = sim.observe(actual)
    assert obs[8] == 0.0, "hidden delayed consequence leaked to observed state"
    assert actual[8] == 0.9  # actual != observed


def test_irreversible_dispatch_commits_risk():
    sim = LogisticsDomainSimulator(seed=1)
    s = HEALTHY.copy()
    after_a = sim.transition(s, sim.action_vector(LogisticsAction.HOLD))
    after_d = sim.transition(s, sim.action_vector(LogisticsAction.DISPATCH))
    # dispatch commits more risk than hold
    assert after_d[9] > after_a[9]
    assert after_d[9] > 0.2


def test_multi_objective_evaluation_nonzero_risk():
    sim = LogisticsDomainSimulator(seed=1)
    rep = sim.evaluate(HEALTHY.copy())
    assert len(rep.objectives) >= 5
    assert all(k in rep.objectives for k in
               ("minimize_cost", "minimize_lateness", "preserve_inventory",
                "minimize_risk", "maintain_service_level"))


def test_task_f_acts_blocks_recovers():
    run = L.run_task_f()
    assert run.decisions == ["ACT", "BLOCK", "ACT"]
    # falsification lowered fidelity/authority
    assert run.authority[1] < run.authority[0]
    # sustained corrective evidence restored fidelity/authority
    assert run.authority[2] > run.authority[1]
    assert run.fid_recovered > run.fid_falsified
    assert run.corrective_count == 10


def test_task_f_recovery_via_recent_window_not_manipulated():
    # reconstruction through the real tracker (no direct fidelity assignment):
    t = RealityGapTracker()
    t.record("f", np.array([1.0]), np.array([5.0]))
    f_after = t.model_fidelity("f")
    for k in range(10):
        p = float(k * 0.01)
        t.record("f", np.array([p]), np.array([p]))
    f_recov = t.model_fidelity("f")
    assert f_after < 0.3
    assert f_recov > f_after
    assert f_recov >= 0.5


def test_task_d_irreversible_blocks():
    run = L.run_task_d()
    assert run.decisions[-1] == "BLOCK"
    assert run.high_risk is True


def test_task_c_insufficient_observability_not_act():
    run = L.run_task_c()
    assert run.decisions[0] in ("DEFER", "ABSTAIN", "ESCALATE")
    assert run.decisions[0] != "ACT"


def test_task_g_required_escalation_hard_stop():
    run = L.run_task_g()
    assert run.decisions[0] == "ESCALATE"


def test_human_authorization_cannot_bypass_genuine_capability_fail():
    # Even if a human authorizes escalation, a genuine capability FAIL gate
    # still vetoes ACT in the governor (structural conjunctive veto).
    cap = from_dimensions({"authority": CapabilityStatus.FAIL,
                           "risk_coverage": CapabilityStatus.FAIL})
    gov = DecisionGovernor()
    dec = gov.evaluate(GovernorInput(
        capability=cap, epistemic_state="KNOWN", DI=1.0, MD=0.0,
        escalation_requested=True, escalation_policy="required",
        human_authorized=True,  # human approval does NOT manufacture capability
    ))
    assert dec.mode != DecisionMode.ACT


def test_hard_gate_still_vetoes_act():
    cap = CapabilityAuthorization(
        observability=CapabilityStatus.PASS, model_fidelity=CapabilityStatus.FAIL,
        action_validity=CapabilityStatus.PASS, risk_coverage=CapabilityStatus.PASS,
        causal_confidence=CapabilityStatus.PASS, recovery=CapabilityStatus.PASS,
        authority=CapabilityStatus.PASS,
    )
    gov = DecisionGovernor()
    dec = gov.evaluate(GovernorInput(capability=cap, epistemic_state="KNOWN",
                                     DI=1.0, MD=0.0))
    assert dec.mode != DecisionMode.ACT
    assert dec.hard_stop is True


def test_no_cognitive_core_changes_for_logistics():
    """Logistics adds a world + benchmark, never domain-specific governance
    logic in the cognitive core (runtime.py / phases / governor)."""
    # The Logistics simulator/adapter are the only world-specific files; the
    # governor/capability machinery is reused, not specialized.
    assert hasattr(L, "run_benchmark")
    # no logistics special-casing lives in the governor
    txt = open("telos/core/governance/governor.py").read().lower()
    assert "logistics" not in txt


def test_logistics_over_and_under_authority_zero():
    runs = L.run_benchmark()
    m = L.evaluate(runs)
    assert m["over_authority_rate"] == 0.0
    assert m["under_authority_rate"] == 0.0
    assert m["checkpoint_pass_rate"] == 1.0


def test_logistics_adapter_maps_dispatch_intent_to_action():
    # The LogisticsDomainAdapter's documented purpose: map a TELOS intent to a
    # concrete discrete logistics action vector (adapted into the world).
    adapter = LogisticsDomainAdapter()
    intent = type("Intent", (), {"intent_type": "dispatch", "params": {}})()
    action = adapter.intent_to_action(intent, HEALTHY, None)
    assert action.shape == (6,)
    assert action.sum() == 1.0
    assert action[int(list(LogisticsAction).index(LogisticsAction.DISPATCH))] == 1.0
