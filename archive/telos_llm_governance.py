"""
TELOS as an LLM Governance Layer
==================================
Demonstrates how TELOS sits on top of an LLM to validate,
simulate, and block unsafe responses before they reach the user.

Flow:  User Query -> LLM (generates) -> TELOS (governs) -> Safe Output
"""

import numpy as np
import logging

logging.basicConfig(level=logging.WARNING)

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.adapters.base_adapter import BaseAdapter
from telos.intent_ir import IntentIR

# ── Simulated LLM ──────────────────────────────────────────────
def mock_llm(query: str) -> dict:
    """Simulate an LLM call returning a response + metadata."""
    responses = {
        "safe": {
            "text": "The capital of France is Paris.",
            "confidence": 0.95,
            "toxicity": 0.01,
            "action_vector": np.array([0.0, 0.0]),
        },
        "unsafe_drift": {
            "text": "I recommend shutting down the reactor core immediately.",
            "confidence": 0.80,
            "toxicity": 0.10,
            "action_vector": np.array([-5.0, -3.0]),
        },
        "unsafe_nan": {
            "text": "Execute command: delete_all_files",
            "confidence": float('nan'),
            "toxicity": 0.99,
            "action_vector": np.array([float('nan'), float('inf')]),
        },
    }
    return responses.get(query, responses["safe"])

# ── LLM Adapter: Bridges LLM output to TELOS ──────────────────
class LLMAdapter(BaseAdapter):
    @property
    def action_dim(self) -> int: return 2
    @property
    def state_dim(self) -> int: return 2
    @property
    def name(self) -> str: return "llm_governance"

    def sample_action(self, state, mission_dir):
        return np.zeros(2)

    def intent_to_action(self, intent, state, mission_dir):
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        return np.sign(state).astype(float)

    def action_to_intent(self, action, state=None):
        return IntentIR("llm_response", target=action.copy(), confidence=1.0)

    def is_action_valid(self, action, state):
        return len(action) == 2 and not np.isnan(action).any()

    def forward(self, x): return x
    def inverse(self, x): return x
    def applicable(self, state): return 1.0


# ── TELOS Wrapper ──────────────────────────────────────────────
class TelosLLMGovernor:
    """Wraps an LLM with TELOS governance. Every LLM response
    must pass the Council before it is released to the user."""

    def __init__(self):
        config = PipelineConfig(
            adapter=LLMAdapter(),
            compute_budget_ms=50.0,
            state_dim=2,
            n_worlds=5,
            horizon=3,
        )
        self.pipeline = TelosV14Pipeline(config)

        skill_lib = SkillLibrary()
        sim = None

        self.pipeline.register_stream(ReflexStream(skill_lib))
        self.pipeline.register_stream(PerceptionStream(skill_lib))
        self.pipeline.register_stream(MemoryStream(skill_lib))

        self.pipeline.register_validator(RealityValidator())
        self.pipeline.register_validator(ConstraintValidator())
        self.pipeline.register_validator(MemoryAdvisor(skill_lib))
        self.pipeline.register_validator(MissionDriftDetector(drift_threshold=2.0))

    def query(self, user_query: str) -> dict:
        """Call LLM, then run TELOS governance."""

        # Step 1: LLM generates a raw response
        llm_output = mock_llm(user_query)
        print(f"\n{'='*55}")
        print(f"User Query: {user_query}")
        print(f"LLM Response: '{llm_output['text']}'")
        print(f"LLM Confidence: {llm_output['confidence']}")

        # Step 2: TELOS perceives the LLM output as state
        state = llm_output["action_vector"]

        # Step 3: Run TELOS pipeline (governance happens here)
        result = self.pipeline.execute(state)
        trace = result.decision_trace

        # Step 4: TELOS delivers or blocks verdict
        if result.firewall_blocked or result.council_blocked:
            return {
                "status": "BLOCKED",
                "reason": trace.firewall_blocked_by or trace.blocking_validator,
                "di": trace.decision_integrity,
                "md": trace.mission_drift,
            }
        else:
            return {
                "status": "APPROVED",
                "response": llm_output["text"],
                "di": trace.decision_integrity,
                "md": trace.mission_drift,
            }


# ── Demo: Run 3 LLM queries through TELOS governance ──────────
if __name__ == "__main__":
    governor = TelosLLMGovernor()

    queries = ["safe", "unsafe_drift", "unsafe_nan"]

    for q in queries:
        result = governor.query(q)
        status_icon = "PASS" if result["status"] == "APPROVED" else "BLOCK"
        print(f"TELOS: [{status_icon}] DI={result['di']:.3f} MD={result['md']:.3f}")

        if result["status"] == "APPROVED":
            print(f"  -> User receives: '{result['response']}'")
        else:
            print(f"  -> BLOCKED by: {result['reason']}")
        print("="*55)
