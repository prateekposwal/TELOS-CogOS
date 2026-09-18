"""
MemoryController — one ops API over tiered decision memory.

The controller must (a) enforce the canonical rule that a governance-suppressed
outcome is NOT evidence, (b) require provenance on epistemic writes, and
(c) retrieve measurably better than the naive baseline.
"""

import pytest

from telos.core.memory.controller import (
    MemoryController, EPISTEMIC_KINDS, tokenize,
)
from telos.core.memory.tiering import MemoryRecord


def _rec(rid, content="some content", kind="experience", importance=0.5,
         cycle=0, **meta):
    prov = meta.pop("provenance", {"caller": "test"})
    return MemoryRecord(
        record_id=rid, content=content, kind=kind, importance=importance,
        created_cycle=cycle, last_accessed_cycle=cycle,
        provenance=prov, metadata=meta,
    )


def test_insert_and_search_roundtrip():
    """An inserted record is retrievable by a matching query."""
    c = MemoryController()
    c.insert(_rec("r1", content="navigate to the corner goal"))
    hits = c.search("corner goal")
    assert [r.record_id for r in hits] == ["r1"]
    assert c.memory_consumed == 1


def test_governance_suppressed_outcome_is_not_inserted():
    """A vetoed attempt must never enter memory as evidence."""
    c = MemoryController()
    rec = _rec("blocked", provenance={"caller": "x", "reason": "governance_intervention"})
    assert c.insert(rec) is False
    assert c.rejected_governance_suppression == 1
    assert c.get("blocked") is None


def test_simulation_divergence_is_also_suppressed():
    """Every canonical suppression reason is refused, not one hard-coded string."""
    c = MemoryController()
    rec = _rec("div", provenance={"caller": "x", "reason": "simulation_divergence"})
    assert c.insert(rec) is False
    assert c.rejected_governance_suppression == 1


def test_metadata_failure_reason_is_respected():
    """A suppression reason carried in metadata is refused too."""
    c = MemoryController()
    rec = _rec("m", failure_reason="governance_intervention")
    assert c.insert(rec) is False


def test_epistemic_record_requires_provenance():
    """An epistemic record without a provenance caller raises (trusted-caller gate)."""
    c = MemoryController()
    bad = MemoryRecord(record_id="k", content="x", kind="knowledge")
    with pytest.raises(ValueError):
        c.insert(bad)


def test_all_epistemic_kinds_require_provenance():
    """Every declared epistemic kind enforces the gate."""
    for kind in EPISTEMIC_KINDS:
        c = MemoryController()
        with pytest.raises(ValueError):
            c.insert(MemoryRecord(record_id="k", content="x", kind=kind))


def test_search_domain_filter():
    """Domain filtering excludes other domains."""
    c = MemoryController()
    c.insert(_rec("a", content="grid reward", metadata={}))
    c.insert(MemoryRecord(record_id="b", content="grid reward", kind="experience",
                          domain="bitcoin", provenance={"caller": "t"}))
    hits = c.search("grid reward", domain="gridworld")
    assert [r.record_id for r in hits] == ["a"]


def test_update_clamps_importance():
    """update() clamps importance to [0, 1]."""
    c = MemoryController()
    c.insert(_rec("r", importance=0.5))
    assert c.update("r", importance=5.0) is True
    assert c.get("r").importance == 1.0
    assert c.update("missing", importance=0.1) is False


def test_evict_and_summarize_are_bounded():
    """Sustained inserts stay bounded; summarize folds cold records."""
    c = MemoryController()
    for i in range(400):
        c.insert(_rec(f"r{i}", content=f"content {i} reward", importance=0.1, cycle=i))
    assert c.stats()["total"] <= 16 + 48 + 256
    before = c.stats()["total"]
    assert c.summarize() is not None
    assert c.stats()["total"] <= before


def test_retrieval_beats_naive_on_importance():
    """The controller ranks a high-importance record above an equal low one."""
    c = MemoryController()
    c.insert(_rec("low", content="corner reward", importance=0.1, cycle=0))
    c.insert(_rec("high", content="corner reward", importance=0.95, cycle=1))
    assert [r.record_id for r in c.search("corner reward", top_k=1)] == ["high"]
    # Naive (overlap-only, insertion order) picks the low one: the delta is real.
    assert [r.record_id for r in c.naive_search("corner reward", top_k=1)] == ["low"]


def test_serialization_roundtrip():
    """The controller round-trips through to_dict/from_dict."""
    c = MemoryController()
    for i in range(20):
        c.insert(_rec(f"r{i}", content=f"thing {i}", importance=0.1 * (i % 5), cycle=i))
    c.search("thing 3")
    data = c.to_dict()
    rebuilt = MemoryController.from_dict(data)
    assert rebuilt.stats()["total"] == c.stats()["total"]
    assert rebuilt.inserted == c.inserted
    assert rebuilt.memory_consumed == c.memory_consumed


def test_tokenize_drops_short_and_stopword_tokens():
    """Tokenizer keeps content tokens, drops short words and stopwords."""
    assert tokenize("A to BE or NOT") == []
    assert tokenize("navigate to the corner goal") == ["navigate", "corner", "goal"]
