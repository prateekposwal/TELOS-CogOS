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

# Novelty band: tasks below this are already well-practised (skip); tasks above
# it are too far out (defer until their prerequisites are learned).
ZPD_LOW = 0.25
ZPD_HIGH = 0.9


@dataclass
class CurriculumTask:
    """One practice task derived from a knowledge gap.

    Attributes:
        task_id: stable id.
        kind: source kind (theory_gap / curiosity / under_visited).
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

    def __init__(self, zpd_low: float = ZPD_LOW, zpd_high: float = ZPD_HIGH,
                 max_tasks: int = 20):
        """Construct a curriculum.

        Args:
            zpd_low: novelty below which a task is already learned.
            zpd_high: novelty above which a task is deferred.
            max_tasks: bound on retained tasks.
        """
        self.zpd_low = zpd_low
        self.zpd_high = zpd_high
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
            self.add(CurriculumTask(
                task_id=f"sig_{sid}",
                kind="under_visited",
                description=str(s.get("description", f"Practice {sid}")),
                novelty=novelty,
                difficulty=novelty,
                metadata={"coverage": coverage},
            ))
            added += 1
        return added

    def frontier(self) -> List[CurriculumTask]:
        """Return tasks in the zone of proximal development, easiest first.

        Returns:
            Ordered list of actionable tasks (prerequisites satisfied by
            ordering — easiest first).
        """
        eligible = [
            t for t in self._tasks.values()
            if self.zpd_low <= t.novelty <= self.zpd_high
        ]
        eligible.sort(key=lambda t: (t.difficulty, t.novelty, t.task_id))
        return eligible

    def deferred(self) -> List[CurriculumTask]:
        """Return tasks too novel to attempt yet (above the ZPD ceiling).

        Returns:
            Ordered list of deferred tasks (most novel first).
        """
        out = [t for t in self._tasks.values() if t.novelty > self.zpd_high]
        out.sort(key=lambda t: (-t.novelty, t.task_id))
        return out

    def stats(self) -> Dict[str, int]:
        """Return task counts by band.

        Returns:
            Dict with total/frontier/deferred/learned counts.
        """
        return {
            "total": len(self._tasks),
            "frontier": len(self.frontier()),
            "deferred": len(self.deferred()),
            "learned": sum(1 for t in self._tasks.values()
                           if t.novelty < self.zpd_low),
        }


__all__ = ["Curriculum", "CurriculumTask", "ZPD_LOW", "ZPD_HIGH"]
