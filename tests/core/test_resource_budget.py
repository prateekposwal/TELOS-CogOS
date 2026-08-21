"""Contract tests for telos/core/attention/resource_budget.py."""

import pytest

from telos.core.attention.resource_budget import (
    ResourceBudgetTracker, AttentionBid, run_attention_auction,
)


def test_resource_budget_record_updates_snapshot():
    r = ResourceBudgetTracker()
    r.record(100.0, 3, 0.2, 0)
    r.record(50.0, 5, 0.4, 1)
    assert r.energy_budget_ms == 50.0
    assert r.memory_trace_length == 5
    assert r.identity_entropy == 0.4
    assert r.recovery_cycles == 1


def test_resource_budget_stats():
    r = ResourceBudgetTracker()
    r.record(100.0, 3, 0.2, 0)
    r.record(50.0, 5, 0.4, 1)
    stats = r.stats
    assert stats['energy_budget_ms'] == 50.0
    assert stats['memory_trace_length'] == 5
    assert stats['identity_entropy'] == 0.4
    assert stats['recovery_cycles'] == 1
    assert stats['history_length'] == 2


def test_resource_budget_to_dict_equals_stats():
    r = ResourceBudgetTracker()
    r.record(10.0, 1, 0.0, 2)
    assert r.to_dict() == r.stats


def test_resource_budget_history_bounded():
    r = ResourceBudgetTracker()
    r._max_history = 3
    for i in range(10):
        r.record(float(i), i, 0.0, 0)
    assert len(r._history) == 3
    assert r.stats['history_length'] == 3


def test_attention_bid_effective_bid():
    b = AttentionBid(stream_name='reflex', bid_amount_ms=10.0,
                     priority_multiplier=2.0)
    assert b.effective_bid == 20.0


def test_auction_empty_returns_empty():
    assert run_attention_auction([], 100.0) == {}


def test_auction_pays_single_price_lowest_winning():
    result = run_attention_auction([
        AttentionBid('a', 10.0, 1.0),
        AttentionBid('b', 20.0, 2.0),
    ], 100.0)
    # both win, both capped at lowest winning (10.0)
    assert result == {'a': 10.0, 'b': 10.0}


def test_auction_budget_constrained_drops_loser():
    result = run_attention_auction([
        AttentionBid('a', 10.0, 1.0),
        AttentionBid('b', 8.0, 1.0),
    ], 10.0)
    assert result == {'a': 10.0, 'b': 0.0}


def test_auction_scarce_budget():
    result = run_attention_auction([
        AttentionBid('a', 10.0, 1.0),
        AttentionBid('b', 20.0, 2.0),
    ], 4.0)
    assert result == {'b': 4.0, 'a': 0.0}
