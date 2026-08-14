import numpy as np
from typing import List, Any
from telos.core.contracts.domain_model import DomainSimulator, DomainFacts, EvaluationReport
from telos.world.world import World

class SyntheticWorld(DomainSimulator):
    """
    A neutral domain with tunable noise and mission dynamics.
    It does not know about representations or missions.
    """
    def __init__(self, noise_std=0.0, seed=None):
        self.noise_std = noise_std
        # Pattern: one RNG authority per engine — private RandomState,
        # never global np.random in the simulation hot path.
        self._rng = np.random.RandomState(seed)

    def initialize(self) -> None: pass
    def cleanup(self) -> None: pass

    def initial_state(self) -> np.ndarray:
        return np.array([0.0, 0.0])

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        return [np.array([0.1, 0.0]), np.array([-0.1, 0.0]), 
                np.array([0.0, 0.1]), np.array([0.0, -0.1])]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        noise = self._rng.normal(0, self.noise_std, 2)
        return state + action + noise

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        futures = []
        curr = state
        for _ in range(horizon):
            curr = self.transition(curr, np.array([0.1, 0.0]))
            futures.append(World(state=curr))
        return futures

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        dist = np.linalg.norm(state)
        return DomainFacts(
            state=state,
            resources={},
            constraints=[],
            events=[],
            metrics={"distance_from_origin": dist}
        )

    def terminal(self, state: np.ndarray) -> bool:
        return bool(np.linalg.norm(state) > 5.0)

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        dist = np.linalg.norm(state)
        return EvaluationReport(
            objectives={"exploration": float(dist)},
            risks=float(max(0.0, dist - 5.0)),
        )
