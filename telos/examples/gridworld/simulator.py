import numpy as np
from typing import List, Any
from telos.core.contracts.domain_model import DomainSimulator, DomainFacts, EvaluationReport
from telos.world.world import World

class GridWorldSimulator(DomainSimulator):
    """A fully compliant GridWorld implementation for architecture validation."""

    def __init__(self, size=10, seed=None):
        self.size = size
        # Pattern: one RNG authority per engine — private RandomState, never
        # global np.random in the simulation hot path. A global stream shared
        # across tests/simulators makes trajectories order-dependent (the
        # discrimination-collapse flake: all 5 options scored identically).
        self._rng = np.random.RandomState(seed)

    def initialize(self) -> None: pass
    def cleanup(self) -> None: pass

    def initial_state(self) -> np.ndarray:
        return np.array([0.0, 0.0])

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        return [
            np.array([0, 1]), np.array([0, -1]),
            np.array([1, 0]), np.array([-1, 0])
        ]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        new_state = state + action
        return np.clip(new_state, 0, self.size - 1)

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        futures = []
        curr = state
        actions = self.legal_transitions(state)
        if not actions:
            return futures
        for _ in range(horizon):
            action = actions[self._rng.randint(len(actions))]
            curr = self.transition(curr, action)
            futures.append(World(state=curr))
        return futures

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        dist = np.linalg.norm(state - np.array([self.size-1, self.size-1]))
        return DomainFacts(
            state=state,
            resources={"steps": 1.0},
            constraints=["boundary"],
            events=[],
            metrics={"distance_to_goal": dist}
        )

    def terminal(self, state: np.ndarray) -> bool:
        return bool(np.linalg.norm(state - np.array([self.size-1, self.size-1])) < 1.0)

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        dist = np.linalg.norm(state - np.array([self.size-1, self.size-1]))
        return EvaluationReport(
            objectives={"goal_progress": float(1.0 / (1.0 + dist))},
            risks=float(dist / self.size),
        )
