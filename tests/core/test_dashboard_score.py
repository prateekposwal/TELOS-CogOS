"""System Score tests — the bounded composite that replaced the unbounded
timer (score = 100 − cycles + rewards, monotonically decreasing forever).

Pattern under test: quality metrics must be bounded — the range is part of
the metric's definition — and derived only from measured signals; endurance
facts (cycles elapsed) are never folded into a quality score.
"""
import itertools

import pytest

from telos.dashboard.producer import (
    DRIFT_THRESHOLD,
    SYSTEM_SCORE_WEIGHTS,
    safe_score,
    system_score,
)

# World constants mirrored from telos_task.py (asserted against the source).
REWARD_AVAILABLE = 20.0  # sum of positive DEFAULT_REWARDS {(0,4):10,(4,0):5,(2,4):3,(4,2):2}
GRID_AREA = 25.0         # GRID_SIZE ** 2


def test_system_score_always_within_bounds():
    """No input combination — including garbage values — can push the score
    outside [0, 100]. This is the structural bound: the range is part of the
    metric's definition."""
    di_vals = [None, 0.0, 0.31, 0.98, 1.0, 5.0, -2.0]
    md_vals = [None, 0.0, 1.2, 4.9, 5.0, 99.0, -3.0]
    rew_vals = [0.0, 5.0, 20.0, 40.0, -5.0]
    cov_vals = [0.0, 1.0, 25.0, 50.0, -1.0]
    for di, md, rw, cv in itertools.product(di_vals, md_vals, rew_vals, cov_vals):
        s = system_score(di, md, rw, REWARD_AVAILABLE, cv, GRID_AREA)
        assert 0.0 <= s <= 100.0, f"score {s} out of [0,100] for di={di} md={md} rw={rw} cv={cv}"


def test_system_score_perfect_state_is_100():
    assert system_score(1.0, 0.0, REWARD_AVAILABLE, REWARD_AVAILABLE,
                        GRID_AREA, GRID_AREA) == 100.0


def test_system_score_zero_quality_is_zero():
    """DI=0 and MD at/beyond threshold eliminate both quality terms; no
    rewards and no coverage leave nothing else to score."""
    s = system_score(0.0, DRIFT_THRESHOLD, 0.0, REWARD_AVAILABLE, 0.0, GRID_AREA)
    assert s == 0.0


def test_system_score_monotonic_in_positive_components():
    """Fixing three components, raising the fourth must never lower the score."""
    # DI up → non-decreasing
    low = system_score(0.4, 0.5, 10.0, REWARD_AVAILABLE, 10.0, GRID_AREA)
    high = system_score(0.9, 0.5, 10.0, REWARD_AVAILABLE, 10.0, GRID_AREA)
    assert high >= low
    # Reward up → non-decreasing
    low = system_score(0.8, 0.5, 2.0, REWARD_AVAILABLE, 10.0, GRID_AREA)
    high = system_score(0.8, 0.5, 18.0, REWARD_AVAILABLE, 10.0, GRID_AREA)
    assert high >= low
    # Coverage up → non-decreasing
    low = system_score(0.8, 0.5, 10.0, REWARD_AVAILABLE, 3.0, GRID_AREA)
    high = system_score(0.8, 0.5, 10.0, REWARD_AVAILABLE, 20.0, GRID_AREA)
    assert high >= low


def test_system_score_decaying_component_is_non_increasing():
    """A decaying DI signal (all else fixed) must never raise the score —
    the old timer guaranteed permanent decay; the new metric only moves
    when the measured signals genuinely move."""
    prev = None
    for di in (1.0, 0.9, 0.7, 0.4, 0.1, 0.0):
        s = system_score(di, 0.0, 10.0, REWARD_AVAILABLE, 10.0, GRID_AREA)
        if prev is not None:
            assert s <= prev + 1e-9, f"score rose while DI decayed: {prev} -> {s}"
        prev = s


def test_system_score_rising_drift_is_non_increasing():
    """Rising mission drift (all else fixed) must never raise the score."""
    prev = None
    for md in (0.0, 1.0, 2.5, 4.0, 5.0, 10.0):
        s = system_score(0.8, md, 10.0, REWARD_AVAILABLE, 10.0, GRID_AREA)
        if prev is not None:
            assert s <= prev + 1e-9, f"score rose while MD rose: {prev} -> {s}"
        prev = s


def test_system_score_reflects_real_reward_and_di_inputs():
    """The score genuinely moves with the measured signals — the correlation
    proof: better decisions and secured world value must raise the score."""
    idle = system_score(0.5, 0.0, 0.0, REWARD_AVAILABLE, 0.0, GRID_AREA)
    rewarded = system_score(0.5, 0.0, REWARD_AVAILABLE, REWARD_AVAILABLE,
                            GRID_AREA, GRID_AREA)
    high_di = system_score(1.0, 0.0, 0.0, REWARD_AVAILABLE, 0.0, GRID_AREA)
    assert rewarded > idle, "securing the world's value must raise the score"
    assert high_di > idle, "better decisions must raise the score"


def test_system_score_weights_sum_to_one():
    assert abs(sum(SYSTEM_SCORE_WEIGHTS.values()) - 1.0) < 1e-9


def test_safe_score_rejects_out_of_range():
    """The range is enforced at the API boundary: the legacy unbounded
    format (-271 and friends) is structurally rejected, never displayed."""
    assert safe_score(78.4) == 78.4
    assert safe_score(0.0) == 0.0
    assert safe_score(100.0) == 100.0
    assert safe_score(-271.0) is None, "legacy unbounded timer score must be rejected"
    assert safe_score(150.0) is None
    assert safe_score(None) is None
    assert safe_score("78") is None
    assert safe_score(True) is None
    assert safe_score(float("nan")) is None
