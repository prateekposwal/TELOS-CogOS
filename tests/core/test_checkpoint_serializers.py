"""Contract tests for telos.core.infra_manager.checkpoint_serializers.

Each subsystem serializer pair (dump_*/load_*) is tested with the real
subsystem objects it is designed to serialize:
  - WorldLedger user profiles / entity counts
  - SkillLibrary active + archived skills
  - StreamCalibrator calibration state
  - FailureLedger failure records
  - MissionPolicyManager current policy + UCB domain pulls/rewards
  - KnowledgeGraph nodes + edges
  - SimEngine last options (StrategicOption)
  - PlanningHorizon duck-typed state
  - DecisionTrace projection
  - session-essence / truncated-history loaders
"""
import numpy as np
import pytest

from telos.core.infra_manager import checkpoint_serializers as ser
from telos.core.ledger.world_ledger import WorldLedger
from telos.core.ledger.skill_library import SkillLibrary, Skill
from telos.core.infra_manager.stream_calibrator import StreamCalibrator, StreamCalibration
from telos.core.infra_manager.failure_ledger import FailureLedger, FailureRecord
from telos.core.infra_manager.mission_policy import MissionPolicy, MissionPolicyManager
from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.simulation.options import StrategicOption
from telos.core.types import DecisionTrace


# ── Ledger ──────────────────────────────────────────────────────────

def _populated_ledger():
    ledger = WorldLedger()
    ledger.upsert_user("alice")
    ledger.record_user_interaction("alice", "perceive", 0.9, cycle=1)
    ledger.record_user_interaction("alice", "inquiry", 0.7, cycle=2)
    ledger.upsert_user("bob")
    return ledger


def test_dump_ledger_contract_fields():
    data = ser.dump_ledger(_populated_ledger())
    assert "entity_count" in data
    assert "user_profiles" in data
    names = [p["name"] for p in data["user_profiles"]]
    assert set(names) == {"alice", "bob"}
    alice = next(p for p in data["user_profiles"] if p["name"] == "alice")
    assert alice["total_interactions"] == 2
    assert alice["last_intent"] == "inquiry"
    assert alice["trust_level"] == pytest.approx(0.5)
    assert alice["relationship_summary"] != "new_user"
    assert len(alice["interaction_history"]) == 2


def test_ledger_round_trip():
    source = _populated_ledger()
    data = ser.dump_ledger(source)
    target = WorldLedger()
    ser.load_ledger(data, target)
    restored = target.get_user_profile("alice")
    assert restored is not None
    assert restored.name == "alice"
    assert restored.total_interactions == 2
    assert restored.last_intent == "inquiry"
    assert restored.trust_level == pytest.approx(source.get_user_profile("alice").trust_level)
    assert restored.relationship_summary == "emerging_familiarity"


def test_load_ledger_empty_or_missing_target_is_noop():
    ser.load_ledger({}, _populated_ledger())
    ser.load_ledger({"user_profiles": []}, WorldLedger())
    ser.load_ledger({"user_profiles": [{"name": "x"}]}, None)


def test_ledger_entity_count_reflects_records():
    ledger = WorldLedger()
    from telos.world.world import World
    w = World(state=np.zeros(2), entities=["ball", "robot"])
    ledger.enrich(w, cycle=0)
    data = ser.dump_ledger(ledger)
    assert data["entity_count"] == 2


# ── SkillLibrary ────────────────────────────────────────────────────

def _populated_skill_library():
    lib = SkillLibrary()
    lib.index_skill(Skill(
        skill_id="sk_a", fingerprint="fp_a", trajectory=None,
        utility_score=0.9, metadata={"trained": True},
    ))
    lib.index_skill(Skill(
        skill_id="sk_b", fingerprint="fp_b", trajectory=None,
        utility_score=0.4, metadata={},
    ))
    lib.skills["sk_a"].last_matched_cycle = 7
    archived = Skill(skill_id="sk_old", fingerprint="fp_old", trajectory=None,
                     utility_score=0.2, metadata={"retired": True})
    archived.last_matched_cycle = 3
    lib._archived.append(archived)
    return lib


def test_dump_skills_contract_fields():
    data = ser.dump_skills(_populated_skill_library())
    assert set(data.keys()) == {"skills", "archived"}
    ids = {s["skill_id"] for s in data["skills"]}
    assert ids == {"sk_a", "sk_b"}
    sk_a = next(s for s in data["skills"] if s["skill_id"] == "sk_a")
    assert sk_a["fingerprint"] == "fp_a"
    assert sk_a["utility_score"] == 0.9
    assert sk_a["last_matched_cycle"] == 7
    assert sk_a["metadata"] == {"trained": True}
    assert [a["skill_id"] for a in data["archived"]] == ["sk_old"]


def test_skills_round_trip():
    data = ser.dump_skills(_populated_skill_library())
    target = SkillLibrary()
    ser.load_skills(data, target)
    assert set(target.skills.keys()) == {"sk_a", "sk_b"}
    assert target.skills["sk_a"].fingerprint == "fp_a"
    assert target.skills["sk_a"].utility_score == 0.9
    assert target.skills["sk_a"].last_matched_cycle == 7
    assert [s.skill_id for s in target._archived] == ["sk_old"]


def test_dump_skills_empty_library():
    data = ser.dump_skills(SkillLibrary())
    assert data == {"skills": [], "archived": []}


# ── StreamCalibrator ────────────────────────────────────────────────

def _populated_calibrator():
    cal = StreamCalibrator()
    cal._calibrations["perceive"] = StreamCalibration(
        stream_name="perceive", total_calls=10, accurate_calls=8,
        confidence_history=[0.8, 0.9], drift_history=[0.1, 0.2],
        historical_reliability=0.85, influence_weight=1.2,
        last_calibrated=123.0,
    )
    return cal


def test_dump_calibrator_contract_fields():
    data = ser.dump_calibrator(_populated_calibrator())
    assert "calibrations" in data
    cal = data["calibrations"]["perceive"]
    assert cal["stream_name"] == "perceive"
    assert cal["total_calls"] == 10
    assert cal["accurate_calls"] == 8
    assert cal["confidence_history"] == [0.8, 0.9]
    assert cal["drift_history"] == [0.1, 0.2]
    assert cal["historical_reliability"] == 0.85
    assert cal["influence_weight"] == 1.2
    assert cal["last_calibrated"] == 123.0


def test_calibrator_round_trip():
    data = ser.dump_calibrator(_populated_calibrator())
    target = StreamCalibrator()
    ser.load_calibrator(data, target)
    restored = target._calibrations["perceive"]
    assert restored.stream_name == "perceive"
    assert restored.total_calls == 10
    assert restored.accurate_calls == 8
    assert restored.confidence_history == [0.8, 0.9]
    assert restored.historical_reliability == 0.85
    assert restored.influence_weight == 1.2


def test_calibrator_legacy_weights_path():
    class LegacyCalibrator:
        def __init__(self):
            self._weights = {}
            self._accuracy = {}
            self._total_calls = {}

    src = LegacyCalibrator()
    src._weights["perceive"] = 1.1
    src._accuracy["perceive"] = 0.9
    src._total_calls["perceive"] = 5
    data = ser.dump_calibrator(src)
    assert data["weights"] == {"perceive": 1.1}
    assert data["accuracy"] == {"perceive": 0.9}
    assert data["total_calls"] == {"perceive": 5}

    target = LegacyCalibrator()
    ser.load_calibrator(data, target)
    assert target._weights["perceive"] == 1.1
    assert target._accuracy["perceive"] == 0.9
    assert target._total_calls["perceive"] == 5


# ── FailureLedger ───────────────────────────────────────────────────

def _populated_failure_ledger():
    ledger = FailureLedger()
    ledger.record_direct(FailureRecord(
        failure_id="f1", cycle=3, timestamp=1.0, failure_type="council_block",
        severity=0.8, root_cause="governance_intervention",
        blocked_by="mission_memory", decision_integrity=0.4, mission_drift=2.0,
    ))
    ledger.record_direct(FailureRecord(
        failure_id="f2", cycle=4, timestamp=2.0, failure_type="high_drift",
        severity=0.6, root_cause="simulation_divergence", decision_integrity=1.0,
        mission_drift=7.0,
    ))
    return ledger


def test_dump_failures_contract_fields():
    data = ser.dump_failures(_populated_failure_ledger())
    assert isinstance(data, list)
    assert len(data) == 2
    first = data[0]
    assert first["cycle"] == 3
    assert first["failure_type"] == "council_block"
    assert first["severity"] == 0.8
    assert first["root_cause"] == "governance_intervention"
    assert first["blocked_by"] == "mission_memory"
    assert first["decision_integrity"] == 0.4
    assert first["mission_drift"] == 2.0


def test_failures_round_trip():
    data = ser.dump_failures(_populated_failure_ledger())
    target = FailureLedger()
    ser.load_failures(data, target)
    assert target.total_failures == 2
    restored = target._failures[0]
    assert restored.failure_id.startswith("restored_")
    assert restored.cycle == 3
    assert restored.failure_type == "council_block"
    assert restored.severity == 0.8
    assert restored.root_cause == "governance_intervention"
    assert restored.blocked_by == "mission_memory"
    assert restored.decision_integrity == 0.4
    assert restored.mission_drift == 2.0


def test_dump_failures_empty_or_missing_attr():
    assert ser.dump_failures(FailureLedger()) == []
    assert ser.dump_failures(object()) == []


def test_load_failures_empty_is_noop():
    target = FailureLedger()
    ser.load_failures([], target)
    assert target.total_failures == 0


# ── MissionPolicy ───────────────────────────────────────────────────

def _populated_policy():
    manager = MissionPolicyManager(MissionPolicy(
        mission_name="probe", risk_tolerance=0.4, exploration_budget=0.5,
        ambition_level=0.6, drift_tolerance=4.0, recovery_mode=True,
    ))
    manager.record_outcome("gridworld", "move", 0.9)
    manager.record_outcome("gridworld", "perceive", 0.7)
    manager.record_outcome("navigation", "scan", 0.5)
    return manager


def test_dump_policy_contract_fields():
    data = ser.dump_policy(_populated_policy())
    assert "current" in data
    cur = data["current"]
    assert cur["mission_name"] == "probe"
    assert cur["risk_tolerance"] == 0.4
    assert cur["exploration_budget"] == 0.5
    assert cur["ambition_level"] == 0.6
    assert cur["drift_tolerance"] == 4.0
    assert cur["recovery_mode"] is True
    assert data["domain_pulls"] == {"gridworld": 2, "navigation": 1}
    assert data["domain_rewards"] == {"gridworld": 1.6, "navigation": 0.5}


def test_policy_round_trip():
    data = ser.dump_policy(_populated_policy())
    target = MissionPolicyManager()
    ser.load_policy(data, target)
    assert target.current.mission_name == "probe"
    assert target.current.risk_tolerance == 0.4
    assert target.current.exploration_budget == 0.5
    assert target.current.ambition_level == 0.6
    assert target.current.drift_tolerance == 4.0
    assert target.current.recovery_mode is True
    assert target._domain_pulls == {"gridworld": 2, "navigation": 1}
    assert target._domain_rewards == {"gridworld": 1.6, "navigation": 0.5}


def test_dump_policy_legacy_risk_tolerance_path():
    class LegacyPolicy:
        def __init__(self):
            self._risk_tolerance = 0.3

    data = ser.dump_policy(LegacyPolicy())
    assert data == {"risk_tolerance": 0.3}


# ── KnowledgeGraph ──────────────────────────────────────────────────

def _populated_knowledge_graph():
    kg = KnowledgeGraph()
    n1 = kg.record("gridworld", "a_star", 0.92, tags=["pathfinding"], provenance={"cycle": 1})
    n2 = kg.record("gridworld", "greedy", 0.45, failure_reason="stuck", tags=["pathfinding"])
    kg.add_edge(n1, n2, edge_type="related", weight=0.8, metadata={"shared": True})
    return kg


def test_dump_knowledge_contract_fields():
    data = ser.dump_knowledge(_populated_knowledge_graph())
    assert set(data.keys()) == {"nodes", "archived_nodes", "cycle", "edges"}
    assert len(data["nodes"]) == 2
    assert data["archived_nodes"] == {}
    assert data["cycle"] == 0
    assert len(data["edges"]) == 1
    edge = next(iter(data["edges"].values()))
    assert edge["edge_type"] == "related"
    assert edge["weight"] == 0.8
    node = next(iter(data["nodes"].values()))
    assert node["domain"] == "gridworld"


def test_knowledge_round_trip():
    data = ser.dump_knowledge(_populated_knowledge_graph())
    target = KnowledgeGraph()
    ser.load_knowledge(data, target)
    assert len(target._nodes) == 2
    assert len(target._edges) == 1
    by_approach = {n.approach: n for n in target._nodes.values()}
    assert by_approach["a_star"].outcome == 0.92
    assert by_approach["greedy"].failure_reason == "stuck"
    assert target._edges[list(data["edges"].keys())[0]].weight == 0.8
    # adjacency restored for edge endpoints
    a_star = by_approach["a_star"].node_id
    greedy = by_approach["greedy"].node_id
    assert greedy in target._adjacency[a_star]
    assert a_star in target._adjacency[greedy]


def test_dump_knowledge_none_or_empty():
    assert ser.dump_knowledge(None) == {}
    assert ser.dump_knowledge(KnowledgeGraph()) == {"nodes": {}, "archived_nodes": {}, "cycle": 0, "edges": {}}


def test_load_knowledge_empty_is_noop():
    target = KnowledgeGraph()
    ser.load_knowledge({"nodes": {}}, target)
    assert len(target._nodes) == 0


# ── SimEngine ───────────────────────────────────────────────────────

def _populated_sim_engine():
    class FakeEngine:
        def __init__(self):
            self._last_options = [
                StrategicOption(world=None, score=0.9, rank=0,
                                metadata={"class": "exploit"}),
                StrategicOption(world=None, score=0.7, rank=1,
                                metadata={"class": "explore"}),
            ]
    return FakeEngine()


def test_dump_sim_engine_contract_fields():
    data = ser.dump_sim_engine(_populated_sim_engine())
    assert len(data) == 2
    first = data[0]
    assert first["score"] == 0.9
    assert first["rank"] == 0
    assert first["world_tag"] is None
    assert first["metadata"] == {"class": "exploit"}


def test_dump_sim_engine_none_or_empty():
    assert ser.dump_sim_engine(None) == []
    assert ser.dump_sim_engine(object()) == []

    class EmptyEngine:
        _last_options = None
    assert ser.dump_sim_engine(EmptyEngine()) == []


# ── PlanningHorizon ─────────────────────────────────────────────────

def test_dump_planning_horizon_contract():
    class FakeHorizon:
        remaining_steps = 3
        current_plan = ["perceive", "act"]
    data = ser.dump_planning_horizon(FakeHorizon())
    assert data == {"remaining_steps": 3, "current_plan": ["perceive", "act"]}


def test_dump_planning_horizon_none_or_missing_attrs():
    assert ser.dump_planning_horizon(None) == {}

    class EmptyHorizon:
        pass
    assert ser.dump_planning_horizon(EmptyHorizon()) == {}


# ── DecisionTrace ───────────────────────────────────────────────────

def _sample_trace():
    return DecisionTrace(
        cycle_id=42,
        timestamp=100.0,
        world_state_snapshot=np.zeros(2),
        domain_facts=None,
        stream_activations=[],
        selected_intent=None,
        selected_action=None,
        representation="default",
        budget_consumed_ms=1.0,
        budget_total_ms=10.0,
        worlds_simulated=1,
        cycle_duration_ms=2.0,
        council_validated=False,
        decision_integrity=0.4,
        mission_drift=3.0,
    )


def test_dump_trace_contract_fields():
    data = ser.dump_trace(_sample_trace())
    assert data == {
        "cycle_id": 42,
        "decision_integrity": 0.4,
        "mission_drift": 3.0,
        "council_validated": False,
        "selected_intent": None,
    }


def test_dump_trace_none():
    assert ser.dump_trace(None) is None


# ── Session continuity loaders ──────────────────────────────────────

def test_load_session_essence():
    assert ser.load_session_essence(None) == {}
    assert ser.load_session_essence({}) == {}
    assert ser.load_session_essence({"mood": "focused"}) == {"mood": "focused"}


def test_load_truncated_history():
    assert ser.load_truncated_history(None) == []
    assert ser.load_truncated_history([]) == []
    assert ser.load_truncated_history([{"cycle": 1}]) == [{"cycle": 1}]
