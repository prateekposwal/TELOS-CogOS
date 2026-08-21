"""Tests for InterpretationEngine — principle-conflict detection, explanation,
trade-off estimation, resolution recommendation, confidence, and archiving."""

from telos.core.reasoning.interpretation_engine import (
    ConflictType,
    Principle,
    InterpretationEngine,
)
from pytest import approx


def _principle(name, priority=0.5, axiom_ref="N/A"):
    return Principle(name=name, description="", axiom_ref=axiom_ref,
                     current_priority=priority)


class TestConflictType:
    def test_known_types(self):
        assert ConflictType.EXPLORE_VS_EXPLOIT.value == "explore_vs_exploit"
        assert ConflictType.CORRECTNESS_VS_SPEED.value == "correctness_vs_speed"
        assert ConflictType.UNKNOWN.value == "unknown"


class TestDetectConflict:
    def test_detects_registered_name_pair(self):
        engine = InterpretationEngine()
        principles = [
            _principle("Axiom 3.4 (Exploration vs Exploitation)", axiom_ref="3.4"),
            _principle("Axiom 4.2 (Exploration/Comfort Trade-off)", axiom_ref="4.2"),
        ]
        assert engine.detect_conflict(principles, {}) == ConflictType.EXPLORE_VS_EXPLOIT

    def test_detects_substring_principle_names(self):
        engine = InterpretationEngine()
        principles = [
            _principle("Exploration"),
            _principle("Axiom 4.2 (Exploration/Comfort Trade-off)"),
        ]
        assert engine.detect_conflict(principles, {}) == ConflictType.EXPLORE_VS_EXPLOIT

    def test_returns_none_when_no_conflict(self):
        engine = InterpretationEngine()
        principles = [_principle("Prudence"), _principle("Speed")]
        assert engine.detect_conflict(principles, {}) is None

    def test_returns_none_for_single_principle(self):
        engine = InterpretationEngine()
        assert engine.detect_conflict([_principle("Axiom 3.4 (Exploration vs Exploitation)")], {}) is None


class TestInterpret:
    def test_explore_exploit_explanation_tracks_uncertainty(self):
        engine = InterpretationEngine()
        principles = [_principle("Exploration", priority=0.6),
                      _principle("Exploitation", priority=0.4)]
        record = engine.interpret(ConflictType.EXPLORE_VS_EXPLOIT, principles,
                                  {"uncertainty": 0.8})
        assert "exploration" in record.explanation
        assert "Exploration=0.60" in record.explanation
        assert record.resolution == (
            "Use UCB-based selection: explore when uncertainty is high, "
            "exploit when confident."
        )
        assert record.trade_off_estimate == {
            "Exploration": approx(0.24),
            "Exploitation": approx(0.06),
        }
        assert record.resolution_confidence == 0.5
        assert record.archived is True
        assert record.outcome_quality is None
        assert record.id.startswith("conflict_0_")

    def test_high_uncertainty_prefers_exploration(self):
        engine = InterpretationEngine()
        principles = [_principle("Exploration"), _principle("Exploitation")]
        record = engine.interpret(ConflictType.EXPLORE_VS_EXPLOIT, principles,
                                  {"uncertainty": 0.2})
        assert "exploitation" in record.explanation

    def test_correctness_speed_explanation_carries_context(self):
        engine = InterpretationEngine()
        principles = [_principle("Correctness"), _principle("Speed")]
        record = engine.interpret(ConflictType.CORRECTNESS_VS_SPEED, principles,
                                  {"di": 0.9, "time_pressure": "high"})
        assert "DI=0.9" in record.explanation
        assert "time pressure=high" in record.explanation
        assert record.trade_off_estimate == {"Correctness": 0.2, "Speed": 0.2}
        assert record.resolution == (
            "Prioritize correctness for high-impact decisions; "
            "speed for low-impact routine actions."
        )

    def test_unknown_type_generic_path(self):
        engine = InterpretationEngine()
        principles = [_principle("Anything")]
        record = engine.interpret(ConflictType.UNKNOWN, principles, {})
        assert record.explanation == "Principles ['Anything'] are in conflict."
        assert record.resolution == "Escalate to human for resolution."
        assert record.trade_off_estimate == {"Anything": 0.25}

    def test_single_principle_drops_confidence(self):
        engine = InterpretationEngine()
        principles = [_principle("Lone")]
        record = engine.interpret(ConflictType.UNKNOWN, principles, {})
        assert record.resolution_confidence == 0.3

    def test_confidence_rises_with_similar_conflicts_and_caps(self):
        engine = InterpretationEngine()
        principles = [_principle("Exploration"), _principle("Exploitation")]
        confidences = [
            engine.interpret(ConflictType.EXPLORE_VS_EXPLOIT, principles, {}).resolution_confidence
            for _ in range(9)
        ]
        assert confidences[0] == 0.5
        assert confidences[1] == 0.55
        assert confidences[8] == 0.9


class TestArchive:
    def test_records_outcome_by_id(self):
        engine = InterpretationEngine()
        principles = [_principle("Exploration"), _principle("Exploitation")]
        record = engine.interpret(ConflictType.EXPLORE_VS_EXPLOIT, principles, {})
        assert record.outcome_quality is None
        engine.record_outcome(record.id, 0.8)
        assert record.outcome_quality == 0.8

    def test_get_conflicts_by_type_filters_history(self):
        engine = InterpretationEngine()
        e = [_principle("Exploration"), _principle("Exploitation")]
        c = [_principle("Correctness"), _principle("Speed")]
        engine.interpret(ConflictType.EXPLORE_VS_EXPLOIT, e, {})
        engine.interpret(ConflictType.EXPLORE_VS_EXPLOIT, e, {})
        engine.interpret(ConflictType.CORRECTNESS_VS_SPEED, c, {})
        assert len(engine.get_conflicts_by_type(ConflictType.EXPLORE_VS_EXPLOIT)) == 2
        assert len(engine.get_conflicts_by_type(ConflictType.CORRECTNESS_VS_SPEED)) == 1
        assert engine.total_conflicts == 3

    def test_history_capped_at_two_hundred(self):
        engine = InterpretationEngine()
        principles = [_principle("Exploration"), _principle("Exploitation")]
        for _ in range(205):
            engine.interpret(ConflictType.EXPLORE_VS_EXPLOIT, principles, {})
        assert engine.total_conflicts == 205
        assert len(engine._conflict_history) == 200


class TestToDict:
    def test_to_dict_contract(self):
        engine = InterpretationEngine()
        principles = [_principle("Exploration"), _principle("Exploitation")]
        record = engine.interpret(ConflictType.EXPLORE_VS_EXPLOIT, principles, {})
        d = engine.to_dict()
        assert d["total_conflicts"] == 1
        assert d["conflict_types"]["explore_vs_exploit"] == 1
        assert d["conflict_types"]["unknown"] == 0
        assert len(d["recent_conflicts"]) == 1
        assert d["recent_conflicts"][0]["id"] == record.id
        assert d["recent_conflicts"][0]["type"] == "explore_vs_exploit"
        assert d["recent_conflicts"][0]["confidence"] == 0.5