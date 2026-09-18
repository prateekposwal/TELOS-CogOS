#!/usr/bin/env python3
"""
TELOS Tool-Channel Scanner — reports every production subprocess/http call site.

PATTERN (one governed channel): TELOS is allowed exactly ONE audited way to
touch the real world — the ActionExecutor (allowlist + firewall + operator
permission + bounded capture). Any other production code that spawns a
subprocess or opens a network connection is an UNGOVERNED channel: it bypasses
that discipline. This scanner makes the bypass surface explicit instead of
silent (same idea as the global-RNG scanner in perf_profiler: measure the
violation, don't hope it isn't there).

Each call site is classified as:
  - governed      — inside the ActionExecutor channel itself (expected);
  - known_bypass  — a DOCUMENTED pre-existing channel scheduled for Phase 1
                    governance (reported, not hidden, not a pass-by-omission);
  - unknown       — anything else: an UNGOVERNED channel that must fail CI.

--ci exits nonzero when any unknown call site exists. Known bypasses are
printed with their reason so the debt is visible.
"""

import argparse
import ast
import json
import os
import sys
from typing import Dict, List, Optional

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

# Production code roots that must route real-world effects through the executor.
SCAN_DIRS = ("telos/core", "telos/world", "telos/adapters", "telos/audit")

# The one governed channel: the executor is SUPPOSED to call subprocess.
GOVERNED = frozenset({
    "telos/core/actions/executor.py",
})

# Documented, pre-existing ungoverned channels. Each is a real debt item that
# Phase 1 (Tool use -> 4.5) migrates under the registry + capability gate. They
# are reported explicitly so the count is honest, never zero-by-omission.
KNOWN_BYPASSES: Dict[str, str] = {
    "telos/core/contracts/model_provider.py": (
        "network chat providers (Ollama/OpenAI/Anthropic) via http.client — "
        "Phase 1 routes them through the tool registry"
    ),
    "telos/core/governance/human_gateway.py": (
        "outbound human-approval webhook via http.client — Phase 1 governs it"
    ),
    "telos/adapters/dev_domain_adapter.py": (
        "dev-domain simulator subprocess — Phase 1 routes it through the executor"
    ),
    "telos/adapters/dev_validation.py": (
        "dev validation subprocess — Phase 1 routes it through the executor"
    ),
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
        {"status": governed|known_bypass|unknown, "reason": str}.
    """
    if relpath in GOVERNED:
        return {"status": "governed", "reason": "the audited ActionExecutor channel"}
    if relpath in KNOWN_BYPASSES:
        return {"status": "known_bypass", "reason": KNOWN_BYPASSES[relpath]}
    return {"status": "unknown", "reason": "ungoverned channel (not documented)"}


def scan(root: str = PROJECT) -> Dict[str, object]:
    """Scan the production roots and classify every call site.

    Args:
        root: repo root to scan (defaults to the project root).

    Returns:
        Dict with governed/known_bypasses/unknown site lists and counts.
    """
    governed: List[Dict[str, object]] = []
    known: Dict[str, Dict[str, object]] = {}
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
                elif status == "known_bypass":
                    entry = known.setdefault(
                        rel, {"path": rel, "reason": verdict["reason"], "calls": []}
                    )
                    entry["calls"].extend(sites)  # type: ignore[union-attr]
                else:
                    for s in sites:
                        unknown.append({"path": rel, **s})
    return {
        "governed": governed,
        "known_bypasses": [known[k] for k in sorted(known)],
        "unknown": unknown,
        "counts": {
            "governed_sites": len(governed),
            "known_bypass_sites": sum(len(v["calls"]) for v in known.values()),
            "unknown_sites": len(unknown),
            "known_bypass_files": len(known),
        },
    }


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
          f"(the ActionExecutor channel)")
    print(f"  known-bypass sites : {counts['known_bypass_sites']} "
          f"across {counts['known_bypass_files']} documented files")
    print(f"  unknown sites      : {counts['unknown_sites']}")
    print("-" * 72)
    print("  Known bypasses (documented debt -> Phase 1):")
    for entry in result["known_bypasses"]:  # type: ignore[union-attr]
        print(f"    - {entry['path']}: {entry['reason']}")
    if result["unknown"]:  # type: ignore[union-attr]
        print("  UNKNOWN (must be governed or documented):")
        for s in result["unknown"]:  # type: ignore[union-attr]
            print(f"    - {s['path']}:{s['lineno']} {s['call']} ({s['kind']})")
    print("=" * 72)
    ok = counts["unknown_sites"] == 0
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
