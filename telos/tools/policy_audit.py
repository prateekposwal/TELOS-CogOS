"""
Mission-policy audit — the firewall DI threshold and its up-driver.

`firewall_di_threshold = 1 − risk_tolerance`. This runs the real GridWorld
workload and reports the threshold/risk trajectory plus every policy mutation
that moved it, grouped by caller + reason (the PolicyChangeLog audit trail).
Instrument-first: see WHO tightens the firewall and on WHAT evidence before
changing anything.

Usage:
    PYTHONPATH=. python3 telos/tools/policy_audit.py --cycles 150
    PYTHONPATH=. python3 telos/tools/policy_audit.py --cycles 150 --json /tmp/policy.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from typing import Dict, List

from telos.tools.bench_loop import drive


def _stats(vals: List[float]) -> Dict[str, object]:
    """min/mean/max for a list of floats.

    Args:
        vals: numeric values.

    Returns:
        A stats dict (n=0 when empty).
    """
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min": round(min(vals), 3),
            "mean": round(sum(vals) / len(vals), 3), "max": round(max(vals), 3)}


def run(cycles: int) -> Dict[str, object]:
    """Run the workload and aggregate policy-threshold telemetry.

    Args:
        cycles: number of cycles.

    Returns:
        An aggregate report dict.
    """
    from telos.tools.theorem_audit import _build

    workdir = tempfile.mkdtemp(prefix="telos_policy_")
    pump, _ = _build(workdir)

    risk: List[float] = []
    thr: List[float] = []
    unlabeled = 0
    for _ in drive(pump, cycles, user_name="policy-audit"):
        pt = getattr(pump, "_infra_manager", None)
        if pt is None:
            continue
        policy = getattr(pt, "policy", None)
        if policy is None:
            continue
        risk.append(float(policy.current.risk_tolerance))
        thr.append(float(policy.firewall_di_threshold))

    policy = pump._infra_manager.policy
    log = list(getattr(getattr(policy, "_change_log", None), "_changes", []) or [])
    by_caller: Counter = Counter()
    by_reason: Counter = Counter()
    for c in log:
        caller = getattr(c, "caller", "") or "(unlabeled)"
        reason = getattr(c, "reason", "") or "(unlabeled)"
        by_caller[f"{getattr(c,'component','?')}::{caller}"] += 1
        by_reason[f"{getattr(c,'component','?')}::{reason[:50]}"] += 1
        if not getattr(c, "caller", "") and not getattr(c, "reason", ""):
            unlabeled += 1

    return {
        "cycles": len(risk),
        "risk_tolerance": _stats(risk),
        "firewall_di_threshold": _stats(thr),
        "at_risk_floor": sum(1 for v in risk if v <= 0.0501),
        "policy_changes": len(log),
        "unlabeled_changes": unlabeled,
        "by_caller": dict(by_caller.most_common(10)),
        "by_reason": dict(by_reason.most_common(10)),
    }


def main(argv=None) -> int:
    """Run the policy audit and print the aggregate.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Exit code (0 — informational).
    """
    parser = argparse.ArgumentParser(description="Mission-policy audit")
    parser.add_argument("--cycles", type=int, default=150)
    parser.add_argument("--json", help="write the aggregate report to this path")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    report = run(args.cycles)
    print("\n            TELOS mission-policy audit")
    print("=" * 78)
    print(f"  cycles={report['cycles']}  policy_changes={report['policy_changes']} "
          f" unlabeled={report['unlabeled_changes']}")
    print(f"  risk_tolerance        : {report['risk_tolerance']}  "
          f"(at floor 0.05: {report['at_risk_floor']})")
    print(f"  firewall_di_threshold : {report['firewall_di_threshold']}")
    print("  who moves the policy (caller):")
    for k, v in (report["by_caller"] or {}).items():
        print(f"      {v:4d}x  {k}")
    print("=" * 78)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
