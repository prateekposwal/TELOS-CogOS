from telos.core.planning_horizon import PlanningHorizon
from telos.intent_ir import IntentIR


def test_planning_horizon():
    horizon = PlanningHorizon()
    intent1 = IntentIR(intent_type="move", confidence=0.9)
    intent2 = IntentIR(intent_type="stop", confidence=0.9)

    horizon.set_plan([intent1, intent2])

    assert horizon.has_plan
    assert horizon.get_next_step() == intent1
    assert horizon.has_plan
    assert horizon.get_next_step() == intent2
    assert not horizon.has_plan


def test_planning_horizon_empty_plan():
    """PlanningHorizon.has_plan is False and get_next_step returns None for empty plan."""
    horizon = PlanningHorizon()
    assert not horizon.has_plan
    assert horizon.get_next_step() is None


def test_planning_horizon_reset():
    """PlanningHorizon.set_plan resets the index mid-execution."""
    horizon = PlanningHorizon()
    intent1 = IntentIR(intent_type="move", confidence=0.9)
    intent2 = IntentIR(intent_type="stop", confidence=0.9)

    horizon.set_plan([intent1])
    assert horizon.get_next_step() == intent1
    assert not horizon.has_plan

    horizon.set_plan([intent1, intent2])
    assert horizon.has_plan
    assert horizon.get_next_step() == intent1
    assert horizon.get_next_step() == intent2
    assert not horizon.has_plan


def test_planning_horizon_read_past_end():
    """PlanningHorizon.get_next_step returns None past the plan end."""
    horizon = PlanningHorizon()
    intent = IntentIR(intent_type="move", confidence=0.9)
    horizon.set_plan([intent])

    assert horizon.get_next_step() == intent
    assert horizon.get_next_step() is None
    assert horizon.get_next_step() is None
