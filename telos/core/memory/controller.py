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

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional

from telos.core.governance.recovery_types import GOVERNANCE_SUPPRESSION_REASONS
from telos.core.memory.embedding import shared_backend, cosine_dense
from telos.core.memory.semantic import (
    normalize, term_frequencies, inverse_document_frequencies, cosine,
)
from telos.core.memory.tiering import (
    MemoryRecord, TieredMemory,
    DEFAULT_HOT_LIMIT, DEFAULT_WARM_LIMIT, DEFAULT_COLD_LIMIT,
)

# Record kinds that make an epistemic claim and therefore require a provenance
# caller before they may enter decision memory.
EPISTEMIC_KINDS = frozenset({"knowledge", "approach_failure", "evidence", "failure"})

_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    """Lowercase word/number tokens of length >= 2, minus stopwords.

    Stopwords are filtered here too (not only in the semantic layer): a shared
    "the"/"at" should never be what makes a lexical match, or every record
    looks relevant to every query.

    Args:
        text: the text to tokenize.

    Returns:
        List of content tokens.
    """
    from telos.core.memory.semantic import STOPWORDS
    return [t for t in _WORD_RE.findall((text or "").lower())
            if len(t) >= 2 and t not in STOPWORDS]


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

    def __init__(self, tiered: Optional[TieredMemory] = None,
                 memory_path: Optional[str] = None):
        """Construct a controller over a (possibly injected) tiered store.

        Args:
            tiered: the backing TieredMemory; a default one is created if None.
            memory_path: optional JSON path; when set, an existing store is
                loaded and save() persists to it (None = in-memory only).
        """
        self._tiered = tiered or TieredMemory(
            hot_limit=DEFAULT_HOT_LIMIT,
            warm_limit=DEFAULT_WARM_LIMIT,
            cold_limit=DEFAULT_COLD_LIMIT,
        )
        self.memory_path = memory_path
        self.inserted = 0
        self.rejected_governance_suppression = 0
        self.memory_consumed = 0
        # Semantic retrieval index (lazily rebuilt when the record set changes).
        self._idf: Dict[str, float] = {}
        self._vectors: Dict[str, Dict[str, float]] = {}
        self._embedding_vectors: Dict[str, List[float]] = {}
        self._backend_used: str = "lexical"
        self._index_size = -1
        if memory_path and os.path.isfile(memory_path):
            self._load(memory_path)

    def _load(self, path: str) -> None:
        """Load a serialized controller from disk (best-effort).

        Args:
            path: the JSON file to load.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            restored = MemoryController.from_dict(data)
            self._tiered = restored._tiered
            self.inserted = restored.inserted
            self.rejected_governance_suppression = restored.rejected_governance_suppression
            self.memory_consumed = restored.memory_consumed
        except (OSError, ValueError, TypeError, KeyError):
            # A corrupt store must not crash the pipeline; start fresh and let
            # the next save overwrite it (Λ2.3: recorded by the caller's logger).
            pass

    def save(self, path: Optional[str] = None) -> bool:
        """Persist the store to memory_path (atomic temp + replace).

        Args:
            path: optional override of self.memory_path.

        Returns:
            True when the store was written.
        """
        target = path or self.memory_path
        if not target:
            return False
        try:
            import tempfile
            d = os.path.dirname(target) or "."
            os.makedirs(d, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".telos_mem_", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.to_dict(), f)
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            return True
        except OSError:
            return False

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
    def record_outcome(self, *, cycle: int, intent_type: str, outcome_success: bool,
                       governance_blocked: bool, approach: str = "",
                       domain: str = "gridworld") -> bool:
        """Record one cycle's decision outcome as a memory record.

        The canonical rule is enforced here: a governance-suppressed cycle is
        NOT evidence, so it is refused and counted rather than stored. Only a
        genuinely tested outcome (an action that ran, or a no-action that was
        clearly attributable) enters memory.

        Args:
            cycle: the cycle number.
            intent_type: the selected intent type.
            outcome_success: whether the cycle's action succeeded.
            governance_blocked: whether council/firewall/governor suppressed it.
            approach: optional approach label (defaults to intent_type).
            domain: domain tag for the record.

        Returns:
            True when the outcome was recorded.
        """
        if governance_blocked:
            self.rejected_governance_suppression += 1
            return False
        label = approach or intent_type
        record = MemoryRecord(
            record_id=f"outcome_{cycle}_{intent_type}",
            content=f"{label} outcome {'success' if outcome_success else 'failure'} "
                    f"at cycle {cycle}",
            kind="experience",
            domain=domain,
            importance=0.8 if outcome_success else 0.4,
            outcome=1.0 if outcome_success else 0.0,
            created_cycle=cycle,
            last_accessed_cycle=cycle,
            provenance={"caller": "runtime_outcome", "cycle": cycle},
            metadata={"intent_type": intent_type, "success": outcome_success},
        )
        return self.insert(record)

    def _rebuild_semantic_index(self, embedding: bool = False) -> None:
        """Rebuild the retrieval index over the live records.

        Two interchangeable backends (Λ6.7, one retrieval surface):
          - LEXICAL (always available, deterministic, offline): concept-
            normalized IDF-weighted vectors;
          - EMBEDDING (when a local model is reachable): real learned vectors
            for the record contents, so UNSEEN vocabulary still matches.

        Args:
            embedding: when True, attempt the embedding index (falls back to
                lexical silently if embeddings are unavailable).
        """
        records = self._tiered.all_records()
        self._index_size = len(records)
        self._embedding_vectors = {}
        self._backend_used = "lexical"
        if embedding and records:
            backend = shared_backend()
            vectors = backend.embed_many([r.content for r in records])
            if vectors is not None:
                for record, vec in zip(records, vectors):
                    self._embedding_vectors[record.record_id] = vec
                self._backend_used = "embedding"
                return
        token_docs = [normalize(r.content) for r in records]
        self._idf = inverse_document_frequencies(token_docs) if token_docs else {}
        self._vectors: Dict[str, Dict[str, float]] = {}
        for record, tokens in zip(records, token_docs):
            tf = term_frequencies(tokens)
            self._vectors[record.record_id] = {
                t: w * self._idf.get(t, 1.0) for t, w in tf.items()
            }

    def _ensure_semantic_index(self) -> None:
        """Rebuild the index when the record set changed since last use."""
        if self._index_size != len(self._tiered.all_records()):
            self._rebuild_semantic_index(embedding=True)

    def semantic_search(self, query: str, top_k: int = 5,
                        domain: Optional[str] = None
                        ) -> List[MemoryRecord]:
        """Rank records by semantic similarity; promote the hits.

        Prefers the EMBEDDING backend (real learned vectors, so unseen
        vocabulary matches) and falls back to the LEXICAL concept layer when no
        local model is available. Both are deterministic for a fixed corpus.

        Args:
            query: natural-language query.
            top_k: maximum number of records to return.
            domain: optional domain filter.

        Returns:
            Ranked list of the top-k matching records.
        """
        self._ensure_semantic_index()
        records = self._tiered.all_records()
        scored = []
        if self._backend_used == "embedding" and self._embedding_vectors:
            q_vec = shared_backend().embed(query)
            if q_vec is not None:
                for record in records:
                    if domain and record.domain != domain:
                        continue
                    vec = self._embedding_vectors.get(record.record_id)
                    if not vec:
                        continue
                    sim = cosine_dense(q_vec, vec)
                    if sim <= 0.0:
                        continue
                    score = sim * (0.6 + 0.4 * record.importance)
                    scored.append((score, record))
        if not scored:
            q_tf = term_frequencies(normalize(query))
            q_vec = {t: w * self._idf.get(t, 1.0) for t, w in q_tf.items()}
            for record in records:
                if domain and record.domain != domain:
                    continue
                sim = cosine(q_vec, self._vectors.get(record.record_id, {}))
                if sim <= 0.0:
                    continue
                score = sim * (0.6 + 0.4 * record.importance)
                scored.append((score, record))
        scored.sort(key=lambda item: (
            -item[0], -item[1].importance, item[1].created_cycle, item[1].record_id,
        ))
        hits = [record for _score, record in scored[:max(0, top_k)]]
        for record in hits:
            self._tiered.access(record.record_id)
        self.memory_consumed += len(hits)
        return hits

    def search(self, query: str, top_k: int = 5,
               domain: Optional[str] = None) -> List[MemoryRecord]:
        """Rank records semantically, falling back to literal overlap.

        The primary path is semantic_search (concept-normalized cosine); the
        lexical fallback preserves behavior for callers passing already-exact
        tokens and guarantees a non-empty result if the semantic index is empty.

        Args:
            query: natural-language query.
            top_k: maximum number of records to return.
            domain: optional domain filter.

        Returns:
            Ranked list of the top-k matching records.
        """
        hits = self.semantic_search(query, top_k=top_k, domain=domain)
        if hits:
            return hits
        return self.lexical_search(query, top_k=top_k, domain=domain)

    def lexical_search(self, query: str, top_k: int = 5,
                       domain: Optional[str] = None) -> List[MemoryRecord]:
        """Rank records by literal token overlap x importance; promote the hits.

        This is the pre-semantic retrieval rule, kept as a first-class method so
        it remains measurable — the semantic layer must beat it.

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
