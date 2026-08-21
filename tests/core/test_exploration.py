"""Contract tests for AutonomousExplorer — self-directed goal generation
when curiosity is high enough (autonomous curiosity-driven exploration)."""
import json

from telos.core.curiosity.exploration import AutonomousExplorer, ExplorationGoal
from telos.core.curiosity.drive import CuriosityDrive


def _explorer():
    return AutonomousExplorer(curiosity=CuriosityDrive())


def test_high_curiosity_generates_goals():
    e = _explorer()
    e._curiosity.state.curiosity_level = 0.9
    goals = e.generate_goals(cycle=1)
    assert any(g.source == "curiosity" for g in goals)
    assert any(g.priority > 0.8 for g in goals)


def test_low_curiosity_generates_none():
    e = _explorer()
    e._curiosity.state.curiosity_level = 0.1
    assert e.generate_goals(cycle=1) == []


def test_should_explore_is_a_property_reflecting_curiosity():
    e = _explorer()
    e._curiosity.state.curiosity_level = 0.9
    assert e.should_explore is True
    e._curiosity.state.curiosity_level = 0.1
    assert e.should_explore is False


def test_goal_persistence_is_capped():
    e = _explorer()
    e._curiosity.state.curiosity_level = 0.9
    for i in range(5):
        e.generate_goals(cycle=i)
    assert len(e._goals) <= e._max_goals
    assert e.to_dict()["has_goals"] is True


def test_to_dict_is_serializable():
    e = _explorer()
    e._curiosity.state.curiosity_level = 0.9
    e.generate_goals(cycle=1)
    json.dumps(e.to_dict())


def test_set_unknown_unknown_is_null_safe():
    e = _explorer()
    e.set_unknown_unknown(None)
    assert e.generate_goals(cycle=1) == []