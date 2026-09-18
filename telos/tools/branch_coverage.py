"""
Branch coverage — real line+branch measurement via coverage.py.

`coverage_priority` answers "is this module referenced by a test at all?".
This tool answers the harder question: **which lines and branches inside the
module actually execute during the suite**, and which critical modules are
least exercised. It runs the real pytest suite under `coverage --branch`,
aggregates line+branch coverage per module, and ranks the worst offenders by
criticality (impact = uncovered_points x package weight).

Usage:
    PYTHONPATH=. python3 telos/tools/branch_coverage.py --top 25
    PYTHONPATH=. python3 telos/tools/branch_coverage.py --ci --threshold 55
    PYTHONPATH=. python3 telos/tools/branch_coverage.py --json telos/audit/branch_coverage.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[2]
TELOS = REPO / "telos"
BASELINE = TELOS / "audit" / "branch_coverage.json"

# Package criticality weights (mirror coverage_priority — one dial for both).
_CRITICAL_PACKAGES = {
    "runtime.py": 5.0, "phases": 4.0, "council": 4.0, "governance": 4.0,
    "verifier": 4.0, "infra_manager": 3.5, "knowledge": 3.0,
    "reasoning": 3.0, "simulation": 3.0, "streams": 3.0, "identity": 2.5,
    "coordination": 2.5, "memory": 2.5, "decision": 2.5, "types.py": 5.0,
}


def _weight(rel: str) -> float:
    """Criticality weight for a telos-relative module path.

    Args:
        rel: e.g. "core/phases/streams.py".

    Returns:
        A positive weight (higher = more load-bearing).
    """
    parts = rel.split("/")
    for key, weight in _CRITICAL_PACKAGES.items():
        if rel == key or (key.endswith(".py") and parts[-1] == key) or key in parts:
            return weight
    return 1.0


def _run_suite(source: str = "telos") -> Dict[str, object]:
    """Run pytest under coverage and return the parsed JSON report.

    Args:
        source: coverage `--source` target (default: the telos package).

    Returns:
        The parsed coverage JSON (with a `files` mapping).

    Raises:
        RuntimeError: if coverage cannot produce a report.
    """
    with tempfile.TemporaryDirectory(prefix="telos_cov_") as tmp:
        data_file = os.path.join(tmp, ".coverage")
        json_file = os.path.join(tmp, "cov.json")
        env = dict(os.environ, PYTHONPATH=".", COVERAGE_FILE=data_file)
        run = subprocess.run(
            [sys.executable, "-m", "coverage", "run", "--branch",
             f"--source={source}", "-m", "pytest", "tests/", "-q", "--tb=no",
             "-p", "no:cacheprovider"],
            cwd=str(REPO), env=env, capture_output=True, text=True)
        if run.returncode not in (0, 1):  # pytest exit 1 = tests failed (reported separately)
            raise RuntimeError(f"coverage run failed: {run.stderr[-400:]}")
        rep = subprocess.run(
            [sys.executable, "-m", "coverage", "json", "-o", json_file],
            cwd=str(REPO), env=env, capture_output=True, text=True)
        if rep.returncode != 0 or not os.path.exists(json_file):
            raise RuntimeError(f"coverage json failed: {rep.stderr[-400:]}")
        with open(json_file) as fh:
            return json.load(fh)


def summarize(payload: Dict[str, object], scope: str = "all") -> Dict[str, object]:
    """Compute overall and per-module branch coverage from a coverage JSON.

    Args:
        payload: parsed coverage JSON.
        scope: "all" (default) or "core" (restrict to telos/core — the runtime
            denominator, excluding CLI tools that are exercised by hand).

    Returns:
        dict with overall totals/percent and a ranked `rows` list.
    """
    files = payload.get("files", {})
    tot_points = tot_covered = 0
    rows: List[Dict[str, object]] = []

    for path, entry in files.items():
        if scope == "core" and "/core/" not in path.replace("\\", "/"):
            continue
        s = entry.get("summary", {})
        stmts = s.get("num_statements", 0)
        covered = s.get("covered_lines", 0)
        branches = s.get("num_branches", 0)
        cbranches = s.get("covered_branches", 0)
        points = stmts + branches
        hit = covered + cbranches
        if points == 0:
            continue
        rel = os.path.relpath(path, str(TELOS))
        pct = 100.0 * hit / points
        w = _weight(rel)
        rows.append({
            "module": f"telos/{rel}",
            "points": points,
            "covered": hit,
            "uncovered": points - hit,
            "percent": round(pct, 2),
            "weight": w,
            "impact": round((points - hit) * w, 1),
        })
        tot_points += points
        tot_covered += hit

    rows.sort(key=lambda r: (-r["impact"], r["percent"]))
    overall = 100.0 * tot_covered / tot_points if tot_points else 0.0
    return {
        "overall_percent": round(overall, 2),
        "total_points": tot_points,
        "covered_points": tot_covered,
        "files": len(rows),
        "rows": rows,
    }


def main(argv=None) -> int:
    """Run coverage, print the summary + worst offenders, gate in --ci.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Exit code (0 = pass/report, 1 = below --threshold in --ci).
    """
    parser = argparse.ArgumentParser(description="Branch coverage measurement")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--scope", choices=("all", "core"), default="all")
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--json", help="write the full report to this path")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    report = summarize(_run_suite(), scope=args.scope)
    report["scope"] = args.scope
    print("\n            TELOS branch coverage (line+branch)")
    print("=" * 70)
    print(f"  overall : {report['overall_percent']:.2f}%  "
          f"({report['covered_points']}/{report['total_points']} points, "
          f"{report['files']} modules)")
    print(f"{'impact':>7} {'cover%':>7} {'pts':>6}  module")
    for row in report["rows"][:args.top]:
        print(f"{row['impact']:>7} {row['percent']:>7.1f} {row['points']:>6}  {row['module']}")
    print("=" * 70)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"wrote {args.json}")

    if args.ci and report["overall_percent"] < args.threshold:
        print(f"BRANCH COVERAGE: FAIL ({report['overall_percent']:.2f}% < {args.threshold})")
        return 1
    if args.ci:
        print("BRANCH COVERAGE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
