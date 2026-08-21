"""Contract tests for MissionLifecycleEngine — completion, death/rebirth,
and failure transitions (the mission ladder)."""
import pytest

from telos.core.identity.mission_lifecycle import (
    MissionLifecycleEngine, LifecycleTransition,
)
from telos.core.identity.mission import Mission, MissionLifecycle


def _mission(name="proj"):
    return Mission(id=name, name=name, description="d")


def test_detect_completion_returns_transition():
    m = _mission()
    t = MissionLifecycleEngine().detect_completion(m, all_projects_completed=True,
                                                   cycle=10)
    assert isinstance(t, LifecycleTransition)
    assert t.new_status == "completed"
    assert m.lifecycle == MissionLifecycle.COMPLETED


def test_detect_completion_noop_when_not_all_done():
    m = _mission()
    t = MissionLifecycleEngine().detect_completion(m, all_projects_completed=False,
                                                   cycle=10)
    assert t is None


def test_mark_failed_sets_failed_lifecycle():
    m = _mission()
    MissionLifecycleEngine().mark_failed(m, cycle=5, reason="abandoned")
    assert m.lifecycle == MissionLifecycle.FAILED
    assert m.completion_cycle == 5


def test_execute_mission_death_noop_on_active():
    m = _mission()
    t = MissionLifecycleEngine().execute_mission_death(
        m, 1, None, None)
    assert t is None