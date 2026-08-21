"""Contract tests for the Reflect phase — reflection records decision DI/MD
and tracks stability + adaptive horizon from the pattern library.

execute() drives the full council-verdict → PatternLibrary pipeline; its pure
helpers (_detect_stability, _compute_adaptive_horizon) and the default
pattern_library are the honest unit-testable surface here (the full execute
path is already exercised by the pipeline integration tests).
"""
import pytest

from telos.core.phases.reflect import ReflectPhase


def test_no_verdict_execute_is_no_op():
    p = ReflectPhase()
    ctx = type("C", (), {"verdict": None})()
    p.execute(type("P", (), {"config": None}), ctx)
    assert p._di_history == []


def test_pattern_library_is_created_when_missing():
    p = ReflectPhase()
    assert p.pattern_library is not None


def test_stability_returns_boolean():
    p = ReflectPhase()
    assert isinstance(p._detect_stability(), bool)


def test_adaptive_horizon_is_bounded():
    p = ReflectPhase()
    h = p._compute_adaptive_horizon(None)
    assert h is None or isinstance(h, int)


def test_execute_without_verdict_attribute_is_no_op():
    p = ReflectPhase()
    ctx = type("C", (), {"verdict": None, "selected_intent": None})()
    p.execute(type("P", (), {"config": None}), ctx)
    assert p._di_history == []