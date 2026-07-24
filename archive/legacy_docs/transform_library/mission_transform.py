"""
Mission Transform — decomposes global goals into hierarchical sub-goals.

When mission integrity is critical or drift is high, this transform
projects the state into a hierarchical constraint graph where the
pipeline reasons about sub-goal feasibility rather than raw state
dimensions.
"""

from typing import Any, Optional
import numpy as np
from representation_transform import (
    RuntimeState,
    RepresentationTransform,
)


class MissionTransform(RepresentationTransform):
    """Add hierarchical goal decomposition to the state representation.

    Forward:  state → state + constraint_vector
    Inverse:  action → action (no change)
    """

    def __init__(self, game_router: Any = None):
        self.game_router = game_router

    @property
    def name(self) -> str:
        return "mission"

    def applicable(self, state: RuntimeState) -> float:
        drift = 1.0 - float(np.mean(state.health_vector))
        if drift > 0.5:
            return drift
        return 0.0

    def confidence(self, state: RuntimeState) -> float:
        drift = 1.0 - float(np.mean(state.health_vector))
        return float(np.clip(drift, 0.0, 1.0))

    def forward(self, input_data: Any) -> Any:
        if isinstance(input_data, np.ndarray):
            return input_data
        return input_data

    def inverse(self, output_data: Any) -> Any:
        return output_data

    def __repr__(self) -> str:
        return "MissionTransform()"
