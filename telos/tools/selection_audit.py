"""
Selection audit + A/B experiment — does mission-progress-aware selection
increase mission progress WITHOUT degrading evidence or safety?

Runs the real GridWorld mission workload under one or all selection policies
and reports the outcome metrics the decision needs:

    % executable intents selected, % inquiry selected, no-op rate,
    mission progress/cycle, episodes completed, moves, mean DI,
    governance-block count.

Policies:
    control                    — current Ω-blend selection
    mission_progress           — damp inquiry blend by executable progress
    mission_progress_readiness — as above, only when execution is READY

Usage:
    PYTHONPATH=. python3 telos/tools/selection_audit.py --policy control --cycles 150
    PYTHONPATH=. python3 telos/tools/selection_audit.py --compare --cycles 150
    PYTHONPATH=. python3 telos/tools/selection_audit.py --dump /tmp/selection.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from typing import Dict, Optional

import numpy as np

POLICIES = ("control", "mission_progress", "mission_progress_readiness")


def _mission_progress_fn(pipeline):
    """Build a domain-aware mission-progress hook for the GridWorld build.

    Args:
        pipeline: the built pipeline (reads config.adapter/config.simulator).

    Returns:
        A callable (state, intent) -> normalized progress toward GOAL.
    """
    from telos_task import GOAL, GRID_SIZE
    adapter = pipeline.config.adapter
    sim = pipeline.config.simulator
    diameter = float(np.sqrt(2.0) * (GRID_SIZE - 1))

    def progress(state, intent):
        if state is None or intent is None:
            return None
        s = np.asarray(state, dtype=float)
        try:
            action = adapter.intent_to_action(intent, s, 0.0)
        except Exception:
            return None
        if action is None:
            return 0.0
        ns = sim.transition(s, action)
        before = float(np.linalg.norm(GOAL[:len(s)] - s))
        after = float(np.linalg.norm(GOAL[:len(s)] - ns))
        return (before - after) / diameter

    return progress


def run(policy: str, cycles: int, dump: Optional[str] = None) -> Dict[str, object]:
    """Run one policy over the GridWorld workload and collect metrics.

    Args:
        policy: the selection_policy to run.
        cycles: number of cycles.
        dump: optional path to write the per-cycle selection JSONL.

    Returns:
        A metrics dict for the policy.
    """
    from telos.tools.theorem_audit import _build
    from telos.core.decision.selection_trace import is_inquiry_intent

    workdir = tempfile.mkdtemp(prefix=f"telos_sel_{policy}_")
    pump, state = _build(workdir)
    pump.config.selection_policy = policy
    pump._mission_progress_fn = _mission_progress_fn(pump)
    sim = pump.config.simulator

    selected_inquiry = 0
    selected_exec = 0
    noop = 0
    moves = 0
    episodes = 0
    di_sum = 0.0
    n = 0
    block_reasons = Counter()
    progress_sum = 0.0
    regimes = Counter()
    dump_rows = []

    for _ in range(cycles):
        res = pump.execute(np.array(state, dtype=float), user_name="selection-audit")
        trace = res.decision_trace
        if trace is None:
            continue
        n += 1
        di_sum += float(getattr(trace, "decision_integrity", 0.0) or 0.0)
        if res.governance_blocked_by:
            block_reasons[res.governance_blocked_by] += 1

        decision = getattr(trace, "selection_decision", None) or {}
        regimes[decision.get("regime", "?")] += 1
        si = trace.selected_intent
        if si is not None:
            if is_inquiry_intent(si):
                selected_inquiry += 1
            else:
                selected_exec += 1

        action = trace.selected_action
        if action is None:
            noop += 1
        elif not res.firewall_blocked:
            ns = sim.transition(state, action)
            if not np.array_equal(ns, state):
                moves += 1
            # observed progress (before -> after), normalized by diameter
            from telos_task import GOAL, GRID_SIZE
            diameter = float(np.sqrt(2.0) * (GRID_SIZE - 1))
            progress_sum += (float(np.linalg.norm(GOAL - state))
                             - float(np.linalg.norm(GOAL - ns))) / diameter
            state = ns

        if dump:
            dump_rows.append(decision)

        if sim.terminal(state):
            episodes += 1
            state = np.array([0.0, 0.0])

    if dump:
        with open(dump, "w") as fh:
            for row in dump_rows:
                fh.write(json.dumps(row) + "\n")

    return {
        "policy": policy,
        "cycles": n,
        "exec_share": selected_exec / n if n else 0.0,
        "inquiry_share": selected_inquiry / n if n else 0.0,
        "noop_rate": noop / n if n else 0.0,
        "moves": moves,
        "episodes": episodes,
        "progress_per_cycle": progress_sum / n if n else 0.0,
        "mean_di": di_sum / n if n else 0.0,
        "governance_blocks": sum(block_reasons.values()),
        "block_reasons": dict(block_reasons),
        "regimes": dict(regimes),
    }


def _line(label: str, m: Dict[str, object]) -> str:
    """Format one policy's metrics as a table row.

    Args:
        label: policy label.
        m: metrics dict from run().

    Returns:
        A formatted row.
    """
    return (f"{label:<26} exec={m['exec_share']*100:5.1f}%  "
            f"inquiry={m['inquiry_share']*100:5.1f}%  "
            f"noop={m['noop_rate']*100:5.1f}%  "
            f"prog/cyc={m['progress_per_cycle']:+.4f}  "
            f"episodes={m['episodes']:3d}  moves={m['moves']:3d}  "
            f"DI={m['mean_di']:.3f}  gov={m['governance_blocks']:3d}")


def main(argv=None) -> int:
    """Run one policy or the full A/B comparison.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Exit code (0 — informational experiment).
    """
    parser = argparse.ArgumentParser(description="Selection A/B audit")
    parser.add_argument("--policy", choices=POLICIES, default="control")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--cycles", type=int, default=150)
    parser.add_argument("--dump", help="write per-cycle selection JSONL")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    print("\n            TELOS selection audit")
    print("=" * 118)
    if args.compare:
        results = [run(p, args.cycles) for p in POLICIES]
        for m in results:
            print(_line(m["policy"], m))
        print("-" * 118)
        control = results[0]
        for m in results[1:]:
            changed = any(abs(float(m[k]) - float(control[k])) > 1e-9 for k in (
                "exec_share", "noop_rate", "progress_per_cycle",
                "episodes", "moves", "governance_blocks"))
            if not changed:
                print(f"{m['policy']:<26} NO EFFECT (policy inert on this "
                      f"workload — mission_progress is non-discriminative)")
                continue
            ok_progress = m["progress_per_cycle"] >= control["progress_per_cycle"]
            ok_exec = m["exec_share"] >= control["exec_share"]
            ok_noop = m["noop_rate"] <= control["noop_rate"] + 1e-9
            ok_evidence = m["mean_di"] >= control["mean_di"] - 0.05
            ok_safety = m["governance_blocks"] <= control["governance_blocks"]
            verdict = all([ok_progress, ok_exec, ok_noop, ok_evidence, ok_safety])
            print(f"{m['policy']:<26} progress>={'Y' if ok_progress else 'N'} "
                  f"exec>={'Y' if ok_exec else 'N'} noop<={'Y' if ok_noop else 'N'} "
                  f"DI>={'Y' if ok_evidence else 'N'} safety>={'Y' if ok_safety else 'N'} "
                  f"=> {'ACCEPT' if verdict else 'REJECT'}")
    else:
        print(_line(args.policy, run(args.policy, args.cycles, dump=args.dump)))
    print("=" * 118)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
