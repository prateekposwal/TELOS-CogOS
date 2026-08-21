"""Honest contract tests for telos/core/research/discovery_rate.py."""

import pytest

from telos.core.research.discovery_rate import DiscoveryRateTracker


def test_empty_tracker_rate_zero():
    t = DiscoveryRateTracker()
    assert t.marginal_rate == 0.0
    assert t.is_discovering is False


def test_record_computes_rate_and_cumulative():
    t = DiscoveryRateTracker()
    t.record(1, new_insights=5, effort=1.0)
    assert t._records[0].rate == 5.0
    assert t._records[0].cumulative == 0
    t.record(2, new_insights=3, effort=1.0)
    assert t._records[1].cumulative == 5
    assert t._cumulative_insights == 8


def test_rate_uses_min_effort_guard():
    t = DiscoveryRateTracker()
    t.record(1, new_insights=10, effort=0.0)
    assert t._records[0].rate == pytest.approx(10.0 / 0.01)


def test_marginal_rate_averages_recent_five():
    t = DiscoveryRateTracker()
    for i in range(6):
        t.record(i, new_insights=2, effort=1.0)
    assert t.marginal_rate == 2.0


def test_is_discovering_threshold():
    t = DiscoveryRateTracker()
    t.record(1, new_insights=0.1, effort=10.0)  # rate 0.01 -> not discovering
    assert t.is_discovering is False
    t.record(2, new_insights=5, effort=1.0)  # marginal 2.505
    assert t.is_discovering is True


def test_window_trims_records():
    t = DiscoveryRateTracker(window=3)
    for i in range(6):
        t.record(i, new_insights=1, effort=1.0)
    assert len(t._records) == 3
    assert t._cumulative_insights == 6


def test_marginal_rate_uses_last_records_in_window():
    t = DiscoveryRateTracker(window=3)
    t.record(1, new_insights=1, effort=1.0)
    t.record(2, new_insights=1, effort=1.0)
    t.record(3, new_insights=1, effort=1.0)
    t.record(4, new_insights=10, effort=1.0)
    # only last 3 records (rates 1,1,10) averaged
    assert t.marginal_rate == pytest.approx((1 + 1 + 10) / 3)


def test_to_dict_is_property_with_fields():
    t = DiscoveryRateTracker()
    t.record(1, new_insights=5, effort=1.0)
    d = t.to_dict
    assert d["marginal_rate"] == pytest.approx(5.0, abs=1e-3)
    assert d["is_discovering"] is True
    assert d["total"] == 5
    assert d["records"] == 1
