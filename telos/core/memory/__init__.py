"""
TELOS decision-memory layer (Phase 2).

One tiered store + one ops controller over TELOS's decision memory. Retrieval
quality is measured (telos/tools/memory_eval.py), not asserted; writes pass a
provenance + poison gate so a governance-suppressed outcome can never enter
memory as evidence.
"""

from telos.core.memory.tiering import (
    MemoryRecord, TieredMemory,
    DEFAULT_HOT_LIMIT, DEFAULT_WARM_LIMIT, DEFAULT_COLD_LIMIT,
    W_IMPORTANCE, W_RECENCY,
)
from telos.core.memory.controller import (
    MemoryController, EPISTEMIC_KINDS, tokenize,
)

__all__ = [
    "MemoryRecord", "TieredMemory", "MemoryController",
    "DEFAULT_HOT_LIMIT", "DEFAULT_WARM_LIMIT", "DEFAULT_COLD_LIMIT",
    "W_IMPORTANCE", "W_RECENCY", "EPISTEMIC_KINDS", "tokenize",
]
