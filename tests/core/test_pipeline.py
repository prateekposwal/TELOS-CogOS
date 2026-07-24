"""
Pipeline execution tests: imports, BudgetManager, RepresentationPlanner,
full pipeline execution, and multi-cycle runs.
"""

import numpy as np
import os

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.attention import BudgetManager
from telos.core.simulation import CounterfactualEngine
from telos.core.planner import RepresentationPlanner
from telos.core.streams.implementations import ReflexStream, PerceptionStream, MemoryStream, PlanningStream
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.experience_manager import ExperienceManager
from telos.audit.monitor import TransparencyMonitor
from telos.world.facts import DomainFacts
from tests.core.conftest import MockSimulator


def test_imports():
    assert BudgetManager is not None
    assert TelosV14Pipeline is not None
    assert ReflexStream is not None
    assert PerceptionStream is not None
    assert MemoryStream is not None
    assert PlanningStream is not None
    assert RepresentationPlanner is not None
    assert ExperienceManager is not None
    assert TransparencyMonitor is not None


def test_budget_manager():
    bm = BudgetManager(total_budget_ms=50.0)
    assert bm.consumed_ms == 0.0
    assert bm.check_budget("test", 10.0) is True
    bm.consume("test", 10.0)
    assert bm.consumed_ms == 10.0
    assert bm.check_budget("test", 45.0) is False
    bm.reset()
    assert bm.consumed_ms == 0.0


def test_planner():
    bm = BudgetManager(total_budget_ms=50.0)
    planner = RepresentationPlanner(bm)

    facts_close = DomainFacts(
        state=np.array([0.1, 0.2]),
        resources={}, constraints=[], events=[],
        metrics={"distance_from_origin": 0.22},
    )
    rep1 = planner.select_representation(facts_close)

    facts_far = DomainFacts(
        state=np.array([4.0, 3.0]),
        resources={}, constraints=[], events=[],
        metrics={"distance_from_origin": 5.0},
    )
    rep2 = planner.select_representation(facts_far)

    assert rep1 in ("cartesian", "polar")
    assert rep2 in ("cartesian", "polar")
    assert len(planner.selection_history) == 2


def test_full_pipeline():
    sim = MockSimulator()
    sim.initialize()

    config = PipelineConfig(
        simulator=sim, compute_budget_ms=100.0, state_dim=6, n_worlds=10, horizon=5,
    )
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    result = pipeline.execute(state)

    assert result.pipeline_phase.value == "complete"
    assert result.decision_trace is not None
    assert len(result.decision_trace.stream_activations) == 4
    assert result.decision_trace.budget_consumed_ms > 0
    assert not result.council_blocked
    assert result.decision_integrity > 0.5
    assert result.decision_trace.council_validated is True

    sim.cleanup()


def test_multi_cycle():
    sim = MockSimulator()
    sim.initialize()

    config = PipelineConfig(
        simulator=sim, compute_budget_ms=100.0, state_dim=6, n_worlds=10, horizon=5,
    )
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)
    experience = ExperienceManager(skill_lib)
    monitor = TransparencyMonitor()

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    state = np.array([2.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    for cycle in range(5):
        result = pipeline.execute(state)
        experience.observe(result)
        if result.decision_trace:
            monitor.record(result.decision_trace)
        state = state + np.random.randn(6) * 0.1

    report = monitor.generate_report()
    assert os.path.exists('telos/audit/runtime/decision_log.json')

    sim.cleanup()
