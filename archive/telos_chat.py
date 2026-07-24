"""
TELOS Chat — Talk to the reasoning engine.
You type, TELOS perceives, simulates, and replies with its reasoning.
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
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR


class ChatSimulator(DomainSimulator):
    def initialize(self): pass
    def cleanup(self): pass
    def legal_transitions(self, state): return [np.array([1,0]), np.array([0,1])]
    def transition(self, state, action): return state + action * 0.1
    def simulate(self, state, horizon): return [World(state=state.copy() + np.random.randn(2)*0.1) for _ in range(5)]
    def get_facts(self, state):
        return DomainFacts(state=state.copy(), resources={"energy": 1.0}, constraints=[], events=[], metrics={"uncertainty": 0.1})
    def terminal(self, state): return False
    def evaluate(self, state):
        return EvaluationReport(objectives={"coherence": float(np.linalg.norm(state))}, risks=0.0)


class ChatAdapter(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, mission_dir):
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        return np.zeros(2)
    @property
    def name(self): return "chat"


def main():
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=ChatAdapter(), simulator=ChatSimulator(),
        compute_budget_ms=50.0, state_dim=2, n_worlds=5, horizon=3,
    ))

    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(ChatSimulator())
    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector())

    print("TELOS Chat")
    print("Type something. TELOS will reason and reply.")
    print("Type 'quit' to exit.\n")

    state = np.array([0.0, 0.0])

    while True:
        user = input("You: ")
        if user.lower() in ("quit", "exit"):
            break

        state = np.array([hash(user) % 10 * 0.1, len(user) * 0.1])
        result = pipeline.execute(state)
        trace = result.decision_trace

        intent = trace.selected_intent.intent_type if trace.selected_intent else "unknown"
        status = "BLOCKED" if (result.firewall_blocked or result.council_blocked) else "APPROVED"

        print(f"\nTELOS:")
        print(f"  Perceived: \"{user}\" ({len(user)} chars, {state[1]:.1f} intensity)")
        print(f"  Intent: {intent}")
        print(f"  Council: [{status}] DI={trace.decision_integrity:.3f} MD={trace.mission_drift:.3f}")
        print(f"  Worlds simulated: {trace.worlds_simulated}")
        print(f"  Budget: {trace.budget_consumed_ms:.1f}/{trace.budget_total_ms:.0f}ms")

        predictions = [o.get("score", 0) for o in trace.strategic_options[:3]]
        if predictions:
            print(f"  Top futures: {[f'{s:.3f}' for s in predictions]}")
        print()


if __name__ == "__main__":
    main()
