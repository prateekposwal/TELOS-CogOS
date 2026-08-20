"""Resource Budget Tracker — multi-resource budget tracking."""
"""
TELOS Attention Management.

Contains:
  - BudgetManager: Global budget governor for pipeline phases (Λ3.2)
  - ResourceBudgetTracker: Multi-resource budget tracking (P1 D3)
  - TokenBudgetManager: Intelligent chat history truncation by signal value
  - AttentionProjectionEngine: Law of Attention and Trajectory modeling
  - IdentityEntropyTracker: Perceived action-space tracking under stress
"""

from telos.core.attention.token_budget import TokenBudgetManager, estimate_tokens, estimate_message_tokens
from telos.core.attention.projection import (
    AttentionProjectionEngine, AttentionAllocation, TrajectoryProjection,
)
from telos.core.attention.identity_entropy import (
    IdentityEntropyTracker, EntropySignal,
)

from typing import Dict, List
from dataclasses import dataclass, field


@dataclass
class ResourceBudgetTracker:
    """
    Multi-resource budget tracking (P1 D3).

    Extends beyond simple compute budgets to track four resource dimensions:
      - Energy: compute_budget_ms consumed this cycle
      - Memory: trace_history length (number of stored traces)
      - Identity: identity entropy (1 - identity_stability)
      - Recovery: number of recovery_mode cycles active
    """

    energy_budget_ms: float = 0.0
    memory_trace_length: int = 0
    identity_entropy: float = 0.0
    recovery_cycles: int = 0
    _history: List[Dict] = field(default_factory=list)
    _max_history: int = 100

    def record(self, energy_ms: float, trace_length: int,
               identity_entropy: float, recovery_cycles: int) -> None:
        """Record a snapshot of all resource dimensions.

        Args:
            energy_ms: compute budget (ms) remaining.
            trace_length: length of the current decision trace.
            identity_entropy: entropy of the identity representation.
            recovery_cycles: count of recovery cycles run this session.
        """
        self.energy_budget_ms = energy_ms
        self.memory_trace_length = trace_length
        self.identity_entropy = identity_entropy
        self.recovery_cycles = recovery_cycles

        self._history.append({
            "energy_ms": energy_ms,
            "trace_length": trace_length,
            "identity_entropy": identity_entropy,
            "recovery_cycles": recovery_cycles,
        })
        if len(self._history) > self._max_history:
            self._history.pop(0)

    @property
    def stats(self) -> Dict:
        return {
            "energy_budget_ms": self.energy_budget_ms,
            "memory_trace_length": self.memory_trace_length,
            "identity_entropy": self.identity_entropy,
            "recovery_cycles": self.recovery_cycles,
            "history_length": len(self._history),
        }

    def to_dict(self) -> Dict:
        return self.stats



@dataclass
class AttentionBid:
    """A bid from a cognitive stream for compute budget (Bitcoin-inspired auction).

    In the attention budget auction, streams bid compute milliseconds for
    their processing. The highest bidder gets priority; all winners pay
    the lowest winning bid (single-price auction).

    Attributes:
        stream_name: Name of the bidding stream
        bid_amount_ms: How many milliseconds this stream requests
        priority_multiplier: Priority-derived multiplier (higher = can outbid)
        base_budget_ms: Stream's base budget before bidding
    """
    stream_name: str
    bid_amount_ms: float
    priority_multiplier: float = 1.0
    base_budget_ms: float = 5.0

    @property
    def effective_bid(self) -> float:
        """Priority-weighted bid amount."""
        return self.bid_amount_ms * self.priority_multiplier


def run_attention_auction(bids: List[AttentionBid],
                           total_budget_ms: float) -> Dict[str, float]:
    """Run a single-price attention budget auction.

    All streams submit bids for compute ms. The highest bidder wins and
    gets their full requested budget. Lower bidders get what remains.
    All winners pay the lowest winning bid (single-price auction).

    Args:
        bids: List of AttentionBid from each stream
        total_budget_ms: Total compute budget available

    Returns:
        Dict mapping stream_name -> allocated budget in ms
    """
    if not bids:
        return {}

    # Sort by effective bid descending
    sorted_bids = sorted(bids, key=lambda b: b.effective_bid, reverse=True)

    # Determine winners: allocate until budget exhausted
    allocated = {}
    remaining = total_budget_ms

    for bid in sorted_bids:
        if remaining <= 0:
            allocated[bid.stream_name] = 0.0
            continue

        # Winner gets their requested amount (if enough budget)
        award = min(bid.bid_amount_ms, remaining)
        allocated[bid.stream_name] = award
        remaining -= award

    # Single-price: all winners pay the lowest winning bid amount
    winning_bids = [b for b in sorted_bids if allocated.get(b.stream_name, 0) > 0]
    if winning_bids:
        lowest_winning = min(
            allocated[b.stream_name] for b in winning_bids
            if allocated.get(b.stream_name, 0) > 0
        )
        # Apply single-price: cap each winner at the lowest winning amount
        for b in winning_bids:
            allocated[b.stream_name] = min(allocated[b.stream_name], lowest_winning)

    return allocated


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
    budget_carryover_ms: float = 0.0  # carried-over credit from the previous cycle (>= 0)
    phase_costs: Dict[str, float] = field(default_factory=dict)
    _reservations: Dict[str, float] = field(default_factory=dict)

    def reserve(self, stream_name: str, amount_ms: float) -> None:
        """Reserve a budget slice exclusively for stream_name.

        Args:
            stream_name: the stream that owns the reservation.
            amount_ms: the budget slice (ms) set aside for that stream.
        """
        self._reservations[stream_name] = amount_ms

    def check_budget(self, phase_name: str, estimated_cost: float) -> bool:
        """Returns True if the phase can proceed within the remaining budget.

        Accounts for reservations made for other streams: a stream can only
        consume from the unreserved pool plus its own reservation.

        Args:
            phase_name: the phase/stream asking to proceed.
            estimated_cost: the projected cost (ms) of the phase.
        """
        my_reservation = self._reservations.get(phase_name, 0.0)
        others_reserved = sum(v for k, v in self._reservations.items() if k != phase_name)
        available = (self.total_budget_ms - self.consumed_ms
                     + self.budget_carryover_ms - others_reserved + my_reservation)
        return estimated_cost <= available

    def consume(self, phase_name: str, cost: float):
        """Register the actual cost of a phase.

        Args:
            phase_name: the phase whose cost is recorded.
            cost: the measured cost (ms) of that phase.
        """
        self.consumed_ms += cost
        self.phase_costs[phase_name] = self.phase_costs.get(phase_name, 0.0) + cost

    def reset(self, carryover_ms: float = 0.0):
        clamped = max(0.0, min(carryover_ms, self.total_budget_ms * 0.5))
        # The carryover is a separate, explicitly-tracked credit: `consumed_ms`
        # NEVER goes negative, so every serialized budget trace reads as a real
        # (non-negative) consumption figure. The credit is applied in
        # check_budget() so a fresh cycle still gets its carried-over budget
        # headroom (P2 budget-carryover telemetry).
        self.budget_carryover_ms = clamped
        self.consumed_ms = 0.0
        self.phase_costs.clear()
        self._reservations.clear()


__all__ = [
    "AttentionBid",
    "run_attention_auction",
    "BudgetManager",
    "ResourceBudgetTracker",
    "TokenBudgetManager",
    "estimate_tokens",
    "estimate_message_tokens",
    "AttentionProjectionEngine",
    "AttentionAllocation",
    "TrajectoryProjection",
    "IdentityEntropyTracker",
    "EntropySignal",
]
