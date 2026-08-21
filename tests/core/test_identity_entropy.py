"""Contract tests for telos/core/attention/identity_entropy.py."""

import pytest

from telos.core.attention.identity_entropy import (
    IdentityEntropyTracker, EntropySignal,
)


def test_empty_state_returns_baseline():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=5)
    assert t.current_size == 10.0
    assert t.raw_size is None
    assert t.collapse_rate == 0.0
    assert not t.is_collapsing
    assert not t.is_critical


def test_record_maintains_rolling_window():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=5)
    for s in [10, 9, 8, 7, 6, 5, 4]:
        t.record(s)
    # window keeps last 5 recorded values: [8, 7, 6, 5, 4]
    assert t.current_size == pytest.approx(6.0)
    assert t.raw_size == 4


def test_record_window_trims_to_window_size():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=3)
    for s in [1, 2, 3, 4, 5, 6, 7, 8]:
        t.record(s)
    assert len(t._sizes) == 3


def test_cycles_since_change_tracks():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=5)
    t.record(5)
    t.record(5)
    t.record(5)
    assert t.assess().cycles_since_change == 3
    t.record(6)
    assert t.assess().cycles_since_change == 0


def test_collapsing_detection_on_shrinking_window():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=5)
    for s in [10, 9, 8, 7, 6]:
        t.record(s)
    assert t.collapse_rate < t.COLLAPSE_THRESHOLD
    assert t.is_collapsing
    assert not t.is_expanding


def test_critical_when_below_critical_fraction():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=5)
    for s in [2, 2, 2, 1, 1]:
        t.record(s)
    assert t.current_size < t.baseline * t.CRITICAL_ENTROPY_FRACTION
    assert t.is_critical


def test_assess_returns_entropy_signal():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=5)
    for s in [10, 9, 8, 7, 6]:
        t.record(s)
    sig = t.assess()
    assert isinstance(sig, EntropySignal)
    assert sig.current_entropy == t.current_size
    assert sig.is_collapsing
    assert 'WARN' in sig.recommended_action


def test_assess_critical_escalates():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=5)
    for s in [2, 2, 2, 1, 1]:
        t.record(s)
    sig = t.assess()
    assert 'ESCALATE' in sig.recommended_action


def test_project_size_requires_history():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=5)
    assert t.project_size(horizon=3) == 10.0
    t.record(6)
    t.record(5)
    projected = t.project_size(horizon=3)
    assert projected >= 1.0


def test_stats_keys():
    t = IdentityEntropyTracker(baseline_action_space=10, window_size=5)
    for s in [10, 9, 8, 7]:
        t.record(s)
    keys = set(t.stats.keys())
    assert {
        'current_size', 'raw_size', 'baseline', 'collapse_rate',
        'is_collapsing', 'is_expanding', 'is_critical',
        'cycles_since_change', 'projected_next_3', 'assessment', 'history',
    } <= keys
