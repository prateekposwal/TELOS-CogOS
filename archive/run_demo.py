"""
TELOS v14: End-to-end GridWorld Demo.

Run:  python3 run_demo.py

Shows TELOS perceiving, simulating, selecting, and acting
across multiple decision cycles in a GridWorld domain.
"""

import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

from telos.examples.gridworld.simulator import GridWorldSimulator
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


GOAL = np.array([4, 4])

class GridWorldAdapter(BaseAdapter):
    @property
    def action_dim(self) -> int: return 2
    @property
    def state_dim(self) -> int: return 2
    @property
    def name(self) -> str: return "gridworld"

    def sample_action(self, state, mission_dir):
        diff = GOAL - state
        return np.sign(diff + 0.5 * np.random.randn(2)).astype(float)

    def intent_to_action(self, intent, state, mission_dir):
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        return np.sign(GOAL - state).astype(float)

    def action_to_intent(self, action, state=None):
        return IntentIR("move", target=action.copy(), confidence=1.0, params={"vector": action.copy()})

    def is_action_valid(self, action, state):
        return len(action) == 2 and not np.isnan(action).any()

    def forward(self, x): return x
    def inverse(self, x): return x
    def applicable(self, state): return 1.0


def visualize_decision(trace):
    cv = next((s for s in trace.council_signals if s["validator"] == "ConstraintValidator"), None)
    cv_status = "PASSED" if cv and cv["passed"] else "BLOCKED"
    
    best_opt = trace.strategic_options[0] if trace.strategic_options else None
    action = trace.selected_intent.intent_type if trace.selected_intent else "NONE"
    
    print(f"\nCycle {trace.cycle_id}:")
    print("World Generation")
    print(f"↓ (Simulated {trace.worlds_simulated} worlds)")
    print("\nConstraint Filtering")
    print(f"↓ ({cv_status})")
    print("\nIdentity Evaluation")
    print(f"↓ (DI={trace.decision_integrity:.2f})")
    print("\nMaintenance Cost")
    print(f"↓ ({trace.budget_consumed_ms:.1f}ms)")
    print("\nCounterfactual Ranking")
    print(f"↓ (Best score={best_opt['score']:.2f})" if best_opt else "↓ (N/A)")
    print("\nChosen Action")
    print(f"→ {action}\n")
    print("-" * 30)


def main():
    sim = GridWorldSimulator(size=5)
    sim.initialize()
    config = PipelineConfig(
        adapter=GridWorldAdapter(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=5, horizon=3,
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

    state = sim.initial_state()
    goal = np.array([4, 4])

    print("TELOS GridWorld Demo")
    print("I am TELOS.")
    print(f"{'='*55}")
    print(f"Start: {state}  Goal: {goal}")
    print()

    for cycle in range(1, 21):
        result = pipeline.execute(state)
        trace = result.decision_trace
        
        visualize_decision(trace)

        if trace.selected_action is not None and not trace.firewall_blocked:
            state = sim.transition(state, trace.selected_action)

        dist = np.linalg.norm(state - goal)
        if dist < 1.0:
            print(f"Goal reached in {cycle} cycles!")
            break

    sim.cleanup()
    print()


if __name__ == "__main__":
    main()
