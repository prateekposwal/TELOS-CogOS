"""
Novelty-driven curriculum (Phase 3, Voyager's self-verifying curriculum).

PATTERN (one curriculum source): Voyager generates its own tasks by asking what
it cannot yet do. TELOS has the raw material — theory gaps (hypotheses that
falsified), curiosity signals, and under-visited situations — but no single
place that turns them into a difficulty-ordered task list.

This module does exactly that, deterministically: it scores candidate tasks by
NOVELTY (how little experience covers them) and orders them easiest-first in
the zone of proximal development, so learning is a ladder rather than a
random walk. The curriculum is advisory: it proposes what to practice; the
pipeline still decides.

No model, no network — the same inputs always produce the same ordering, so a
learning-curve experiment is reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Novelty FLOOR: tasks below this are already well-practised (skip). Novelty
# has no ceiling — never-seen tasks are always eligible.
ZPD_LOW = 0.25
# Difficulty BAND: once a competence level is known, tasks more than this far
# beyond it are deferred (the classic zone of proximal development). This is
# the ceiling that belongs to DIFFICULTY, not novelty — applying it to novelty
# deferred every hard task and left only the easy ones (or vice versa).
ZPD_BAND = 0.6
# Retained for backward compatibility: the historical single-ceiling name.
ZPD_HIGH = 0.9


@dataclass
class CurriculumTask:
    """One practice task derived from a knowledge gap.

    IMPORTANT (novelty != difficulty): these are INDEPENDENT axes and must be
    supplied independently. Difficulty is "how far beyond current competence";
    novelty is "how little experience covers this". A task can be hard AND
    unpractised (novelty high, difficulty high) or easy AND unpractised. Deriving
    one from the other (e.g. ``novelty = 1 - difficulty``) is a category error:
    it classifies the HARDEST tasks as "already learned" and silently drops them
    from every practice frontier.

    Attributes:
        task_id: stable id.
        kind: source kind (theory_gap / curiosity / under_visited / practice).
        description: human-readable task.
        novelty: 0..1 (higher = less covered by experience).
        difficulty: 0..1 (higher = further from current competence).
        prerequisites: task ids that should precede this one.
        metadata: extra context (action, predicted outcome, domain).
    """

    task_id: str
    kind: str
    description: str
    novelty: float
    difficulty: float
    prerequisites: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """Serializable form."""
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "description": self.description,
            "novelty": round(self.novelty, 3),
            "difficulty": round(self.difficulty, 3),
            "prerequisites": list(self.prerequisites),
            "metadata": dict(self.metadata),
        }


class Curriculum:
    """Deterministic, novelty-ordered task generator."""

    def __init__(self, zpd_low: float = ZPD_LOW, zpd_band: float = ZPD_BAND,
                 max_tasks: int = 20):
        """Construct a curriculum.

        Args:
            zpd_low: novelty floor below which a task is already mastered.
            zpd_band: difficulty band above current competence within which a
                task is attempted (the ZPD ceiling).
            max_tasks: bound on retained tasks.
        """
        self.zpd_low = zpd_low
        self.zpd_band = zpd_band
        self.max_tasks = max(1, max_tasks)
        self._tasks: Dict[str, CurriculumTask] = {}

    def add(self, task: CurriculumTask) -> None:
        """Add (or replace) a task, keeping the set bounded.

        Args:
            task: the task to add.
        """
        self._tasks[task.task_id] = task
        if len(self._tasks) > self.max_tasks:
            worst = sorted(
                self._tasks.values(),
                key=lambda t: (t.novelty, t.task_id),
            )[0]
            self._tasks.pop(worst.task_id, None)

    def check_independence(self, tolerance: float = 0.02) -> None:
        """Assert novelty is not merely ``1 - difficulty`` across the set.

        A single task can coincidentally satisfy ``novelty == 1 - difficulty``
        (e.g. both 0.5). The category error is a *whole set* whose novelty is
        the complement of its difficulty — which reclassifies the hardest tasks
        as already-learned. Detecting the pattern, not one point, avoids false
        positives while still failing loud on the real bug (Λ2.3).

        Args:
            tolerance: per-task absolute tolerance for the complement relation.

        Raises:
            ValueError: when every task's novelty is the complement of its
                difficulty (the derived axis error).
        """
        if len(self._tasks) < 2:
            return
        matches = sum(
            1 for t in self._tasks.values()
            if abs(t.novelty - (1.0 - t.difficulty)) <= tolerance
        )
        if matches == len(self._tasks):
            raise ValueError(
                "curriculum novelty is the complement of difficulty for every "
                "task — novelty and difficulty are independent axes; pass both "
                "explicitly (novelty = how little experience covers the task, "
                "difficulty = how far beyond current competence it is)"
            )

    def from_theory_gaps(self, hypotheses: List[Dict[str, object]],
                         min_novelty: float = ZPD_LOW) -> int:
        """Derive tasks from falsified / untested theory hypotheses.

        Args:
            hypotheses: dicts with id/action/predicted_outcome/confidence/
                tests_passed/tests_failed/falsified.
            min_novelty: novelty floor for admission.

        Returns:
            Number of tasks added.
        """
        added = 0
        for h in hypotheses:
            hid = str(h.get("id", ""))
            if not hid:
                continue
            tested = int(h.get("tests_passed", 0) or 0) + int(
                h.get("tests_failed", 0) or 0)
            confidence = float(h.get("confidence", 0.0) or 0.0)
            falsified = bool(h.get("falsified", False))
            # Novelty: untested hypotheses are most novel; falsified ones are
            # novel again (the belief did not hold); confident tested ones are
            # least novel.
            if falsified:
                novelty = 0.85
            elif tested == 0:
                novelty = 0.95
            else:
                novelty = max(0.0, 1.0 - confidence) * 0.5
            if novelty < min_novelty:
                continue
            action = str(h.get("action", "unknown"))
            predicted = float(h.get("predicted_outcome", 0.5) or 0.5)
            self.add(CurriculumTask(
                task_id=f"gap_{hid}",
                kind="theory_gap",
                description=(
                    f"Test/repair hypothesis '{action}' (predicted {predicted:.2f}, "
                    f"{'falsified' if falsified else f'{tested} tests'})"
                ),
                novelty=novelty,
                difficulty=novelty if not falsified else min(1.0, novelty + 0.1),
                metadata={"action": action, "predicted_outcome": predicted,
                          "falsified": falsified, "tests": tested},
            ))
            added += 1
        return added

    def from_signals(self, signals: List[Dict[str, object]]) -> int:
        """Derive tasks from curiosity / under-visited situation signals.

        Args:
            signals: dicts with id/description/coverage (0..1 coverage).

        Returns:
            Number of tasks added.
        """
        added = 0
        for s in signals:
            sid = str(s.get("id", ""))
            if not sid:
                continue
            coverage = float(s.get("coverage", 0.0) or 0.0)
            novelty = max(0.0, min(1.0, 1.0 - coverage))
            # Difficulty is a SEPARATE input: an under-visited situation is not
            # automatically hard. Callers may supply an explicit difficulty
            # (e.g. from a competence gap); absent that, this signal carries no
            # difficulty information, so it is recorded as unknown (None ->
            # treated as the midpoint by ZPD_band consumers).
            difficulty = s.get("difficulty")
            difficulty = (max(0.0, min(1.0, float(difficulty)))
                          if difficulty is not None else 0.5)
            self.add(CurriculumTask(
                task_id=f"sig_{sid}",
                kind="under_visited",
                description=str(s.get("description", f"Practice {sid}")),
                novelty=novelty,
                difficulty=difficulty,
                metadata={"coverage": coverage},
            ))
            added += 1
        self.check_independence()
        return added

    def frontier(self, current_competence: float = 0.0) -> List[CurriculumTask]:
        """Return actionable tasks in the zone of proximal development.

        Two INDEPENDENT bands decide eligibility (see CurriculumTask's
        novelty-vs-difficulty note):

          - novelty FLOOR (zpd_low): skip what is already mastered. Novelty has
            no ceiling — a task you have never seen is eligible no matter how
            novel it is.
          - difficulty CEILING (zpd_high): defer what is too far beyond current
            competence. With no competence supplied (the default) the ceiling
            is not applied, because there is nothing to compare against.

        Ordering is easiest-first so each task's prerequisites come before it.

        Args:
            current_competence: the learner's competence in [0, 1]; when > 0 the
                ZPD_BAND ceiling defers tasks beyond competence + band.

        Returns:
            Ordered list of actionable tasks (easiest first).
        """
        ceiling = None
        if current_competence > 0.0:
            ceiling = min(1.0, current_competence + self.zpd_band)
        eligible = [
            t for t in self._tasks.values()
            if t.novelty >= self.zpd_low
            and (ceiling is None or t.difficulty <= ceiling)
        ]
        eligible.sort(key=lambda t: (t.difficulty, -t.novelty, t.task_id))
        return eligible

    def deferred(self, current_competence: float = 0.0) -> List[CurriculumTask]:
        """Return tasks deliberately not attempted yet.

        A task is deferred when it is already mastered (novelty below the
        floor) OR — once a competence level is supplied — when it lies beyond
        the zone of proximal development.

        Args:
            current_competence: the learner's competence in [0, 1].

        Returns:
            Ordered list of deferred tasks (hardest first).
        """
        ceiling = None
        if current_competence > 0.0:
            ceiling = min(1.0, current_competence + self.zpd_band)
        out = [
            t for t in self._tasks.values()
            if t.novelty < self.zpd_low
            or (ceiling is not None and t.difficulty > ceiling)
        ]
        out.sort(key=lambda t: (-t.difficulty, t.task_id))
        return out

    def stats(self, current_competence: float = 0.0) -> Dict[str, int]:
        """Return task counts by band.

        Args:
            current_competence: the learner's competence in [0, 1] (passed
                through to frontier/deferred when > 0).

        Returns:
            Dict with total/frontier/deferred/learned counts.
        """
        return {
            "total": len(self._tasks),
            "frontier": len(self.frontier(current_competence)),
            "deferred": len(self.deferred(current_competence)),
            "learned": sum(1 for t in self._tasks.values()
                           if t.novelty < self.zpd_low),
        }


__all__ = ["Curriculum", "CurriculumTask", "ZPD_LOW", "ZPD_HIGH", "ZPD_BAND"]