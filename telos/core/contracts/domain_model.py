from abc import ABC, abstractmethod
from typing import List, Any, Optional, Dict, Set
import numpy as np
from dataclasses import dataclass, field
from telos.world.world import World
from telos.world.facts import DomainFacts


# ─── Phase 1: WorldSpec — explicit, self-describing world contract ──────────────
@dataclass
class WorldSpec:
    """What a world IS and what it PERMITS.

    This is the TELOS v6 "World Manifest". It is deliberately small and
    does NOT contain EvidenceSource / experiments / causal discovery /
    learning / provenance graphs. Its purpose is only:

        what the world is, and what the world permits.

    Fields:
        name:         required, unique domain identifier (no silent 'gridworld').
        version:      optional schema/domain version.
        state_dim:    declared dimensionality of the latent state vector.
        action_dim:   declared dimensionality of the action vector.
        objectives:   what the world values (for evaluate()/ranking).
        constraints:  hard constraints the domain enforces.
        observability: qualitative observability label (high/medium/low/partial).
        capabilities: capability names this world exposes (for authorization).
        authorized_modes: set of decision modes the world currently permits
                      from {ACT, DEFER, ABSTAIN, ESCALATE, BLOCK}.
    """
    name: str
    state_dim: int
    action_dim: int = 0
    version: str = "1.0"
    objectives: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    observability: str = "unknown"
    capabilities: List[str] = field(default_factory=list)
    authorized_modes: Set[str] = field(
        default_factory=lambda: {"ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK"}
    )
    # TELOS v6 escalation policy: "advisory" (proceed + log, low-risk worlds) or
    # "required" (human/domain approval is a HARD GATE before ACT, safety-critical
    # worlds). Deliberate per-world policy, NOT a global default.
    escalation_policy: str = "advisory"

    def validate(self) -> Optional[str]:
        """Return a human-readable error string if the spec is invalid, else None."""
        if not self.name or not self.name.strip():
            return "WorldSpec.name is required and must be non-empty"
        if self.state_dim is None or self.state_dim <= 0:
            return "WorldSpec.state_dim must be a positive integer"
        valid_modes = {"ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK"}
        unknown = self.authorized_modes - valid_modes
        if unknown:
            return f"WorldSpec.authorized_modes contains unknown modes: {sorted(unknown)}"
        if self.escalation_policy not in ("advisory", "required"):
            return f"WorldSpec.escalation_policy must be 'advisory' or 'required', got {self.escalation_policy!r}"
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "state_dim": self.state_dim,
            "action_dim": self.action_dim,
            "objectives": list(self.objectives),
            "constraints": list(self.constraints),
            "observability": self.observability,
            "capabilities": list(self.capabilities),
            "authorized_modes": sorted(self.authorized_modes),
            "escalation_policy": self.escalation_policy,
        }


# Sentinel to detect "module forgot to declare its name" instead of silently
# defaulting to 'gridworld' (P1: no silent default).
_MISSING = object()

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
        """RuleGate: Define allowable actions.

        Args:
            state: the current domain state to compute legal actions for.
        """

    @abstractmethod
    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        """The 'physics' of the domain.

        Args:
            state: the starting state before the step.
            action: the action vector applied to produce the next state.
        """

    @abstractmethod
    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        """Project future trajectories.

        Args:
            state: the state to begin the simulation from.
            horizon: number of future steps to project.
        """

    @abstractmethod
    def get_facts(self, state: np.ndarray) -> DomainFacts:
        """Returns objective domain facts for reasoning.

        Args:
            state: the state to derive domain facts from.
        """

    @abstractmethod
    def terminal(self, state: np.ndarray) -> bool:
        """Boundary condition definition.

        Args:
            state: the state to test for terminal/boundary condition.
        """

    @abstractmethod
    def evaluate(self, state: np.ndarray) -> "EvaluationReport":
        """Score a state for trajectory ranking (CounterfactualEngine)."""

    # ─── Phase 1: WorldSpec — every world describes itself ─────────────────────
    # Concrete-by-default so existing simulators keep working, but a real world
    # that wants dimension/capability validation supplies a fuller spec. This is
    # deliberately NOT a silent 'gridworld' default — identity must come from the
    # subclass (name/state_dim attrs or an explicit world_spec override).
    def world_spec(self) -> WorldSpec:
        name = getattr(self, "name", None) or getattr(type(self), "__name__", "unnamed")
        state_dim = getattr(self, "state_dim", None)
        if state_dim is None and hasattr(self, "world_spec") is False:
            # best-effort: if the subclass didn't declare dims, leave unknown
            state_dim = state_dim
        return WorldSpec(
            name=name,
            state_dim=int(state_dim) if state_dim else 0,
            action_dim=int(getattr(self, "action_dim", 0) or 0),
            objectives=list(getattr(self, "objectives", []) or []),
            constraints=list(getattr(self, "constraints", []) or []),
            observability=getattr(self, "observability", "unknown"),
        )

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
        """Map raw domain data to TELOS latent space.

        Args:
            domain_state: the raw domain state to encode.
        """
        ...

    @abstractmethod
    def inverse(self, telos_action: np.ndarray) -> np.ndarray:
        """Map TELOS action to domain-appropriate primitive.

        Args:
            telos_action: the TELOS action vector to map back to the domain.
        """
        ...

    # ─── Phase 1: explicit contract (was implicit/duck-typed) ─────────────────
    # `name` and `intent_to_action` were previously assumed ad hoc (see act.py /
    # runtime.py). Now they are first-class abstract members of the interface so
    # a domain that forgets them FAILS EARLY instead of silently becoming a grid
    # world (acceptance: no silent 'gridworld' default, intent_to_action cannot
    # silently disappear, name cannot silently disappear).
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identity of this world/domain. MUST be declared."""
        ...

    @abstractmethod
    def intent_to_action(self, intent: Any, state: np.ndarray,
                         mission_dir: np.ndarray) -> np.ndarray:
        """Map a TELOS intent to a concrete domain action vector.

        Args:
            intent: the selected TELOS intent to execute.
            state: the current domain state.
            mission_dir: the direction toward the mission goal.
        """
        ...

    def declared_state_dim(self) -> Optional[int]:
        """Return the declared latent state dimension, if the adapter exposes one.

        Subclasses that define `state_dim` (property or attr) are picked up here
        so the runtime can validate against the actual state vector shape
        (acceptance: state/action dimensions are validated, no accidental shape
        inference alone).
        """
        v = getattr(self, "state_dim", None)
        return int(v) if isinstance(v, int) else (v if isinstance(v, float) else None)

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
