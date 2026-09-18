"""
Embedding backend — real learned embeddings with a deterministic offline fallback.

The lexicon could not match unseen vocabulary by construction. These tests lock
that embeddings close the gap AND that retrieval still works when no embedding
model is reachable (the pipeline must run headless).
"""

import numpy as np

from telos.core.memory.controller import MemoryController
from telos.core.memory.embedding import (
    EmbeddingBackend, cosine_dense, DEFAULT_MODEL,
)
from telos.core.memory.tiering import MemoryRecord


def _add(c, rid, content, importance=0.5, domain="gridworld"):
    c.insert(MemoryRecord(record_id=rid, content=content, kind="experience",
                          domain=domain, importance=importance,
                          provenance={"caller": "test"}))


def test_backend_probe_reports_availability():
    """The backend reports availability truthfully (no exception either way)."""
    b = EmbeddingBackend()
    assert isinstance(b.available, bool)


def test_disabled_backend_is_unavailable():
    """An explicitly disabled backend never probes or returns vectors."""
    b = EmbeddingBackend(enabled=False)
    assert b.available is False
    assert b.embed_many(["x"]) is None


def test_unreachable_backend_returns_none():
    """A backend pointed at a dead port returns None rather than raising."""
    b = EmbeddingBackend(port=9, timeout=0.5)
    assert b.embed_many(["hello"]) is None


def test_cosine_dense_bounds():
    """Dense cosine is 1.0 for identical, 0.0 for degenerate/mismatched."""
    v = [0.1, 0.2, 0.3]
    assert abs(cosine_dense(v, v) - 1.0) < 1e-9
    assert cosine_dense([], v) == 0.0
    assert cosine_dense(v, [0.0, 0.0, 0.0]) == 0.0
    assert cosine_dense(v, [1.0]) == 0.0


def test_embeddings_resolve_unseen_vocabulary():
    """A query with no lexicon entry still finds the semantically close record.

    This is the specific capability embeddings add: the curated lexicon has no
    entry for these words, so the lexical path is blind to the match.
    """
    b = EmbeddingBackend()
    if not b.available:
        return  # offline: the fallback tests below cover this path
    target = "quixotic tesselation discrepancy in the frobnicator"
    unrelated = "hashrate climbed across the mining network"
    c = MemoryController()
    _add(c, "target", target, importance=0.9)
    _add(c, "other", unrelated, importance=0.5)
    hits = c.semantic_search("inexplicable frobnicator anomaly", top_k=2)
    assert hits, "embedding retrieval returned nothing"
    assert hits[0].record_id == "target"


def test_lexical_fallback_when_embeddings_unavailable(monkeypatch):
    """With embeddings forced unavailable, the lexical layer still retrieves."""
    from telos.core.memory import controller as controller_mod
    monkeypatch.setattr(controller_mod, "shared_backend",
                        lambda: EmbeddingBackend(enabled=False))
    c = controller_mod.MemoryController()
    _add(c, "t", "hazard near obstacle blocked the path", importance=0.9)
    hits = c.semantic_search("avoid the wall", top_k=3)
    assert [h.record_id for h in hits] == ["t"]
    assert c._backend_used == "lexical"


def test_backend_choice_is_recorded():
    """The controller records which backend served the index."""
    c = MemoryController()
    _add(c, "t", "hazard near obstacle blocked the path", importance=0.9)
    c.semantic_search("avoid the wall", top_k=1)
    assert c._backend_used in ("embedding", "lexical")


def test_embedding_results_are_cached():
    """Repeated embedding of the same text does not re-request it."""
    b = EmbeddingBackend()
    if not b.available:
        return
    first = b.embed("a stable cached sentence")
    assert first is not None
    key = b._key("a stable cached sentence")
    assert key in b._cache
    second = b.embed("a stable cached sentence")
    assert second == first


def test_default_model_constant_is_set():
    """The default embedding model is named (local, overridable by env)."""
    assert DEFAULT_MODEL
