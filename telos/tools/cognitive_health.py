"""
Cognitive-health gate — one consolidated check over the four instruments.

Runs the selection, ACT-gate, council/firewall, and mission-policy audits on
the real GridWorld workload and evaluates a single health verdict against
regression thresholds. `--ci` exits 1 if any invariant regresses.

This is the single gate that protects the throughput arc: action emission,
no-op rate, episode completion, evidence integrity, capability DEFERs, the
circular-evidence rule (low_integrity dissents), model fidelity, and policy
telemetry.

Usage:
    PYTHONPATH=. python3 telos/tools/cognitive_health.py --cycles 150
    PYTHONPATH=. python3 telos/tools/cognitive_health.py --cycles 150 --ci
    PYTHONPATH=. python3 telos/tools/cognitive_health.py --json /tmp/health.json
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Tuple

# (name, measured, comparator, threshold) — thresholds sit just below the
# 2026-09-18 corrected baseline so a real regression fails while noise passes.
CHECKS: List[Tuple[str, float, str, float]] = [
    ("action_emission_rate", 0.0, ">=", 0.75),
    ("noop_rate", 0.0, "<=", 0.25),
    ("episodes_completed", 0.0, ">=", 8),
    ("mean_di", 0.0, ">=", 0.90),
    ("model_fidelity_mean", 0.0, ">=", 0.90),
    ("low_integrity_blocks", 0.0, "<=", 0.0),          # circular-evidence rule
    ("evidence_validator_dissent", 0.0, "<=", 0.0),    # no circular dissent
    ("capability_defers", 0.0, "<=", 0.0),             # after harness fix
    ("risk_tolerance_at_floor", 0.0, "<=", 0.0),       # no threshold railing
    ("unlabeled_policy_changes", 0.0, "<=", 0.0),      # telemetry complete
]


def collect(cycles: int) -> Dict[str, object]:
    """Run all four audits and merge their headline metrics.

    Args:
        cycles: cycles per audit.

    Returns:
        A dict with the raw reports and the measured check values.
    """
    from telos.tools.act_gate_audit import run as run_act
    from telos.tools.council_gate_audit import run as run_council
    from telos.tools.policy_audit import run as run_policy
    from telos.tools.selection_audit import run as run_selection

    act = run_act(cycles)
    council = run_council(cycles)
    policy = run_policy(cycles)
    selection = run_selection("control", cycles)

    def _get(d, *path, default=0.0):
        cur = d
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur if cur is not None else default

    measured = {
        "action_emission_rate": float(act.get("action_rate", 0.0)),
        "noop_rate": float(selection.get("noop_rate", 1.0)),
        "episodes_completed": float(selection.get("episodes", 0)),
        "mean_di": float(_get(council, "di", "mean", default=0.0)),
        "model_fidelity_mean": float(_get(act, "model_fidelity", "mean", default=0.0)),
        "low_integrity_blocks": float(
            (council.get("block_reasons") or {}).get("low_integrity", 0)),
        "evidence_validator_dissent": float(
            (council.get("dissenters") or {}).get("EvidenceProvenanceValidator", 0)),
        "capability_defers": float((act.get("modes") or {}).get("DEFER", 0)),
        "risk_tolerance_at_floor": float(policy.get("at_risk_floor", 0)),
        "unlabeled_policy_changes": float(policy.get("unlabeled_changes", 0)),
    }
    return {
        "reports": {"act_gate": act, "council_gate": council,
                    "policy": policy, "selection": selection},
        "measured": measured,
    }


def evaluate(measured: Dict[str, float]) -> List[Dict[str, object]]:
    """Compare measured values to thresholds.

    Args:
        measured: the measured check values.

    Returns:
        One row per check with passed flag.
    """
    rows = []
    for name, _placeholder, comparator, threshold in CHECKS:
        value = float(measured.get(name, 0.0))
        passed = (value >= threshold) if comparator == ">=" else (value <= threshold)
        rows.append({"check": name, "measured": round(value, 4),
                     "op": comparator, "threshold": threshold, "passed": passed})
    return rows


def main(argv=None) -> int:
    """Run the consolidated gate and print the verdict.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Exit code (0 = healthy, 1 = regression in --ci).
    """
    parser = argparse.ArgumentParser(description="TELOS cognitive-health gate")
    parser.add_argument("--cycles", type=int, default=150)
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--json", help="write the full report to this path")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    data = collect(args.cycles)
    rows = evaluate(data["measured"])
    healthy = all(r["passed"] for r in rows)

    print("\n            TELOS cognitive-health gate")
    print("=" * 72)
    for r in rows:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"  [{mark}] {r['check']:<28} {r['measured']:>8} "
              f"{r['op']} {r['threshold']}")
    print("=" * 72)
    print(f"COGNITIVE HEALTH: {'PASS' if healthy else 'FAIL'} "
          f"({sum(r['passed'] for r in rows)}/{len(rows)} checks)")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"healthy": healthy, "checks": rows, **data}, fh, indent=2)
        print(f"wrote {args.json}")
    return 0 if (healthy or not args.ci) else 1


if __name__ == "__main__":
    raise SystemExit(main())
