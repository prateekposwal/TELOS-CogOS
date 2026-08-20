"""
Tests for PipelineCoordinator — multi-agent Supervisor pattern.
"""

import numpy as np

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.coordination.coordinator import (
    PipelineCoordinator, SubPipelineConfig, _build_subpipeline,
)
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR


class QuickSim(DomainSimulator):
    def initialize(self): pass
    def cleanup(self): pass
    def legal_transitions(self, s):
        return [np.array([1, 0]), np.array([0, 1])]
    def transition(self, s, a): return s + a
    def simulate(self, s, h):
        return [World(state=s.copy() + np.random.randn(2) * 0.1) for _ in range(3)]
    def get_facts(self, s):
        return DomainFacts(state=s.copy(), resources={}, constraints=[],
                          events=[], metrics={})
    def terminal(self, s): return False
    def evaluate(self, s):
        return EvaluationReport(objectives={}, risks=0.0)

    name = "quick"
    state_dim = 2


class QuickAdpt(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, md):
        av = intent.params.get('action_vector')
        if av is not None:
            if isinstance(av, np.ndarray) and av.size > 0:
                return np.asarray(av)
            elif av:
                return np.asarray(av)
        return np.sign(np.array([4, 4]) - state).astype(float)
    @property
    def name(self): return "quick"
    @property
    def state_dim(self): return 2


def test_build_subpipeline():
    config = SubPipelineConfig(name="test", budget_ms=20.0)
    p = _build_subpipeline(config, simulator=QuickSim(), adapter=QuickAdpt())
    assert p is not None
    assert len(p.streams) == 4
    assert p.config.compute_budget_ms == 20.0


def test_build_subpipeline_selective_streams():
    config = SubPipelineConfig(name="test", budget_ms=20.0,
                               streams=["reflex", "perception"])
    p = _build_subpipeline(config)
    assert len(p.streams) == 2


def test_coordinator_spawn():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    config = SubPipelineConfig(name="analyst", budget_ms=20.0)
    p = coord.spawn(config)
    assert p is not None
    assert "analyst" in coord._sub_pipelines
    assert coord.stats["sub_pipelines"] == 1


def test_coordinator_orchestrate_fan_out():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    state = np.array([0.0, 0.0])

    result = coord.orchestrate(
        state=state,
        subtasks=[
            SubPipelineConfig(name="scout", budget_ms=15.0,
                              streams=["reflex", "perception"]),
            SubPipelineConfig(name="planner", budget_ms=25.0,
                              streams=["memory", "planning"]),
        ],
    )

    assert result.success is not None
    assert len(result.sub_results) == 2
    assert result.sub_results[0].name == "scout"
    assert result.sub_results[1].name == "planner"
    assert result.aggregate_di >= 0.0
    assert 0.0 <= result.aggregate_md <= 1.0


def test_coordinator_chain():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    state = np.array([0.0, 0.0])

    result = coord.chain(
        state=state,
        subtasks=[
            SubPipelineConfig(name="step1", budget_ms=15.0),
            SubPipelineConfig(name="step2", budget_ms=15.0),
        ],
    )

    assert len(result.sub_results) == 2
    assert result.sub_results[0].name == "step1"
    assert result.sub_results[1].name == "step2"


def test_coordinator_callback():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    called = []
    coord.on_subresult(lambda r: called.append(r.name))

    result = coord.orchestrate(
        state=np.array([0.0, 0.0]),
        subtasks=[SubPipelineConfig(name="cb_test", budget_ms=15.0)],
    )

    assert len(called) == 1
    assert called[0] == "cb_test"


def test_coordinator_with_supervisor_pipeline():
    sim = QuickSim()
    config = PipelineConfig(simulator=sim, adapter=QuickAdpt(),
                            compute_budget_ms=50.0, state_dim=2)
    supervisor = TelosV14Pipeline(config)
    sl = SkillLibrary()
    se = CounterfactualEngine(sim)
    for s in [ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
              PlanningStream(sl, sim_engine=se)]:
        supervisor.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(),
              MemoryAdvisor(sl), MissionDriftDetector(drift_threshold=5.0)]:
        supervisor.register_validator(v)

    coord = PipelineCoordinator(
        supervisor=supervisor,
        default_simulator=sim,
        default_adapter=QuickAdpt(),
    )

    result = coord.orchestrate(
        state=np.array([0.0, 0.0]),
        subtasks=[SubPipelineConfig(name="sub", budget_ms=15.0)],
    )

    # Supervisor should have produced a verdict
    assert result.coordinator_verdict is not None


def test_coordinator_empty_subtasks():
    coord = PipelineCoordinator()
    result = coord.orchestrate(state=np.array([0.0, 0.0]), subtasks=[])
    assert len(result.sub_results) == 0
