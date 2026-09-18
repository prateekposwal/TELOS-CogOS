"""
TieredMemory — hot/warm/cold tiering for DECISION memory (Λ4.7, Λ1.4).

PATTERN (one memory discipline): the conversation layer already pages context
(HOT/WARM/COLD, telos/core/context/tiered.py) so a session can run forever
without unbounded growth. Decision memory had no equivalent — every store grew
to its own cap with its own eviction rule. TieredMemory gives decision records
ONE tiered structure with ONE retention rule, so "what do I retain, and why?"
has a single, measurable answer.

Tiers:
  HOT  — recently added / accessed records, full fidelity.
  WARM — demoted records, still individually searchable.
  COLD — oldest low-retention records; compressed by summarize() into summaries.

Retention is a declared function of importance and recency, so eviction is
reproducible (same inputs -> same survivors), never a dict-ordering accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_HOT_LIMIT = 16
DEFAULT_WARM_LIMIT = 48
DEFAULT_COLD_LIMIT = 256

# Retention weights: importance dominates, recency breaks ties. Exposed so the
# policy is auditable rather than buried in the eviction code.
W_IMPORTANCE = 0.7
W_RECENCY = 0.3


@dataclass
class MemoryRecord:
    """One decision-memory record (entity, skill, knowledge, experience, ...).

    Attributes:
        record_id: unique id.
        content: the searchable text.
        kind: record class (entity/skill/knowledge/experience/failure/summary).
        domain: domain tag used for filtered retrieval.
        importance: 0..1 declared importance (drives retention).
        outcome: optional observed outcome in [0, 1] (None when unobserved).
        created_cycle: cycle the record was created.
        last_accessed_cycle: cycle the record was last retrieved.
        access_count: number of retrievals.
        tier: current tier (hot/warm/cold), maintained by TieredMemory.
        provenance: audit provenance (caller/source/reason) — required for
            epistemic kinds by the controller's write gate.
        metadata: free-form extra fields.
    """

    record_id: str
    content: str
    kind: str = "experience"
    domain: str = "gridworld"
    importance: float = 0.5
    outcome: Optional[float] = None
    created_cycle: int = 0
    last_accessed_cycle: int = 0
    access_count: int = 0
    tier: str = "hot"
    provenance: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def retention_score(self, cycle: int) -> float:
        """Score this record's claim to retention at a given cycle.

        Args:
            cycle: the current cycle (monotonic).

        Returns:
            importance-weighted retention in [0, 1].
        """
        age = max(0, cycle - self.last_accessed_cycle)
        recency = 1.0 / (1.0 + age)
        return W_IMPORTANCE * self.importance + W_RECENCY * recency

    def to_dict(self) -> Dict[str, Any]:
        """Serializable form."""
        return {
            "record_id": self.record_id,
            "content": self.content,
            "kind": self.kind,
            "domain": self.domain,
            "importance": self.importance,
            "outcome": self.outcome,
            "created_cycle": self.created_cycle,
            "last_accessed_cycle": self.last_accessed_cycle,
            "access_count": self.access_count,
            "tier": self.tier,
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        """Rebuild a record from to_dict() output.

        Args:
            data: the serialized record.

        Returns:
            A MemoryRecord.
        """
        return cls(
            record_id=data["record_id"],
            content=data.get("content", ""),
            kind=data.get("kind", "experience"),
            domain=data.get("domain", "gridworld"),
            importance=float(data.get("importance", 0.5)),
            outcome=data.get("outcome"),
            created_cycle=int(data.get("created_cycle", 0)),
            last_accessed_cycle=int(data.get("last_accessed_cycle", 0)),
            access_count=int(data.get("access_count", 0)),
            tier=data.get("tier", "hot"),
            provenance=dict(data.get("provenance", {})),
            metadata=dict(data.get("metadata", {})),
        )


class TieredMemory:
    """A bounded, three-tier store of MemoryRecords with one retention rule."""

    def __init__(self, hot_limit: int = DEFAULT_HOT_LIMIT,
                 warm_limit: int = DEFAULT_WARM_LIMIT,
                 cold_limit: int = DEFAULT_COLD_LIMIT):
        """Construct an empty tiered store.

        Args:
            hot_limit: max records in HOT before demotion.
            warm_limit: max records in WARM before demotion.
            cold_limit: max records in COLD before eviction.
        """
        self.hot_limit = max(1, hot_limit)
        self.warm_limit = max(1, warm_limit)
        self.cold_limit = max(1, cold_limit)
        self.hot: List[str] = []
        self.warm: List[str] = []
        self.cold: List[str] = []
        self._index: Dict[str, MemoryRecord] = {}
        self._cycle = 0
        self.evicted = 0
        self.summarized = 0

    @property
    def cycle(self) -> int:
        """Current logical cycle (advanced on every add/access)."""
        return self._cycle

    def _tier_list(self, tier: str) -> List[str]:
        """Return the id list for a tier name.

        Args:
            tier: hot/warm/cold.

        Returns:
            The backing id list.
        """
        return {"hot": self.hot, "warm": self.warm, "cold": self.cold}[tier]

    def add(self, record: MemoryRecord) -> MemoryRecord:
        """Insert a record into HOT and rebalance.

        Args:
            record: the record to insert (its tier is set to hot).

        Returns:
            The inserted record.
        """
        self._cycle += 1
        record.tier = "hot"
        record.last_accessed_cycle = max(record.last_accessed_cycle, self._cycle)
        if record.record_id in self._index:
            self.remove(record.record_id)
        self._index[record.record_id] = record
        self.hot.append(record.record_id)
        self._rebalance()
        return record

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        """Look up a record without affecting its tier.

        Args:
            record_id: the record id.

        Returns:
            The record, or None.
        """
        return self._index.get(record_id)

    def access(self, record_id: str) -> Optional[MemoryRecord]:
        """Mark a record accessed and promote it to HOT.

        Args:
            record_id: the record id.

        Returns:
            The accessed record, or None when unknown.
        """
        record = self._index.get(record_id)
        if record is None:
            return None
        self._cycle += 1
        record.access_count += 1
        record.last_accessed_cycle = self._cycle
        for tier in ("warm", "cold"):
            ids = self._tier_list(tier)
            if record_id in ids:
                ids.remove(record_id)
                record.tier = "hot"
                self.hot.append(record_id)
                break
        self._rebalance()
        return record

    def remove(self, record_id: str) -> bool:
        """Remove a record from whichever tier holds it.

        Args:
            record_id: the record id.

        Returns:
            True when the record existed and was removed.
        """
        if record_id not in self._index:
            return False
        for tier in ("hot", "warm", "cold"):
            ids = self._tier_list(tier)
            if record_id in ids:
                ids.remove(record_id)
                break
        del self._index[record_id]
        return True

    def all_records(self) -> List[MemoryRecord]:
        """Return every live record (hot, then warm, then cold).

        Returns:
            List of records in tier order.
        """
        out: List[MemoryRecord] = []
        for tier in ("hot", "warm", "cold"):
            for rid in self._tier_list(tier):
                rec = self._index.get(rid)
                if rec is not None:
                    out.append(rec)
        return out

    def _demote_lowest(self, tier: str) -> Optional[str]:
        """Move the lowest-retention id from one tier to the next.

        Args:
            tier: the source tier (hot or warm).

        Returns:
            The demoted record id, or None when the tier is empty.
        """
        ids = self._tier_list(tier)
        if not ids:
            return None
        target = "warm" if tier == "hot" else "cold"
        worst = min(
            ids,
            key=lambda rid: (
                self._index[rid].retention_score(self._cycle),
                self._index[rid].created_cycle,
                rid,
            ),
        )
        ids.remove(worst)
        self._index[worst].tier = target
        self._tier_list(target).append(worst)
        return worst

    def evict(self) -> int:
        """Drop the lowest-retention COLD records beyond the cold limit.

        Returns:
            Number of records evicted by this call.
        """
        dropped = 0
        while len(self.cold) > self.cold_limit:
            worst = min(
                self.cold,
                key=lambda rid: (
                    self._index[rid].retention_score(self._cycle),
                    self._index[rid].created_cycle,
                    rid,
                ),
            )
            self.cold.remove(worst)
            del self._index[worst]
            self.evicted += 1
            dropped += 1
        return dropped

    def _rebalance(self) -> None:
        """Enforce tier limits by demotion + eviction."""
        while len(self.hot) > self.hot_limit:
            if self._demote_lowest("hot") is None:
                break
        while len(self.warm) > self.warm_limit:
            if self._demote_lowest("warm") is None:
                break
        self.evict()

    def summarize(self, max_records: int = 8) -> Optional[MemoryRecord]:
        """Compress the coldest COLD records into one summary record.

        Args:
            max_records: how many cold records to fold into the summary.

        Returns:
            The summary record, or None when COLD is empty.
        """
        if not self.cold:
            return None
        self.cold.sort(key=lambda rid: (
            self._index[rid].retention_score(self._cycle),
            self._index[rid].created_cycle,
            rid,
        ))
        victims = list(self.cold[:max_records])
        if not victims:
            return None
        excerpts = []
        importance = 0.0
        summary_domain = "gridworld"
        for rid in victims:
            rec = self._index[rid]
            importance = max(importance, rec.importance)
            summary_domain = rec.domain
            text = rec.content.strip().replace("\n", " ")
            excerpts.append(text[:80])
            self.cold.remove(rid)
            del self._index[rid]
        self.summarized += len(victims)
        summary = MemoryRecord(
            record_id=f"summary_{self.summarized}_{len(victims)}",
            content=" | ".join(excerpts),
            kind="summary",
            domain=summary_domain,
            importance=importance,
            created_cycle=self._cycle,
            last_accessed_cycle=self._cycle,
            provenance={"caller": "tiered_memory", "source": "summarize"},
        )
        self.warm.append(summary.record_id)
        self._index[summary.record_id] = summary
        summary.tier = "warm"
        self._rebalance()
        return summary

    def stats(self) -> Dict[str, int]:
        """Return tier sizes and lifetime counters.

        Returns:
            Dict with hot/warm/cold sizes, total, evicted, summarized.
        """
        return {
            "hot": len(self.hot),
            "warm": len(self.warm),
            "cold": len(self.cold),
            "total": len(self._index),
            "evicted": self.evicted,
            "summarized": self.summarized,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the whole store.

        Returns:
            Dict with config, cycle, counters, and all records.
        """
        return {
            "hot_limit": self.hot_limit,
            "warm_limit": self.warm_limit,
            "cold_limit": self.cold_limit,
            "cycle": self._cycle,
            "evicted": self.evicted,
            "summarized": self.summarized,
            "records": [r.to_dict() for r in self.all_records()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TieredMemory":
        """Rebuild a store from to_dict() output.

        Args:
            data: the serialized store.

        Returns:
            A TieredMemory with the saved records re-tiered.
        """
        store = cls(
            hot_limit=data.get("hot_limit", DEFAULT_HOT_LIMIT),
            warm_limit=data.get("warm_limit", DEFAULT_WARM_LIMIT),
            cold_limit=data.get("cold_limit", DEFAULT_COLD_LIMIT),
        )
        for raw in data.get("records", []):
            rec = MemoryRecord.from_dict(raw)
            store._index[rec.record_id] = rec
            store._tier_list(rec.tier if rec.tier in ("hot", "warm", "cold") else "warm").append(
                rec.record_id
            )
        store._cycle = int(data.get("cycle", 0))
        store.evicted = int(data.get("evicted", 0))
        store.summarized = int(data.get("summarized", 0))
        store._rebalance()
        return store


__all__ = [
    "MemoryRecord", "TieredMemory",
    "DEFAULT_HOT_LIMIT", "DEFAULT_WARM_LIMIT", "DEFAULT_COLD_LIMIT",
    "W_IMPORTANCE", "W_RECENCY",
]
