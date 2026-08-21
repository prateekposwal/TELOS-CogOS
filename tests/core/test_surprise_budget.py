"""Contract tests for telos/core/attention/surprise_budget.py."""

import pytest

from telos.core.attention.surprise_budget import (
    SurpriseBudget, SurpriseSignal, BudgetAllocation,
)


def test_surprise_signal_ratio():
    s = SurpriseSignal(1, 0.5, 'x', prediction_error=10.0,
                       expected_error=2.0, novelty=0.1)
    assert s.surprise_ratio == 5.0


def test_surprise_signal_ratio_zero_expected():
    s = SurpriseSignal(1, 0.5, 'x', prediction_error=5.0,
                       expected_error=0.0, novelty=0.0)
    assert s.surprise_ratio == 1.0


def test_surprise_signal_ratio_zero_both():
    s = SurpriseSignal(1, 0.5, 'x', prediction_error=0.0,
                       expected_error=0.0, novelty=0.0)
    assert s.surprise_ratio == 0.0


def test_initial_state():
    sb = SurpriseBudget(base_budget_ms=1000.0, surprise_gain=2.0,
                        decay_half_life=10)
    assert sb.surprise_level == 0.0
    assert sb.predictability == 0.5
    assert sb.get_surprise_trend() == "insufficient_data"


def test_record_incorrect_prediction_raises_surprise():
    sb = SurpriseBudget(base_budget_ms=1000.0, surprise_gain=2.0,
                        decay_half_life=10)
    sig = sb.record_prediction(correct=False, channel='perceive',
                               error=10.0, expected_error=1.0)
    assert 0.0 < sig.surprise_level <= 1.0
    assert sig.source == 'perceive'
    assert sig.cycle == 0
    assert sb.predictability == 0.0


def test_surprise_signal_decays_toward_recent():
    sb = SurpriseBudget(base_budget_ms=1000.0, surprise_gain=2.0,
                        decay_half_life=10)
    sb.record_prediction(False, 'perceive', 10.0, 1.0)
    s2 = sb.record_prediction(False, 'perceive', 10.0, 1.0)
    assert s2.cycle == 1
    assert sb.surprise_level > 0.0


def test_compute_information_gain_bounded():
    sb = SurpriseBudget()
    ig = sb.compute_information_gain(error=10.0, expected=1.0, novelty=1.0)
    assert 0.0 <= ig <= 1.0


def test_compute_budget_scales_with_surprise():
    sb = SurpriseBudget(base_budget_ms=1000.0, surprise_gain=2.0)
    before = sb.compute_budget(cycle=0)
    sb.record_prediction(False, 'simulate', 20.0, 2.0)
    after = sb.compute_budget(cycle=1)
    assert after.surprise_level > 0.0
    assert after.total_budget_ms > before.total_budget_ms


def test_compute_budget_phases_sum_to_total():
    sb = SurpriseBudget(base_budget_ms=1000.0, surprise_gain=2.0)
    sb.record_prediction(False, 'simulate', 20.0, 2.0)
    alloc = sb.compute_budget(cycle=7)
    assert isinstance(alloc, BudgetAllocation)
    assert abs(sum(alloc.phase_allocations.values())
               - alloc.total_budget_ms) < 1e-6
    assert alloc.cycle == 7


def test_get_surprising_channels_sorted():
    sb = SurpriseBudget(base_budget_ms=1000.0, surprise_gain=2.0)
    sb.record_prediction(False, 'simulate', 20.0, 2.0)
    sb.record_prediction(False, 'perceive', 20.0, 2.0)
    channels = sb.get_surprising_channels(threshold=0.3)
    assert len(channels) == 2
    assert channels[0][1] >= channels[1][1]


def test_reset_clears_signal():
    sb = SurpriseBudget(base_budget_ms=1000.0, surprise_gain=2.0)
    sb.record_prediction(False, 'simulate', 20.0, 2.0)
    sb.reset()
    assert sb.surprise_level == 0.0
    assert sb._channel_surprise == {}
    assert sb.predictability == 0.5


def test_predictability_fraction():
    sb = SurpriseBudget()
    sb.record_prediction(True, 'default')
    sb.record_prediction(True, 'default')
    sb.record_prediction(False, 'default')
    assert sb.predictability == pytest.approx(2 / 3)


def test_to_dict_keys():
    sb = SurpriseBudget()
    sb.record_prediction(False, 'simulate', 20.0, 2.0)
    d = sb.to_dict()
    for k in ['surprise_level', 'predictability', 'base_budget_ms',
              'surprise_gain', 'decay_rate', 'surprise_trend',
              'surprising_channels', 'channel_surprise',
              'total_predictions', 'correct_predictions', 'accuracy',
              'recent_allocations']:
        assert k in d
