"""Tests for MetaErrorAttribution — attributing pipeline errors to subsystems
and tracking longitudinal per-subsystem health."""

from telos.core.meta.error_attribution import (
    ErrorAttributionEngine,
    ErrorAttribution,
    ErrorClass,
    Subsystem,
    SubsystemErrorRecord,
)


def _call(engine, cycle=1, was_blocked=False, should_have_blocked=False,
          council_signals=None, simulation_error=0.0, perception_quality=0.9,
          action_error=0.0, intent_type="explore"):
    return engine.attribute(
        cycle=cycle,
        predicted_state=None,
        actual_state=None,
        was_blocked=was_blocked,
        should_have_blocked=should_have_blocked,
        council_signals=council_signals or [],
        simulation_error=simulation_error,
        perception_quality=perception_quality,
        action_error=action_error,
        intent_type=intent_type,
    )


class TestEnums:
    def test_subsystem_values(self):
        assert Subsystem.PERCEPTION.value == "perception"
        assert Subsystem.STREAM.value == "stream"
        assert Subsystem.SIMULATION.value == "simulation"
        assert Subsystem.COUNCIL.value == "council"
        assert Subsystem.GOVERNANCE.value == "governance"
        assert Subsystem.EXECUTION.value == "execution"
        assert Subsystem.IDENTITY.value == "identity"
        assert Subsystem.UNKNOWN.value == "unknown"

    def test_error_class_values(self):
        assert ErrorClass.FALSE_POSITIVE.value == "false_positive"
        assert ErrorClass.FALSE_NEGATIVE.value == "false_negative"
        assert ErrorClass.MISPLANNING.value == "misplanning"
        assert ErrorClass.MISPERCEPTION.value == "misperception"
        assert ErrorClass.MISATTRIBUTION.value == "misattribution"
        assert ErrorClass.RESOURCE_ERROR.value == "resource_error"
        assert ErrorClass.TIMING_ERROR.value == "timing_error"
        assert ErrorClass.CONSTRAINT_VIOLATION.value == "constraint_violation"


class TestSubsystemRecord:
    def test_record_accumulates(self):
        rec = SubsystemErrorRecord(subsystem=Subsystem.COUNCIL)
        a = ErrorAttribution(
            cycle=1, primary_subsystem=Subsystem.COUNCIL,
            contributing_subsystems=[], error_class=ErrorClass.FALSE_POSITIVE,
            confidence=0.8, evidence={}, description="d",
        )
        rec.record(a)
        rec.record(a)
        assert rec.total_errors == 2
        assert rec.error_counts["false_positive"] == 2
        assert rec.primary_error_class == "false_positive"
        assert rec.error_rate == 1.0

    def test_primary_error_class_none_when_empty(self):
        rec = SubsystemErrorRecord(subsystem=Subsystem.COUNCIL)
        assert rec.primary_error_class is None
        assert rec.error_rate == 0.0

    def test_history_capped(self):
        rec = SubsystemErrorRecord(subsystem=Subsystem.COUNCIL)
        for i in range(rec.max_history + 20):
            rec.record(ErrorAttribution(
                cycle=i, primary_subsystem=Subsystem.COUNCIL,
                contributing_subsystems=[], error_class=ErrorClass.MISATTRIBUTION,
                confidence=0.5, evidence={}, description="d",
            ))
        assert len(rec.recent_attributions) == rec.max_history


class TestAttributionRules:
    def test_unblocked_engine_defaults_to_unknown(self):
        engine = ErrorAttributionEngine()
        a = _call(engine)
        assert a.primary_subsystem == Subsystem.UNKNOWN
        assert a.error_class == ErrorClass.MISATTRIBUTION
        assert a.confidence == 0.3
        assert a.evidence == {"ambiguous": True}

    def test_false_positive_council_block(self):
        engine = ErrorAttributionEngine()
        signals = [
            {"validator_name": "safety", "passed": False},
            {"validator_name": "mission", "passed": True},
        ]
        a = _call(engine, was_blocked=True, should_have_blocked=False,
                  council_signals=signals)
        assert a.primary_subsystem == Subsystem.COUNCIL
        assert a.error_class == ErrorClass.FALSE_POSITIVE
        assert a.confidence == 0.8
        assert a.evidence["verdict"] == "blocked_incorrectly"
        assert a.evidence["blocking_validators"] == ["safety"]

    def test_false_negative_council_pass(self):
        engine = ErrorAttributionEngine()
        signals = [{"validator_name": "safety", "passed": True}]
        a = _call(engine, was_blocked=False, should_have_blocked=True,
                  council_signals=signals)
        assert a.primary_subsystem == Subsystem.COUNCIL
        assert a.error_class == ErrorClass.FALSE_NEGATIVE
        assert a.evidence["verdict"] == "passed_incorrectly"
        assert a.evidence["passing_validators"] == ["safety"]

    def test_simulation_error(self):
        engine = ErrorAttributionEngine()
        a = _call(engine, simulation_error=8.0)
        assert a.primary_subsystem == Subsystem.SIMULATION
        assert a.error_class == ErrorClass.MISPLANNING
        assert a.confidence == 0.8
        assert a.evidence["prediction_error"] == 8.0

    def test_simulation_error_threshold(self):
        engine = ErrorAttributionEngine()
        a = _call(engine, simulation_error=5.001)
        assert a.primary_subsystem == Subsystem.SIMULATION
        b = _call(engine, cycle=2, simulation_error=5.0)
        assert b.primary_subsystem == Subsystem.UNKNOWN

    def test_perception_error(self):
        engine = ErrorAttributionEngine()
        a = _call(engine, perception_quality=0.2)
        assert a.primary_subsystem == Subsystem.PERCEPTION
        assert a.error_class == ErrorClass.MISPERCEPTION
        assert a.confidence == 0.7

    def test_execution_error(self):
        engine = ErrorAttributionEngine()
        a = _call(engine, action_error=0.8)
        assert a.primary_subsystem == Subsystem.EXECUTION
        assert a.error_class == ErrorClass.RESOURCE_ERROR
        assert a.confidence == 0.6


class TestContributors:
    def test_simulation_presence_contributes(self):
        engine = ErrorAttributionEngine()
        a = _call(engine, simulation_error=3.0)
        assert Subsystem.SIMULATION in a.contributing_subsystems

    def test_simulation_not_contributor_when_primary(self):
        engine = ErrorAttributionEngine()
        a = _call(engine, simulation_error=8.0)
        assert Subsystem.SIMULATION not in a.contributing_subsystems

    def test_perception_contributes_below_half(self):
        engine = ErrorAttributionEngine()
        a = _call(engine, perception_quality=0.4)
        assert Subsystem.PERCEPTION in a.contributing_subsystems

    def test_council_contributes_when_blocked(self):
        engine = ErrorAttributionEngine()
        a = _call(engine, was_blocked=True, should_have_blocked=True,
                  simulation_error=7.0)
        assert a.primary_subsystem == Subsystem.SIMULATION
        assert Subsystem.COUNCIL in a.contributing_subsystems


class TestHealthTracking:
    def test_records_are_shared_with_contributors(self):
        engine = ErrorAttributionEngine()
        _call(engine, simulation_error=3.0)
        health = engine.get_subsystem_health()
        assert health["simulation"]["total_errors"] == 1
        assert health["unknown"]["total_errors"] == 1

    def test_fixable_flags(self):
        engine = ErrorAttributionEngine()
        health = engine.get_subsystem_health()
        assert health["council"]["fixable"] is True
        assert health["stream"]["fixable"] is True
        assert health["identity"]["fixable"] is True
        assert health["perception"]["fixable"] is True
        assert health["simulation"]["fixable"] is True
        assert health["governance"]["fixable"] is True
        assert health["execution"]["fixable"] is False
        assert health["unknown"]["fixable"] is False

    def test_subsystem_health_fields(self):
        engine = ErrorAttributionEngine()
        _call(engine)
        health = engine.get_subsystem_health()
        entry = health["unknown"]
        assert set(entry) == {
            "total_errors", "error_rate", "primary_error_class",
            "fixable", "error_breakdown",
        }

    def test_most_erratic_subsystem(self):
        engine = ErrorAttributionEngine()
        _call(engine, was_blocked=True, should_have_blocked=False)
        worst = engine.get_most_erratic_subsystem()
        assert worst is not None
        assert worst[0] == Subsystem.COUNCIL
        assert worst[1] == 1.0

    def test_total_attributions(self):
        engine = ErrorAttributionEngine()
        assert engine.total_attributions == 0
        _call(engine)
        _call(engine, cycle=2, simulation_error=9.0)
        assert engine.total_attributions == 2

    def test_to_dict(self):
        engine = ErrorAttributionEngine()
        _call(engine, was_blocked=True, should_have_blocked=True)
        d = engine.to_dict()
        assert d["total_attributions"] == 1
        assert d["worst_subsystem"] is not None
        assert "subsystem_health" in d