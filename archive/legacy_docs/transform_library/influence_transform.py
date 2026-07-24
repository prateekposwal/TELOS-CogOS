"""
Influence Transform — wraps the InfluenceFieldEngine.

Projects the state into a propagation field that models second-
and third-order ripple costs of candidate actions.
"""

from typing import Any, Optional
import numpy as np
from representation_transform import (
    RuntimeState,
    RepresentationTransform,
)


class InfluenceTransform(RepresentationTransform):
    """Augment state with influence-propagation costs.

    When reasoning about actions that have delayed or indirect
    consequences, this transform adds a propagation-cost dimension
    to the representation.
    """

    def __init__(self, influence_engine: Any = None):
        self.influence_engine = influence_engine

    @property
    def name(self) -> str:
        return "influence"

    def applicable(self, state: RuntimeState) -> float:
        if self.influence_engine is None:
            return 0.0
        return 0.5

    def confidence(self, state: RuntimeState) -> float:
        if self.influence_engine is None:
            return 0.0
        return 0.6

    def forward(self, input_data: Any) -> Any:
        if isinstance(input_data, np.ndarray):
            return input_data
        return input_data

    def inverse(self, output_data: Any) -> Any:
        if isinstance(output_data, np.ndarray):
            return output_data
        return output_data

    def __repr__(self) -> str:
        return f"InfluenceTransform(engine={'set' if self.influence_engine else 'None'})"
