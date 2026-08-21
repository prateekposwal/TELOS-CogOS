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