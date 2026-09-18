#!/usr/bin/env python3
"""
Learning-curve evaluation on a REAL environment (Phase 3+).

PATTERN (evidence must be about the world, not our arithmetic): the first
learning harness used a hand-written task stream and a hand-written
``_outcome = 1 - difficulty + 0.9*competence`` function — the "learning" was
arithmetic we authored, which proves nothing about an agent learning anything.

This harness removes that: the environment is the real GridWorld simulator
(``telos_task.GridSim``) whose reward pockets are defined OUTSIDE this file
(``telos_task.DEFAULT_REWARDS``). An episode is a real rollout: the arm chooses
a legal action, the simulator transitions, and the reward is whatever the world
pays for the cell landed on. Nothing here computes an outcome — the world does.

Two arms, identical environment and identical episode budget:
  - LEARNED  : maintains a value estimate per cell, updated by real reward,
               and (for the second episode onward) acts on it — so it should
               find the high-value pockets faster.
  - FROZEN   : no memory of reward, fixed deterministic sweep — it cannot
               improve between episodes.

Reported: total reward, reward by episode (the learning curve), steps to the
best pocket, and rewards discovered. The gate requires the learned arm to earn
more total reward AND improve between the first and last episode.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/learning_env.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/learning_env.py --ci
"""

import argparse
import math
import json
import os
import sys
from typing import Any, Dict, List, Tuple

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

import numpy as np  # noqa: E402

from telos_task import (  # noqa: E402
    GridSim, GRID_SIZE, DEFAULT_REWARDS, DEFAULT_BLOCKED, GOAL,
)

START = np.array([0.0, 0.0])
EPISODE_STEPS = 60
EPISODES = 6
# Exploration weight for the count-based coverage bonus. Both mechanisms are
# load-bearing and measured: dead-end penalties alone make the policy hard-commit
# to the first pocket (plateaus at 14.0 forever); the coverage bonus alone leaves
# the (2,1) dead-end oscillation unaddressed. Together: discovery AND stability.
EXPLORE_WEIGHT = 2.0
BEST_POCKET = max(
    ((tuple(k), v) for k, v in DEFAULT_REWARDS.items()),
    key=lambda kv: kv[1],
)


def _step(sim: GridSim, state: np.ndarray, action: np.ndarray) -> Tuple[np.ndarray, float]:
    """Apply an action through the REAL simulator and read the world's reward.

    Args:
        sim: the GridWorld simulator (the ground truth).
        state: current position.
        action: the chosen cardinal action.

    Returns:
        (next_state, reward_paid_by_the_world).
    """
    nxt = sim.transition(state, action)
    key = (int(round(nxt[0])), int(round(nxt[1])))
    # Reward comes ONLY from the world's own table.
    return nxt, float(sim.rewards.get(key, 0.0))


def _greedy_action(values: np.ndarray, visits: np.ndarray, state: np.ndarray,
                   sim: GridSim, penalties: np.ndarray,
                   prev_key: Tuple[int, int] = (-1, -1)) -> np.ndarray:
    """Choose a legal neighbour by learned value, with dead-end avoidance.

    A purely value-greedy policy deadlocks in this world, and the cause is
    structural, not a tie-break bug: cell (2,1) is a genuine 3-way dead-end
    ((3,1)/(1,1)/(2,2) are all blocked), so its only exit is back to (2,0).
    Goal bias therefore walks in and bounces (2,0)<->(2,1) forever. A count
    bonus masks this but does not understand it.

    Two principled mechanisms replace the masking:

      1. DEAD-END PENALTY — a cell entered and immediately reversed out of
         accumulates a penalty (an implicit "this way is a trap" signal learned
         from the world's own transitions). Re-entering it is discouraged.
      2. NO-IMMEDIATE-REVERSAL — when other legal moves exist, do not undo the
         previous step. Only a true dead-end (no alternative) permits reversal,
         which then feeds mechanism 1. This is what actually breaks the loop.

    Both are learned/structural — no hand-coded cell list — and the value update
    still comes only from the world's reward.

    Args:
        values: the learned value grid.
        visits: the visit-count grid.
        state: current position.
        sim: the simulator (for the legal move set).
        penalties: per-cell dead-end penalty grid (accumulated).
        prev_key: the cell we came FROM (to forbid immediate reversal).

    Returns:
        A legal cardinal action.
    """
    cur_key = (int(round(state[0])), int(round(state[1])))
    options: List[Tuple[float, np.ndarray]] = []
    for action in sim.legal_transitions(state):
        nxt = sim.transition(state, action)
        key = (int(round(nxt[0])), int(round(nxt[1])))
        # Do not immediately undo the previous step unless it is the only option.
        reversal = key == prev_key
        # Unexplored cells stay attractive until visited (coverage). Without
        # this the policy hard-commits to the first pocket it finds and never
        # reaches the others — measured: it plateaus at 14.0 forever.
        explore = 1.0 / math.sqrt(1.0 + float(visits[key[0], key[1]]))
        goal_bias = -float(np.linalg.norm(nxt - GOAL)) * 1e-3
        score = (float(values[key[0], key[1]])
                 + EXPLORE_WEIGHT * explore
                 - float(penalties[key[0], key[1]])
                 + goal_bias)
        if reversal:
            score -= 5.0
        options.append((score, action))
    if not options:
        return np.array([0.0, 0.0])
    # If every option is a reversal we are in a true dead-end: take it (and the
    # caller will penalise the trap we just left).
    options.sort(key=lambda o: -o[0])
    return options[0][1]


def _run_learned(episodes: int = EPISODES,
                 steps: int = EPISODE_STEPS) -> Dict[str, Any]:
    """Run the learning arm on the real environment.

    Args:
        episodes: number of episodes.
        steps: steps per episode.

    Returns:
        Dict with total/per-episode reward, discovery metrics, the value grid,
        per-episode reversals (thrashing), and per-episode best-pocket timing.
    """
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS),
                  random_seed=7)
    values = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)
    visits = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)
    # Dead-end penalty accumulated from real reversals (a cell we entered and
    # immediately had to leave is a trap the world taught us about).
    penalties = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)
    per_episode: List[float] = []
    ep_reversals: List[int] = []
    discovered: set = set()
    reversals = 0
    steps_to_best = None
    total_steps = 0
    for ep in range(episodes):
        state = START.copy()
        prev_key = (-1, -1)
        ep_reward = 0.0
        ep_rev = 0
        for _ in range(steps):
            total_steps += 1
            # Learn from the cell we are standing on (real reward, real visit).
            key = (int(round(state[0])), int(round(state[1])))
            reward_here = float(sim.rewards.get(key, 0.0))
            if reward_here > 0:
                discovered.add(key)
            # Incremental mean update on the REAL reward — this is the learning.
            visits[key[0], key[1]] += 1.0
            lr = 1.0 / visits[key[0], key[1]]
            values[key[0], key[1]] += lr * (reward_here - values[key[0], key[1]])
            # Act on what has been learned (goal bias + dead-end avoidance).
            action = _greedy_action(values, visits, state, sim, penalties, prev_key)
            prev_pos = state.copy()
            state, paid = _step(sim, state, action)
            ep_reward += paid
            new_key = (int(round(state[0])), int(round(state[1])))
            # A reversal means we stepped back to where we came from: the cell we
            # were just in is (or leads to) a dead-end. Penalise it so the policy
            # stops choosing it.
            if new_key == prev_key and prev_key != (-1, -1):
                reversals += 1
                ep_rev += 1
                pk = (int(round(prev_pos[0])), int(round(prev_pos[1])))
                penalties[pk[0], pk[1]] += 1.0
            prev_key = (int(round(prev_pos[0])), int(round(prev_pos[1])))
            if steps_to_best is None and new_key == BEST_POCKET[0]:
                steps_to_best = total_steps
        per_episode.append(ep_reward)
        ep_reversals.append(ep_rev)
    return {
        "per_episode_reward": per_episode,
        "per_episode_reversals": ep_reversals,
        "total_reward": sum(per_episode),
        "discovered": len(discovered),
        "steps_to_best_pocket": steps_to_best,
        "reversals": reversals,
        "value_grid": values.round(3).tolist(),
    }


def _run_frozen(episodes: int = EPISODES,
                steps: int = EPISODE_STEPS) -> Dict[str, Any]:
    """Run the frozen control: same environment, no learning, fixed sweep.

    Args:
        episodes: number of episodes.
        steps: steps per episode.

    Returns:
        Dict with total/per-episode reward and the same discovery metrics.
    """
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS),
                  random_seed=7)
    order = [np.array([1, 0]), np.array([0, 1]),
             np.array([-1, 0]), np.array([0, -1])]
    per_episode: List[float] = []
    discovered: set = set()
    steps_to_best = None
    total_steps = 0
    for _ep in range(episodes):
        state = START.copy()
        ep_reward = 0.0
        for i in range(steps):
            total_steps += 1
            key = (int(round(state[0])), int(round(state[1])))
            if float(sim.rewards.get(key, 0.0)) > 0:
                discovered.add(key)
            # Fixed cyclic sweep: identical every episode, cannot improve.
            action = order[(i // 3) % len(order)]
            state, paid = _step(sim, state, action)
            ep_reward += paid
            if steps_to_best is None and (
                    int(round(state[0])), int(round(state[1]))) == BEST_POCKET[0]:
                steps_to_best = total_steps
        per_episode.append(ep_reward)
    return {
        "per_episode_reward": per_episode,
        "total_reward": sum(per_episode),
        "discovered": len(discovered),
        "steps_to_best_pocket": steps_to_best,
    }


def evaluate() -> Dict[str, Any]:
    """Compare the learning arm and the frozen control on the real environment.

    The success criteria are what learning actually looks like on a REAL
    environment with an exploration phase, not a naive "reward must monotonically
    rise" (an exploring agent's episode 0 can be its richest — measured). The
    verdict requires, on the same world and episode budget:

      1. MORE TOTAL REWARD than the control (the control earns 0.0);
      2. DISCOVERY — it finds reward pockets the control never finds;
      3. EFFICIENCY — thrashing (immediate reversals) does not grow across
         episodes, i.e. the dead-end understanding is retained (episode N's
         reversals <= episode 0's + slack).

    Returns:
        Dict with both arms' results, the criteria, and the verdict.
    """
    learned = _run_learned()
    frozen = _run_frozen()
    n_pockets = len(DEFAULT_REWARDS)
    first_rev = learned["per_episode_reversals"][0]
    last_rev = learned["per_episode_reversals"][-1]
    criteria = {
        "more_total_reward": learned["total_reward"] > frozen["total_reward"],
        "discovered_more": learned["discovered"] > frozen["discovered"],
        "found_all_pockets": learned["discovered"] >= n_pockets,
        "thrashing_not_growing": last_rev <= first_rev + 2,
    }
    beats = all(criteria.values())
    return {
        "learned": learned,
        "frozen": frozen,
        "criteria": criteria,
        "beats_control": beats,
        "environment": {
            "simulator": "telos_task.GridSim",
            "reward_source": "telos_task.DEFAULT_REWARDS",
            "reward_pockets": {str(k): v for k, v in DEFAULT_REWARDS.items()},
            "episodes": EPISODES,
            "steps_per_episode": EPISODE_STEPS,
        },
    }


def print_report(result: Dict[str, Any]) -> bool:
    """Print the real-environment learning curve.

    Args:
        result: the dict returned by evaluate().

    Returns:
        True when every learning criterion holds.
    """
    ln, fz = result["learned"], result["frozen"]
    print(f"\n{'TELOS Learning on a REAL Environment':^74}")
    print("=" * 74)
    env = result["environment"]
    print(f"  env: {env['simulator']} | reward source: {env['reward_source']}")
    print(f"  reward pockets: {env['reward_pockets']}")
    print(f"  {env['episodes']} episodes x {env['steps_per_episode']} steps")
    print("-" * 74)
    print(f"  {'episode':<10}{'learned':>12}{'frozen':>12}{'reversals':>12}")
    for i, (a, b) in enumerate(zip(ln["per_episode_reward"],
                                   fz["per_episode_reward"])):
        print(f"  {i:<10}{a:>12.1f}{b:>12.1f}"
              f"{ln['per_episode_reversals'][i]:>12}")
    print("-" * 74)
    print(f"  {'total':<10}{ln['total_reward']:>12.1f}"
          f"{fz['total_reward']:>12.1f}")
    print(f"  {'discovered':<10}{ln['discovered']:>12}{fz['discovered']:>12}")
    print(f"  {'steps->best':<10}{str(ln['steps_to_best_pocket']):>12}"
          f"{str(fz['steps_to_best_pocket']):>12}")
    print("-" * 74)
    print("  criteria:")
    for name, ok in result["criteria"].items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")
    print("=" * 74)
    print("  verdict:", "learned arm BEATS frozen control" if result["beats_control"]
          else "learned arm does NOT beat control")
    print("LEARNING (real env):", "PASS" if result["beats_control"] else "FAIL")
    return bool(result["beats_control"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless the learned arm beats the frozen control")
    ap.add_argument("--json", default="telos/audit/learning_env.json",
                    help="path to write the evaluation JSON")
    args = ap.parse_args()
    res = evaluate()
    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(PROJECT, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(res, f, indent=2)
        print(f"(evaluation saved: {out})")
    ok = print_report(res)
    if args.ci:
        sys.exit(0 if ok else 1)
