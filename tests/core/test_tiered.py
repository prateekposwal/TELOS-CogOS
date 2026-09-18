"""
TieredContext (core/context/tiered.py) — three-tier context compression.

Covers the HOT->WARM->COLD promotion path, serialization round-trip, pressure
math, and the `size` property (which a latent double-@property bug had turned
into a TypeError — these tests are the regression that catches it).
"""
import pytest

from telos.core.context.tiered import TieredContext


def _msg(role, content):
    return {"role": role, "content": content}


def test_size_is_an_int_dict_not_a_broken_property():
    tc = TieredContext()
    tc.add_message(_msg("user", "hi"))
    assert tc.size == {"hot": 1, "warm": 0, "cold": 0, "total_messages": 1}


def test_add_message_caps_hot_and_promotes_to_warm():
    tc = TieredContext(hot_limit=4, warm_limit=50)
    for i in range(10):
        tc.add_message(_msg("user", f"m{i}"))
    assert len(tc.hot) <= tc.hot_limit
    assert len(tc.warm) >= 1
    assert tc.size["total_messages"] == 10


def test_warm_overflow_promotes_to_cold():
    tc = TieredContext(hot_limit=2, warm_limit=3, cold_compress_count=2)
    for i in range(40):
        tc.add_message(_msg("user", f"message number {i}"))
    assert tc.cold is not None
    assert tc.cold["source_count"] >= 2
    assert "paragraph" in tc.cold and "essence" in tc.cold


def test_get_context_includes_warm_and_cold_blocks():
    tc = TieredContext(hot_limit=2, warm_limit=2, cold_compress_count=2)
    for i in range(30):
        tc.add_message(_msg("user", f"content {i}"))
    ctx = tc.get_context()
    joined = "\n".join(m["content"] for m in ctx)
    assert "TIER 2 — WARM" in joined
    assert "TIER 3 — COLD" in joined
    assert "SESSION ESSENCE" in joined


def test_token_estimate_and_pressure_bounds():
    tc = TieredContext(token_budget=4096)
    for i in range(20):
        tc.add_message(_msg("user", "x" * 50))
    assert tc.get_token_estimate() > 0
    assert 0.0 <= tc.get_pressure() <= 1.0


def test_compress_drains_hot_into_warm_and_cold():
    tc = TieredContext(hot_limit=100, warm_limit=100)
    for i in range(6):
        tc.add_message(_msg("user", f"m{i}"))
    tc.compress()
    assert tc.hot == []
    # compress() drains HOT -> WARM -> COLD, so everything ends in COLD.
    assert tc.cold is not None and tc.cold["source_count"] >= 1


def test_serialization_round_trip():
    tc = TieredContext(hot_limit=3, warm_limit=2, cold_compress_count=2)
    for i in range(15):
        tc.add_message(_msg("assistant", f"reply {i}"))
    data = tc.to_dict()
    restored = TieredContext.from_dict(data)
    assert restored.hot_limit == tc.hot_limit
    assert restored.size["total_messages"] == tc.size["total_messages"]
    assert restored.get_context() is not None


def test_from_chat_history_distributes_messages():
    history = [_msg("user", f"turn {i}") for i in range(12)]
    tc = TieredContext.from_chat_history(history, hot_limit=4, warm_limit=50)
    assert tc.size["total_messages"] == 12
    assert len(tc.hot) <= tc.hot_limit


def test_merge_cold_combines_paragraphs_and_source_counts():
    tc = TieredContext()
    tc._merge_cold({"paragraph": "First.", "essence": {}, "source_count": 2})
    tc._merge_cold({"paragraph": "Second.", "essence": {}, "source_count": 3})
    assert tc.cold["source_count"] == 5
    assert "First" in tc.cold["paragraph"] and "Second" in tc.cold["paragraph"]


def test_extract_keywords_and_pair_compression():
    kw = TieredContext._extract_keywords("alpha alpha beta gamma delta epsilon", max_items=2)
    assert kw[0] == "alpha"
    tc = TieredContext()
    summary = tc._compress_pair_to_sentence([_msg("user", "hello there"), _msg("assistant", "hi")])
    assert summary["role"] == "system"
    assert "hello there" in summary["content"]


def test_constructor_clamps_limits():
    tc = TieredContext(hot_limit=0, warm_limit=0, cold_compress_count=0, token_budget=1)
    assert tc.hot_limit >= 2 and tc.warm_limit >= 2
    assert tc.cold_compress_count >= 1 and tc.token_budget >= 256
