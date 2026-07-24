"""
Representation Transform: The core abstraction for coordinate-system
transformation in TELOS.

Every transformation implements `forward(input) → transformed` and
`inverse(output) → action`, plus `applicable(state) → score` to
allow the RepresentationPlanner to dynamically dispatch the right
coordinate system for the current runtime state.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional
import numpy as np


# ── Runtime State (selection context for the planner) ─────────────────────

@dataclass
class RuntimeState:
    """Snapshot of the runtime used to select representations.

    Fields mirror the $f(G_0, H_t, B_t, H_i, C_t, T_t, D)$ selection
    function described in the RTE architecture.
    """
    mission_vector: np.ndarray
    health_vector: np.ndarray
    coupling_index: float
    identity_entropy: float
    compute_budget_ms: float
    time_budget_ms: float
    domain_topology: str = "continuous"
    step_count: int = 0
    metadata: dict = field(default_factory=dict)


# ── Base Transform Trait ──────────────────────────────────────────────────

class RepresentationTransform(ABC):
    """Abstract interface for all coordinate-system transformations.

    Each transform owns its coordinate system, metrics, and inverse
    mapping, allowing the RTE to compose them into arbitrary chains.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this transform (e.g. 'semantic', 'risk')."""
        ...

    @abstractmethod
    def applicable(self, state: RuntimeState) -> float:
        """Score in [0, 1] indicating suitability for the given runtime state.

        A score of 0 means "do not use"; 1 means "ideal for this state".
        """
        ...

    @abstractmethod
    def forward(self, input_data: Any) -> Any:
        """Transform raw input into the domain-specific representation.

        The output is fed into the next transform in the chain or
        directly into the simulation engine.
        """
        ...

    @abstractmethod
    def inverse(self, output_data: Any) -> Any:
        """Transform simulation results back into the physical/action domain.

        This is the critical grounding step that prevents abstract-space
        hallucination: the optimal solution in the transformed space must
        map to an executable action in the real world.
        """
        ...

    def confidence(self, state: RuntimeState) -> float:
        """Confidence in this transform's representation for the given state.

        Returns a value in [0, 1].  1 means "fully confident the chosen
        representation is correct"; 0 means "no confidence — use at your
        own risk."  The default 1.0 assumes the transform is always
        confident; subclasses should override when appropriate.
        """
        return 1.0

    def estimate_information_loss(self, input_data: Any) -> float:
        """Estimate information lost through forward → inverse round-trip.

        Returns a value in [0, 1].  0 means zero loss (perfectly
        invertible); 1 means complete loss.  The default computes
        ``||input - inverse(forward(input))|| / ||input||`` when the
        data is a numpy array, and returns 0 otherwise.
        """
        if isinstance(input_data, np.ndarray):
            transformed = self.forward(input_data)
            recovered = self.inverse(transformed)
            norm_in = float(np.linalg.norm(input_data))
            if norm_in < 1e-9:
                return 0.0
            diff = float(np.linalg.norm(input_data - recovered))
            return float(np.clip(diff / norm_in, 0.0, 1.0))
        return 0.0


# ── Transform Chain (composable pipeline) ─────────────────────────────────

class TransformChain:
    """An ordered sequence of transforms applied as a pipeline.

    Forward:  T₁ → T₂ → … → Tₙ   (each transform's output feeds the next)
    Inverse:  Tₙ⁻¹ → … → T₂⁻¹ → T₁⁻¹   (reverse order for grounding)
    """

    def __init__(self, transforms: Optional[List[RepresentationTransform]] = None):
        self.transforms = list(transforms) if transforms else []

    def apply(self, input_data: Any) -> Any:
        data = input_data
        for t in self.transforms:
            data = t.forward(data)
        return data

    def inverse(self, output_data: Any) -> Any:
        data = output_data
        for t in reversed(self.transforms):
            data = t.inverse(data)
        return data

    def append(self, transform: RepresentationTransform) -> None:
        self.transforms.append(transform)

    def compute_information_loss(self, input_data: Any) -> float:
        """Aggregate information loss across the entire chain.

        Each transform's round-trip loss is accumulated, giving an
        upper bound on the total information lost through the full
        transform → inverse cycle.
        """
        total = 0.0
        data = input_data
        for t in self.transforms:
            loss = t.estimate_information_loss(data)
            total += loss
            data = t.forward(data)
        return float(np.clip(total / max(len(self.transforms), 1), 0.0, 1.0))

    def __len__(self) -> int:
        return len(self.transforms)

    def __bool__(self) -> bool:
        return len(self.transforms) > 0

    def __repr__(self) -> str:
        names = [t.name for t in self.transforms]
        return f"TransformChain([{', '.join(names)}])"


# ── Identity Transform (pass-through, default fallback) ──────────────────

class IdentityTransform(RepresentationTransform):
    """A no-op transform used when no transformation is needed.

    This is the default entry point: it passes data through unchanged
    and is trivially invertible.
    """

    @property
    def name(self) -> str:
        return "identity"

    def applicable(self, state: RuntimeState) -> float:
        return 1.0

    def confidence(self, state: RuntimeState) -> float:
        return 1.0

    def forward(self, input_data: Any) -> Any:
        return input_data

    def inverse(self, output_data: Any) -> Any:
        return output_data

    def __repr__(self) -> str:
        return "IdentityTransform()"
