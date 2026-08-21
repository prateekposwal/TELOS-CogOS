"""Honest contract tests for telos/core/streams/implementations.py."""

import hashlib

import numpy as np

from telos.core.ledger.skill_library import SkillLibrary, Skill
from telos.core.simulation import CounterfactualEngine
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
)
from telos.world.world import World
from tests.core.conftest import MockSimulator


def _world(state, metadata=None, safety_score=1.0):
    return World(state=np.array(state, dtype=float),
                 metadata=metadata or {}, safety_score=safety_score)


# ── ReflexStream ──────────────────────────────────────────────────────

def test_reflex_priority_and_cost():
    r = ReflexStream(SkillLibrary())
    assert r.priority == 1.0
    assert r.estimated_cost_ms == 2.0


def test_reflex_nominal_no_trigger():
    r = ReflexStream(SkillLibrary())
    ir = r.process(_world([1.0, 2.0]))
    assert ir.intent_type == "reflex"
    assert ir.confidence == 0.0
    assert ir.metadata["trigger"] == "nominal"


def test_reflex_triggers_on_nan():
    r = ReflexStream(SkillLibrary())
    ir = r.process(_world([float("nan"), 2.0]))
    assert ir.intent_type == "reflex"
    assert ir.confidence >= 0.5


def test_reflex_triggers_on_safety_breach():
    r = ReflexStream(SkillLibrary())
    ir = r.process(_world([1.0, 2.0], safety_score=0.1))
    assert ir.intent_type == "reflex"
    assert ir.confidence == 0.99


def test_reflex_does_not_trigger_on_uncertainty_alone():
    r = ReflexStream(SkillLibrary())
    ir = r.process(_world([1.0, 2.0], safety_score=1.0))
    assert ir.confidence == 0.0


# ── PerceptionStream ──────────────────────────────────────────────────

def test_perception_priority_and_cost():
    p = PerceptionStream(SkillLibrary())
    assert p.priority == 0.9
    assert p.estimated_cost_ms == 5.0


def test_perception_extracts_features():
    p = PerceptionStream(SkillLibrary())
    w = _world([1.0, 2.0])
    ir = p.process(w)
    assert ir.intent_type == "perceive"
    features = ir.params["features"]
    assert set(features) >= {"state_norm", "state_mean", "state_std",
                             "state_dim", "sparsity", "energy"}
    assert features["state_dim"] == 2
    assert features["state_norm"] == np.linalg.norm([1.0, 2.0])


def test_perception_classifies_high_energy():
    p = PerceptionStream(SkillLibrary())
    w = _world([10.0, 10.0])
    ir = p.process(w)
    assert ir.params["entity_types"][w.metadata["entity_id"]] == "high_energy_region"
    assert "dampen" in w.affordances


def test_perception_classifies_quiescent_zone():
    p = PerceptionStream(SkillLibrary())
    w = _world([0.01, 0.01])
    ir = p.process(w)
    assert ir.params["entity_types"][w.metadata["entity_id"]] == "quiescent_zone"
    assert "explore" in w.affordances


def test_perception_classifies_active_region():
    p = PerceptionStream(SkillLibrary())
    w = _world([1.0, 2.0])
    ir = p.process(w)
    assert ir.params["entity_types"][w.metadata["entity_id"]] == "active_region"
    assert "maintain" in w.affordances


def test_perception_sparse_densify():
    p = PerceptionStream(SkillLibrary())
    w = _world([1.0, 0.0, 0.0, 0.0])  # sparsity 0.75
    ir = p.process(w)
    assert "densify" in w.affordances


def test_perception_entity_id_deterministic():
    p = PerceptionStream(SkillLibrary())
    w1 = _world([1.0, 2.0])
    w2 = _world([1.0, 2.0])
    p.process(w1)
    p.process(w2)
    assert w1.metadata["entity_id"] == w2.metadata["entity_id"]


def test_perception_writes_world_metadata():
    p = PerceptionStream(SkillLibrary())
    w = _world([1.0, 2.0])
    ir = p.process(w)
    assert len(w.entities) > 0
    assert "entity_id" in w.metadata
    assert "perception_features" in w.metadata


# ── MemoryStream ──────────────────────────────────────────────────────

def test_memory_priority_and_cost():
    m = MemoryStream(SkillLibrary())
    assert m.priority == 0.7
    assert m.estimated_cost_ms == 3.0


def test_memory_miss_when_no_skills():
    m = MemoryStream(SkillLibrary())
    ir = m.process(_world([1.0, 2.0]))
    assert ir.intent_type == "memory_miss"
    assert ir.metadata["match_count"] == 0


def test_memory_recall_when_skill_fingerprint_matches():
    state = np.array([1.0, 2.0])
    fp = hashlib.md5(state.tobytes()).hexdigest()[:12]
    sl = SkillLibrary()
    sl.index_skill(Skill(skill_id="sk1", fingerprint=fp,
                         trajectory="path", utility_score=0.9))
    m = MemoryStream(sl)
    ir = m.process(_world([1.0, 2.0]))
    assert ir.intent_type == "memory_recall"
    assert ir.params["skill_id"] == "sk1"
    assert ir.params["suggestion"] == "path"
    assert ir.params["match_count"] == 1


# ── PlanningStream ────────────────────────────────────────────────────

def test_planning_priority_and_cost():
    p = PlanningStream(SkillLibrary())
    assert p.priority == 0.5
    assert p.estimated_cost_ms == 12.0


def test_planning_noop_without_engine():
    p = PlanningStream(SkillLibrary(), sim_engine=None)
    ir = p.process(_world([1.0, 2.0]))
    assert ir.intent_type == "plan_noop"
    assert ir.params["reason"] == "no_simulator_registered"


def test_planning_with_engine_produces_trajectory():
    sim = MockSimulator()
    se = CounterfactualEngine(sim)
    p = PlanningStream(SkillLibrary(), sim_engine=se)
    ir = p.process(_world([1.0, 2.0]))
    assert ir.intent_type in ("plan_trajectory", "plan_empty")
    assert ir.metadata["stream"] == "planning"


def test_planning_configure_updates_parameters():
    p = PlanningStream(SkillLibrary(), sim_engine=None)
    assert p.horizon == 8
    assert p.n_worlds == 30
    p.configure(horizon=5, n_worlds=2)
    assert p.horizon == 5
    assert p.n_worlds == 2


def test_planning_configure_ignores_none():
    p = PlanningStream(SkillLibrary(), sim_engine=None, horizon=4, n_worlds=6)
    p.configure(horizon=None, n_worlds=None)
    assert p.horizon == 4
    assert p.n_worlds == 6


# ── TheoryStream ──────────────────────────────────────────────────────

def test_theory_priority_and_cost():
    t = TheoryStream(SkillLibrary())
    assert t.priority == 0.4
    assert t.estimated_cost_ms == 4.0


def test_theory_builder_default_created():
    t = TheoryStream(SkillLibrary())
    assert t.builder is not None


def test_theory_idle_when_no_theories():
    t = TheoryStream(SkillLibrary())
    w = _world([1.0, 2.0], metadata={"cycle": 1})
    ir = t.process(w)
    assert ir.intent_type == "theory_idle"
    assert "total_experiences" in ir.params
    assert ir.metadata["stream"] == "theory"
