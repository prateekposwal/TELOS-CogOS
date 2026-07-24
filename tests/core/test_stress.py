import numpy as np
import pytest
from tests.core.conftest import MockSimulator
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.contracts.domain_model import DomainAdapter

class MockAdapter(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, mission_dir): return np.zeros(2)
    @property
    def name(self): return "mock"

from telos.core.streams.implementations import ReflexStream
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.council.validators import RealityValidator

def test_stress_soak_100_cycles():
    sim = MockSimulator()
    config = PipelineConfig(simulator=sim, adapter=MockAdapter(), checkpoint_path="/tmp/stress_test_ckpt")
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_validator(RealityValidator())
    
    state = np.array([0., 0.])
    for i in range(105):
        result = pipeline.execute(state)
        # Only transition if action is not None (pipeline not blocked)
        if result.decision_trace.selected_action is not None:
            state = sim.transition(state, result.decision_trace.selected_action)
        
        assert result.decision_trace is not None
        # Verify no permanent drift block
        assert result.decision_trace.mission_drift < 1000.0 # Arbitrary high threshold

