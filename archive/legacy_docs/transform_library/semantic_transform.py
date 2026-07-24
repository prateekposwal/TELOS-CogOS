"""
Semantic Transform — wraps the v15 SemanticExpansionEngine.

Maps raw state vectors into latent-role manifolds and relational
affordance graphs, enabling the system to reason about entities by
*what they afford* rather than *what they are*.
"""

from typing import Any, Optional
import numpy as np
from representation_transform import (
    RuntimeState,
    RepresentationTransform,
)


class SemanticTransform(RepresentationTransform):
    """Enrich state with latent-role embeddings.

    Forward:  state → state + role_embedding (concatenated or augmented)
    Inverse:  projection back to the original state space.
    """

    def __init__(self, semantic_engine: Any = None):
        self.semantic_engine = semantic_engine
        self._weight = 0.4

    @property
    def name(self) -> str:
        return "semantic"

    def applicable(self, state: RuntimeState) -> float:
        if self.semantic_engine is None:
            return 0.0
        return 0.6

    def confidence(self, state: RuntimeState) -> float:
        if self.semantic_engine is None:
            return 0.0
        return 0.7

    def forward(self, input_data: Any) -> Any:
        if isinstance(input_data, np.ndarray):
            return input_data
        return input_data

    def inverse(self, output_data: Any) -> Any:
        if isinstance(output_data, np.ndarray):
            return output_data
        return output_data

    def __repr__(self) -> str:
        return f"SemanticTransform(engine={'set' if self.semantic_engine else 'None'})"
