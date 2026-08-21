"""Phase 4 — test-shaped curriculum contracts.

A gap may feed the autonomous fix loop ONLY when it carries a `test_id`
(a failing pytest id). Delivery gaps without one are ledger-of-intent only
and can never be consumed as code fixes (Λ2.3: curriculum is test-shaped).
"""
import json

from telos.core.curricula import load_gaps, curriculum_for
from telos.core.curricula import test_shaped_tasks as _test_shaped_tasks


def _tracker(gaps):
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w") as f:
        json.dump({"schema_version": "1", "gaps": gaps}, f)
    return path


def _gap(gid, title, test_id=None):
    g = {"id": gid, "title": title, "status": "open",
         "category": "research"}
    if test_id:
        g["test_id"] = test_id
    return g


def test_gap_with_test_id_flows_to_loop():
    path = _tracker([
        _gap("G-90", "broken arithmetic", test_id="test_calc.py::test_add"),
    ])
    tasks = _test_shaped_tasks(path=path)
    assert tasks == ["test_calc.py::test_add"]


def test_delivery_gap_without_test_id_cannot_flow():
    path = _tracker([
        _gap("G-18", "a paper not a test"),
        _gap("G-91", "real code bug", test_id="test_code.py::test_bug"),
    ])
    tasks = _test_shaped_tasks(path=path)
    assert tasks == ["test_code.py::test_bug"], \
        "delivery gaps must never enter the code queue"


def test_curriculum_deduplicates():
    path = _tracker([
        _gap("G-1", "a", test_id="t1"),
        _gap("G-2", "b", test_id="t1"),
        _gap("G-3", "c", test_id="t2"),
    ])
    assert curriculum_for(path=path) == ["t1", "t2"]


def test_real_tracker_has_no_test_ids_today():
    """The 6 open delivery gaps (G-18..G-23) are NOT code-consumable."""
    gaps = load_gaps()
    assert _test_shaped_tasks(gaps) == [], \
        "delivery tickets must remain ledger-only until someone writes a test"


def test_missing_tracker_is_safe():
    assert load_gaps(path="/nonexistent/gap.json") == []