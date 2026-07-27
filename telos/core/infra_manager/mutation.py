"""MutationGuard — security defense for infrastructure changes."""
from dataclasses import dataclass
from typing import Dict, Optional, Any, List
import time
import hmac
import hashlib
import logging
logger = logging.getLogger("telos_infrastructure")

class MutationGuard:
    """Per-cycle rate limiter for InfrastructureManager self-modification.
    
    Prevents any single observe() call from making large, runaway changes
    to cognitive parameters by capping total delta per parameter per cycle.
    """
    
    MAX_DELTA_PER_CYCLE = {
        'risk_tolerance': 0.05,
        'exploration_budget': 0.05,
        'influence_weight': 0.1,
        'ambition_level': 0.1,
        'drift_tolerance': 1.0,
        'maintenance_bias': 0.1,
        'recovery_urgency': 0.1,
    }
    
    def __init__(self):
        self._cycle_deltas: Dict[str, float] = {}
        self._cycle_number: int = 0
        self._blocked_changes: int = 0
    
    def begin_cycle(self, cycle_number: int) -> None:
        self._cycle_number = cycle_number
        self._cycle_deltas = {}
    
    def check(self, param: str, proposed_delta: float) -> bool:
        current = self._cycle_deltas.get(param, 0.0)
        new_total = current + proposed_delta
        cap = self.MAX_DELTA_PER_CYCLE.get(param, 0.05)
        if abs(new_total) > cap:
            logger.warning(
                f"MutationGuard BLOCKED: {param} would drift {new_total:.3f} "
                f"(cap={cap}) in cycle {self._cycle_number}"
            )
            self._blocked_changes += 1
            return False
        self._cycle_deltas[param] = new_total
        return True


