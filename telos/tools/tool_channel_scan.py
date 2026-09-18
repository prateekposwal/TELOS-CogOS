#!/usr/bin/env python3
"""
TELOS Tool-Channel Scanner — reports every production subprocess/http call site.

PATTERN (one governed channel per effect class): TELOS is allowed exactly ONE
audited way to touch the real world for each effect class:
  * subprocesses  -> the ActionExecutor (allowlist + firewall + operator
    permission + bounded capture);
  * network       -> the NetworkSandbox (host/port/route allowlist + bounds).
Any other production code that spawns a subprocess or opens a network
connection is an UNGOVERNED channel: it bypasses that discipline. This scanner
makes the bypass surface explicit instead of silent (same idea as the global-RNG
scanner in perf_profiler: measure the violation, don't hope it isn't there).

Each call site is classified as:
  - governed — inside one of the governed channels themselves (expected);
  - exempt   — an EXPLICIT, REVIEWED exemption: a documented reason AND the
               phase/plan that would govern it. Never silent. The dev-domain
               external-project validation harness is the only such exemption.
  - unknown  — anything else: an UNGOVERNED channel that must fail CI.

--ci exits nonzero when any unknown call site exists. Exemptions are printed
with their reason + governing plan so the debt is visible, never zero-by-
omission.
"""

import argparse
import ast
import json
import os
import sys
from typing import Dict, List, Optional

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

# Production code roots that must route real-world effects through a governed
# channel (the ActionExecutor for subprocesses, the NetworkSandbox for network).
SCAN_DIRS = ("telos/core", "telos/world", "telos/adapters", "telos/audit")

# The governed channels: the executor is SUPPOSED to call subprocess; the
# sandbox is SUPPOSED to call http.client (it IS the network gate).
GOVERNED = frozenset({
    "telos/core/actions/executor.py",
    "telos/core/actions/sandbox.py",
})

# Explicit, reviewed exemptions. Each MUST carry a non-empty reason AND the
# phase/plan that would govern it; tool_governance_eval.py fails CI if any
# exemption lacks either (an exemption is a reviewed decision, never a silent
# allowance). The two dev-domain files are the SAME external-project validation
# harness: read-only inspection of an operator-supplied project whose command
# argv is DISCOVERED at runtime.
EXEMPTIONS: Dict[str, Dict[str, str]] = {
    "telos/adapters/dev_validation.py": {
        "reason": (
            "External-project validation harness: discovers and runs the target "
            "project's own test/typecheck/lint commands at runtime (argv is a "
            "function of the scanned project, not a fixed operator template) "
            "inside the operator-supplied project_path. It cannot route through "
            "the ActionExecutor without either forbidding all validation or "
            "letting the harness self-authorize arbitrary argv — both worse "
            "governance. Bounded: list-form (never a shell), per-command "
            "timeout, 1MB output cap."
        ),
        "governed_by": (
            "external-project validation executor profile: an operator-declared "
            "project root + a binary allowlist (pytest/npm/yarn/pnpm/npx/tsc/"
            "eslint/go) enforced with the same four gates"
        ),
        "reviewed": "true",
    },
    "telos/adapters/dev_domain_adapter.py": {
        "reason": (
            "Dev-domain snapshot helper: runs `npx eslint` (lint count) and "
            "`du -sk node_modules` (bundle size) read-only over the "
            "operator-supplied project_path, and delegates test/typecheck/lint "
            "to dev_validation.validate_project. Same external-project "
            "measurement channel and rationale as dev_validation.py; read-only "
            "inspection only."
        ),
        "governed_by": (
            "same external-project validation executor profile as "
            "dev_validation.py (shared binary allowlist + same four gates)"
        ),
        "reviewed": "true",
    },
}

_SUBPROCESS_CALLS = frozenset({
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_call", "subprocess.check_output",
})
_NETWORK_CALLS = frozenset({
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    "urllib.request.urlopen",
})


def _dotted(node: ast.AST) -> Optional[str]:
    """Render an attribute chain as a dotted name (e.g. subprocess.run).

    Args:
        node: the AST node to render.

    Returns:
        The dotted name, or None when the node is not a simple name/attribute.
    """
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def iter_call_sites(path: str) -> List[Dict[str, object]]:
    """Find ungoverned-channel call sites in one Python file via AST.

    Args:
        path: absolute path to the Python file to scan.

    Returns:
        List of dicts {lineno, kind, call} for each subprocess/network call.
        Unparseable files return an empty list (never a crash).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
    except (OSError, SyntaxError):
        return []
    hits: List[Dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted(node.func)
        if dotted is None:
            continue
        kind: Optional[str] = None
        if dotted in _SUBPROCESS_CALLS:
            kind = "subprocess"
        elif dotted in _NETWORK_CALLS or dotted.startswith("http.client."):
            kind = "network"
        if kind is not None:
            hits.append({"lineno": node.lineno, "kind": kind, "call": dotted})
    return hits


def classify(relpath: str) -> Dict[str, str]:
    """Classify a production file's channel status by its path.

    Args:
        relpath: repo-relative path (POSIX separators).

    Returns:
        {"status": governed|exempt|unknown, "reason": str}.
    """
    if relpath in GOVERNED:
        return {"status": "governed", "reason": "a governed effect channel"}
    if relpath in EXEMPTIONS:
        return {"status": "exempt", "reason": EXEMPTIONS[relpath]["reason"]}
    return {"status": "unknown", "reason": "ungoverned channel (not documented)"}


def scan(root: str = PROJECT) -> Dict[str, object]:
    """Scan the production roots and classify every call site.

    Args:
        root: repo root to scan (defaults to the project root).

    Returns:
        Dict with governed/exemptions/unknown site lists and counts.
    """
    governed: List[Dict[str, object]] = []
    exempt: Dict[str, Dict[str, object]] = {}
    unknown: List[Dict[str, object]] = []
    for rel_dir in SCAN_DIRS:
        abs_dir = os.path.join(root, rel_dir)
        for dirpath, dirnames, filenames in os.walk(abs_dir):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                abs_path = os.path.join(dirpath, fn)
                rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
                sites = iter_call_sites(abs_path)
                if not sites:
                    continue
                verdict = classify(rel)
                status = verdict["status"]
                if status == "governed":
                    for s in sites:
                        governed.append({"path": rel, **s})
                elif status == "exempt":
                    meta = EXEMPTIONS[rel]
                    entry = exempt.setdefault(
                        rel, {"path": rel, "reason": meta["reason"],
                              "governed_by": meta["governed_by"],
                              "reviewed": meta["reviewed"], "calls": []}
                    )
                    entry["calls"].extend(sites)  # type: ignore[union-attr]
                else:
                    for s in sites:
                        unknown.append({"path": rel, **s})
    return {
        "governed": governed,
        "exemptions": [exempt[k] for k in sorted(exempt)],
        "unknown": unknown,
        "counts": {
            "governed_sites": len(governed),
            "known_bypass_sites": 0,
            "exemption_sites": sum(len(v["calls"]) for v in exempt.values()),
            "exemption_files": len(exempt),
            "unknown_sites": len(unknown),
        },
    }


def exemptions_reviewed(result: Dict[str, object]) -> bool:
    """Whether every reported exemption carries a reason + governing plan.

    Args:
        result: the dict returned by scan().

    Returns:
        True when each exemption names a reason, a governing plan, and is
        marked reviewed (an exemption is never silent).
    """
    for entry in result["exemptions"]:  # type: ignore[union-attr]
        if not str(entry.get("reason") or "").strip():
            return False
        if not str(entry.get("governed_by") or "").strip():
            return False
        if str(entry.get("reviewed")) != "true":
            return False
    return True


def print_report(result: Dict[str, object]) -> bool:
    """Print the scan report.

    Args:
        result: the dict returned by scan().

    Returns:
        True when there are no unknown (ungoverned) call sites.
    """
    counts = result["counts"]  # type: ignore[index]
    print(f"\n{'TELOS Tool-Channel Scan':^72}")
    print("=" * 72)
    print(f"  governed sites     : {counts['governed_sites']} "
          f"(ActionExecutor + NetworkSandbox)")
    print(f"  known-bypass sites : {counts['known_bypass_sites']}")
    print(f"  exempt sites       : {counts['exemption_sites']} "
          f"across {counts['exemption_files']} reviewed files")
    print(f"  unknown sites      : {counts['unknown_sites']}")
    print("-" * 72)
    if result["exemptions"]:  # type: ignore[union-attr]
        print("  Reviewed exemptions (reason -> governing plan):")
        for entry in result["exemptions"]:  # type: ignore[union-attr]
            print(f"    - {entry['path']}: {entry['reason']}")
            print(f"      governed_by: {entry['governed_by']}")
    if result["unknown"]:  # type: ignore[union-attr]
        print("  UNKNOWN (must be governed or exempted):")
        for s in result["unknown"]:  # type: ignore[union-attr]
            print(f"    - {s['path']}:{s['lineno']} {s['call']} ({s['kind']})")
    print("=" * 72)
    ok = counts["unknown_sites"] == 0 and exemptions_reviewed(result)
    print("TOOL CHANNEL:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 when an unknown (ungoverned) channel exists")
    ap.add_argument("--json", default=None, help="write the report JSON here")
    args = ap.parse_args()
    res = scan()
    if args.json:
        with open(args.json, "w") as f:
            json.dump(res, f, indent=2)
        print(f"(report saved: {args.json})")
    ok = print_report(res)
    if args.ci:
        sys.exit(0 if ok else 1)
