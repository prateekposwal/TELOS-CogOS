"""
TieredMemory — hot/warm/cold decision memory with one retention rule.

The tiering must be bounded, deterministic, and actually demote/evict/summarize
rather than silently growing (the unbounded-retention leak class).
"""

from telos.core.memory.tiering import (
    MemoryRecord, TieredMemory, W_IMPORTANCE, W_RECENCY,
)


def _rec(rid, importance=0.5, cycle=0, content=None, domain="gridworld", kind="experience"):
    return MemoryRecord(
        record_id=rid,
        content=content or f"record {rid}",
        kind=kind,
        domain=domain,
        importance=importance,
        created_cycle=cycle,
        last_accessed_cycle=cycle,
        provenance={"caller": "test"},
    )


def test_add_and_get_roundtrip():
    """A record added to HOT is retrievable by id."""
    store = TieredMemory(hot_limit=4, warm_limit=8, cold_limit=16)
    store.add(_rec("a"))
    assert store.get("a") is not None
    assert store.get("a").tier == "hot"


def test_hot_overflow_demotes_to_warm():
    """Exceeding hot_limit demotes the lowest-retention record to WARM."""
    store = TieredMemory(hot_limit=3, warm_limit=8, cold_limit=16)
    for i in range(5):
        store.add(_rec(f"r{i}", importance=0.1 * i, cycle=i))
    assert len(store.hot) == 3
    assert len(store.warm) == 2


def test_warm_overflow_demotes_to_cold():
    """Exceeding warm_limit pushes records to COLD."""
    store = TieredMemory(hot_limit=2, warm_limit=3, cold_limit=20)
    for i in range(10):
        store.add(_rec(f"r{i}", importance=0.1, cycle=i))
    assert len(store.warm) <= 3
    assert len(store.cold) >= 1


def test_cold_overflow_evicts_and_counts():
    """Exceeding cold_limit evicts lowest-retention records and counts them."""
    store = TieredMemory(hot_limit=2, warm_limit=3, cold_limit=4)
    for i in range(30):
        store.add(_rec(f"r{i}", importance=0.1, cycle=i))
    assert len(store.cold) <= 4
    assert store.evicted > 0
    assert store.stats()["total"] <= 2 + 3 + 4


def test_retention_prioritizes_importance():
    """A high-importance record outlives a trivial one under real pressure."""
    store = TieredMemory(hot_limit=1, warm_limit=1, cold_limit=1)
    store.add(_rec("important", importance=1.0, cycle=0))
    store.add(_rec("trivial", importance=0.0, cycle=0))
    # Push well past the 1+1+1 capacity so eviction must choose a victim.
    for i in range(20):
        store.add(_rec(f"filler{i}", importance=0.5, cycle=i + 1))
    assert store.get("trivial") is None
    assert store.get("important") is not None


def test_retention_score_is_weighted():
    """retention_score equals the declared importance/recency weighting."""
    rec = _rec("x", importance=1.0, cycle=0)
    rec.last_accessed_cycle = 0
    assert abs(rec.retention_score(0) - (W_IMPORTANCE + W_RECENCY)) < 1e-9


def test_access_promotes_to_hot():
    """Accessing a cold record promotes it back to HOT."""
    store = TieredMemory(hot_limit=1, warm_limit=1, cold_limit=10)
    for i in range(6):
        store.add(_rec(f"r{i}", importance=0.1, cycle=i))
    cold_ids = list(store.cold)
    assert cold_ids
    target = cold_ids[0]
    store.access(target)
    assert store.get(target).tier == "hot"
    assert target in store.hot


def test_summarize_folds_cold_records():
    """summarize() replaces a batch of cold records with one summary."""
    store = TieredMemory(hot_limit=1, warm_limit=2, cold_limit=20)
    for i in range(10):
        store.add(_rec(f"r{i}", importance=0.1, cycle=i))
    before = store.stats()["total"]
    summary = store.summarize(max_records=3)
    assert summary is not None
    assert summary.kind == "summary"
    assert store.stats()["total"] < before
    assert store.summarized >= 3


def test_serialization_roundtrip():
    """to_dict/from_dict preserves records, tiers, and counters."""
    store = TieredMemory(hot_limit=2, warm_limit=3, cold_limit=20)
    for i in range(8):
        store.add(_rec(f"r{i}", importance=0.1 * i, cycle=i))
    store.access("r0")
    data = store.to_dict()
    rebuilt = TieredMemory.from_dict(data)
    assert rebuilt.stats()["total"] == store.stats()["total"]
    assert rebuilt.get("r0") is not None
    assert rebuilt.evicted == store.evicted


def test_remove_returns_false_for_unknown():
    """Removing an unknown id is a no-op, not an error."""
    store = TieredMemory()
    assert store.remove("nope") is False


def test_bounded_under_sustained_growth():
    """10k inserts leave the store bounded at hot+warm+cold."""
    store = TieredMemory(hot_limit=16, warm_limit=48, cold_limit=64)
    for i in range(10_000):
        store.add(_rec(f"r{i}", importance=(i % 7) / 7.0, cycle=i))
    total = store.stats()["total"]
    assert total <= 16 + 48 + 64
