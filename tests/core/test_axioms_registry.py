"""Test for axioms registry — the machine-readable axiom constitution.

Verifies that the AXIOMS list in core/axioms/registry.py is well-formed,
has the correct number of axioms (42), and that enforcement statuses are
honest (enforced / scaffold / aspirational).

Axiom 5.2 (Λ5.2): A → Proposal → Human → Update — the registry is the
single source of truth; self_audit checks that declared count matches.
"""

import pytest

from telos.core.axioms.registry import AXIOMS, AXIOM_IDS, accounted_count,     enforced_ids, accounting


def test_registry_has_42_axioms():
    """The axiom registry must declare exactly 42 axioms."""
    assert accounted_count() == 42,         f"Expected 42 axioms, got {accounted_count()}"


def test_axiom_ids_are_unique_and_ordered():
    """All axiom ids must be unique and in constitution order."""
    ids = AXIOM_IDS
    assert len(ids) == len(set(ids)), "Duplicate axiom ids found"
    assert ids == sorted(ids, key=lambda x: int(x.split(".")[0]) * 10 + int(x.split(".")[1])),         "Axiom ids not in constitution order"


def test_enforcement_statuses_are_honest():
    """Enforcement status must be one of enforced, scaffold, or aspirational."""
    valid_statuses = {"enforced", "scaffold", "aspirational"}
    for axiom in AXIOMS:
        assert axiom["enforcement"] in valid_statuses,             f"Invalid enforcement status '{axiom['enforcement']}' for axiom {axiom['id']}"


def test_at_least_one_enforced():
    """At least one axiom must be enforced (not all aspirational)."""
    enforced = enforced_ids()
    assert len(enforced) > 0, "At least one axiom must be enforced"


def test_accounting_totals_match():
    """The accounting totals must sum to the total axiom count."""
    acct = accounting()
    assert acct["enforced"] + acct["scaffold"] + acct["aspirational"] == acct["total"],         f"Accounting totals don't sum: {acct}"
