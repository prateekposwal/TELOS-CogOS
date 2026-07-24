import numpy as np
import pytest
from tests.core.conftest import MockSimulator
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.core.council.base import CouncilVerdict, ValidationSignal
from telos.core.council.base import Validator

class BlockingValidator(Validator):
    @property
    def name(self) -> str: return "BlockingValidator"

    def validate(self, world, intent, facts, **kwargs) -> ValidationSignal:
        return ValidationSignal(
            validator_name=self.name,
            passed=False,
            confidence=1.0,
            reason="Blocked for test",
            evidence_weight=1.0
        )

# MockSimulator removed as it is now imported from conftest.py

class MockAdapter(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, mission_dir): return np.zeros(2)
    @property
    def name(self): return "mock"

def test_council_blocks_action():
    sim = MockSimulator()
    config = PipelineConfig(simulator=sim, adapter=MockAdapter())
    pipeline = TelosV14Pipeline(config)
    pipeline.register_validator(BlockingValidator())
    
    # Execute a cycle
    result = pipeline.execute(np.array([0., 0.]))
    
    # Assert blocking
    assert result.council_blocked is True
    assert result.selected_trajectory is None
    assert result.decision_trace.council_validated is False
    assert result.decision_trace.blocking_validator == "BlockingValidator"
