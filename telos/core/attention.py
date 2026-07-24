from typing import Dict, List
from dataclasses import dataclass, field

@dataclass
class BudgetManager:
    """
    Acts as a Global Governor for the pipeline's computational attention.
    Tracks budget consumption across pipeline phases.

    Supports stream budget reservation (Λ3.2): a high-priority stream
    can reserve a slice of budget for a lower-priority stream, preventing
    the first stream from consuming all resources.
    """
    total_budget_ms: float
    consumed_ms: float = 0.0
    phase_costs: Dict[str, float] = field(default_factory=dict)
    _reservations: Dict[str, float] = field(default_factory=dict)

    def reserve(self, stream_name: str, amount_ms: float) -> None:
        """Reserve a budget slice exclusively for stream_name."""
        self._reservations[stream_name] = amount_ms

    def check_budget(self, phase_name: str, estimated_cost: float) -> bool:
        """Returns True if the phase can proceed within the remaining budget.

        Accounts for reservations made for other streams: a stream can only
        consume from the unreserved pool plus its own reservation.
        """
        my_reservation = self._reservations.get(phase_name, 0.0)
        others_reserved = sum(v for k, v in self._reservations.items() if k != phase_name)
        available = self.total_budget_ms - self.consumed_ms - others_reserved + my_reservation
        return estimated_cost <= available

    def consume(self, phase_name: str, cost: float):
        """Register the actual cost of a phase."""
        self.consumed_ms += cost
        self.phase_costs[phase_name] = self.phase_costs.get(phase_name, 0.0) + cost

    def reset(self, carryover_ms: float = 0.0):
        clamped = max(0.0, min(carryover_ms, self.total_budget_ms * 0.5))
        self.consumed_ms = -clamped
        self.phase_costs.clear()
        self._reservations.clear()
