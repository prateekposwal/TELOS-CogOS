"""
Decision Calibration tests — CalibrationTracker + CalibrationValidator.

Covers the System One borrow: honest confidence measured against realized
outcomes (Brier / ECE / reliability curve / recalibration), the validator's
advisory vs. enforce modes, and pipeline wiring (tracker records one pair per
cycle and surfaces the snapshot on the trace).
"""

import math

import numpy as np
import pytest

from telos.core.calibration import CalibrationTracker
from telos.core.calibration.tracker import CalibrationStats
from telos.core.council.base import Council, ValidationSignal
from telos.core.council.validators.calibration import CalibrationValidator
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import ReflexStream
from telos.core.council.validators import RealityValidator
from telos.core.ledger.skill_library import SkillLibrary
from telos.intent_ir import IntentIR
from telos.world.world import World
from tests.core.conftest import MockSimulator


# ── Tracker: math ────────────────────────────────────────────────────────────

def test_tracker_brier_and_ece_exact():
    t = CalibrationTracker(min_samples=1, min_bin_samples=1)
    for p, y in [(0.1, 0.0), (0.2, 0.0), (0.8, 1.0), (0.9, 1.0)]:
        t.record(p, y)
    assert t.sample_count == 4
    # Brier = mean((p - y)^2) = (0.01+0.04+0.04+0.01)/4
    assert t.brier_score() == pytest.approx(0.025)
    # ECE = mean bin gap = (0.1+0.2+0.2+0.1)/4
    assert t.ece() == pytest.approx(0.15)
    assert t.mean_confidence() == pytest.approx(0.5)
    assert t.mean_accuracy() == pytest.approx(0.5)
    assert t.overconfidence() == pytest.approx(0.0)


def test_tracker_perfectly_calibrated():
    t = CalibrationTracker(min_samples=1, min_bin_samples=1)
    for _ in range(10):
        t.record(0.8, 0.8)
    assert t.ece() == pytest.approx(0.0, abs=1e-9)
    assert t.is_calibrated(ece_threshold=0.05) is True


def test_tracker_insufficient_data_is_honest():
    t = CalibrationTracker(min_samples=20)
    # No data at all -> identity map (never a fabricated correction).
    assert t.calibrated_confidence(0.73) == pytest.approx(0.73)
    t.record(0.9, 1.0)
    assert t.has_signal is False
    assert t.brier_score() is None
    assert t.ece() is None
    assert t.is_calibrated() is False


def test_tracker_recalibration_maps_to_empirical_accuracy():
    t = CalibrationTracker(min_samples=1, min_bin_samples=1)
    for _ in range(10):
        t.record(0.9, 0.0)  # claims 0.9, never succeeds
    # The 0.9 bin's empirical accuracy is 0.0.
    assert t.calibrated_confidence(0.9) == pytest.approx(0.0)


def test_tracker_recalibration_shrinks_when_bin_undersampled():
    t = CalibrationTracker(min_samples=1, min_bin_samples=100)
    for _ in range(10):
        t.record(0.9, 1.0)
    # Bin under-sampled -> shrink toward base rate (1.0), not the raw claim.
    got = t.calibrated_confidence(0.9)
    assert 0.9 <= got <= 1.0


def test_tracker_clamps_and_drops_non_finite():
    t = CalibrationTracker(min_samples=1)
    t.record(2.0, -1.0)          # clamped to (1.0, 0.0)
    t.record(float('nan'), 1.0)  # dropped
    t.record(0.5, float('inf'))  # dropped
    assert t.sample_count == 1
    assert t.mean_confidence() == pytest.approx(1.0)
    assert t.mean_accuracy() == pytest.approx(0.0)


def test_tracker_window_is_bounded():
    t = CalibrationTracker(window=5, min_samples=1)
    for i in range(10):
        t.record(0.5, 1.0)
    assert t.sample_count == 5  # Λ4.7 retention cap


def test_tracker_stats_and_to_dict():
    t = CalibrationTracker(min_samples=1, min_bin_samples=1)
    for _ in range(4):
        t.record(0.5, 1.0)
    stats = t.stats()
    assert isinstance(stats, CalibrationStats)
    d = t.to_dict()
    assert d["sample_count"] == 4
    assert d["brier_score"] is not None
    assert isinstance(d["bins"], list) and len(d["bins"]) == 1


# ── Validator: modes ─────────────────────────────────────────────────────────

def _overconfident_tracker():
    """A tracker where high confidence has never once been right."""
    t = CalibrationTracker(min_samples=1, min_bin_samples=1)
    for _ in range(10):
        t.record(0.9, 0.0)
    return t


def test_validator_abstains_without_intent():
    v = CalibrationValidator(_overconfident_tracker(), enforce=True)
    sig = v.validate(World(state=np.array([0.0, 0.0])), None)
    assert sig.passed is True
    assert sig.evidence_weight == 0.0


def test_validator_abstains_without_tracker():
    v = CalibrationValidator(None, enforce=True)
    sig = v.validate(World(state=np.array([0.0, 0.0])), IntentIR("x", confidence=0.9))
    assert sig.passed is True
    assert sig.evidence_weight == 0.0


def test_validator_abstains_under_min_samples():
    t = CalibrationTracker(min_samples=20)
    t.record(0.9, 0.0)
    v = CalibrationValidator(t, enforce=True)
    sig = v.validate(World(state=np.array([0.0, 0.0])), IntentIR("x", confidence=0.9))
    assert sig.passed is True
    assert sig.evidence_weight == 0.0
    assert "insufficient" in sig.reason


def test_validator_advisory_is_zero_weight_pass():
    v = CalibrationValidator(_overconfident_tracker(), enforce=False)
    sig = v.validate(World(state=np.array([0.0, 0.0])), IntentIR("x", confidence=0.9))
    assert sig.passed is True
    assert sig.evidence_weight == 0.0
    assert sig.confidence == 0.0
    assert sig.metadata["overconfident"] is True
    assert "ADVISORY" in sig.reason


def test_validator_enforce_blocks_overconfidence():
    v = CalibrationValidator(_overconfident_tracker(), enforce=True)
    sig = v.validate(World(state=np.array([0.0, 0.0])), IntentIR("x", confidence=0.9))
    assert sig.passed is False
    assert sig.confidence < 0
    assert sig.evidence_weight > 0.0
    assert sig.metadata["miscalibrated"] is True


def test_validator_enforce_passes_when_calibrated():
    t = CalibrationTracker(min_samples=1, min_bin_samples=1)
    for _ in range(10):
        t.record(0.8, 0.8)
    v = CalibrationValidator(t, enforce=True)
    sig = v.validate(World(state=np.array([0.0, 0.0])), IntentIR("x", confidence=0.8))
    assert sig.passed is True
    assert sig.metadata["calibrated_confidence"] == pytest.approx(0.8)


def test_validator_enforce_does_not_block_low_confidence():
    # Miscalibrated overall, but the claim itself is not high -> no block.
    v = CalibrationValidator(_overconfident_tracker(), enforce=True)
    sig = v.validate(World(state=np.array([0.0, 0.0])), IntentIR("x", confidence=0.4))
    assert sig.passed is True


def test_validator_runs_through_council():
    council = Council()
    council.register(CalibrationValidator(_overconfident_tracker(), enforce=True))
    verdict = council.evaluate(
        World(state=np.array([0.0, 0.0])), IntentIR("x", confidence=0.9),
    )
    names = [s.validator_name for s in verdict.signals]
    assert "CalibrationValidator" in names
    # Sole validator blocks -> council refuses to validate.
    assert verdict.validated is False


# ── Pipeline wiring ──────────────────────────────────────────────────────────

@pytest.fixture
def pipeline():
    sim = MockSimulator()
    sim.initialize()
    config = PipelineConfig(
        simulator=sim, compute_budget_ms=200.0, state_dim=2,
        n_worlds=5, horizon=3, quality_threshold=0.3,
    )
    pl = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    pl.register_stream(ReflexStream(skill_lib))
    pl.register_validator(RealityValidator())
    pl.register_validator(CalibrationValidator(pl.calibration_tracker))
    return pl


def test_pipeline_records_one_pair_per_cycle(pipeline):
    assert pipeline.calibration_tracker.sample_count == 0
    for _ in range(3):
        pipeline.execute(np.array([1.0, 2.0]))
    assert pipeline.calibration_tracker.sample_count == 3


def test_pipeline_calibration_report_shape(pipeline):
    pipeline.execute(np.array([1.0, 2.0]))
    report = pipeline.calibration_report()
    assert report["sample_count"] == 1
    assert "brier_score" in report and "ece" in report


def test_pipeline_trace_carries_calibration_snapshot(pipeline):
    result = pipeline.execute(np.array([1.0, 2.0]))
    trace = result.decision_trace
    assert trace is not None
    if trace.reflection is not None:
        assert "calibration" in trace.reflection
        assert trace.reflection["calibration"]["sample_count"] >= 1
