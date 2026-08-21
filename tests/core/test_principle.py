"""Contract tests for scale/principle — the Scale-Invariance Principle
definition (one deliberation law at every granularity, Λ1.1)."""
from telos.core.scale.principle import (
    ScaleInvariancePrinciple, CANONICAL_PHASES, CANONICAL_AXIOM_COUNT,
)


def test_canonical_phases_span_the_law():
    assert CANONICAL_PHASES[0] == "perceive"
    assert "council" in CANONICAL_PHASES
    assert "reflect" in CANONICAL_PHASES
    assert len(CANONICAL_PHASES) >= 9


def test_canonical_axiom_count_is_42():
    assert CANONICAL_AXIOM_COUNT == 42


def test_matches_phases_exact():
    pr = ScaleInvariancePrinciple()
    assert pr.matches_phases(CANONICAL_PHASES) is True
    assert pr.matches_phases(("perceive", "council")) is False


def test_axiom_set_bound_sanity():
    pr = ScaleInvariancePrinciple()
    assert pr.axiom_set_is_constitutional(frozenset({"1.1", "2.3"})) is True
    assert pr.axiom_set_is_constitutional(frozenset()) is False


def test_principle_carries_documented_fields():
    pr = ScaleInvariancePrinciple()
    assert pr.id == "P1.0"
    d = pr.to_dict()
    assert d["canonical_phases"] == list(CANONICAL_PHASES)
    assert d["canonical_axiom_count"] == 42
    assert set(d["scales"]) == {"macro", "meso", "micro"}