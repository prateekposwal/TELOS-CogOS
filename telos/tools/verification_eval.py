#!/usr/bin/env python3
"""
Verification-rigor evaluation — actually RUNS the adversarial verifiers and
records their measured pass counts.

PATTERN (verification must be executed, not inferred from files — Λ6.5): the
verification_rigor score used to count four module paths (4/4 present = 4.5),
which proves the files exist, not that verification finds anything. This
harness executes the two real adversarial verifiers:

  * the AxiomFalsifier, which sabotages each axiom's inputs and requires the
    real AxiomProver to notice (an axiom that cannot be made to fail is not
    verified);
  * the Falsifiable Theorem Audit, which runs a real, identically-seeded
    GridWorld pipeline twice and evaluates the theorem catalogue against its
    declared nulls.

It writes telos/audit/verification_eval.json with the measured counts, an
explicit criteria map, a machine-checkable verdict and provenance.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/verification_eval.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/verification_eval.py --ci
"""

import argparse
import json
import os
import sys
import tempfile
from typing import Any, Dict, List

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.verifier.axiom_falsifier import AxiomFalsifier  # noqa: E402
from telos.core.verifier.measurement import provenance  # noqa: E402
from telos.core.verifier.theorem_audit import run_audit  # noqa: E402
from telos.tools.theorem_audit import _run  # noqa: E402

PRODUCER = "telos/tools/verification_eval.py"

# The canonical axiom count (AXIOMS.md / genesis = 42). The falsifier must see
# the whole constitution, not a subset.
EXPECTED_AXIOMS = 42

# The behavioural criteria the scorer reads. Locked to the writer by
# tests/core/test_verification_eval.py.
VERIFICATION_CRITERIA: List[str] = [
    "axioms_baseline_green",
    "axioms_all_falsifiable",
    "axiom_count_complete",
    "theorems_all_hold",
]


def evaluate(cycles: int = 12) -> Dict[str, Any]:
    """Run the axiom falsifier and the theorem audit; build the artifact.

    Args:
        cycles: pipeline cycles per identical seeded run for the theorem audit.

    Returns:
        The measurement payload (provenance, criteria, verdict, metrics).
    """
    falsifier = AxiomFalsifier().run()
    with tempfile.TemporaryDirectory(prefix="telos_verif_eval_a_") as wa, \
            tempfile.TemporaryDirectory(prefix="telos_verif_eval_b_") as wb:
        config, traces_a, fp_a = _run(wa, cycles)
        _, _traces_b, fp_b = _run(wb, cycles)
    audit = run_audit(traces_a, config, fp_a, fp_b)

    criteria = {
        "axioms_baseline_green": bool(falsifier["healthy_passed"])
        and not falsifier["healthy_failed"],
        "axioms_all_falsifiable": len(falsifier["unfalsifiable"]) == 0,
        "axiom_count_complete": len(falsifier["results"]) == EXPECTED_AXIOMS,
        "theorems_all_hold": bool(audit["passed"]),
    }
    passed = sum(1 for v in criteria.values() if v)
    return {
        "provenance": provenance(PRODUCER, VERIFICATION_CRITERIA),
        "criteria": criteria,
        "verdict": {
            "passed": passed == len(VERIFICATION_CRITERIA),
            "passed_count": passed,
            "total": len(VERIFICATION_CRITERIA),
        },
        "metrics": {
            "axioms_total": len(falsifier["results"]),
            "axioms_falsifiable": len(falsifier["falsifiable"]),
            "axioms_unfalsifiable": len(falsifier["unfalsifiable"]),
            "healthy_failed": falsifier["healthy_failed"],
            "theorems_total": len(audit["rows"]),
            "theorems_passed": sum(1 for r in audit["rows"] if r["passed"]),
            "theorem_rows": audit["rows"],
        },
    }


def print_report(result: Dict[str, Any]) -> bool:
    """Print the verification evaluation table.

    Args:
        result: the dict returned by evaluate().

    Returns:
        True when every verification criterion passes.
    """
    metrics = result["metrics"]
    print(f"\n{'TELOS Verification-Rigor Evaluation (executed)':^74}")
    print("=" * 74)
    print(f"  {'criterion':<40}{'result':>10}")
    for name, passed in result["criteria"].items():
        print(f"  {name:<40}{'PASS' if passed else 'FAIL':>10}")
    print("-" * 74)
    print(f"  axioms falsifiable: {metrics['axioms_falsifiable']}/"
          f"{metrics['axioms_total']}  "
          f"unfalsifiable: {metrics['axioms_unfalsifiable']}")
    print(f"  theorems passed:    {metrics['theorems_passed']}/"
          f"{metrics['theorems_total']}")
    print("=" * 74)
    verdict = result["verdict"]
    print(f"VERIFICATION EVAL: {'PASS' if verdict['passed'] else 'FAIL'} "
          f"({verdict['passed_count']}/{verdict['total']} criteria)")
    return bool(verdict["passed"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=12,
                    help="pipeline cycles per seeded run (default 12)")
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless every verification criterion passes")
    ap.add_argument("--json", default="telos/audit/verification_eval.json",
                    help="path to write the evaluation JSON")
    args = ap.parse_args()
    res = evaluate(cycles=max(1, args.cycles))
    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(PROJECT, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(res, f, indent=2)
        print(f"(evaluation saved: {out})")
    ok = print_report(res)
    if args.ci:
        sys.exit(0 if ok else 1)
