from abc import ABC, abstractmethod
from typing import List, Any, Optional, Dict
import numpy as np
from dataclasses import dataclass, field
from telos.world.world import World
from telos.world.facts import DomainFacts

# --- 1. The Physics (Simulator) ---
class DomainSimulator(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Lifecycle hook: Prepare domain resources."""

    @abstractmethod
    def cleanup(self) -> None:
        """Lifecycle hook: Release domain resources."""

    @abstractmethod
    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        """RuleGate: Define allowable actions."""

    @abstractmethod
    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        """The 'physics' of the domain."""

    @abstractmethod
    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        """Project future trajectories."""

    @abstractmethod
    def get_facts(self, state: np.ndarray) -> DomainFacts:
        """Returns objective domain facts for reasoning."""

    @abstractmethod
    def terminal(self, state: np.ndarray) -> bool:
        """Boundary condition definition."""

    @abstractmethod
    def evaluate(self, state: np.ndarray) -> "EvaluationReport":
        """Score a state for trajectory ranking (CounterfactualEngine)."""

@dataclass
class EvaluationReport:
    """Result of simulator.evaluate() — used by CounterfactualEngine to rank paths."""
    objectives: Dict[str, float] = field(default_factory=dict)
    risks: float = 0.0

    @property
    def score(self) -> float:
        return sum(self.objectives.values()) - self.risks

# --- 2. The Representation (Adapter) ---
class DomainAdapter(ABC):
    @abstractmethod
    def forward(self, domain_state: np.ndarray) -> np.ndarray:
        """Map raw domain data to TELOS latent space."""
        ...

    @abstractmethod
    def inverse(self, telos_action: np.ndarray) -> np.ndarray:
        """Map TELOS action to domain-appropriate primitive."""
        ...

# --- Core Model Interfaces ---

@dataclass
class Constraint:
    name: str
    description: str

@dataclass
class RiskProfile:
    harm_types: List[str]
    threshold: float

@dataclass
class Objectives:
    goals: List[str]
