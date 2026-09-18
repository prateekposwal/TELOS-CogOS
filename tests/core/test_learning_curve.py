"""
Learning-curve evaluation (Phase 3) — measured against a frozen control.

The harness must be deterministic, PASS when the learned arm genuinely learns,
and FAIL if the learning mechanism is removed (a regression guard against a
rigged fixture).
"""

from telos.tools.learning_curve import (
    TASKS, evaluate, _run_frozen, _run_learned, _slope, _outcome,
)


def test_evaluate_passes():
    """The learned arm beats the frozen control on the fixed stream."""
    result = evaluate()
    assert result["beats_control"] is True
    assert result["learned"]["successes"] > result["frozen"]["successes"]
    assert result["learned"]["slope"] > result["frozen"]["slope"]
    assert result["learned"]["acquired"] > 0


def test_learned_arm_attempts_every_task():
    """REGRESSION: the learned arm must attempt the FULL task stream.

    An earlier version derived novelty as (1 - difficulty), so the three hardest
    tasks were classified 'already learned' and silently skipped — the learned
    arm only ran 5 of 8 tasks and the '5 vs 2' headline was partly a smaller
    task set. Both arms must cover the same tasks.
    """
    learned = _run_learned(TASKS)
    frozen = _run_frozen(TASKS)
    assert len(learned["order"]) + len(learned["outcomes"]) >= len(TASKS)
    assert len(learned["outcomes"]) == len(TASKS), \
        f"learned arm attempted {len(learned['outcomes'])}/{len(TASKS)} tasks"
    assert len(frozen["outcomes"]) == len(TASKS)


def test_novelty_is_independent_of_difficulty():
    """Every task carries explicit novelty that is not 1-difficulty."""
    for task in TASKS:
        assert "novelty" in task, task["id"]
        assert abs(task["novelty"] - (1.0 - task["difficulty"])) > 0.02, task["id"]


def test_evaluate_is_deterministic():
    """Two evaluations over the fixed stream are identical."""
    assert evaluate() == evaluate()


def test_frozen_control_never_learns():
    """The control's competence and acquisition are permanently zero."""
    frozen = _run_frozen(TASKS)
    assert frozen["competence"] == 0.0
    assert frozen["acquired"] == 0
    assert frozen["skills"] == 0


def test_learned_arm_shows_transfer():
    """The learned arm reuses held prerequisites (transfer > 0)."""
    learned = _run_learned(TASKS)
    assert learned["reuse"] > 0


def test_slope_positive_for_improving_sequence():
    """_slope is positive for an increasing sequence and negative for a falling one."""
    assert _slope([0.1, 0.2, 0.3, 0.4]) > 0
    assert _slope([0.9, 0.7, 0.5, 0.3]) < 0
    assert _slope([0.5]) == 0.0


def test_outcome_rises_with_competence():
    """Outcome is monotonically non-decreasing in competence."""
    task = {"id": "x", "difficulty": 0.7}
    values = [_outcome(task, c) for c in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert values == sorted(values)


def test_no_learning_arm_does_not_beat_control():
    """If competence is frozen (no learning), the arm cannot beat the control.

    This locks the harness against a trivially passing fixture: swapping the
    learned arm for a no-learning version must remove the advantage.
    """
    learned = _run_learned(TASKS)
    frozen = _run_frozen(TASKS)
    # A no-learning arm would have the same success count as the frozen one.
    assert learned["successes"] != frozen["successes"], \
        "the learned arm's advantage must come from actual competence growth"
