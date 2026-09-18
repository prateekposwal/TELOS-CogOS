"""
Novelty-driven curriculum (Phase 3) — gap-derived, deterministic, ZPD-ordered.
"""

import pytest

from telos.core.learning.curriculum import (
    Curriculum, CurriculumTask, ZPD_LOW, ZPD_HIGH, ZPD_BAND,
)


def test_task_generation_from_falsified_hypotheses():
    """A falsified hypothesis becomes a high-novelty repair task."""
    cur = Curriculum()
    n = cur.from_theory_gaps([
        {"id": "h1", "action": "navigate", "predicted_outcome": 0.8,
         "confidence": 0.4, "tests_passed": 3, "tests_failed": 2, "falsified": True},
    ])
    assert n == 1
    tasks = cur.frontier() + cur.deferred()
    task = next(t for t in tasks if t.task_id == "gap_h1")
    assert task.kind == "theory_gap"
    assert task.novelty >= 0.8


def test_untested_hypothesis_is_most_novel():
    """An untested hypothesis is more novel than a well-tested confident one."""
    cur = Curriculum()
    cur.from_theory_gaps([
        {"id": "untested", "action": "a", "confidence": 0.0, "tests_passed": 0,
         "tests_failed": 0, "falsified": False},
        {"id": "proven", "action": "b", "confidence": 0.95, "tests_passed": 20,
         "tests_failed": 0, "falsified": False},
    ])
    untested = next(t for t in (cur.frontier() + cur.deferred())
                    if t.task_id == "gap_untested")
    assert untested.novelty > 0.9


def test_signal_generation_novelty_is_inverse_coverage():
    """A signal's novelty is 1 - coverage."""
    cur = Curriculum()
    cur.from_signals([{"id": "s1", "description": "visit corner", "coverage": 0.2}])
    task = next(t for t in (cur.frontier() + cur.deferred())
                if t.task_id == "sig_s1")
    assert abs(task.novelty - 0.8) < 1e-9


def test_frontier_is_difficulty_ordered_and_novelty_floored():
    """Frontier tasks clear the novelty floor and are ordered easiest-first.

    Novelty has NO ceiling — a never-seen task is eligible however novel it is.
    (The old code applied the ceiling to novelty, which deferred every novel
    task and left only the easy ones; that is the bug this locks out.)
    """
    cur = Curriculum()
    cur.from_signals([
        {"id": "easy", "coverage": 0.7},   # novelty 0.3
        {"id": "mid", "coverage": 0.4},    # novelty 0.6
        {"id": "hard_novel", "coverage": 0.05},  # novelty 0.95 -> still eligible
    ])
    frontier = cur.frontier()
    assert all(t.novelty >= ZPD_LOW for t in frontier)
    difficulties = [t.difficulty for t in frontier]
    assert difficulties == sorted(difficulties)
    assert any(t.task_id == "sig_hard_novel" for t in frontier)


def test_learned_task_is_deferred_not_frontier():
    """A mastered task (novelty below the floor) is deferred, not attempted."""
    cur = Curriculum()
    cur.from_signals([
        {"id": "mastered", "coverage": 0.95},  # novelty 0.05 -> below floor
        {"id": "fresh", "coverage": 0.5},      # novelty 0.5  -> frontier
    ])
    assert all(t.task_id != "sig_mastered" for t in cur.frontier())
    assert any(t.task_id == "sig_mastered" for t in cur.deferred())


def test_zpd_ceiling_defers_beyond_competence():
    """With a competence level, tasks beyond competence+band are deferred."""
    cur = Curriculum(zpd_band=0.2)
    cur.from_signals([
        {"id": "near", "coverage": 0.5, "difficulty": 0.3},
        {"id": "far", "coverage": 0.5, "difficulty": 0.9},
    ])
    frontier = [t.task_id for t in cur.frontier(current_competence=0.2)]
    assert "sig_near" in frontier
    assert "sig_far" not in frontier
    assert any(t.task_id == "sig_far"
               for t in cur.deferred(current_competence=0.2))


def test_curriculum_is_bounded():
    """The task set never exceeds max_tasks."""
    cur = Curriculum(max_tasks=12)
    cur.from_signals([{"id": f"s{i}", "coverage": (i % 10) / 10,
                       "difficulty": (i % 7) / 7} for i in range(100)])
    assert cur.stats()["total"] <= 12


def test_curriculum_is_deterministic():
    """The same inputs always produce the same ordering."""
    def build():
        cur = Curriculum()
        cur.from_signals([{"id": f"s{i}", "coverage": (i % 10) / 10,
                           "difficulty": (i % 5) / 5} for i in range(10)])
        return [t.task_id for t in cur.frontier()]
    assert build() == build()


def test_derived_novelty_is_rejected():
    """A whole set whose novelty is 1-difficulty fails loud (the real bug)."""
    cur = Curriculum()
    with pytest.raises(ValueError):
        for i in range(5):
            d = 0.1 + i * 0.15
            cur.add(CurriculumTask(
                task_id=f"t{i}", kind="practice", description="x",
                novelty=1.0 - d, difficulty=d,   # the category error
            ))
        cur.check_independence()


def test_stats_bands():
    """Stats report total/frontier/deferred/learned consistently."""
    cur = Curriculum()
    cur.from_signals([
        {"id": "learned", "coverage": 0.95},          # novelty 0.05 -> learned
        {"id": "front", "coverage": 0.5, "difficulty": 0.4},
        {"id": "other", "coverage": 0.2, "difficulty": 0.6},
    ])
    stats = cur.stats()
    assert stats["total"] == 3
    assert stats["learned"] == 1
    assert stats["frontier"] >= 1


def test_theory_gap_explicit_difficulty_is_honoured():
    """An explicit per-hypothesis difficulty is used verbatim."""
    cur = Curriculum()
    cur.from_theory_gaps([
        {"id": "h1", "action": "navigate", "confidence": 0.4,
         "tests_passed": 3, "tests_failed": 2, "falsified": True,
         "difficulty": 0.33},
    ])
    task = next(t for t in (cur.frontier() + cur.deferred())
                if t.task_id == "gap_h1")
    assert abs(task.difficulty - 0.33) < 1e-9


def test_theory_gap_explicit_difficulty_is_clamped():
    """Out-of-range explicit difficulties clamp into [0, 1]."""
    cur = Curriculum()
    cur.from_theory_gaps([
        {"id": "hi", "action": "a", "falsified": True, "difficulty": 1.7},
        {"id": "lo", "action": "b", "falsified": True, "difficulty": -0.4},
    ])
    tasks = {t.task_id: t for t in (cur.frontier() + cur.deferred())}
    assert tasks["gap_hi"].difficulty == 1.0
    assert tasks["gap_lo"].difficulty == 0.0


def test_theory_gap_default_difficulty_is_independent_of_novelty():
    """The default path derives difficulty from evidence, not from novelty.

    A mixed set clears the whole-set independence guard (no ValueError), the
    set is not the complement pattern, and two hypotheses with IDENTICAL
    novelty (same confidence) can carry different difficulty because the
    difficulty axis reads the pass/fail record instead.
    """
    cur = Curriculum()
    cur.from_theory_gaps([
        {"id": "falsified", "action": "a", "confidence": 0.2,
         "tests_passed": 1, "tests_failed": 4, "falsified": True},
        {"id": "untested", "action": "b", "confidence": 0.0,
         "tests_passed": 0, "tests_failed": 0, "falsified": False},
        {"id": "mostly_failed", "action": "c", "confidence": 0.2,
         "tests_passed": 0, "tests_failed": 4, "falsified": False},
        {"id": "mostly_passed", "action": "d", "confidence": 0.2,
         "tests_passed": 4, "tests_failed": 0, "falsified": False},
    ])
    tasks = list(cur.frontier() + cur.deferred())
    assert len(tasks) == 4
    # No ValueError above: the set is not the complement pattern.
    complements = sum(1 for t in tasks
                      if abs(t.novelty - (1.0 - t.difficulty)) <= 0.02)
    assert complements < len(tasks)
    by_id = {t.task_id: t for t in tasks}
    # Same novelty (confidence-only), different difficulty (evidence-driven).
    assert (abs(by_id["gap_mostly_failed"].novelty
                - by_id["gap_mostly_passed"].novelty) < 1e-9)
    assert (by_id["gap_mostly_failed"].difficulty
            > by_id["gap_mostly_passed"].difficulty)


def test_theory_gap_complement_set_fails_loud():
    """A complement set built through from_theory_gaps raises ValueError.

    Falsified hypotheses carry novelty 0.85; supplying difficulty 0.15 makes
    novelty == 1 - difficulty for every task, which must trip the guard.
    """
    cur = Curriculum()
    with pytest.raises(ValueError):
        cur.from_theory_gaps([
            {"id": "h1", "action": "a", "falsified": True, "difficulty": 0.15},
            {"id": "h2", "action": "b", "falsified": True, "difficulty": 0.15},
        ])
