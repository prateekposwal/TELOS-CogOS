"""
MemoryController — one ops API over TELOS's decision memory (Phase 2).

PATTERN (one memory discipline, Λ6.7): decision memory was six stores with six
retrieval rules and no measured quality. This controller gives memory ONE ops
surface — insert / search / update / evict / summarize — over the tiered store,
with a retrieval score that is explicit and a write gate that keeps the
canonical epistemic rule:

    a GOVERNANCE-SUPPRESSED outcome is NOT evidence.

A vetoed action was never tested, so recording it as a memory outcome would
poison the approach-failure space (the exact mechanism behind the documented
~30k-cycle plateau). The controller refuses such writes and counts them.

Retrieval is deterministic (token overlap x importance) — no external model, no
network — so retrieval quality is measurable against a fixed evaluation
(telos/tools/memory_eval.py) rather than asserted.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from telos.core.governance.recovery_types import GOVERNANCE_SUPPRESSION_REASONS
from telos.core.memory.tiering import (
    MemoryRecord, TieredMemory,
    DEFAULT_HOT_LIMIT, DEFAULT_WARM_LIMIT, DEFAULT_COLD_LIMIT,
)

# Record kinds that make an epistemic claim and therefore require a provenance
# caller before they may enter decision memory.
EPISTEMIC_KINDS = frozenset({"knowledge", "approach_failure", "evidence", "failure"})

_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    """Lowercase word/number tokens of length >= 2.

    Args:
        text: the text to tokenize.

    Returns:
        List of tokens.
    """
    return [t for t in _WORD_RE.findall((text or "").lower()) if len(t) >= 2]


def _overlap(query_tokens: List[str], content_tokens: List[str]) -> float:
    """Query-coverage overlap in [0, 1].

    Args:
        query_tokens: tokens of the query.
        content_tokens: tokens of the record content.

    Returns:
        Fraction of query tokens present in the content (0.0 when no query).
    """
    if not query_tokens:
        return 0.0
    q = set(query_tokens)
    d = set(content_tokens)
    return len(q & d) / len(q)


class MemoryController:
    """Unified insert/search/update/evict/summarize over tiered decision memory."""

    def __init__(self, tiered: Optional[TieredMemory] = None):
        """Construct a controller over a (possibly injected) tiered store.

        Args:
            tiered: the backing TieredMemory; a default one is created if None.
        """
        self._tiered = tiered or TieredMemory(
            hot_limit=DEFAULT_HOT_LIMIT,
            warm_limit=DEFAULT_WARM_LIMIT,
            cold_limit=DEFAULT_COLD_LIMIT,
        )
        self.inserted = 0
        self.rejected_governance_suppression = 0
        self.memory_consumed = 0

    # ── Write path ─────────────────────────────────────────────────────

    def insert(self, record: MemoryRecord) -> bool:
        """Insert a record through the provenance + poison gates.

        Args:
            record: the record to insert.

        Returns:
            True when the record entered memory; False when it was refused as a
            governance-suppressed outcome.

        Raises:
            ValueError: when an epistemic record carries no provenance caller.
        """
        prov = record.provenance or {}
        reason = prov.get("reason") or record.metadata.get("failure_reason")
        if reason in GOVERNANCE_SUPPRESSION_REASONS:
            self.rejected_governance_suppression += 1
            return False
        if record.kind in EPISTEMIC_KINDS and not prov.get("caller"):
            raise ValueError(
                f"epistemic memory record {record.record_id!r} requires "
                "provenance.caller (trusted-caller gate)"
            )
        self._tiered.add(record)
        self.inserted += 1
        return True

    def insert_many(self, records: Iterable[MemoryRecord]) -> int:
        """Insert many records, returning how many were accepted.

        Args:
            records: the records to insert.

        Returns:
            Count of accepted records.
        """
        return sum(1 for r in records if self.insert(r))

    # ── Read path ──────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5,
               domain: Optional[str] = None) -> List[MemoryRecord]:
        """Rank records by query overlap x importance; promote the hits.

        Args:
            query: natural-language query.
            top_k: maximum number of records to return.
            domain: optional domain filter.

        Returns:
            Ranked list of the top-k matching records.
        """
        qtokens = tokenize(query)
        scored = []
        for record in self._tiered.all_records():
            if domain and record.domain != domain:
                continue
            ov = _overlap(qtokens, tokenize(record.content))
            if ov <= 0.0:
                continue
            score = ov * (0.6 + 0.4 * record.importance)
            scored.append((score, record))
        scored.sort(key=lambda item: (
            -item[0], -item[1].importance, item[1].created_cycle, item[1].record_id,
        ))
        hits = [record for _score, record in scored[:max(0, top_k)]]
        for record in hits:
            self._tiered.access(record.record_id)
        self.memory_consumed += len(hits)
        return hits

    def naive_search(self, query: str, top_k: int = 5,
                     domain: Optional[str] = None) -> List[MemoryRecord]:
        """Baseline retrieval (plain overlap, insertion order) for evaluation.

        Deliberately model-free of importance/recency/tiering: it is the
        "before" against which the controller's "after" is measured.

        Args:
            query: natural-language query.
            top_k: maximum number of records to return.
            domain: optional domain filter.

        Returns:
            Ranked list of the top-k matching records (overlap only).
        """
        qtokens = tokenize(query)
        scored = []
        for order, record in enumerate(self._tiered.all_records()):
            if domain and record.domain != domain:
                continue
            ov = _overlap(qtokens, tokenize(record.content))
            if ov <= 0.0:
                continue
            scored.append((ov, order, record))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [record for _ov, _order, record in scored[:max(0, top_k)]]

    # ── Maintenance ────────────────────────────────────────────────────

    def update(self, record_id: str, **changes: Any) -> bool:
        """Update mutable fields of a record.

        Args:
            record_id: the record to update.
            **changes: fields to set (importance is clamped to [0, 1]).

        Returns:
            True when the record existed and was updated.
        """
        record = self._tiered.get(record_id)
        if record is None:
            return False
        for key, value in changes.items():
            if key == "importance":
                record.importance = max(0.0, min(1.0, float(value)))
            elif hasattr(record, key):
                setattr(record, key, value)
        return True

    def evict(self) -> int:
        """Enforce the cold-tier bound, returning records evicted this call.

        Returns:
            Number of records evicted by this call.
        """
        before = self._tiered.evicted
        self._tiered._rebalance()
        return self._tiered.evicted - before

    def summarize(self, max_records: int = 8) -> Optional[MemoryRecord]:
        """Fold the coldest records into one summary record.

        Args:
            max_records: how many cold records to compress.

        Returns:
            The summary record, or None when COLD is empty.
        """
        return self._tiered.summarize(max_records)

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        """Retrieve a record by id.

        Args:
            record_id: the record id.

        Returns:
            The record, or None.
        """
        return self._tiered.get(record_id)

    def records(self) -> List[MemoryRecord]:
        """Return all live records.

        Returns:
            List of records in tier order.
        """
        return self._tiered.all_records()

    def stats(self) -> Dict[str, Any]:
        """Return tier stats plus controller counters.

        Returns:
            Merged dict of tier sizes and insert/reject/consume counters.
        """
        stats: Dict[str, Any] = dict(self._tiered.stats())
        stats.update({
            "inserted": self.inserted,
            "rejected_governance_suppression": self.rejected_governance_suppression,
            "memory_consumed": self.memory_consumed,
        })
        return stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the store plus counters.

        Returns:
            Dict suitable for checkpointing.
        """
        data = self._tiered.to_dict()
        data["counters"] = {
            "inserted": self.inserted,
            "rejected_governance_suppression": self.rejected_governance_suppression,
            "memory_consumed": self.memory_consumed,
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryController":
        """Rebuild a controller from to_dict() output.

        Args:
            data: the serialized controller.

        Returns:
            A MemoryController.
        """
        controller = cls(TieredMemory.from_dict(data))
        counters = data.get("counters", {})
        controller.inserted = int(counters.get("inserted", 0))
        controller.rejected_governance_suppression = int(
            counters.get("rejected_governance_suppression", 0)
        )
        controller.memory_consumed = int(counters.get("memory_consumed", 0))
        return controller


__all__ = [
    "MemoryController", "MemoryRecord", "TieredMemory",
    "EPISTEMIC_KINDS", "tokenize",
]
