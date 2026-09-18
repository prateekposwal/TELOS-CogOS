#!/usr/bin/env python3
"""
Reproducibility evaluation — MEASURES determinism and RNG isolation on the
real pipeline instead of counting harness files.

PATTERN (measure it, don't infer it — Λ6.5): the reproducibility score used to
count four module paths (perf_profiler/endurance/coverage/pyproject = 4.5).
This harness runs the actual pipeline and measures the two properties the
dimension claims:

  * DETERMINISM — two identically-seeded runs over the same inputs produce an
    identical decision fingerprint.
  * SEED SENSITIVITY — a different seed produces a different fingerprint (so a
    constant fingerprint cannot masquerade as determinism).
  * RNG ISOLATION — a structural scan finds ZERO global ``np.random.*`` /
    ``random.*`` calls in production hot paths (one RNG authority per engine).

It writes telos/audit/reproducibility_eval.json with explicit criteria, the
measured fingerprints, a machine-checkable verdict and provenance.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/reproducibility_eval.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/reproducibility_eval.py --ci
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from typing import Any, Dict, List

import numpy as np

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.verifier.measurement import provenance  # noqa: E402
from telos.tools.endurance import build_pipeline  # noqa: E402
from telos.tools.perf_profiler import _scan_global_rng  # noqa: E402

PRODUCER = "telos/tools/reproducibility_eval.py"

# The behavioural criteria the scorer reads. Locked to the writer by
# tests/core/test_reproducibility_eval.py.
REPRODUCIBILITY_CRITERIA: List[str] = [
    "determinism_same_seed_identical",
    "distinct_seed_differs",
    "rng_isolation_zero_global",
]

DEFAULT_CYCLES = 15


def _fingerprint(cycles: int, seed: int) -> str:
    """Run a fresh fast-mode pipeline and hash its decision fingerprint.

    Args:
        cycles: number of pipeline cycles to execute.
        seed: deterministic seed for the run.

    Returns:
        A hex digest of the per-cycle decision fingerprint.
    """
    cp = tempfile.mkdtemp(prefix="telos_repro_fp_")
    try:
        pipe = build_pipeline(cp, seed=seed, fast=True)
        state = np.array([0.0, 0.0])
        parts = []
        for _ in range(cycles):
            result = pipe.execute(state, user_name="repro")
            trace = result.decision_trace
            parts.append(
                f"{trace.decision_integrity:.3f}:{trace.mission_drift:.3f}:"
                f"{trace.selected_intent.intent_type if trace.selected_intent else 'none'}"
                f":{trace.council_validated}")
            action = trace.selected_action
            if action is not None:
                nxt = pipe.config.simulator.transition(state, action)
                if 0.0 <= float(nxt[0]) <= 4.0 and 0.0 <= float(nxt[1]) <= 4.0:
                    state = nxt
        return hashlib.sha256("|".join(parts).encode()).hexdigest()
    finally:
        shutil.rmtree(cp, ignore_errors=True)


def evaluate(cycles: int = DEFAULT_CYCLES) -> Dict[str, Any]:
    """Measure determinism, seed sensitivity, and RNG isolation.

    Args:
        cycles: pipeline cycles per fingerprint run.

    Returns:
        The measurement payload (provenance, criteria, verdict, metrics).
    """
    fingerprint_a = _fingerprint(cycles, 42)
    fingerprint_b = _fingerprint(cycles, 42)
    fingerprint_other = _fingerprint(cycles, 43)
    rng_hits = _scan_global_rng()

    criteria = {
        "determinism_same_seed_identical": fingerprint_a == fingerprint_b,
        "distinct_seed_differs": fingerprint_a != fingerprint_other,
        "rng_isolation_zero_global": len(rng_hits) == 0,
    }
    passed = sum(1 for v in criteria.values() if v)
    return {
        "provenance": provenance(PRODUCER, REPRODUCIBILITY_CRITERIA),
        "criteria": criteria,
        "verdict": {
            "passed": passed == len(REPRODUCIBILITY_CRITERIA),
            "passed_count": passed,
            "total": len(REPRODUCIBILITY_CRITERIA),
        },
        "metrics": {
            "cycles": cycles,
            "fingerprint_seed42_a": fingerprint_a[:16],
            "fingerprint_seed42_b": fingerprint_b[:16],
            "fingerprint_seed43": fingerprint_other[:16],
            "global_rng_hits": len(rng_hits),
            "global_rng_sites": [f"{f}:{line}" for f, line in rng_hits[:10]],
        },
    }


def print_report(result: Dict[str, Any]) -> bool:
    """Print the reproducibility evaluation table.

    Args:
        result: the dict returned by evaluate().

    Returns:
        True when every reproducibility criterion passes.
    """
    metrics = result["metrics"]
    print(f"\n{'TELOS Reproducibility Evaluation (measured)':^74}")
    print("=" * 74)
    print(f"  {'criterion':<40}{'result':>10}")
    for name, passed in result["criteria"].items():
        print(f"  {name:<40}{'PASS' if passed else 'FAIL':>10}")
    print("-" * 74)
    print(f"  fp(seed=42) a={metrics['fingerprint_seed42_a']} "
          f"b={metrics['fingerprint_seed42_b']}")
    print(f"  fp(seed=43) = {metrics['fingerprint_seed43']}  "
          f"(must differ)")
    print(f"  global RNG hits: {metrics['global_rng_hits']} (must be 0)")
    print("=" * 74)
    verdict = result["verdict"]
    print(f"REPRODUCIBILITY EVAL: {'PASS' if verdict['passed'] else 'FAIL'} "
          f"({verdict['passed_count']}/{verdict['total']} criteria)")
    return bool(verdict["passed"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=DEFAULT_CYCLES,
                    help="pipeline cycles per fingerprint run (default 15)")
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless every reproducibility criterion passes")
    ap.add_argument("--json", default="telos/audit/reproducibility_eval.json",
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
