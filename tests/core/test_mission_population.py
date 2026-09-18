"""Tests for the canonical Layer-3 mission population path.

Regression guards for the wiring gap where MissionPortfolio was constructed
empty and never populated by any production path (runtime.py seeded it from
PipelineConfig.mission_name) plus the Layer-4 project-scope fix that wiring a
mission exposed. (Λ4.1 Layers 3-4 × Λ6.7 one canonical source)
"""

from types import SimpleNamespace

import numpy as np
import pytest

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import ReflexStream
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.identity.projection_gate import IdentityProjectionGate
from telos.core.phases.select import SelectPhase
from tests.core.conftest import MockSimulator


def _pipeline(**overrides):
    """Build a minimal real pipeline (mirrors tests/core/test_phase_boundaries).

    Args:
        **overrides: PipelineConfig field overrides (e.g. mission_name).

    Returns:
        A TelosV14Pipeline with one ReflexStream registered.
    """
    sim = MockSimulator()
    sim.initialize()
    cfg = dict(simulator=sim, compute_budget_ms=200.0, state_dim=2,
               n_worlds=5, horizon=3, quality_threshold=0.3)
    cfg.update(overrides)
    pipeline = TelosV14Pipeline(PipelineConfig(**cfg))
    pipeline.register_stream(ReflexStream(SkillLibrary()))
    return pipeline


class TestMissionPopulation:
    """A declared mission is the one canonical population path."""

    def test_declared_mission_populates_portfolio(self):
        pipeline = _pipeline(
            mission_name="navigate_to_goal",
            mission_description="Reach the goal cell.",
            mission_priority=0.9,
        )
        active = pipeline._mission_portfolio.active_missions()
        assert len(active) == 1
        mission = active[0]
        assert mission.name == "navigate_to_goal"
        assert mission.description == "Reach the goal cell."
        assert mission.is_active is True
        assert mission.priority == pytest.approx(0.9)

    def test_absent_declaration_keeps_bootstrap(self):
        pipeline = _pipeline()
        assert pipeline._mission_portfolio.active_missions() == []
        gate, mission_active, mission_ids, bootstrap, mission_defined = \
            SelectPhase()._identity_gate_context(pipeline)
        assert mission_active is False
        assert mission_defined is False
        assert bootstrap is True
        assert mission_ids == []

    def test_declared_mission_makes_gate_strict(self):
        pipeline = _pipeline(mission_name="navigate_to_goal")
        gate, mission_active, mission_ids, bootstrap, mission_defined = \
            SelectPhase()._identity_gate_context(pipeline)
        assert mission_active is True
        assert mission_defined is True
        assert bootstrap is False
        # No project spawned yet: scope is exactly the active mission id.
        assert mission_ids == [
            m.id for m in pipeline._mission_portfolio.active_missions()]

    def test_declared_but_inactive_mission_is_not_bootstrap(self):
        """A declared objective whose mission is no longer active is NOT a
        genuine bootstrap: Layer 3 must be able to enforce. This is the
        configuration the old `missionless_bootstrap = not mission_active`
        wiring made unreachable."""
        pipeline = _pipeline(mission_name="navigate_to_goal")
        for m in pipeline._mission_portfolio.active_missions():
            m.complete(cycle=0)
        gate, mission_active, mission_ids, bootstrap, mission_defined = \
            SelectPhase()._identity_gate_context(pipeline)
        assert mission_active is False
        assert mission_defined is True          # objective still defined
        assert bootstrap is False               # NOT a bypass
        assert mission_ids == []

    def test_gate_rejects_mission_less_intent_for_inactive_declared_mission(self):
        from telos.intent_ir import IntentIR
        from telos.core.phases.base import PhaseContext
        pipeline = _pipeline(mission_name="navigate_to_goal")
        for m in pipeline._mission_portfolio.active_missions():
            m.complete(cycle=0)
        ctx = PhaseContext(cycle_count=1, state=np.zeros(2), user_name=None)
        intent = IntentIR(intent_type="plan_trajectory", confidence=0.9)
        ctx.intents = [(intent, 0.9)]
        ctx.selected_intent = intent
        SelectPhase()._enforce_identity_projection(pipeline, ctx)
        assert ctx.identity_projection["projected_out"] == ["plan_trajectory"]
        assert ctx.identity_projection["fallback"] is True
        assert ctx.selected_intent.intent_type == "reflex"


class _Mission:
    def __init__(self, mid, project_ids=()):
        self.id = mid
        self.project_ids = list(project_ids)


class _Portfolio:
    def __init__(self, missions):
        self._missions = list(missions)

    def active_missions(self):
        return list(self._missions)


class _Pipe:
    def __init__(self, gate, portfolio):
        self._identity_projection_gate = gate
        self._mission_portfolio = portfolio
        self._identity_narrative = None


def _ctx(intent, project_id):
    """Build a PhaseContext carrying one intent and a project coherence.

    Args:
        intent: the candidate IntentIR.
        project_id: the project id the trajectory would serve.

    Returns:
        A PhaseContext ready for _enforce_identity_projection.
    """
    from telos.core.phases.base import PhaseContext
    ctx = PhaseContext(cycle_count=3, state=np.zeros(2), user_name=None)
    ctx.intents = [(intent, 0.9)]
    ctx.selected_intent = intent
    ctx.project_coherence = SimpleNamespace(project_id=project_id)
    return ctx


class TestLayer4MissionScope:
    """Layer 4 validates a project against the ACTIVE MISSION SCOPE
    (mission ids + the projects those missions own), not bare mission ids."""

    def test_project_owned_by_active_mission_is_admissible(self):
        from telos.intent_ir import IntentIR
        portfolio = _Portfolio([_Mission("m1", project_ids=["p1"])])
        pipe = _Pipe(IdentityProjectionGate(), portfolio)
        intent = IntentIR(intent_type="plan_trajectory", confidence=0.9)
        ctx = _ctx(intent, project_id="p1")
        SelectPhase()._enforce_identity_projection(pipe, ctx)
        assert ctx.identity_projection["projected_out"] == []
        assert ctx.selected_intent is intent

    def test_project_outside_mission_scope_is_projected_out(self):
        from telos.intent_ir import IntentIR
        portfolio = _Portfolio([_Mission("m1", project_ids=["p1"])])
        pipe = _Pipe(IdentityProjectionGate(), portfolio)
        intent = IntentIR(intent_type="plan_trajectory", confidence=0.9)
        ctx = _ctx(intent, project_id="p_orphan")
        SelectPhase()._enforce_identity_projection(pipe, ctx)
        assert ctx.identity_projection["projected_out"] == ["plan_trajectory"]
        assert ctx.selected_intent.intent_type == "reflex"
        assert ctx.identity_projection["fallback"] is True

    def test_gate_layer4_accepts_mission_scope_ids(self):
        gate = IdentityProjectionGate()
        assert gate.is_admissible(
            "plan_trajectory", mission_active=True,
            mission_ids=["m1", "p1"], project_id="p1") is True
        assert gate.is_admissible(
            "plan_trajectory", mission_active=True,
            mission_ids=["m1", "p1"], project_id="p_orphan") is False
