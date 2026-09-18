"""
Council/firewall audit — WHICH validator suppresses cycles, and is it warranted?

Runs the real GridWorld workload and aggregates the per-cycle council/firewall
record: dissenters (validator + reason), DI/evidence-integrity distribution, the
firewall block reason, and the applied DI threshold/domain behind
`low_integrity`. Instrument-first: decide whether the remaining suppression is
justified before touching a threshold.

Usage:
    PYTHONPATH=. python3 telos/tools/council_gate_audit.py --cycles 150
    PYTHONPATH=. python3 telos/tools/council_gate_audit.py --cycles 150 --json /tmp/council.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from typing import Dict, List

from telos.tools.bench_loop import drive


def run(cycles: int) -> Dict[str, object]:
    """Run the workload and aggregate council/firewall suppression telemetry.

    Args:
        cycles: number of cycles.

    Returns:
        An aggregate report dict.
    """
    from telos.tools.theorem_audit import _build

    workdir = tempfile.mkdtemp(prefix="telos_council_gate_")
    pump, _ = _build(workdir)

    n = 0
    block_by = Counter()
    dissenters = Counter()
    dissent_reasons = Counter()
    thresholds = Counter()
    domains = Counter()
    di_values: List[float] = []
    evidence_values: List[float] = []
    low_integrity_dissent: Counter = Counter()

    for step in drive(pump, cycles, user_name="council-gate-audit"):
        trace = step["trace"]
        if trace is None:
            continue
        rec = getattr(trace, "council_gate", None)
        if not rec:
            continue
        n += 1
        if rec.get("decision_integrity") is not None:
            di_values.append(float(rec["decision_integrity"]))
        if rec.get("evidence_integrity") is not None:
            evidence_values.append(float(rec["evidence_integrity"]))
        if rec.get("firewall_blocked_by"):
            block_by[rec["firewall_blocked_by"]] += 1
        for d in rec.get("dissenters", []):
            dissenters[d.get("validator")] += 1
            dissent_reasons[f"{d.get('validator')}: {str(d.get('reason'))[:70]}"] += 1
        if rec.get("applied_di_threshold") is not None:
            thresholds[rec["applied_di_threshold"]] += 1
        if rec.get("di_domain") is not None:
            domains[rec["di_domain"]] += 1
        # When the firewall blocked on low_integrity, capture who dissented.
        if rec.get("firewall_blocked_by") == "low_integrity":
            for d in rec.get("dissenters", []):
                low_integrity_dissent[d.get("validator")] += 1

    def _stats(vals: List[float]) -> Dict[str, object]:
        if not vals:
            return {"n": 0}
        return {"n": len(vals), "min": round(min(vals), 3),
                "mean": round(sum(vals) / len(vals), 3),
                "max": round(max(vals), 3)}

    return {
        "cycles": n,
        "block_reasons": dict(block_by.most_common()),
        "dissenters": dict(dissenters.most_common()),
        "dissent_reasons": dict(dissent_reasons.most_common(10)),
        "applied_thresholds": dict(thresholds.most_common()),
        "di_domains": dict(domains.most_common()),
        "di": _stats(di_values),
        "evidence_integrity": _stats(evidence_values),
        "low_integrity_dissenters": dict(low_integrity_dissent.most_common()),
    }


def main(argv=None) -> int:
    """Run the council/firewall audit and print the aggregate.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Exit code (0 — informational).
    """
    parser = argparse.ArgumentParser(description="Council/firewall audit")
    parser.add_argument("--cycles", type=int, default=150)
    parser.add_argument("--json", help="write the aggregate report to this path")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    report = run(args.cycles)
    print("\n            TELOS council/firewall audit")
    print("=" * 78)
    print(f"  cycles={report['cycles']}")
    print(f"  firewall blocks      : {report['block_reasons']}")
    print(f"  dissent by validator : {report['dissenters']}")
    print(f"  low_integrity source : {report['low_integrity_dissenters']}")
    print(f"  applied DI threshold : {report['applied_thresholds']}")
    print(f"  DI domain            : {report['di_domains']}")
    print(f"  DI                   : {report['di']}")
    print(f"  evidence integrity   : {report['evidence_integrity']}")
    print("  top dissent reasons  :")
    for reason, count in (report["dissent_reasons"] or {}).items():
        print(f"      {count:3d}x  {reason}")
    print("=" * 78)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
