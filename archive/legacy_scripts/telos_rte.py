"""
TELOS Representation Transform Engine (RTE).

The orchestration layer that sits between perception and simulation.
Given a problem input and the current runtime state, the RTE:

  1. Asks the RepresentationPlanner for the optimal TransformChain.
  2. Applies the chain's forward transforms to the input.
  3. Returns the transformed representation (to be consumed by the
     simulation engine) along with the chain (so the inverse can be
     applied to the selected action).

This is the core architectural shift: representation selection is
treated as a first-class optimisation problem, not a hard-coded
preprocessing step.
"""

from typing import Any, Tuple
from representation_transform import (
    RuntimeState,
    TransformChain,
)
from telos.core.planner import RepresentationPlanner


class TelosRTE:
    """Representation Transform Engine — the meta-cognitive layer.

    Usage in a pipeline::

        rte = TelosRTE(planner)
        transformed_state, chain = rte.transform(runtime_state, raw_state)
        # ... run simulation on transformed_state ...
        domain_action = chain.inverse(selected_action)
    """

    def __init__(self, planner: RepresentationPlanner):
        self.planner = planner

    def transform(self, state: RuntimeState,
                  input_data: Any) -> Tuple[Any, TransformChain]:
        """Apply the optimal forward transforms to *input_data*.

        Returns:
            (transformed_data, chain) — the chain must be kept so the
            caller can call ``chain.inverse(output)`` later.
        """
        chain = self.planner.plan(state)
        transformed = chain.apply(input_data)
        return transformed, chain

    def __repr__(self) -> str:
        return f"TelosRTE(planner={self.planner})"
