"""Honest contract tests for telos/core/research/belief_capital.py."""

import pytest

from telos.core.research.belief_capital import BeliefCapitalAccount, BeliefCapitalMarket


def test_account_defaults():
    a = BeliefCapitalAccount(idea_id="i1", idea_name="n1")
    assert a.evidence == 0.0
    assert a.trust == 0.0
    assert a.influence == 0.0
    assert a.predictions_correct == 0
    assert a.predictions_total == 0


def test_accuracy_uses_max_guard():
    a = BeliefCapitalAccount(idea_id="i1", idea_name="n1")
    assert a.accuracy == 0.0
    a.record_prediction(True)
    assert a.accuracy == 1.0


def test_capital_formula():
    a = BeliefCapitalAccount(idea_id="i1", idea_name="n1")
    expected = a.evidence * 0.4 + a.trust * 0.3 + a.influence * 0.2 + a.accuracy * 0.1
    assert a.capital == expected


def test_record_prediction_correct_raises_evidence_and_trust():
    a = BeliefCapitalAccount(idea_id="i1", idea_name="n1")
    a.record_prediction(True)
    assert a.predictions_total == 1
    assert a.predictions_correct == 1
    assert a.evidence == pytest.approx(0.1)
    assert a.trust == pytest.approx(0.05)


def test_record_prediction_incorrect_drops_trust():
    a = BeliefCapitalAccount(idea_id="i1", idea_name="n1", trust=0.1)
    a.record_prediction(False)
    assert a.predictions_total == 1
    assert a.predictions_correct == 0
    assert a.evidence == 0.0
    assert a.trust == pytest.approx(0.05)


def test_evidence_and_trust_capped_at_one():
    a = BeliefCapitalAccount(idea_id="i1", idea_name="n1")
    for _ in range(30):
        a.record_prediction(True)
    assert a.evidence <= 1.0
    assert a.trust <= 1.0


def test_trust_floor_at_zero():
    a = BeliefCapitalAccount(idea_id="i1", idea_name="n1", trust=0.02)
    for _ in range(5):
        a.record_prediction(False)
    assert a.trust == 0.0


def test_capital_increases_with_correct_predictions():
    a = BeliefCapitalAccount(idea_id="i1", idea_name="n1")
    low = a.capital
    for _ in range(5):
        a.record_prediction(True)
    assert a.capital > low


def test_market_register_and_get():
    m = BeliefCapitalMarket()
    acct = m.register("idea1", "The Big Idea")
    assert m.get("idea1") is acct
    assert m.get("missing") is None


def test_market_record_prediction_ignores_unknown():
    m = BeliefCapitalMarket()
    m.record_prediction("missing", True)
    assert m.to_dict()["total_ideas"] == 0


def test_market_record_prediction_updates_account():
    m = BeliefCapitalMarket()
    m.register("idea1", "A")
    m.record_prediction("idea1", True)
    assert m.get("idea1").predictions_correct == 1


def test_top_ideas_sorted_by_capital_desc():
    m = BeliefCapitalMarket()
    a = m.register("low", "Low")
    b = m.register("high", "High")
    b.record_prediction(True)
    b.record_prediction(True)
    b.record_prediction(True)
    a.record_prediction(True)
    top = m.top_ideas(2)
    assert top[0].idea_id == "high"
    assert [t.idea_id for t in top] == ["high", "low"]


def test_market_to_dict():
    m = BeliefCapitalMarket()
    m.register("idea1", "Star")
    m.record_prediction("idea1", True)
    d = m.to_dict()
    assert d["total_ideas"] == 1
    assert d["top_ideas"][0]["name"] == "Star"
    assert isinstance(d["top_ideas"][0]["capital"], float)
