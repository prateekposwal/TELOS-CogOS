"""
RegretMemory — counterfactual "what if" archival with retroactive regret.
Honest contract coverage (telos/core/memory/regret_memory.py):
  - record_decision: builds CounterfactualEntry list from option dicts,
    computes best-alternative regret = max(0, best_sim_score - chosen_outcome),
    per-counterfactual would_have_been_better + regret, and appends a
    RegretRecord (bounded by max_records).
  - Aggregation: get_regret_by_type, average_regret, get_highest_regret_decisions,
    get_decision_types_with_most_regret, get_blind_spots, query_similar_contexts.
  - to_dict serialization.
"""
import pytest

from telos.core.memory.regret_memory import RegretMemory, RegretRecord, CounterfactualEntry


class TestRecordDecision:
    def test_empty_memory_state(self):
        rm = RegretMemory()
        assert rm.record_count == 0
        assert rm.average_regret == 0.0
        assert rm.get_regret_by_type("exploit") == (0.0, 0)
        assert rm.query_similar_contexts("ctx") == []
        assert rm.get_highest_regret_decisions() == []
        assert rm.get_blind_spots() == []

    def test_record_builds_regret_record(self):
        rm = RegretMemory()
        record = rm.record_decision(
            cycle=1, chosen_intent="plan", chosen_score=0.8, chosen_outcome=0.3,
            counterfactual_options=[
                {"intent_type": "explore", "score": 0.9, "metadata": {"k": 1}},
                {"intent_type": "wait", "score": 0.5},
            ],
            decision_type="exploit", context_hash="ctx-1",
        )
        assert isinstance(record, RegretRecord)
        assert record.cycle == 1
        assert record.chosen_intent == "plan"
        assert record.decision_type == "exploit"
        assert record.context_hash == "ctx-1"
        assert len(record.counterfactuals) == 2

    def test_regret_is_best_alternative_minus_outcome(self):
        rm = RegretMemory()
        record = rm.record_decision(
            cycle=1, chosen_intent="plan", chosen_score=0.8, chosen_outcome=0.3,
            counterfactual_options=[
                {"intent_type": "explore", "score": 0.9},
                {"intent_type": "wait", "score": 0.5},
            ],
        )
        assert record.regret == pytest.approx(0.6)

    def test_regret_never_negative_when_chosen_wins(self):
        rm = RegretMemory()
        record = rm.record_decision(
            cycle=1, chosen_intent="plan", chosen_score=0.8, chosen_outcome=0.95,
            counterfactual_options=[{"intent_type": "explore", "score": 0.6}],
        )
        assert record.regret == 0.0
        assert record.counterfactuals[0].would_have_been_better is False

    def test_per_counterfactual_evaluation(self):
        rm = RegretMemory()
        record = rm.record_decision(
            cycle=1, chosen_intent="plan", chosen_score=0.8, chosen_outcome=0.3,
            counterfactual_options=[
                {"intent_type": "explore", "score": 0.9},
                {"intent_type": "wait", "score": 0.2},
            ],
        )
        better, worse = record.counterfactuals
        assert better.would_have_been_better is True
        assert better.regret == pytest.approx(0.6)
        assert worse.would_have_been_better is False
        assert worse.regret == 0.0

    def test_no_counterfactuals_regret_is_chosen_score_gap(self):
        """With no counterfactuals, best_alternative defaults to chosen_score, so
        regret is the gap between the hoped-for score and the realized outcome
        (max(0, chosen_score - chosen_outcome)) — not zero."""
        rm = RegretMemory()
        record = rm.record_decision(
            cycle=1, chosen_intent="plan", chosen_score=0.8, chosen_outcome=0.3,
            counterfactual_options=[],
        )
        assert record.regret == pytest.approx(0.5)
        assert rm._total_counterfactuals == 0

    def test_no_counterfactual_regret_zero_when_outcome_beats_score(self):
        rm = RegretMemory()
        record = rm.record_decision(
            cycle=2, chosen_intent="plan", chosen_score=0.8, chosen_outcome=0.95,
            counterfactual_options=[],
        )
        assert record.regret == 0.0

    def test_counterfactual_entry_dataclass_fields(self):
        from dataclasses import fields
        entry = CounterfactualEntry(
            option_id="cf_0_0", intent_type="explore", simulated_score=0.9,
            actual_score=0.8, would_have_been_better=True, regret=0.4,
            metadata={"k": 1},
        )
        assert entry.option_id == "cf_0_0"
        assert entry.intent_type == "explore"
        assert entry.simulated_score == 0.9
        assert entry.actual_score == 0.8
        assert entry.would_have_been_better is True
        assert entry.regret == 0.4
        assert entry.metadata == {"k": 1}
        assert {f.name for f in fields(CounterfactualEntry)} == {
            "option_id", "intent_type", "simulated_score", "actual_score",
            "would_have_been_better", "regret", "metadata",
        }

    def test_counterfactual_option_id_is_cycle_scoped(self):
        rm = RegretMemory()
        r1 = rm.record_decision(cycle=3, chosen_intent="a", chosen_score=1.0,
                                chosen_outcome=0.5, counterfactual_options=[{"score": 0.9}])
        r2 = rm.record_decision(cycle=3, chosen_intent="b", chosen_score=1.0,
                                chosen_outcome=0.5, counterfactual_options=[{"score": 0.8}])
        assert r1.counterfactuals[0].option_id == "cf_3_0"
        assert r2.counterfactuals[0].option_id == "cf_3_0"

    def test_record_count_and_counterfactual_count(self):
        rm = RegretMemory()
        rm.record_decision(cycle=1, chosen_intent="a", chosen_score=1.0,
                           chosen_outcome=0.5,
                           counterfactual_options=[{"score": 0.9}, {"score": 0.8}])
        rm.record_decision(cycle=2, chosen_intent="b", chosen_score=1.0,
                           chosen_outcome=0.5, counterfactual_options=[{"score": 0.9}])
        assert rm.record_count == 2
        assert rm.to_dict()["total_counterfactuals"] == 3

    def test_max_records_evicts_oldest(self):
        rm = RegretMemory(max_records=2)
        rm.record_decision(cycle=0, chosen_intent="a", chosen_score=1.0,
                           chosen_outcome=0.1, counterfactual_options=[{"score": 0.9}])
        rm.record_decision(cycle=1, chosen_intent="b", chosen_score=1.0,
                           chosen_outcome=0.1, counterfactual_options=[{"score": 0.9}])
        rm.record_decision(cycle=2, chosen_intent="c", chosen_score=1.0,
                           chosen_outcome=0.1, counterfactual_options=[{"score": 0.9}])
        assert rm.record_count == 2
        kept = {r.cycle for r in rm.get_highest_regret_decisions(5)}
        assert kept == {1, 2}


class TestQuery:
    def test_query_similar_contexts_exact_match(self):
        rm = RegretMemory()
        for cycle in range(4):
            rm.record_decision(cycle=cycle, chosen_intent="a", chosen_score=1.0,
                               chosen_outcome=0.5, counterfactual_options=[],
                               context_hash="same" if cycle < 3 else "other")
        matches = rm.query_similar_contexts("same")
        assert [r.cycle for r in matches] == [0, 1, 2]

    def test_query_top_k_returns_most_recent(self):
        rm = RegretMemory()
        for cycle in range(5):
            rm.record_decision(cycle=cycle, chosen_intent="a", chosen_score=1.0,
                               chosen_outcome=0.5, counterfactual_options=[],
                               context_hash="ctx")
        assert [r.cycle for r in rm.query_similar_contexts("ctx", top_k=2)] == [3, 4]

    def test_query_unknown_context_returns_empty(self):
        rm = RegretMemory()
        rm.record_decision(cycle=0, chosen_intent="a", chosen_score=1.0,
                           chosen_outcome=0.5, counterfactual_options=[],
                           context_hash="ctx")
        assert rm.query_similar_contexts("nope") == []


class TestAggregation:
    def test_get_regret_by_type_averages(self):
        rm = RegretMemory()
        rm.record_decision(cycle=1, chosen_intent="a", chosen_score=1.0,
                           chosen_outcome=0.3, counterfactual_options=[{"score": 0.9}],
                           decision_type="exploit")
        rm.record_decision(cycle=2, chosen_intent="b", chosen_score=1.0,
                           chosen_outcome=0.4, counterfactual_options=[{"score": 0.6}],
                           decision_type="exploit")
        avg, count = rm.get_regret_by_type("exploit")
        assert count == 2
        assert avg == 0.4

    def test_get_regret_by_type_unknown(self):
        assert RegretMemory().get_regret_by_type("missing") == (0.0, 0)

    def test_average_regret_over_records(self):
        rm = RegretMemory()
        rm.record_decision(cycle=1, chosen_intent="a", chosen_score=1.0,
                           chosen_outcome=0.3, counterfactual_options=[{"score": 0.9}])
        rm.record_decision(cycle=2, chosen_intent="b", chosen_score=1.0,
                           chosen_outcome=0.4, counterfactual_options=[{"score": 0.6}])
        assert rm.average_regret == 0.4

    def test_highest_regret_decisions_sorted(self):
        rm = RegretMemory()
        rm.record_decision(cycle=1, chosen_intent="a", chosen_score=1.0,
                           chosen_outcome=0.3, counterfactual_options=[{"score": 0.5}])
        rm.record_decision(cycle=2, chosen_intent="b", chosen_score=1.0,
                           chosen_outcome=0.1, counterfactual_options=[{"score": 0.9}])
        top = rm.get_highest_regret_decisions(5)
        assert [r.cycle for r in top] == [2, 1]

    def test_decision_types_ranked_by_avg_regret(self):
        rm = RegretMemory()
        rm.record_decision(cycle=1, chosen_intent="a", chosen_score=1.0,
                           chosen_outcome=0.1, counterfactual_options=[{"score": 0.8}],
                           decision_type="exploit")
        rm.record_decision(cycle=2, chosen_intent="b", chosen_score=1.0,
                           chosen_outcome=0.5, counterfactual_options=[{"score": 0.6}],
                           decision_type="explore")
        ranked = rm.get_decision_types_with_most_regret()
        assert ranked[0][0] == "exploit"
        assert ranked[0][1] > ranked[1][1]

    def test_blind_spot_detected_after_frequent_high_regret(self):
        rm = RegretMemory()
        for cycle in range(5):
            rm.record_decision(cycle=cycle, chosen_intent="choose", chosen_score=0.9,
                               chosen_outcome=0.1,
                               counterfactual_options=[{"intent_type": "alt", "score": 0.5}],
                               decision_type="blind_type")
        blind_spots = rm.get_blind_spots()
        assert len(blind_spots) == 1
        assert blind_spots[0]["decision_type"] == "blind_type"
        assert blind_spots[0]["count"] == 5
        assert blind_spots[0]["severity"] == "medium"

    def test_blind_spot_high_severity_above_half(self):
        rm = RegretMemory()
        for cycle in range(5):
            rm.record_decision(cycle=cycle, chosen_intent="choose", chosen_score=0.9,
                               chosen_outcome=0.05,
                               counterfactual_options=[{"intent_type": "alt", "score": 0.9}],
                               decision_type="severe")
        assert rm.get_blind_spots()[0]["severity"] == "high"

    def test_rare_regret_not_a_blind_spot(self):
        rm = RegretMemory()
        rm.record_decision(cycle=0, chosen_intent="c", chosen_score=0.9,
                           chosen_outcome=0.1,
                           counterfactual_options=[{"intent_type": "alt", "score": 0.9}],
                           decision_type="rare")
        assert rm.get_blind_spots() == []


class TestSerialization:
    def test_to_dict_structure(self):
        rm = RegretMemory()
        rm.record_decision(cycle=1, chosen_intent="plan", chosen_score=0.8,
                           chosen_outcome=0.3,
                           counterfactual_options=[{"intent_type": "explore", "score": 0.9}],
                           decision_type="exploit", context_hash="ctx")
        d = rm.to_dict()
        assert set(d) == {"total_records", "total_counterfactuals", "average_regret",
                          "regret_by_type", "blind_spots", "highest_regret"}
        assert d["total_records"] == 1
        assert d["total_counterfactuals"] == 1
        assert d["average_regret"] == 0.6
        assert d["regret_by_type"]["exploit"] == {"avg": 0.6, "count": 1}
        assert d["highest_regret"][0]["cycle"] == 1
        assert d["highest_regret"][0]["chosen"] == "plan"
