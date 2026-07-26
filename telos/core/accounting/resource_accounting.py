"""Resource Accounting Layer — R(a,s) = (C_compute, C_memory, C_bandwidth, C_storage).

Every cognitive action has measurable computational costs.
Blockchain is one possible backend that instantiates this abstraction.

Architecture:
  ResourceAccountingLayer — per-action cost accounting with per-cycle aggregation
    delegates compute → BudgetManager
    delegates memory → ResourceBudgetTracker
    manages bandwidth + storage natively

  ResourceLedgerBackend — pluggable persistence for cost records
    DictLedgerBackend — in-memory (default)
    BlockchainLedgerBackend — future, for cryptographic audit trails
"""

from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger('telos_resource_accounting')


@dataclass
class ResourceCost:
    """R(a,s) = (C_compute, C_memory, C_bandwidth, C_storage).

    The cost of executing a single cognitive action in a given state.
    """
    compute_ms: float = 0.0
    memory_traces: int = 0
    bandwidth_bytes: float = 0.0
    storage_entries: int = 0
    timestamp: float = field(default_factory=time.time)

    def __add__(self, other: ResourceCost) -> ResourceCost:
        return ResourceCost(
            compute_ms=self.compute_ms + other.compute_ms,
            memory_traces=self.memory_traces + other.memory_traces,
            bandwidth_bytes=self.bandwidth_bytes + other.bandwidth_bytes,
            storage_entries=self.storage_entries + other.storage_entries,
        )

    def to_dict(self) -> Dict:
        return {
            "compute_ms": round(self.compute_ms, 3),
            "memory_traces": self.memory_traces,
            "bandwidth_bytes": round(self.bandwidth_bytes, 1),
            "storage_entries": self.storage_entries,
        }


class ResourceLedgerBackend(ABC):
    """Pluggable persistence for cost records."""

    @abstractmethod
    def commit(self, records: List[Dict]) -> None:
        """Persist a batch of cost records."""

    @abstractmethod
    def query(self, action_id: str) -> Optional[Dict]:
        """Retrieve cost for a specific action."""

    @abstractmethod
    def get_cycle_costs(self, cycle: int) -> List[Dict]:
        """Get all costs recorded in a given cycle."""


class DictLedgerBackend(ResourceLedgerBackend):
    """In-memory storage (default backend)."""

    def __init__(self):
        self._records: List[Dict] = []
        self._by_action: Dict[str, Dict] = {}
        self._by_cycle: Dict[int, List[Dict]] = {}

    def commit(self, records: List[Dict]) -> None:
        for r in records:
            self._records.append(r)
            aid = r.get("action_id", "")
            if aid:
                self._by_action[aid] = r
            cycle = r.get("cycle", -1)
            if cycle not in self._by_cycle:
                self._by_cycle[cycle] = []
            self._by_cycle[cycle].append(r)

    def query(self, action_id: str) -> Optional[Dict]:
        return self._by_action.get(action_id)

    def get_cycle_costs(self, cycle: int) -> List[Dict]:
        return self._by_cycle.get(cycle, [])


class ResourceAccountingLayer:
    """Per-action cost accounting with per-cycle aggregation.

    R(a,s) = (C_compute, C_memory, C_bandwidth, C_storage)

    Usage:
        ral = ResourceAccountingLayer()
        ral.record_action("reflex_check", ResourceCost(compute_ms=2.0))
        ral.record_action("planning", ResourceCost(compute_ms=12.0, memory_traces=3,
                           bandwidth_bytes=500, storage_entries=1))
        summary = ral.cycle_summary()
    """

    def __init__(self, backend: Optional[ResourceLedgerBackend] = None):
        self._backend = backend or DictLedgerBackend()
        self._current_cycle: int = 0
        self._cycle_buffer: List[Dict] = []
        self._cycle_totals: Optional[ResourceCost] = None

    def set_cycle(self, cycle: int) -> None:
        """Start a new accounting cycle. Flushes previous cycle to backend."""
        if self._cycle_buffer:
            self._backend.commit(self._cycle_buffer)
        self._current_cycle = cycle
        self._cycle_buffer = []
        self._cycle_totals = None

    def record_action(self, action_id: str, cost: ResourceCost,
                      metadata: Optional[Dict] = None) -> None:
        """Record a cognitive action's resource cost for the current cycle."""
        record = {
            "action_id": action_id,
            "cycle": self._current_cycle,
            "cost": cost.to_dict(),
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self._cycle_buffer.append(record)
        if self._cycle_totals is None:
            self._cycle_totals = cost
        else:
            self._cycle_totals = self._cycle_totals + cost
        logger.debug(
            f"ResourceAccounting: {action_id} → "
            f"compute={cost.compute_ms:.1f}ms, mem={cost.memory_traces}, "
            f"bw={cost.bandwidth_bytes:.0f}B, storage={cost.storage_entries}"
        )

    def record_stream_activation(self, stream_name: str, compute_ms: float,
                                  memory_traces: int = 0) -> None:
        """Convenience: record a stream's resource usage."""
        cost = ResourceCost(
            compute_ms=compute_ms,
            memory_traces=memory_traces,
        )
        self.record_action(f"stream:{stream_name}", cost,
                          metadata={"type": "stream_activation"})

    @property
    def total_cost(self) -> ResourceCost:
        if self._cycle_totals is None:
            return ResourceCost()
        return self._cycle_totals

    def cycle_summary(self) -> Dict:
        """Summary of current cycle's resource consumption."""
        tc = self.total_cost
        return {
            "cycle": self._current_cycle,
            "total_compute_ms": round(tc.compute_ms, 3),
            "total_memory_traces": tc.memory_traces,
            "total_bandwidth_bytes": round(tc.bandwidth_bytes, 1),
            "total_storage_entries": tc.storage_entries,
            "action_count": len(self._cycle_buffer),
            "actions": [r["action_id"] for r in self._cycle_buffer],
        }

    def attach_backend(self, backend: ResourceLedgerBackend) -> None:
        """Replace the persistence backend at runtime."""
        self._backend = backend

    def get_action_cost(self, action_id: str) -> Optional[Dict]:
        return self._backend.query(action_id)

    def get_cycle_costs(self, cycle: int) -> List[Dict]:
        return self._backend.get_cycle_costs(cycle)

    def to_dict(self) -> Dict:
        tc = self.total_cost
        return {
            "current_cycle": self._current_cycle,
            "pending_actions": len(self._cycle_buffer),
            "cycle_total": tc.to_dict(),
        }
