import logging
import numpy as np

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter
from telos.core.contracts.domain_model import EvaluationReport
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.world.facts import DomainFacts
from telos.world.world import World


class DemoSimulator(DomainSimulator):
    def initialize(self): pass
    def cleanup(self): pass
    def legal_transitions(self, state):
        return [np.array([1, 0]), np.array([-1, 0]), np.array([0, 1]), np.array([0, -1])]
    def transition(self, state, action):
        return state + action
    def simulate(self, state, horizon):
        return [World(state=state.copy() + np.random.randn(2) * 0.1) for _ in range(5)]
    def get_facts(self, state):
        return DomainFacts(
            state=state.copy(),
            resources={"energy": float(np.linalg.norm(state))},
            constraints=[],
            events=[],
            metrics={"distance": float(np.linalg.norm(state)), "uncertainty": 0.1},
        )
    def terminal(self, state):
        return bool(np.linalg.norm(np.array([4., 4.]) - state) < 1.0)
    def evaluate(self, state):
        return EvaluationReport(
            objectives={"distance": -float(np.linalg.norm(np.array([4., 4.]) - state))},
            risks=0.0,
        )
    name = "gridworld_demo"
    state_dim = 2

    def world_spec(self):
        from telos.core.contracts.domain_model import WorldSpec
        return WorldSpec(
            name=self.name,
            state_dim=self.state_dim,
            action_dim=2,
            objectives=["distance"],
            constraints=[],
            observability="high",
            capabilities=["transition", "simulate"],
        )


class DemoAdapter(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, mission_dir):
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        return np.sign(np.array([4., 4.]) - state).astype(float)
    @property
    def name(self): return "demo"
    @property
    def state_dim(self): return 2


def main():
    logging.basicConfig(level=logging.WARNING, format='%(name)s - %(levelname)s - %(message)s')

    sim = DemoSimulator()
    config = PipelineConfig(
        adapter=DemoAdapter(), simulator=sim,
        compute_budget_ms=50.0, state_dim=2, n_worlds=5, horizon=3,
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
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))

    state = np.array([0., 0.])
    goal = np.array([4., 4.])

    print("TELOS Runtime — GridWorld Demo")
    print("=" * 40)

    for cycle in range(1, 6):
        result = pipeline.execute(state)
        trace = result.decision_trace

        action_desc = trace.selected_intent.intent_type if trace.selected_intent else "none"
        status = "BLOCKED" if (result.firewall_blocked or result.council_blocked) else "APPROVED"

        print(f"Cycle {cycle}: {action_desc} [{status}] DI={trace.decision_integrity:.3f} MD={trace.mission_drift:.3f}")

        if trace.selected_action is not None and not result.firewall_blocked:
            state = sim.transition(state, trace.selected_action)

        dist = np.linalg.norm(state - goal)
        if dist < 1.0:
            print(f"Goal reached in {cycle} cycles!")
            break

    print("=" * 40)
    print("Demo complete.")
    pipeline.shutdown()
    return 0


if __name__ == "__main__":
    main()
