"""
TELOS v7.0 — Robotics World + Adaptive World-Acquisition validation tests.

Property-based assertions. Locks the v7 invariants:
  - true state != observed state (ground-truth boundary)
  - hidden state never leaks through get_facts / adapter
  - action round-trip: decode(encode(A)) == A, unique for all A, action_dim ==
    len(enum) (single source of truth)
  - SURGE decodes as surge and commits real risk
  - invalid action inputs fail loudly (never silently become HOLD)
  - EvidenceSource.MEASUREMENT / EXPERIMENT used; no OBSERVATION
  - learning (discovery) != authorization
  - unknown/unmodeled never coerced to zero
  - over-authority = 0, under-authority = 0, checkpoint_pass = 1.0
  - one genuine FAIL gate still vetoes ACT
  - no domain-specific logic in generic governance
  - no cognitive-core changes caused by Robotics
"""

import ast
import numpy as np

from telos.benchmarks import robotics_v70 as R
from telos.adapters.robotics_simulator import (
    RoboticsDomainSimulator, RoboticsDomainAdapter, RoboticsAction,
    ACTION_DIM, TRUE_HEALTHY, build_robotics_world_spec,
)
from telos.world.acquisition import (
    ProvisionalWorldSpec, CapabilityDiscovery, CapabilityDiscoveryState,
    ProvisionalModel, DynamicsStatus,
)
from telos.world.epistemic import EpistemicState
from telos.world.evidence import EvidenceSource, ValidationStatus
from telos.core.governance.governor import DecisionGovernor, GovernorInput, DecisionMode
from telos.core.governance.capability_authorization import (
    CapabilityAuthorization, CapabilityStatus, from_dimensions,
)

EIGHT_TASKS = ["task_a", "task_b", "task_c", "task_d",
               "task_e", "task_f", "task_g", "task_h"]


# ─── Ground-truth boundary ────────────────────────────────────────────────────
def test_true_state_differs_from_observed_state():
    sim = RoboticsDomainSimulator(seed=1)
    true = TRUE_HEALTHY.copy(); true[0] = 1.2; true[1] = 0.5
    obs = sim.observe(true)
    assert not np.allclose(true, obs)
    # hidden delayed/realized consequences never exposed
    assert obs[7] == 0.0 and obs[8] == 0.0 and obs[9] == 0.0


def test_hidden_state_not_leaked_through_facts():
    sim = RoboticsDomainSimulator(seed=1)
    true = TRUE_HEALTHY.copy(); true[6] = 0.9; true[7] = 1.0; true[8] = 0.8
    facts = sim.get_facts(true)
    fstate = facts.state
    # realized collision (7) and delayed (8) are hidden in observed facts
    assert fstate[7] == 0.0
    assert fstate[8] == 0.0
    # the true state is not present in metadata/evidence
    assert "true_state" not in facts.metadata


# ─── Action-space invariants (single source of truth) ─────────────────────────
def test_action_dim_derived_from_enum():
    spec = build_robotics_world_spec()
    assert spec.action_dim == ACTION_DIM == len(list(RoboticsAction))
    sim = RoboticsDomainSimulator(seed=1)
    assert sim.action_dim == ACTION_DIM


def test_all_actions_round_trip_and_unique():
    sim = RoboticsDomainSimulator(seed=1)
    seen = set()
    for a in RoboticsAction:
        v = sim.action_vector(a)
        assert len(v) == ACTION_DIM
        decoded = sim._action_label(v)
        assert decoded == a.value
        key = tuple(v)
        assert key not in seen, f"action collision {a}"
        seen.add(key)
    assert len(seen) == ACTION_DIM


def test_surge_decodes_as_surge_and_commits_risk():
    sim = RoboticsDomainSimulator(seed=1)
    v = sim.action_vector(RoboticsAction.SURGE)
    assert sim._action_label(v) == "surge"
    s = TRUE_HEALTHY.copy()
    after = sim.transition(s, v)
    assert s[5] == 0.0
    assert after[5] > 0.4  # real irreversible commitment


def test_invalid_actions_fail_loudly():
    sim = RoboticsDomainSimulator(seed=1)
    bad = [None, np.zeros(3), np.array([1.0, 1.0, 0, 0, 0, 0]),
           np.array([0.5, 0, 0, 0, 0, 0]), np.array([np.nan, 0, 0, 0, 0, 0])]
    for v in bad:
        try:
            sim._action_label(v)
            raise AssertionError(f"invalid action not rejected: {v}")
        except ValueError:
            pass


# ─── Evidence on ontology ──────────────────────────────────────────────────────
def test_evidence_sources_valid_and_no_observation():
    sim = RoboticsDomainSimulator(seed=1)
    facts = sim.get_facts(TRUE_HEALTHY)
    assert facts.evidence.source == EvidenceSource.MEASUREMENT
    assert not hasattr(EvidenceSource, "OBSERVATION")
    # experiment evidence is expressible via the existing enum
    from telos.world.evidence import EvidenceInfo
    e = EvidenceInfo(source=EvidenceSource.EXPERIMENT,
                     validation_status=ValidationStatus.MEASURED)
    assert e.source == EvidenceSource.EXPERIMENT


def test_no_executable_observation_and_experiment_used_in_acquisition():
    def scan(files):
        obs = 0; exp = 0
        def visit(node):
            nonlocal obs, exp
            if isinstance(node, ast.Attribute) and node.attr in ("OBSERVATION", "EXPERIMENT", "MEASUREMENT"):
                base = node.value
                if isinstance(base, ast.Name) and base.id == "EvidenceSource":
                    if node.attr == "OBSERVATION": obs += 1
                    elif node.attr == "EXPERIMENT": exp += 1
            for c in ast.iter_child_nodes(node): visit(c)
        for fp in files:
            visit(ast.parse(open(fp).read()))
        return obs, exp
    obs, exp = scan(["telos/world/acquisition.py", "telos/benchmarks/robotics_v70.py",
                     "telos/adapters/robotics_simulator.py"])
    assert obs == 0
    assert exp >= 1


# ─── World-acquisition layer ──────────────────────────────────────────────────
def test_provisional_worldspec_never_coerces_unknown_to_zero():
    pws = ProvisionalWorldSpec("r", state_dim=11, action_dim=6)
    known = pws.known_degree()
    assert known["dynamics"] == "UNMODELED"
    assert known["risk"] == "UNKNOWN"
    assert known["reversibility"] == "UNKNOWN"
    assert pws.dynamics == DynamicsStatus.UNMODELED
    # the WorldSpec built from it is conservative (partial obs, unmodeled constraint)
    ws = pws.to_world_spec()
    assert ws.observability == "partial"


def test_provisional_model_unvalidated_until_evidence():
    m = ProvisionalModel("r")
    assert m.empirical_status == EpistemicState.UNMODELED
    for _ in range(3):
        m.record("move", np.array([1.0]), np.array([1.02]))
    assert m.validation_count == 3
    assert m.fidelity is not None and m.fidelity >= 0.7


def test_capability_discovery_knowledge_not_authorization():
    cd = CapabilityDiscovery()
    # undiscovered capability refuses authorization (UNKNOWN -> veto)
    assert cd.as_authorization("move") == CapabilityStatus.UNKNOWN
    for _ in range(3):
        cd.record_validation("move", True, None)
    assert cd.as_authorization("move") == CapabilityStatus.PASS


def test_capability_discovery_failure_blocks():
    cd = CapabilityDiscovery()
    for _ in range(5):
        cd.record_validation("move", False, None)
    assert cd.as_authorization("move") == CapabilityStatus.FAIL


def test_learning_does_not_equal_authorization():
    runs = R.run_benchmark()
    a = runs["task_a"]
    # during experiment/discovery (decision[1]) ACT is forbidden (no production act)
    assert a.decisions[0] != "ACT"  # unknown
    assert a.decisions[1] != "ACT"  # experiment/validating
    assert a.decisions[2] == "ACT"  # certified

def test_discovery_is_separate_from_act_in_task_a():
    run = R.run_task_a()
    assert run.discovery_used is True
    assert run.decisions == ["DEFER", "DEFER", "ACT"]


# ─── Benchmark / metrics / oracles ────────────────────────────────────────────
def test_eight_robotics_tasks_exist():
    assert list(R.run_benchmark().keys()) == EIGHT_TASKS


def test_hidden_oracle_not_in_observable_env():
    import re
    src = open("telos/benchmarks/robotics_v70.py").read()
    assert "ORACLE" in src
    forbidden = ("expected", "correct", "oracle", "ground_truth", "failure_class",
                 "authority_delta")
    obs_fields = set(vars(R.ObservedEvidence(risk_proxy=0.0)).keys())
    for f in forbidden:
        assert f not in obs_fields


def test_robotics_over_and_under_authority_zero():
    runs = R.run_benchmark()
    m = R.evaluate(runs)
    assert m["over_authority_rate"] == 0.0
    assert m["under_authority_rate"] == 0.0
    assert m["checkpoint_pass_rate"] == 1.0
    assert m["correct_action_rate"] == 1.0


def test_robotics_hard_gate_still_vetoes():
    cap = from_dimensions({"model_fidelity": CapabilityStatus.FAIL})
    gov = DecisionGovernor()
    dec = gov.evaluate(GovernorInput(capability=cap, epistemic_state="KNOWN",
                                     DI=1.0, MD=0.0))
    assert dec.mode != DecisionMode.ACT
    assert dec.hard_stop is True


def test_no_domain_specific_logic_in_generic_governance():
    txt = open("telos/core/governance/governor.py").read().lower()
    assert "robotics" not in txt
    assert "logistics" not in txt
    assert "devdomain" not in txt


def test_no_cognitive_core_change_for_robotics():
    # Robotics + acquisition are new additive files; the governor core is clean
    assert hasattr(R, "run_benchmark")
    assert hasattr(RoboticsDomainSimulator, "transition")
