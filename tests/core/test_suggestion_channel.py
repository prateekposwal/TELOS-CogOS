"""Contract tests for SuggestionChannel — surfacing TELOS findings to the user.

Suggestions carry category/title/message/severity/domain; get_pending filters
non-dismissed suggestions by severity, display() renders a grouped block,
summary() one-lines the severity counts, and clear() empties the channel.
"""
import pytest

from telos.core.suggestion_channel import SuggestionChannel, Suggestion


def test_push_and_pending():
    ch = SuggestionChannel()
    ch.push("📦", "Outdated deps", "3 packages newer", severity=2)
    pending = ch.get_pending()
    assert len(pending) == 1
    assert pending[0].title == "Outdated deps"
    assert pending[0].severity == 2


def test_min_severity_filters():
    ch = SuggestionChannel()
    ch.push("🔧", "minor", "x", severity=1)
    ch.push("⚠️", "warn", "y", severity=2)
    ch.push("🔴", "crit", "z", severity=3)
    assert len(ch.get_pending(min_severity=2)) == 2
    assert len(ch.get_pending(min_severity=3)) == 1


def test_dismiss_removes_from_pending():
    ch = SuggestionChannel()
    ch.push("⚠️", "warn", "y", severity=2)
    ch.dismiss("warn")
    assert ch.get_pending() == []


def test_display_renders_grouped_block():
    ch = SuggestionChannel()
    ch.push("🔴", "Crit", "boom", severity=3)
    ch.push("🔵", "Info", "hey", severity=1)
    out = ch.display()
    # Only groups with pending suggestions render (CRITICAL + INFO here).
    assert "CRITICAL" in out and "INFO" in out
    assert "Crit" in out and "boom" in out
    assert "Info" in out and "hey" in out


def test_display_renders_warnings_when_present():
    ch = SuggestionChannel()
    ch.push("⚠️", "Warn", "careful", severity=2)
    out = ch.display()
    assert "WARNINGS" in out and "careful" in out


def test_display_empty():
    ch = SuggestionChannel()
    assert "No active suggestions" in ch.display()


def test_summary_counts_by_severity():
    ch = SuggestionChannel()
    ch.push("🔴", "a", "x", severity=3)
    ch.push("🔴", "b", "y", severity=3)
    ch.push("⚠️", "c", "z", severity=2)
    s = ch.summary()
    assert "🔴2" in s and "🟡1" in s


def test_summary_all_clear():
    assert SuggestionChannel().summary() in ("✅ All clear",)


def test_clear_empties():
    ch = SuggestionChannel()
    ch.push("🔵", "a", "x")
    ch.clear()
    assert ch.get_pending() == []


def test_max_history_trims():
    ch = SuggestionChannel(max_history=3)
    for i in range(10):
        ch.push("🔵", f"t{i}", "x")
    assert len(ch.get_pending()) == 3
    assert ch.get_pending()[0].title == "t7"


def test_push_findings_adds_one_per_finding():
    ch = SuggestionChannel()
    ch.push_findings(["3 packages outdated", "2 TS errors"], domain="repo")
    pending = ch.get_pending()
    assert len(pending) == 2
    assert pending[0].message == "3 packages outdated"
    assert pending[0].domain == "repo"
    assert all(p.category == "🔧" for p in pending)


def test_push_findings_empty_and_blank_are_noops():
    ch = SuggestionChannel()
    ch.push_findings([])
    ch.push_findings(None)
    ch.push_findings(["", "   "])
    assert ch.get_pending() == []


def test_push_findings_title_is_leading_segment():
    ch = SuggestionChannel()
    ch.push_findings(["Tests: 0 found — suite missing"])
    pending = ch.get_pending()
    assert pending[0].title == "Tests"
    assert pending[0].message == "Tests: 0 found — suite missing"


def test_push_findings_respects_max_history():
    ch = SuggestionChannel(max_history=3)
    ch.push_findings([f"finding {i}" for i in range(10)])
    assert len(ch.get_pending()) == 3