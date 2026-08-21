"""Contract tests for OmegaThresholdLearner — the self-tuning Ω threshold.

Uses Beta(α, β) statistics per 0.1-width omega bucket to dynamically adjust
the threshold at which the Ω operator triggers inquiry mode: lowers when
inquiries improve DI, raises when they lead to blocked cycles. Persists via
to_dict/from_dict (checkpoint roundtrip).
"""
import pytest

from telos.core.decision.omega_threshold import OmegaThresholdLearner


def test_priors_seeded_for_all_buckets():
    t = OmegaThresholdLearner()
    assert len(t.buckets) == 11


def test_low_omega_priors_favor_success():
    t = OmegaThresholdLearner()
    low = t.buckets["0.0"]
    assert low["alpha"] > low["beta"]  # low omega improves DI


def test_high_omega_priors_favor_block():
    t = OmegaThresholdLearner()
    high = t.buckets["0.9"]
    assert high["beta"] > high["alpha"]  # high omega wastes compute


def test_record_outcome_updates_bucket():
    t = OmegaThresholdLearner()
    before = t.buckets["0.4"]["alpha"]
    t.record_outcome(0.42, di_improved=True, was_blocked=False)
    assert t.buckets["0.4"]["alpha"] == before + 1


def test_record_blocked_increments_beta():
    t = OmegaThresholdLearner()
    before = t.buckets["0.5"]["beta"]
    t.record_outcome(0.52, di_improved=True, was_blocked=True)
    assert t.buckets["0.5"]["beta"] == before + 1


def test_threshold_stays_in_bounds():
    t = OmegaThresholdLearner()
    for i in range(200):
        t.record_outcome((i % 11) * 0.1 + 0.01,
                         di_improved=(i % 2 == 0), was_blocked=False)
    thr = t.get_threshold()
    assert 0.1 <= thr <= 0.9


def test_difficulty_history_capped_at_20():
    t = OmegaThresholdLearner()
    for i in range(50):
        t.compute_decision_difficulty(0.5, worlds_simulated=i, council_blocks=0)
    assert len(t._difficulty_history) == 20


def test_state_roundtrip_via_checkpoint_dict():
    t = OmegaThresholdLearner()
    t.record_outcome(0.7, di_improved=False, was_blocked=True)
    t.compute_decision_difficulty(0.2, worlds_simulated=10, council_blocks=3)
    restored = OmegaThresholdLearner.from_dict(t.to_dict())
    assert restored.buckets == t.buckets
    assert restored.decision_difficulty == t.decision_difficulty
    assert restored.to_dict()["default_threshold"] == t.default_threshold