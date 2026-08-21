"""Honest contract tests for telos/core/research/debt.py (ResearchDebtTracker)."""

import pytest

from telos.core.research.debt import DebtEntry, ResearchDebtTracker


def test_default_tracker_is_empty():
    t = ResearchDebtTracker()
    assert t.total_debt == 0.0
    assert t.debt_entries == []


def test_incur_appends_unresolved_entry():
    t = ResearchDebtTracker()
    t.incur("todooo", severity=2.0, cycle=1)
    assert t.total_debt == 2.0
    assert len(t.debt_entries) == 1
    e = t.debt_entries[0]
    assert isinstance(e, DebtEntry)
    assert e.description == "todooo"
    assert e.severity == 2.0
    assert e.cycle_incurred == 1
    assert e.resolved is False


def test_total_debt_sums_only_unresolved():
    t = ResearchDebtTracker()
    t.incur("a", severity=1.0, cycle=1)
    t.incur("b", severity=2.5, cycle=1)
    assert t.total_debt == pytest.approx(3.5)
    assert len(t.debt_entries) == 2


def test_resolve_marks_entry_resolved():
    t = ResearchDebtTracker()
    t.incur("a", severity=1.0, cycle=1)
    t.incur("b", severity=2.0, cycle=1)
    assert t.resolve("a") is True
    assert t.total_debt == pytest.approx(2.0)
    assert len(t.debt_entries) == 1
    assert t.debt_entries[0].description == "b"


def test_resolve_returns_false_for_unknown():
    t = ResearchDebtTracker()
    assert t.resolve("nope") is False


def test_resolve_returns_false_when_already_resolved():
    t = ResearchDebtTracker()
    t.incur("a", severity=1.0, cycle=1)
    assert t.resolve("a") is True
    assert t.resolve("a") is False


def test_to_dict_fields():
    t = ResearchDebtTracker()
    t.incur("a", severity=1.0, cycle=1)
    t.incur("b", severity=2.0, cycle=1)
    t.resolve("b")
    d = t.to_dict()
    assert d["total_debt"] == pytest.approx(1.0)
    assert d["open_entries"] == 1
    assert d["total_incurred"] == 2
