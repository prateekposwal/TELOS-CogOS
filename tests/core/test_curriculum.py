"""
Novelty-driven curriculum (Phase 3) — gap-derived, deterministic, ZPD-ordered.
"""

from telos.core.learning.curriculum import Curriculum, CurriculumTask, ZPD_LOW, ZPD_HIGH


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


def test_frontier_is_within_zpd_and_difficulty_ordered():
    """Frontier tasks are inside the ZPD and ordered easiest-first."""
    cur = Curriculum()
    cur.from_signals([
        {"id": "easy", "coverage": 0.7},   # novelty 0.3
        {"id": "mid", "coverage": 0.4},    # novelty 0.6
        {"id": "hard", "coverage": 0.05},  # novelty 0.95 -> deferred
    ])
    frontier = cur.frontier()
    assert all(ZPD_LOW <= t.novelty <= ZPD_HIGH for t in frontier)
    difficulties = [t.difficulty for t in frontier]
    assert difficulties == sorted(difficulties)
    assert all(t.task_id != "sig_hard" for t in frontier)


def test_deferred_excludes_frontier():
    """Too-novel tasks are deferred, not attempted."""
    cur = Curriculum()
    cur.from_signals([{"id": "hard", "coverage": 0.0}])
    assert cur.frontier() == []
    assert len(cur.deferred()) == 1


def test_curriculum_is_bounded():
    """The task set never exceeds max_tasks."""
    cur = Curriculum(max_tasks=12)
    cur.from_signals([{"id": f"s{i}", "coverage": 0.5} for i in range(100)])
    assert cur.stats()["total"] <= 12


def test_curriculum_is_deterministic():
    """The same inputs always produce the same ordering."""
    def build():
        cur = Curriculum()
        cur.from_signals([{"id": f"s{i}", "coverage": (i % 10) / 10} for i in range(10)])
        return [t.task_id for t in cur.frontier()]
    assert build() == build()


def test_stats_bands():
    """Stats report total/frontier/deferred/learned consistently."""
    cur = Curriculum()
    cur.from_signals([
        {"id": "learned", "coverage": 0.95},  # novelty 0.05 -> learned
        {"id": "front", "coverage": 0.5},     # novelty 0.5 -> frontier
        {"id": "def", "coverage": 0.0},       # novelty 1.0 -> deferred
    ])
    stats = cur.stats()
    assert stats["total"] == 3
    assert stats["learned"] == 1
    assert stats["frontier"] >= 1
    assert stats["deferred"] >= 1
