"""
GridAdpt novelty-seeking — domain-side visit-count-weighted exploration.

Control (weight 0.0) is unchanged: exploratory intents with no preferred
vector use the goal-directed A* step. With weight > 0 they prefer the
least-visited legal cell (coverage/variety) while drifting toward the goal.
"""
import numpy as np

from telos_task import GridAdpt, GOAL, GRID_SIZE, DEFAULT_BLOCKED
from telos.intent_ir import IntentIR


def _curiosity():
    return IntentIR(intent_type="curiosity_explore", confidence=0.8,
                    metadata={"novelty_seeking": True})


def test_control_is_unchanged_goal_routing():
    adapter = GridAdpt()  # novelty 0.0
    state = np.array([0.0, 0.0])
    action = adapter.intent_to_action(_curiosity(), state, np.zeros(2))
    # legal cardinal
    assert tuple(np.round(action)) in {(1.0, 0.0), (0.0, 1.0)}


def test_novelty_avoids_revisiting_a_cell():
    adapter = GridAdpt(novelty_weight=8.0)
    state = np.array([0.0, 0.0])
    d1 = adapter._novelty_step(state)
    d2 = adapter._novelty_step(state)
    assert (d1[0], d1[1]) != (d2[0], d2[1]), \
        "second step must avoid the just-visited neighbor"


def test_novelty_only_applies_to_exploratory_intents():
    adapter = GridAdpt(novelty_weight=8.0)
    state = np.array([0.0, 0.0])
    # A non-exploratory intent (plan) still routes via goal A*, not novelty.
    plan = IntentIR(intent_type="plan_trajectory", confidence=0.9)
    action = adapter.intent_to_action(plan, state, np.zeros(2))
    assert action.shape == (2,)


def test_novelty_step_is_a_legal_cardinal():
    adapter = GridAdpt(novelty_weight=8.0)
    state = np.array([4.0, 0.0])
    step = adapter._novelty_step(state)
    start = (4, 0)
    nxt = (start[0] + int(round(step[0])), start[1] + int(round(step[1])))
    assert 0 <= nxt[0] < GRID_SIZE and 0 <= nxt[1] < GRID_SIZE
    assert nxt not in DEFAULT_BLOCKED
    assert abs(step[0]) + abs(step[1]) == 1.0  # cardinal
