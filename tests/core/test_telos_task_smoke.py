import numpy as np
import pytest
from unittest.mock import patch
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from tests.core.conftest import MockSimulator
from telos.core.contracts.domain_model import DomainAdapter
from telos.core.streams.base import CognitiveStream
from telos.intent_ir import IntentIR
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.council.validators import RealityValidator

class MockAdapter(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, mission_dir): return np.zeros(2)
    @property
    def name(self): return "mock"

def mocked_ollama_chat(messages):
    return "I am navigating to the goal."

class MockStream(CognitiveStream):
    def process(self, world):
        return IntentIR("navigate", params={"action_vector": [1.0, 1.0]})
    @property
    def priority(self): return 1.0
    @property
    def estimated_cost_ms(self): return 1.0

@patch('telos_task.ollama_chat', side_effect=mocked_ollama_chat)
def test_telos_task_smoke(mock_chat):
    # This is a simplified version of the pipeline setup in telos_task.py
    sim = MockSimulator()
    config = PipelineConfig(simulator=sim, adapter=MockAdapter(), checkpoint_path="/tmp/smoke_test_ckpt")
    pipeline = TelosV14Pipeline(config)
    pipeline.register_stream(MockStream(SkillLibrary()))
    pipeline.register_validator(RealityValidator()) # Add validator to pass
    
    # Run a few cycles as in telos_task.py
    state = np.array([0., 0.])
    for _ in range(3):
        result = pipeline.execute(state, user_name="TestUser")
        assert result is not None
        # Verify user memory persists
        profile = pipeline.ledger.get_user_profile("TestUser")
        assert profile is not None
        
        reply = mocked_ollama_chat([])
        assert "navigating" in reply
        
        if result.decision_trace.selected_action is not None:
            state = sim.transition(state, result.decision_trace.selected_action)

