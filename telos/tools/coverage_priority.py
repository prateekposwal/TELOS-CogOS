"""
Coverage priority — rank genuinely-uncovered core modules by criticality.

WHY THIS EXISTS
---------------
`self_audit` check 27 matched a module to a test only by basename
(`builder.py` -> `test_builder.py`). TELOS's tests are named by *feature*
(`test_theory_builder.py`, `test_research_amplification_gate.py`), so the
check reported 150+ "untested" modules that were in fact exercised. That is a
broken metric driving a phantom backlog.

This tool measures real coverage: a module is covered when a test file either
imports its dotted path or references a symbol it defines. It then ranks the
genuinely-uncovered modules by criticality = fan-in (how many modules depend
on it) weighted by package importance and size, so the backlog is worked
highest-risk-first.

Usage:
    PYTHONPATH=. python3 telos/tools/coverage_priority.py --top 40
    PYTHONPATH=. python3 telos/tools/coverage_priority.py --json /tmp/cov.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
TELOS = REPO / "telos"
CORE = TELOS / "core"
TESTS = REPO / "tests"

# Packages whose failure is most load-bearing (weight multiplies fan-in).
CRITICAL_PACKAGES = {
    "runtime.py": 5.0, "phases": 4.0, "council": 4.0, "governance": 4.0,
    "verifier": 4.0, "infra_manager": 3.5, "knowledge": 3.0,
    "reasoning": 3.0, "simulation": 3.0, "streams": 3.0, "identity": 2.5,
    "coordination": 2.5, "memory": 2.5, "decision": 2.5, "types.py": 5.0,
}

# Generic symbol names that would create false "covered" positives.
_GENERIC = {"main", "run", "process", "validate", "evaluate", "update", "reset",
            "build", "load", "save", "observe", "get", "set", "factory", "init"}


def _iter_files(root: Path):
    """Yield .py files under root, skipping caches.

    Args:
        root: directory to walk.

    Returns:
        Generator of Path objects.
    """
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                yield Path(dirpath) / f


def _module_dotted(rel: str) -> str:
    """Convert a core-relative path to a dotted module path.

    Args:
        rel: e.g. "reasoning/theory/builder.py".

    Returns:
        e.g. "telos.core.reasoning.theory.builder".
    """
    return "telos.core." + rel[:-3].replace(os.sep, ".").replace("/", ".")


def _public_symbols(path: Path) -> List[str]:
    """Extract public top-level class/function names defined in a module.

    Args:
        path: the module file.

    Returns:
        List of symbol names (no leading underscore, non-generic).
    """
    try:
        text = path.read_text()
    except OSError:
        return []
    names = re.findall(r"^(?:class|def)\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.M)
    return [n for n in names if not n.startswith("_") and n not in _GENERIC]


def _load_test_blobs() -> List[str]:
    """Load all test-file source texts.

    Returns:
        List of test file contents.
    """
    blobs = []
    for path in _iter_files(TESTS):
        if path.name.startswith("test_") or path.name == "conftest.py":
            try:
                blobs.append(path.read_text())
            except OSError:
                pass
    return blobs


def _load_src_blobs(exclude: Path) -> List[Tuple[str, str]]:
    """Load non-test source blobs for fan-in counting.

    Args:
        exclude: a path to skip (the module itself).

    Returns:
        List of (path, text) pairs.
    """
    blobs = []
    for path in _iter_files(TELOS):
        if path == exclude:
            continue
        try:
            blobs.append((str(path), path.read_text()))
        except OSError:
            pass
    entry = REPO / "telos_task.py"
    if entry.exists():
        blobs.append((str(entry), entry.read_text()))
    return blobs


def _fan_in(symbol: str, dotted: str, src_blobs: List[Tuple[str, str]]) -> int:
    """Count source files that import the module (by dotted path or symbol).

    Args:
        symbol: module basename (e.g. "builder").
        dotted: full dotted module path.
        src_blobs: source (path, text) pairs.

    Returns:
        Number of distinct importer files.
    """
    dotted_frag = dotted.replace("telos.core.", "")
    count = 0
    for _path, text in src_blobs:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if dotted in stripped or dotted_frag in stripped or symbol in stripped:
                count += 1
                break
    return count


def _coverage_weight(rel: str) -> float:
    """Criticality weight for a module by package/name.

    Args:
        rel: core-relative module path.

    Returns:
        A positive weight (higher = more load-bearing).
    """
    parts = rel.split(os.sep)
    for key, weight in CRITICAL_PACKAGES.items():
        if rel == key or (key.endswith(".py") and parts[-1] == key) or key in parts:
            return weight
    return 1.0


def analyze() -> Dict[str, object]:
    """Compute the coverage picture over telos/core.

    Returns:
        dict with `total`, `covered`, `uncovered` (int), and `rows` (ranked
        list of uncovered modules with fan_in/loc/score).
    """
    test_blobs = _load_test_blobs()
    tests_join = "\n".join(test_blobs)
    modules = []
    for path in _iter_files(CORE):
        if path.name == "__init__.py":
            continue
        modules.append(path)

    covered = 0
    uncovered_paths = []
    for path in modules:
        rel = str(path.relative_to(CORE))
        dotted = _module_dotted(rel)
        dotted_frag = dotted.replace("telos.core.", "")
        referenced = (dotted in tests_join) or (dotted_frag in tests_join)
        if not referenced:
            for sym in _public_symbols(path):
                # A specific symbol reference counts as coverage of the module.
                if len(sym) >= 6 and tests_join.count(sym) >= 1:
                    referenced = True
                    break
        if referenced:
            covered += 1
        else:
            uncovered_paths.append((path, rel))

    rows = []
    for path, rel in uncovered_paths:
        src_blobs = _load_src_blobs(exclude=path)
        try:
            loc = sum(1 for _ in path.open())
        except OSError:
            loc = 0
        fan = _fan_in(path.stem, _module_dotted(rel), src_blobs)
        weight = _coverage_weight(rel)
        score = round((fan + 1) * weight * (1.0 + loc / 500.0), 3)
        rows.append({"module": f"core/{rel}", "fan_in": fan, "loc": loc,
                     "weight": weight, "score": score})
    rows.sort(key=lambda r: (-r["score"], -r["fan_in"]))

    return {
        "total": len(modules),
        "covered": covered,
        "uncovered": len(uncovered_paths),
        "rows": rows,
    }


def main(argv=None) -> int:
    """Print the prioritized coverage backlog.

    Args:
        argv: optional argv list.

    Returns:
        Exit code (0 always — informational).
    """
    parser = argparse.ArgumentParser(description="Prioritized coverage backlog")
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--json", help="write the full report as JSON")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    report = analyze()
    pct = 100.0 * report["covered"] / max(report["total"], 1)
    print(f"Coverage (referenced-by-test): {report['covered']}/{report['total']} "
          f"({pct:.1f}%) — {report['uncovered']} genuinely uncovered")
    print(f"{'score':>7} {'fanin':>5} {'loc':>5}  module")
    for row in report["rows"][:args.top]:
        print(f"{row['score']:>7} {row['fan_in']:>5} {row['loc']:>5}  {row['module']}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
