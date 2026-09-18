"""
ACT-gate audit — measure WHY cycles do not execute.

Runs the real GridWorld workload and aggregates the per-cycle act-gate record
(governor decision mode/reason, failed capability gates, capability profile,
model fidelity, firewall/governance blocks, action emission). This is the
instrument-first step for the throughput bottleneck identified by the selection
experiment.

Usage:
    PYTHONPATH=. python3 telos/tools/act_gate_audit.py --cycles 150
    PYTHONPATH=. python3 telos/tools/act_gate_audit.py --cycles 150 --json /tmp/act_gate.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import Counter
from typing import Dict, List

import numpy as np

_FLOAT_RE = re.compile(r"value=([0-9.]+)")


def run(cycles: int) -> Dict[str, object]:
    """Run the workload and aggregate the act-gate telemetry.

    Args:
        cycles: number of cycles.

    Returns:
        An aggregate report dict.
    """
    from telos.tools.theorem_audit import _build

    from telos.tools.bench_loop import drive

    workdir = tempfile.mkdtemp(prefix="telos_act_gate_")
    pump, _ = _build(workdir)

    records: List[Dict] = []
    for step in drive(pump, cycles, user_name="act-gate-audit"):
        trace = step["trace"]
        if trace is None:
            continue
        rec = getattr(trace, "act_gate", None)
        if rec:
            records.append(rec)

    n = len(records)
    modes = Counter(r.get("decision_mode") for r in records)
    reasons = Counter(r.get("governor_reason") for r in records)
    blocked_by_gate = Counter(r.get("blocked_by_gate") for r in records)
    fw_blocks = Counter(r.get("firewall_blocked_by") for r in records
                        if r.get("firewall_blocked_by"))
    gate_fail = Counter()
    dim_fail = Counter()
    mf_values: List[float] = []
    mf_tested = Counter()
    for r in records:
        for g in r.get("failed_gates", []) or []:
            gate_fail[g] += 1
        for name, status in (r.get("capability_profile") or {}).items():
            if status == "FAIL":
                dim_fail[name] += 1
        detail = (r.get("capability_details") or {}).get("model_fidelity", "")
        m = _FLOAT_RE.search(str(detail))
        if m:
            mf_values.append(float(m.group(1)))
        if "tested=True" in str(detail):
            mf_tested["tested"] += 1
        elif "tested=False" in str(detail):
            mf_tested["untested"] += 1

    emitted = sum(1 for r in records if r.get("action_emitted"))
    return {
        "cycles": n,
        "action_emitted": emitted,
        "action_rate": emitted / n if n else 0.0,
        "modes": dict(modes),
        "governor_reasons": dict(reasons.most_common(8)),
        "blocked_by_gate": dict(blocked_by_gate.most_common(8)),
        "failed_gates": dict(gate_fail.most_common()),
        "dimension_fails": dict(dim_fail.most_common()),
        "firewall_blocked_by": dict(fw_blocks.most_common()),
        "model_fidelity": {
            "n": len(mf_values),
            "min": min(mf_values) if mf_values else None,
            "max": max(mf_values) if mf_values else None,
            "mean": (sum(mf_values) / len(mf_values)) if mf_values else None,
            "below_0.5": sum(1 for v in mf_values if v < 0.5),
            "tested": dict(mf_tested),
        },
    }


def main(argv=None) -> int:
    """Run the act-gate audit and print the aggregate.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Exit code (0 — informational).
    """
    parser = argparse.ArgumentParser(description="ACT-gate audit")
    parser.add_argument("--cycles", type=int, default=150)
    parser.add_argument("--json", help="write the aggregate report to this path")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    report = run(args.cycles)
    print("\n            TELOS ACT-gate audit")
    print("=" * 74)
    print(f"  cycles={report['cycles']}  action_emitted={report['action_emitted']} "
          f"({report['action_rate']*100:.1f}%)")
    print(f"  decision modes     : {report['modes']}")
    print(f"  failed gates       : {report['failed_gates']}")
    print(f"  dimension FAILs    : {report['dimension_fails']}")
    print(f"  blocked_by_gate    : {report['blocked_by_gate']}")
    print(f"  firewall blocks    : {report['firewall_blocked_by']}")
    print(f"  governor reasons   : {report['governor_reasons']}")
    print(f"  model fidelity     : {report['model_fidelity']}")
    print("=" * 74)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
