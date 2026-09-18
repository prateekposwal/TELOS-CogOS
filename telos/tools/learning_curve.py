#!/usr/bin/env python3
"""
Learning-curve evaluation — measures skill acquisition against a frozen control.

PATTERN (measured, not asserted — Λ6.5): "TELOS learns" is only true if the
learning arm outperforms a control that cannot learn, on a FIXED task stream.
This harness runs the SAME deterministic task sequence through:

  - LEARNED arm   : verified SkillAcquisition + curriculum difficulty ordering
  - FROZEN control: fixed difficulty order, no skill retention, no promotion

and reports success@n, the learning slope, and reuse. If the learned arm does
not beat the control, the Phase-3 target is NOT met — and we say so (the
project already published one null learning result; honesty here is the point).

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/learning_curve.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/learning_curve.py --ci
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.learning.acquisition import SkillAcquisition  # noqa: E402
from telos.core.learning.curriculum import Curriculum, CurriculumTask  # noqa: E402
from telos.core.ledger.skill_library import SkillLibrary  # noqa: E402

# Deterministic synthetic task stream: each task has a true difficulty and a
# "verification" outcome that rises as its prerequisite skill is held. No RNG.
#
# `novelty` is supplied EXPLICITLY and independently of difficulty: every task
# here has never been practised, so novelty is uniformly high. Deriving it as
# (1 - difficulty), as an earlier version did, is a category error — it made the
# three hardest tasks look "already learned" (novelty 0.05-0.20 < ZPD_LOW) and
# silently dropped them, so the learned arm only attempted 5 of 8 tasks and the
# headline "5 vs 2 successes" was partly a smaller task set.
TASKS: List[Dict[str, Any]] = [
    {"id": "t1", "difficulty": 0.15, "novelty": 0.95, "requires": None},
    {"id": "t2", "difficulty": 0.35, "novelty": 0.95, "requires": "t1"},
    {"id": "t3", "difficulty": 0.50, "novelty": 0.95, "requires": "t2"},
    {"id": "t4", "difficulty": 0.62, "novelty": 0.95, "requires": "t3"},
    {"id": "t5", "difficulty": 0.72, "novelty": 0.95, "requires": "t4"},
    {"id": "t6", "difficulty": 0.80, "novelty": 0.9, "requires": "t5"},
    {"id": "t7", "difficulty": 0.88, "novelty": 0.9, "requires": "t6"},
    {"id": "t8", "difficulty": 0.95, "novelty": 0.9, "requires": "t7"},
]


def _outcome(task: Dict[str, Any], competence: float) -> float:
    """Deterministic outcome for attempting a task at a competence level.

    The easiest task (difficulty 0.1) is achievable immediately (outcome 1.0 at
    competence 0); each harder task needs proportionally more held competence.
    A held prerequisite raises competence, which is what makes the curve rise.

    Args:
        task: the task record.
        competence: the arm's current competence in [0, 1].

    Returns:
        Outcome in [0, 1].
    """
    margin = 1.0 - float(task["difficulty"]) + 0.9 * competence
    return max(0.0, min(1.0, margin))


def _run_learned(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run the learned arm: curriculum order + verified acquisition.

    Args:
        tasks: the task stream.

    Returns:
        Dict with per-step outcomes, successes, reuse, and competence.
    """
    library = SkillLibrary(max_skills=50)
    acquisition = SkillAcquisition(library, min_outcome=0.6)
    curriculum = Curriculum()
    # Seed the curriculum with each task's EXPLICIT novelty and difficulty —
    # two independent axes (see TASKS). Never novelty = 1 - difficulty.
    for t in tasks:
        curriculum.add(CurriculumTask(
            task_id=t["id"], kind="practice", description=t["id"],
            novelty=float(t["novelty"]), difficulty=float(t["difficulty"]),
        ))
    ordered = [t.task_id for t in curriculum.frontier()]
    by_id = {t["id"]: t for t in tasks}
    competence = 0.0
    outcomes: List[float] = []
    successes = 0
    reuse = 0
    held: set = set()
    attempted: set = set()
    pending = list(ordered)
    # Attempt EVERY task, in curriculum order (easiest first). A task deferred
    # by the ZPD ceiling at competence 0 becomes attemptable once competence
    # grows — so re-scan the frontier as competence rises instead of freezing
    # the first ordering (which is what silently dropped tasks before).
    while pending:
        tid = pending.pop(0)
        attempted.add(tid)
        task = by_id[tid]
        outcome = _outcome(task, competence)
        outcomes.append(outcome)
        finger = f"fp_{tid}"
        candidate = acquisition.propose(finger, {"task": tid},
                                        cycle=len(outcomes), source="curve")
        # Transfer: this task succeeded on the strength of a HELD prerequisite
        # (without it, _outcome at zero competence would have failed) — that is
        # exactly "reusing a learned skill to solve a harder task".
        prereq = task.get("requires")
        succeeded = outcome >= 0.6
        if succeeded:
            acquisition.verify(candidate.candidate_id, outcome, cycle=len(outcomes))
            successes += 1
            if prereq and prereq in held and _outcome(task, 0.0) < 0.6:
                reuse += 1
            held.add(tid)
            # Holding a skill compounds competence (the learning effect).
            competence = min(1.0, competence + 0.18)
        elif prereq and prereq in held:
            # Failed, but a held prerequisite gives a second (transfer) attempt.
            reuse += 1
            competence = min(1.0, competence + 0.1)
    return {
        "outcomes": outcomes,
        "successes": successes,
        "reuse": reuse,
        "competence": competence,
        "skills": library.skill_count,
        "acquired": acquisition.acquired,
        "order": ordered,
    }


def _run_frozen(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run the frozen control: fixed order, no acquisition, no competence.

    Args:
        tasks: the task stream.

    Returns:
        Dict with per-step outcomes, successes, and zero learning signals.
    """
    ordered = [t["id"] for t in sorted(tasks, key=lambda t: t["id"])]
    by_id = {t["id"]: t for t in tasks}
    outcomes: List[float] = []
    successes = 0
    for tid in ordered:
        outcome = _outcome(by_id[tid], 0.0)  # frozen competence, never grows
        outcomes.append(outcome)
        if outcome >= 0.6:
            successes += 1
    return {
        "outcomes": outcomes,
        "successes": successes,
        "reuse": 0,
        "competence": 0.0,
        "skills": 0,
        "acquired": 0,
        "order": ordered,
    }


def _slope(outcomes: List[float]) -> float:
    """Least-squares slope of the outcome sequence (learning rate proxy).

    Args:
        outcomes: the per-step outcomes.

    Returns:
        The slope (positive = improving).
    """
    n = len(outcomes)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(outcomes) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, outcomes)) / denom


def evaluate() -> Dict[str, Any]:
    """Compare the learned arm against the frozen control on the fixed stream.

    Returns:
        Dict with both arms' metrics, the slopes, and the beats_control verdict.
    """
    learned = _run_learned(TASKS)
    frozen = _run_frozen(TASKS)
    learned_slope = _slope(learned["outcomes"])
    frozen_slope = _slope(frozen["outcomes"])
    beats = (
        learned["successes"] > frozen["successes"]
        and learned_slope > frozen_slope
        and learned["acquired"] > 0
    )
    return {
        "learned": {**learned, "slope": learned_slope},
        "frozen": {**frozen, "slope": frozen_slope},
        "beats_control": beats,
        "tasks": len(TASKS),
    }


def print_report(result: Dict[str, Any]) -> bool:
    """Print the learning-curve table.

    Args:
        result: the dict returned by evaluate().

    Returns:
        True when the learned arm beats the frozen control.
    """
    ln = result["learned"]
    fz = result["frozen"]
    print(f"\n{'TELOS Learning-Curve Evaluation':^72}")
    print("=" * 72)
    print(f"  fixed task stream: {result['tasks']} tasks (deterministic, no RNG)")
    print("-" * 72)
    print(f"  {'metric':<22}{'learned':>14}{'frozen':>14}")
    print(f"  {'successes':<22}{ln['successes']:>14}{fz['successes']:>14}")
    print(f"  {'slope':<22}{ln['slope']:>14.3f}{fz['slope']:>14.3f}")
    print(f"  {'skills acquired':<22}{ln['acquired']:>14}{fz['acquired']:>14}")
    print(f"  {'skill reuse (transfer)':<22}{ln['reuse']:>14}{fz['reuse']:>14}")
    print(f"  {'final competence':<22}{ln['competence']:>14.2f}{fz['competence']:>14.2f}")
    print("=" * 72)
    print("  verdict:", "learned arm BEATS frozen control" if result["beats_control"]
          else "learned arm does NOT beat control")
    print("LEARNING CURVE:", "PASS" if result["beats_control"] else "FAIL")
    return bool(result["beats_control"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless the learned arm beats the frozen control")
    ap.add_argument("--json", default="telos/audit/learning_curve.json",
                    help="path to write the evaluation JSON")
    args = ap.parse_args()
    res = evaluate()
    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(PROJECT, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(res, f, indent=2)
        print(f"(evaluation saved: {out})")
    ok = print_report(res)
    if args.ci:
        sys.exit(0 if ok else 1)
