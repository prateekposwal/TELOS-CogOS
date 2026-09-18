"""
Shared test infrastructure for TELOS core tests.

The MockSimulator provides a minimal domain simulation environment
for testing the Pipeline, Council, Governance, and Infrastructure
Manager without real domain plugins.
"""

import sys
import os
import numpy as np
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.core.contracts.domain_model import DomainSimulator


class MockSimulator(DomainSimulator):
    """Minimal simulator for testing the core runtime.

    Owns a private RNG (like every production simulator): reading the global
    `np.random` stream made simulate()/legal_transitions() non-deterministic and
    order-dependent, which flaked tests that assume simulate() always yields
    worlds (the global state depended on whatever ran first in the suite).
    """

    name = "mock"
    state_dim = 2
    action_dim = 2

    def __init__(self, seed: int = 1234):
        """Construct a mock simulator with an isolated RNG.

        Args:
            seed: seed for the private RandomState (deterministic by default).
        """
        self._rng = np.random.RandomState(seed)

    def world_spec(self):
        from telos.core.contracts.domain_model import WorldSpec
        return WorldSpec(
            name=self.name,
            state_dim=self.state_dim,
            action_dim=self.action_dim,
            objectives=["utility"],
            constraints=["bounds"],
            observability="high",
            capabilities=["transition", "simulate"],
        )

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        return [state + self._rng.randn(*state.shape) * 0.1 for _ in range(5)]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        return state + action * 0.1

    def simulate(self, state: np.ndarray, horizon: int) -> list:
        worlds = []
        s = state.copy()
        for _ in range(min(horizon, 5)):
            s = s + self._rng.randn(*s.shape) * 0.05
            worlds.append(World(state=s.copy(), metadata={"simulated": True}))
        return worlds

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        return DomainFacts(
            state=state,
            resources={"energy": float(np.linalg.norm(state))},
            constraints=["bounds"] if np.any(np.abs(state) > 5) else [],
            events=["convergence"] if np.linalg.norm(state) < 0.5 else [],
            metrics={
                "distance_from_origin": float(np.linalg.norm(state)),
                "uncertainty": float(min(np.std(state), 1.0)),
            },
        )

    def terminal(self, state: np.ndarray) -> bool:
        return bool(np.linalg.norm(state) < 0.01)

    def evaluate(self, state):
        from telos.core.contracts.domain_model import EvaluationReport
        return EvaluationReport(
            objectives={"utility": float(1.0 / (1.0 + np.linalg.norm(state)))},
            risks=float(max(0.0, np.linalg.norm(state) - 3.0)),
        )
