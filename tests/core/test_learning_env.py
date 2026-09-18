"""
Learning on a REAL environment — reward comes from the world, not our arithmetic.

The earlier learning fixture used a hand-written outcome function, so the
"learning" was arithmetic we authored. This harness uses the real GridWorld
simulator: the reward table lives in telos_task.DEFAULT_REWARDS (outside the
harness), the agent learns only from rewards actually paid, and a frozen
control runs the same environment with no learning.
"""

import numpy as np

from telos.tools.learning_env import (
    evaluate, _run_learned, _run_frozen, _greedy_action, _step,
    EPISODES, EPISODE_STEPS,
)
from telos_task import GridSim, DEFAULT_REWARDS, DEFAULT_BLOCKED, GRID_SIZE


def test_evaluate_passes():
    """The learned arm earns more reward and improves across episodes."""
    result = evaluate()
    assert result["beats_control"] is True
    assert result["learned"]["total_reward"] > result["frozen"]["total_reward"]
    assert result["learned_improved"] is True


def test_evaluate_is_deterministic():
    """Two evaluations on the fixed world are identical."""
    assert evaluate() == evaluate()


def test_reward_is_paid_by_the_world():
    """Landed-on reward equals the simulator's own table (no harness override)."""
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS),
                  random_seed=1)
    state = np.array([0.0, 0.0])
    # Walk right one cell: (1,0) has no reward in DEFAULT_REWARDS.
    _next, paid = _step(sim, state, np.array([1.0, 0.0]))
    assert paid == 0.0
    # Force a high-value cell into the world and confirm the harness reads it.
    sim.rewards[(1, 0)] = 7.5
    _next, paid2 = _step(sim, state, np.array([1.0, 0.0]))
    assert paid2 == 7.5


def test_frozen_control_cannot_learn():
    """The control's reward does not increase between episodes."""
    frozen = _run_frozen()
    first, last = frozen["per_episode_reward"][0], frozen["per_episode_reward"][-1]
    assert last <= first
    assert frozen["discovered"] == 0


def test_learned_arm_discovers_reward_pockets():
    """The learning arm actually reaches world reward cells."""
    learned = _run_learned()
    assert learned["discovered"] > 0
    assert learned["total_reward"] > 0


def test_exploration_escapes_local_optimum():
    """Count-based exploration moves the agent off a zero-value deadlock.

    Regression: a purely value-greedy policy (no visit bonus) oscillates
    (2,0)<->(2,1) forever in this world, because every value starts at 0 and the
    goal bias is symmetric. The visit bonus must break that.
    """
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS),
                  random_seed=3)
    values = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)
    visits = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)
    state = np.array([0.0, 0.0])
    seen = set()
    for _ in range(20):
        key = (int(round(state[0])), int(round(state[1])))
        seen.add(key)
        visits[key[0], key[1]] += 1.0
        action = _greedy_action(values, visits, state, sim)
        state = sim.transition(state, action)
    # It must not be stuck in a 2-cell oscillation.
    assert len(seen) > 2


def test_episode_budget_is_identical_for_both_arms():
    """Both arms run the same number of episodes/steps (fair comparison)."""
    learned = _run_learned()
    frozen = _run_frozen()
    assert len(learned["per_episode_reward"]) == EPISODES
    assert len(frozen["per_episode_reward"]) == EPISODES
    assert len(learned["per_episode_reward"]) == len(frozen["per_episode_reward"])


def test_value_grid_is_learned_from_real_reward():
    """The value grid is non-zero only where the world paid reward."""
    learned = _run_learned()
    grid = np.array(learned["value_grid"])
    assert grid.max() > 0.0
    # And it must be concentrated on actual reward cells, not invented.
    reward_cells = {k for k in DEFAULT_REWARDS}
    nonzero = {(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)
               if grid[x, y] > 0.0}
    assert nonzero <= reward_cells
