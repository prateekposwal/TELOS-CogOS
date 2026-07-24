"""
Risk Transform — activated when Observer Coupling (B_t) is high.

In Mirror or Critical coupling modes, the system risks identity-
anchored bias.  This transform forces an objective, identity-detached
coordinate system by counterfactual red-teaming and worst-case
adversarial framing.

The activation threshold θ_t is *adaptive* — it depends on the
current runtime state rather than a hard-coded constant:

  θ_t = f(Domain, Volatility, H_t, B_t, Mission)

This means a high-volatility market naturally raises or lowers the
threshold without changing code.
"""

from typing import Any
import numpy as np
from representation_transform import (
    RuntimeState,
    RepresentationTransform,
)


class RiskTransform(RepresentationTransform):
    """Force objective, identity-detached reasoning.

    Forward:  state → anti-mission adversarial perturbation
    Inverse:  action → action (no change — actions remain grounded)

    The activation threshold θ_t adapts to the current runtime state.
    """

    def __init__(self, base_threshold: float = 0.6):
        self.base_threshold = base_threshold

    @property
    def name(self) -> str:
        return "risk"

    def compute_threshold(self, state: RuntimeState) -> float:
        """Dynamic activation threshold θ_t = f(D, σ, H_t, B_t, G₀).

        Returns a value in [0.2, 0.8].
        """
        volatility = float(np.std(state.health_vector)) if len(state.health_vector) > 1 else 0.0
        avg_health = float(np.mean(state.health_vector))

        domain_penalty = 0.0
        if state.domain_topology == "discrete":
            domain_penalty = 0.1
        elif state.domain_topology == "graph":
            domain_penalty = 0.15

        volatility_penalty = volatility * 0.2
        health_penalty = (1.0 - avg_health) * 0.15
        coupling_penalty = state.coupling_index * 0.1

        θ = (self.base_threshold
             - domain_penalty
             - volatility_penalty
             - health_penalty
             - coupling_penalty)

        return float(np.clip(θ, 0.2, 0.8))

    def applicable(self, state: RuntimeState) -> float:
        threshold = self.compute_threshold(state)
        if state.coupling_index > threshold:
            return state.coupling_index
        return 0.0

    def confidence(self, state: RuntimeState) -> float:
        threshold = self.compute_threshold(state)
        if state.coupling_index <= threshold:
            return 0.0
        margin = (state.coupling_index - threshold) / (1.0 - threshold + 1e-8)
        return float(np.clip(margin, 0.0, 1.0))

    def estimate_information_loss(self, input_data: Any) -> float:
        if isinstance(input_data, np.ndarray):
            norm_in = float(np.linalg.norm(input_data))
            if norm_in < 1e-9:
                return 0.0
            anti_norm = float(np.linalg.norm(np.ones_like(input_data) * 0.15))
            return float(np.clip(anti_norm / norm_in, 0.0, 1.0))
        return 0.0

    def forward(self, input_data: Any) -> Any:
        if isinstance(input_data, np.ndarray):
            anti_pull = -np.ones_like(input_data) * 0.15
            return input_data + anti_pull
        return input_data

    def inverse(self, output_data: Any) -> Any:
        return output_data

    def __repr__(self) -> str:
        return f"RiskTransform(θ_base={self.base_threshold})"
