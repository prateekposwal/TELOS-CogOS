import numpy as np
import pytest
from tests.core.conftest import MockSimulator
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.council.base import Validator, ValidationSignal
from telos.core.contracts.domain_model import DomainAdapter

class CrashingValidator(Validator):
    @property
    def name(self) -> str: return "CrashingValidator"
    def validate(self, world, intent, facts, **kwargs) -> ValidationSignal:
        raise ValueError("Validator crashed!")

class MockAdapter(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, mission_dir): return np.zeros(2)
    @property
    def name(self): return "mock"

def test_validator_exception_handling():
    sim = MockSimulator()
    config = PipelineConfig(simulator=sim, adapter=MockAdapter())
    pipeline = TelosV14Pipeline(config)
    pipeline.register_validator(CrashingValidator())
    
    # Pipeline should handle exception and report failure without crashing the whole process
    result = pipeline.execute(np.array([0., 0.]))
    
    assert result.council_blocked is True
    # Verify that the failure was logged or handled in signals
    signals = result.decision_trace.council_signals
    crashing_signal = next((s for s in signals if s["validator"] == "CrashingValidator"), None)
    assert crashing_signal is not None
    assert "validator error" in crashing_signal["reason"]

