"""Environment validation tests for TELOS CogOS."""

import sys
import importlib
import numpy as np


def test_python_version():
    assert sys.version_info >= (3, 8), "Python 3.8+ required"


def test_numpy_import():
    import numpy as np
    assert np is not None


def test_core_packages_importable():
    packages = [
        "telos.core.runtime",
        "telos.core.attention",
        "telos.core.simulation",
        "telos.core.planner",
        "telos.core.streams.base",
        "telos.core.streams.implementations",
        "telos.core.council.base",
        "telos.core.council.validators",
        "telos.core.governance.trust_manager",
        "telos.core.governance.timing",
        "telos.core.governance.firewall",
        "telos.core.infra_manager.infrastructure_manager",
        "telos.core.infra_manager.stream_calibrator",
        "telos.core.infra_manager.failure_ledger",
        "telos.core.infra_manager.mission_policy",
        "telos.core.infra_manager.audit_controller",
        "telos.core.ledger.world_ledger",
        "telos.core.ledger.skill_library",
        "telos.core.ledger.experience_manager",
        "telos.core.contracts.domain_model",
        "telos.world.world",
        "telos.world.facts",
        "telos.intent_ir",
        "telos.audit.monitor",
    ]
    for pkg in packages:
        mod = importlib.import_module(pkg)
        assert mod is not None, f"Failed to import {pkg}"


def test_pipeline_can_instantiate():
    from telos.core.runtime import PipelineConfig, TelosV14Pipeline
    config = PipelineConfig(compute_budget_ms=50.0, state_dim=2)
    pipeline = TelosV14Pipeline(config)
    assert pipeline is not None
    assert pipeline.budget_manager is not None


def test_all_streams_importable():
    from telos.core.streams.implementations import (
        ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
    )
    assert ReflexStream is not None
    assert PerceptionStream is not None
    assert MemoryStream is not None
    assert PlanningStream is not None


def test_all_validators_importable():
    from telos.core.council.validators import (
        RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
    )
    assert RealityValidator is not None
    assert ConstraintValidator is not None
    assert MemoryAdvisor is not None
    assert MissionDriftDetector is not None


def test_world_dataclass():
    from telos.world.world import World
    w = World(state=np.array([0.0, 0.0]))
    assert w.is_valid()
    assert w.state.shape == (2,)


def test_intent_ir():
    from telos.intent_ir import IntentIR
    intent = IntentIR("test", target=np.array([1.0]), confidence=0.9)
    assert intent.intent_type == "test"
    assert intent.confidence == 0.9


def test_full_single_pipeline_cycle():
    from telos.core.runtime import PipelineConfig, TelosV14Pipeline
    from telos.core.streams.implementations import (
        ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
    )
    from telos.core.council.validators import (
        RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
    )
    from telos.core.ledger.skill_library import SkillLibrary
    from telos.core.simulation import CounterfactualEngine
    from telos.core.contracts.domain_model import DomainSimulator, EvaluationReport
    from telos.world.facts import DomainFacts
    from telos.world.world import World
    from telos.adapters.base_adapter import BaseAdapter

    class TSim(DomainSimulator):
        def initialize(self): pass
        def cleanup(self): pass
        def legal_transitions(self, state): return [np.array([1,0])]
        def transition(self, state, action): return state + action
        def simulate(self, state, horizon): return [World(state=state.copy()) for _ in range(3)]
        def get_facts(self, state): return DomainFacts(state=state.copy(), resources={}, constraints=[], events=[], metrics={})
        def terminal(self, state): return False
        def evaluate(self, state): return EvaluationReport(objectives={"test": 1.0}, risks=0.0)

    class TAdpt(BaseAdapter):
        @property
        def action_dim(self): return 2
        @property
        def state_dim(self): return 2
        @property
        def name(self): return "test"
        def sample_action(self, state, md): return np.zeros(2)
        def intent_to_action(self, intent, state, md):
            if "action_vector" in intent.params:
                return np.asarray(intent.params["action_vector"], dtype=float)
            return np.zeros(2)
        def action_to_intent(self, action, state=None):
            from telos.intent_ir import IntentIR
            return IntentIR("test", target=action.copy(), confidence=1.0)
        def is_action_valid(self, action, state): return True
        def forward(self, x): return x
        def inverse(self, x): return x
        def applicable(self, state): return 1.0

    sim = TSim()
    config = PipelineConfig(
        adapter=TAdpt(), simulator=sim,
        compute_budget_ms=50.0, state_dim=2, n_worlds=3, horizon=2,
    )
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector())

    state = np.array([0.0, 0.0])
    result = pipeline.execute(state)
    assert result is not None
    assert result.decision_trace is not None
    assert result.decision_integrity > 0
