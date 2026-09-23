"""
Exploration audit (A/B) — does giving curiosity its own vector break the loop?

Control: `curiosity_explore` carries no `action_vector`, so `GridAdpt` falls
back to the goal-directed A* step (identical trajectory every episode).
Treatment: `PipelineConfig.curiosity_explore_probability = p` attaches a seeded
exploratory vector with probability p, so the adapter sometimes random-walks.

Measures trajectory variety (distinct positions, action transitions), mission
progress (episodes, goal progress/move), and safety/evidence (DI, blocks).

Usage:
    PYTHONPATH=. python3 telos/tools/exploration_audit.py --cycles 200 --compare
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from typing import Dict

import numpy as np

from telos.tools.bench_loop import drive


def _distance_progress(before, after, goal) -> float:
    """Normalized reduction in goal distance for one step.

    Args:
        before: state before the step.
        after: state after the step.
        goal: the goal coordinate.

    Returns:
        (dist_before - dist_after) / grid diameter.
    """
    from telos_task import GRID_SIZE
    diameter = float(np.sqrt(2.0) * (GRID_SIZE - 1))
    return (float(np.linalg.norm(goal - before))
            - float(np.linalg.norm(goal - after))) / diameter


def run(prob: float, cycles: int) -> Dict[str, object]:
    """Run the workload at a given curiosity-exploration probability.

    Args:
        prob: `curiosity_explore_probability` (0.0 = control).
        cycles: number of cycles.

    Returns:
        A metrics dict.
    """
    from telos.tools.theorem_audit import _build
    from telos_task import GOAL

    workdir = tempfile.mkdtemp(prefix="telos_explore_")
    pump, _ = _build(workdir)
    pump.config.curiosity_explore_probability = prob
    sim = pump.config.simulator

    positions = set()
    actions = []
    episodes = 0
    noop = 0
    di_sum = 0.0
    blocks = 0
    progress = 0.0
    n = 0
    vector_intents = 0

    for step in drive(pump, cycles, user_name="exploration-audit"):
        trace = step["trace"]
        if trace is None:
            continue
        n += 1
        di_sum += float(getattr(trace, "decision_integrity", 0.0) or 0.0)
        res = step["result"]
        if res.governance_blocked_by:
            blocks += 1
        positions.add(tuple(step["state_before"]))
        si = trace.selected_intent
        if si is not None and si.intent_type == "curiosity_explore" \
                and (si.params or {}).get("action_vector") is not None:
            vector_intents += 1
        action = trace.selected_action
        actions.append(None if action is None else tuple(np.round(action, 3)))
        if action is None:
            noop += 1
        else:
            progress += _distance_progress(step["state_before"], step["state_after"], GOAL)
        if step["terminal"]:
            episodes += 1

    transitions = sum(1 for i in range(1, len(actions)) if actions[i] != actions[i - 1])
    distinct_actions = len({a for a in actions if a is not None})
    return {
        "prob": prob,
        "cycles": n,
        "distinct_positions": len(positions),
        "distinct_actions": distinct_actions,
        "action_transitions": transitions,
        "episodes": episodes,
        "noop_rate": noop / n if n else 0.0,
        "di_mean": di_sum / n if n else 0.0,
        "blocks": blocks,
        "progress_per_cycle": progress / n if n else 0.0,
        "vector_intents": vector_intents,
    }


def _line(m: Dict[str, object]) -> str:
    """Format one arm's metrics.

    Args:
        m: metrics dict from run().

    Returns:
        A formatted row.
    """
    return (f"p={m['prob']:.2f}     "
            f"positions={m['distinct_positions']:3d} "
            f"actions={m['distinct_actions']:2d} "
            f"transitions={m['action_transitions']:4d} "
            f"episodes={m['episodes']:3d} "
            f"noop={m['noop_rate']*100:5.1f}% "
            f"prog/cyc={m['progress_per_cycle']:+.4f} "
            f"DI={m['di_mean']:.3f} blocks={m['blocks']:3d} "
            f"vec_intents={m['vector_intents']:3d}")


def main(argv=None) -> int:
    """Run the exploration A/B.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Exit code (0 — informational).
    """
    parser = argparse.ArgumentParser(description="Curiosity-exploration A/B")
    parser.add_argument("--cycles", type=int, default=200)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--grid", default="0.0,0.15,0.3,0.5",
                        help="comma-separated probabilities to sweep")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    print("\n            TELOS exploration audit")
    print("=" * 108)
    if args.compare:
        probs = [float(x) for x in args.grid.split(",")]
        results = [run(p, args.cycles) for p in probs]
        control = results[0]
        for m in results:
            print(_line(m))
        print("-" * 108)
        for m in results[1:]:
            variety = (m["distinct_positions"] > control["distinct_positions"]
                       or m["action_transitions"] > control["action_transitions"])
            prog = m["progress_per_cycle"] >= control["progress_per_cycle"] - 1e-9
            eps = m["episodes"] >= control["episodes"] - 1
            di = m["di_mean"] >= control["di_mean"] - 0.05
            safe = m["blocks"] <= control["blocks"]
            print(f"p={m['prob']:.2f}: variety={'Y' if variety else 'N'} "
                  f"progress={'Y' if prog else 'N'} episodes={'Y' if eps else 'N'} "
                  f"DI={'Y' if di else 'N'} safety={'Y' if safe else 'N'} => "
                  f"{'ACCEPT' if all([variety, prog, eps, di, safe]) else 'REJECT'}")
    else:
        print(_line(run(0.0, args.cycles)))
    print("=" * 108)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
