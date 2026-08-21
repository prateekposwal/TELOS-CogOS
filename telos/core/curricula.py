"""
Test-shaped curriculum — the gap tracker bridge for the autonomous fix loop.

PATTERN (curriculum is test-shaped): a gap may feed the fix loop ONLY when it
is expressed as a failing pytest id (`test_id`). Delivery tickets (e.g.
G-18..G-23: papers, publications, posts) have no `test_id` and can NEVER be
consumed as automated fixes — they are ledger-of-intent records, not code
work. This prevents the autonomous loop from burning governed compute on
non-code deliverables, and keeps the loop's input contract exactly what
FixLoopController.run_autonomous() already accepts: real failing test ids.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger('telos_curriculum')


GAP_TRACKER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))),
    "tracking", "gap-tracker.json",
)


def load_gaps(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load the gap tracker (default: telos/tracking/gap-tracker.json).

    Args:
        path: optional override for the tracker JSON path.

    Returns:
        The list of gap records (empty on missing/unparsable file).
    """
    p = path or GAP_TRACKER_PATH
    try:
        with open(p, encoding="utf-8") as fp:
            data = json.load(fp)
        return list(data.get("gaps", []) or [])
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Curriculum: cannot load gap tracker %s: %r", p, e)
        return []


def test_shaped_tasks(gaps: Optional[List[Dict[str, Any]]] = None,
                      path: Optional[str] = None) -> List[str]:
    """Return only the test-shaped gap test ids (those bearing a `test_id`).

    The intake rule (Λ2.3): a gap is code-consumable only when it explicitly
    names a failing pytest id. Delivery gaps (no test_id) are excluded by
    construction and can never flow into the fix loop.

    Args:
        gaps: optional gap list (loads the tracker when omitted).
        path: optional tracker path override.

    Returns:
        The ordered list of `test_id` values that may feed the fix loop.
    """
    src = gaps if gaps is not None else load_gaps(path)
    tasks: List[str] = []
    for g in src:
        tid = g.get("test_id")
        if isinstance(tid, str) and tid.strip():
            tasks.append(tid.strip())
    return tasks


def curriculum_for(gaps: Optional[List[Dict[str, Any]]] = None,
                   path: Optional[str] = None) -> List[str]:
    """The full curriculum: deduplicated test-shaped gap test ids.

    Currently-failing real tests are discovered by the fix loop itself (from
    RepoSnapshot evidence); this helper merges the gap-declared test ids so a
    controller can prefer them in order.

    Args:
        gaps: optional gap list override.
        path: optional tracker path override.

    Returns:
        The deduplicated ordered list of test ids to attempt.
    """
    seen: List[str] = []
    for tid in test_shaped_tasks(gaps=gaps, path=path):
        if tid not in seen:
            seen.append(tid)
    return seen


__all__ = ["load_gaps", "test_shaped_tasks", "curriculum_for",
           "GAP_TRACKER_PATH"]