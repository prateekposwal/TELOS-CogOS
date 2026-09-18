"""
Gap-tracker curriculum bridge — a gap is code-consumable only when test-shaped.

PATTERN (curriculum is test-shaped): delivery gaps (papers, posts — no
`test_id`) must NEVER flow into the autonomous fix loop; only gaps naming a
real failing pytest id may.
"""

import json

from telos.core.curricula import (
    load_gaps, curriculum_for, GAP_TRACKER_PATH,
    # Aliased so pytest does not collect the production helper (its name
    # starts with `test_`) as if it were a test function.
    test_shaped_tasks as _test_shaped_tasks,
)


def _tracker(tmp_path, gaps):
    p = tmp_path / "gap-tracker.json"
    p.write_text(json.dumps({"gaps": gaps}))
    return str(p)


def test_load_gaps_reads_records(tmp_path):
    """load_gaps returns the gap records from a tracker file."""
    path = _tracker(tmp_path, [{"id": "G-1", "test_id": "tests/x.py::test_a"}])
    gaps = load_gaps(path)
    assert len(gaps) == 1
    assert gaps[0]["id"] == "G-1"


def test_load_gaps_missing_file_returns_empty(tmp_path):
    """A missing tracker is an empty list, not a crash."""
    assert load_gaps(str(tmp_path / "nope.json")) == []


def test_load_gaps_bad_json_returns_empty(tmp_path):
    """An unparsable tracker is logged and yields an empty list."""
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert load_gaps(str(p)) == []


def test_shaped_tasks_filters_non_test_gaps():
    """Only gaps with a non-empty test_id are returned, in order."""
    gaps = [
        {"id": "G-1", "test_id": "tests/a.py::test_one"},
        {"id": "G-2"},                            # delivery gap: excluded
        {"id": "G-3", "test_id": "  "},           # blank: excluded
        {"id": "G-4", "test_id": "tests/b.py::test_two"},
    ]
    assert _test_shaped_tasks(gaps=gaps) == [
        "tests/a.py::test_one", "tests/b.py::test_two",
    ]


def test_curriculum_for_deduplicates_preserving_order():
    """curriculum_for deduplicates while preserving first-seen order."""
    gaps = [
        {"id": "G-1", "test_id": "tests/a.py::test_one"},
        {"id": "G-2", "test_id": "tests/a.py::test_one"},
        {"id": "G-3", "test_id": "tests/b.py::test_two"},
    ]
    assert curriculum_for(gaps=gaps) == [
        "tests/a.py::test_one", "tests/b.py::test_two",
    ]


def test_default_tracker_path_is_the_project_tracker():
    """The default path points at the project's gap-tracker.json."""
    assert GAP_TRACKER_PATH.endswith("gap-tracker.json")
    assert "tracking" in GAP_TRACKER_PATH
