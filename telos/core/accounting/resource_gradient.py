"""
Resource Gradient Tracker — ∂J/∂r_i marginal utility of each resource.

P4: Resource Gradient and Reallocation Loop

The gradient is computed by:
1. For each resource dimension (energy, memory, identity, recovery),
   temporarily increase by 10%
2. Recompute CommitmentScore
3. ∂J / ∂r_i = gradient
4. Reallocate: shift budget from negative-gradient resources to positive-gradient

This implements a simple form of gradient ascent on cognitive resource allocation:
  R_{t+1} = argmax_R U_R  — shift resources toward highest gradient.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from copy import deepcopy

logger = logging.getLogger('telos_resource_gradient')


class ResourceGradientTracker:
    """∂J/∂r_i — marginal utility of each resource.
    
    Tracks the marginal contribution of each resource dimension to the
    system's overall commitment score, enabling optimal reallocation.
    
    Resource dimensions:
      - energy: Compute budget (ms)
      - memory: Trace history length / context size
      - identity: Identity stability budget
      - recovery: Recovery capacity budget
    """

    RESOURCE_DIMENSIONS = ['energy', 'memory', 'identity', 'recovery']
    PERTURBATION_FRACTION = 0.10  # 10% increase to measure gradient

    def __init__(self):
        self._gradients: Dict[str, float] = {r: 0.0 for r in self.RESOURCE_DIMENSIONS}
        self._gradient_history: List[Dict[str, float]] = []
        self._max_history: int = 50
        self._reallocation_count: int = 0
        self._last_budgets: Optional[Dict[str, float]] = None

    def compute_gradients(self,
                          commitment_optimizer: Any,
                          resource_budgets: Dict[str, Any]) -> Dict[str, float]:
        """Perturb each resource dimension + measure ΔJ.
        
        For each resource dimension, temporarily increase by PERTURBATION_FRACTION
        and recompute the CommitmentScore. The gradient is ΔJ / Δr_i.
        
        Args:
            commitment_optimizer: The system's CommitmentOptimizer instance
            resource_budgets: Dict with current resource budget values.
                Expected keys: 'energy', 'memory', 'identity', 'recovery'
                Each value is a dict with at minimum a numeric 'value' or 
                equivalent field that can be perturbed.
                
        Returns:
            Dict mapping resource name to gradient value
        """
        if commitment_optimizer is None:
            return {r: 0.0 for r in self.RESOURCE_DIMENSIONS}

        # Extract base resource values
        base_values = self._extract_resource_values(resource_budgets)
        if not base_values:
            return {r: 0.0 for r in self.RESOURCE_DIMENSIONS}

        # Compute base commitment score as reference
        base_score = self._compute_reference_score(commitment_optimizer, base_values)
        if base_score is None:
            return {r: 0.0 for r in self.RESOURCE_DIMENSIONS}

        gradients = {}
        for resource in self.RESOURCE_DIMENSIONS:
            if resource not in base_values:
                gradients[resource] = 0.0
                continue

            # Perturb this resource by +10%
            perturbed_values = dict(base_values)
            base_val = base_values[resource]
            delta = base_val * self.PERTURBATION_FRACTION
            perturbed_values[resource] = base_val + delta

            # Recompute score with perturbed values
            perturbed_score = self._compute_reference_score(
                commitment_optimizer, perturbed_values
            )

            if perturbed_score is not None and base_score != 0:
                # ∂J / ∂r_i = ΔJ / Δr_i
                delta_j = perturbed_score - base_score
                gradient = delta_j / max(delta, 1e-8)
                gradients[resource] = float(gradient)
            else:
                gradients[resource] = 0.0

        self._gradients = gradients
        self._last_budgets = base_values

        snapshot = dict(gradients)
        snapshot['_base_score'] = base_score
        self._gradient_history.append(snapshot)
        if len(self._gradient_history) > self._max_history:
            self._gradient_history.pop(0)

        logger.debug(
            f"Resource gradients: " + ", ".join(
                f"{k}={v:.4f}" for k, v in gradients.items()
            )
        )

        return gradients

    def reallocate(self, budgets: Dict[str, Any],
                   gradients: Dict[str, float],
                   step_size: float = 0.05) -> Dict[str, float]:
        """R_{t+1} = argmax_R U_R — shift resources toward highest gradient.
        
        Shift budget from negative-gradient resources to positive-gradient ones.
        
        Args:
            budgets: Current resource budget dict (same structure as resource_budgets)
            gradients: Dict mapping resource name to gradient value
            step_size: Fraction of budget to reallocate (default 0.05 = 5%)
            
        Returns:
            Dict with reallocated budget values for each resource dimension,
            normalized to sum to approximately 1.0
        """
        self._reallocation_count += 1

        # Extract numeric values
        alloc = {}
        for r in self.RESOURCE_DIMENSIONS:
            if r in budgets:
                budget_info = budgets[r]
                if isinstance(budget_info, dict):
                    if 'utilization' in budget_info:
                        alloc[r] = budget_info['utilization']
                    elif 'value' in budget_info:
                        alloc[r] = budget_info['value']
                    else:
                        alloc[r] = 0.25  # default equal share
                elif isinstance(budget_info, (int, float)):
                    alloc[r] = float(budget_info)
                else:
                    alloc[r] = 0.25
            else:
                alloc[r] = 0.25

        # Normalize so they sum to 1.0
        total = sum(alloc.values()) or 1.0
        alloc = {k: v / total for k, v in alloc.items()}

        # Shift: positive gradient → get more, negative → give up
        reallocated = dict(alloc)
        for resource, grad in gradients.items():
            if resource not in reallocated:
                continue
            if grad > 0:
                # Increase allocation
                reallocated[resource] += step_size * min(1.0, grad)
            elif grad < 0:
                # Decrease allocation (but floor at 0.05)
                reallocated[resource] += step_size * max(-1.0, grad)  # negative += negative → decrease
                reallocated[resource] = max(0.05, reallocated[resource])

        # Re-normalize
        new_total = sum(reallocated.values()) or 1.0
        reallocated = {k: v / new_total for k, v in reallocated.items()}

        logger.info(
            f"Resource reallocation #{self._reallocation_count}: "
            + ", ".join(f"{k}: {alloc[k]:.3f}→{reallocated[k]:.3f}" for k in alloc)
        )

        return reallocated

    def _extract_resource_values(self, budgets: Dict) -> Dict[str, float]:
        """Extract numeric values from resource budget dict."""
        values = {}
        if not budgets:
            return values

        for r in self.RESOURCE_DIMENSIONS:
            if r in budgets:
                info = budgets[r]
                if isinstance(info, dict):
                    # Try common fields
                    for key in ['utilization', 'value', 'consumed_ms', 'budget']:
                        if key in info:
                            val = info[key]
                            if isinstance(val, (int, float)):
                                values[r] = float(val)
                                break
                    if r not in values:
                        # Fall back to identity_entropy for identity resource
                        if 'identity_entropy' in info:
                            values[r] = 1.0 - float(info.get('identity_stability', 0.5))
                        elif 'current_state' in info:
                            values[r] = 0.5
                elif isinstance(info, (int, float)):
                    values[r] = float(info)

        # Fill in defaults for missing dimensions
        for r in self.RESOURCE_DIMENSIONS:
            if r not in values:
                values[r] = 0.25

        return values

    def _compute_reference_score(self, optimizer: Any,
                                  resource_values: Dict[str, float]) -> Optional[float]:
        """Compute a reference commitment score from resource values."""
        try:
            score = optimizer.evaluate(
                expected_reward=0.5,
                maintenance_cost=1.0 - resource_values.get('energy', 0.5),
                recovery_cost=resource_values.get('recovery', 0.3),
                identity_cost=resource_values.get('identity', 0.2),
                future_option_value=resource_values.get('memory', 0.5) * 0.5,
                prediction_error=resource_values.get('energy', 0.5) * 0.1,
            )
            return score.commitment
        except Exception as e:
            logger.warning(f"Resource gradient reference score failed: {e}")
            return None

    @property
    def gradients(self) -> Dict[str, float]:
        return dict(self._gradients)

    @property
    def gradient_history(self) -> List[Dict]:
        return list(self._gradient_history)

    @property
    def dominant_resource(self) -> Optional[str]:
        """Return the resource with the highest positive gradient."""
        if not self._gradients:
            return None
        pos = {k: v for k, v in self._gradients.items() if v > 0}
        if not pos:
            return None
        return max(pos, key=pos.get)

    @property
    def reallocations_performed(self) -> int:
        return self._reallocation_count

    def to_dict(self) -> Dict:
        return {
            "gradients": self._gradients,
            "dominant_resource": self.dominant_resource,
            "reallocations_performed": self._reallocation_count,
            "recent_history": self._gradient_history[-5:] if self._gradient_history else [],
        }
