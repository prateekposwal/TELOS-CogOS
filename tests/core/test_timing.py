"""
Honest contract tests for telos/core/governance/timing.py
(InformationReadinessEngine, LockedFact) using ReadinessCondition/ReadinessState
from telos/core/governance/base.py.

Facts progress LOCKED -> READY -> EXPIRED; the engine exposes only READY facts.
"""

from telos.core.governance.timing import InformationReadinessEngine, LockedFact
from telos.core.governance.base import ReadinessCondition, ReadinessState


def test_new_fact_is_locked():
    engine = InformationReadinessEngine()
    engine.register_fact("emergency_plan", conditions=[
        ReadinessCondition("signal_detected", threshold=1.0, description="high_severity_alarm"),
    ])
    fact = engine._facts["emergency_plan"]
    assert fact.state == ReadinessState.LOCKED
    assert engine.is_ready("emergency_plan") is False


def test_fact_with_no_conditions_is_immediately_ready_after_tick():
    engine = InformationReadinessEngine()
    engine.register_fact("unconditional_fact")
    assert engine.is_ready("unconditional_fact") is False
    engine.tick()
    assert engine.is_ready("unconditional_fact") is True


def test_signal_condition_releases_lock():
    engine = InformationReadinessEngine()
    engine.register_fact("disaster_plan", conditions=[
        ReadinessCondition("signal_detected", threshold=1.0, description="high_severity_alarm"),
    ])
    engine.tick()
    assert engine.is_ready("disaster_plan") is False

    engine.emit_signal("high_severity_alarm", strength=1.0)
    engine.tick()
    assert engine.is_ready("disaster_plan") is True


def test_cycle_count_condition_releases_after_threshold_ticks():
    engine = InformationReadinessEngine()
    engine.register_fact("strategic_data", conditions=[
        ReadinessCondition("cycle_count", threshold=3),
    ])
    engine.tick()
    engine.tick()
    assert engine.is_ready("strategic_data") is False
    engine.tick()
    assert engine.is_ready("strategic_data") is True


def test_unknown_condition_type_never_meets():
    engine = InformationReadinessEngine()
    engine.register_fact("mystery", conditions=[
        ReadinessCondition("mission_match", threshold=1.0, description="some_mission"),
    ])
    for _ in range(5):
        engine.tick()
    assert engine.is_ready("mystery") is False
    assert engine._facts["mystery"].state == ReadinessState.LOCKED


def test_conjunctive_conditions_require_all_met():
    engine = InformationReadinessEngine()
    engine.register_fact("both", conditions=[
        ReadinessCondition("cycle_count", threshold=1),
        ReadinessCondition("signal_detected", threshold=1.0, description="go_signal"),
    ])
    engine.tick()  # cycle_count met, but no signal yet
    assert engine.is_ready("both") is False

    engine.emit_signal("go_signal")
    engine.tick()
    assert engine.is_ready("both") is True


def test_manual_release_forces_ready():
    engine = InformationReadinessEngine()
    engine.register_fact("locked_fact", conditions=[
        ReadinessCondition("signal_detected", threshold=1.0, description="never"),
    ])
    assert engine.is_ready("locked_fact") is False
    assert engine.release_manually("locked_fact") is True
    assert engine.is_ready("locked_fact") is True


def test_manual_release_unknown_fact_returns_false():
    engine = InformationReadinessEngine()
    assert engine.release_manually("nonexistent") is False


def test_fact_expires_after_ready_for_more_than_10_cycles():
    engine = InformationReadinessEngine()
    engine.register_fact("expiring")  # no conditions -> ready on next tick
    engine.tick()
    engine.is_ready("expiring") is True
    # 11 more ticks: cycle - cycle_locked(1) > 10 -> expired.
    for _ in range(11):
        engine.tick()
    assert engine._facts["expiring"].state == ReadinessState.EXPIRED
    assert engine.is_ready("expiring") is False


def test_expired_fact_is_not_re_released():
    engine = InformationReadinessEngine()
    engine.register_fact("f", conditions=[
        ReadinessCondition("signal_detected", threshold=1.0, description="s"),
    ])
    engine.emit_signal("s")
    engine.tick()
    assert engine.is_ready("f") is True
    for _ in range(12):
        engine.tick()
    assert engine._facts["f"].state == ReadinessState.EXPIRED
    # Emitting the signal again must not resurrect an EXPIRED fact.
    engine.emit_signal("s")
    engine.tick()
    assert engine._facts["f"].state == ReadinessState.EXPIRED


def test_signals_expire_after_ttl():
    engine = InformationReadinessEngine(signal_ttl=2)
    engine.emit_signal("short_lived")
    assert engine._signals.get("short_lived") is not None

    engine.tick()
    engine.tick()
    engine.tick()
    assert "short_lived" not in engine._signals


def test_stats_reflect_states():
    engine = InformationReadinessEngine()
    engine.register_fact("ready_now")  # no conditions
    engine.register_fact("still_locked", conditions=[
        ReadinessCondition("signal_detected", threshold=1.0, description="never"),
    ])
    engine.tick()
    stats = engine.stats
    assert stats["total_facts"] == 2
    assert stats["ready"] == 1
    assert stats["locked"] == 1
    assert stats["expired"] == 0
    assert stats["cycle"] == 1


def test_is_ready_false_for_unknown_fact():
    engine = InformationReadinessEngine()
    assert engine.is_ready("does_not_exist") is False
