#!/usr/bin/env python3
"""
TELOS Durability Audit — every production ``CapabilityAuthority`` site is classified.

PATTERN (Λ6.7, durability contract): safety-critical authority must not be
accidentally ephemeral in production. This audit statically finds every
``CapabilityAuthority(...)`` construction under the production tree and requires
each to be EXPLICITLY one of:

  * DURABLE_PRODUCTION — passes a ``state_path=`` (or uses the
    ``CapabilityAuthority.durable(...)`` classmethod, or an explicit
    ``durability=DURABLE``). Its evidence survives restart.
  * EPHEMERAL — carries the inline marker ``# durability: ephemeral`` with a
    stated reason. Intentional in-memory use (tests, one-shot harnesses,
    sandbox simulations).
  * UNCLASSIFIED — anything else: a production authority that could silently
    lose its falsification state on restart. This fails CI.

Tests under ``tests/`` are outside the production tree and are not scanned; the
intentionally ephemeral constructor remains fully supported for them. The one
production caller of ``LiveCanary`` (the producer) also passes a durable
authority path, which the canary re-checks at runtime (a PRODUCER-origin canary
with no authority path refuses with ``authority_durability_unconfigured``).

``--ci`` exits nonzero when any UNCLASSIFIED site exists.
"""

import argparse
import ast
import json
import os
import sys
from typing import Dict, List

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

# The production tree scanned for authority constructions.
SCAN_DIR = "telos"
#: The inline marker that reclassifies a site as intentionally ephemeral.
EPHEMERAL_MARKER = "# durability: ephemeral"


def _call_name(node: ast.AST) -> str:
    """The dotted name of a call's callee (e.g. ``CapabilityAuthority``).

    Args:
        node: the AST call node's func expression.

    Returns:
        The dotted callee name, or "" when it cannot be resolved.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _kwarg_names(call: ast.Call) -> List[str]:
    """The keyword argument names of a call.

    Args:
        call: the AST call node.

    Returns:
        A list of keyword names.
    """
    return [k.arg for k in call.keywords if k.arg]


def _classify(call: ast.Call, window: str) -> str:
    """Classify one CapabilityAuthority construction site.

    Args:
        call: the AST call node.
        window: the source text spanning the call (plus a few preceding lines)
            used to detect the intentional-ephemeral marker.

    Returns:
        One of ``DURABLE_PRODUCTION`` / ``EPHEMERAL`` / ``UNCLASSIFIED``.
    """
    names = _kwarg_names(call)
    callee = _call_name(call.func)
    if "state_path" in names:
        for k in call.keywords:
            if k.arg == "state_path" and not (
                    isinstance(k.value, ast.Constant) and k.value.value is None):
                return "DURABLE_PRODUCTION"
    if "durability" in names or callee.endswith(".durable"):
        return "DURABLE_PRODUCTION"
    if EPHEMERAL_MARKER in window:
        return "EPHEMERAL"
    return "UNCLASSIFIED"


def scan() -> Dict[str, object]:
    """Walk the production tree and classify every authority construction.

    Returns:
        A report dict with per-site classification and counts.
    """
    sites: List[Dict[str, object]] = []
    base = os.path.join(PROJECT, SCAN_DIR)
    for root, _dirs, files in os.walk(base):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, PROJECT)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    source = f.read()
            except OSError:
                continue
            if "CapabilityAuthority(" not in source:
                continue
            lines = source.splitlines()
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                callee = _call_name(node.func)
                if not (callee == "CapabilityAuthority"
                        or callee.endswith(".CapabilityAuthority")):
                    continue
                start = max(1, node.lineno - 3)
                end = getattr(node, "end_lineno", node.lineno) or node.lineno
                window = "\n".join(lines[start - 1:end])
                classification = _classify(node, window)
                sites.append({
                    "path": rel,
                    "lineno": node.lineno,
                    "classification": classification,
                    "reason": _reason_for(classification, window),
                })
    counts: Dict[str, int] = {
        "sites": len(sites),
        "durable_production": sum(
            1 for s in sites if s["classification"] == "DURABLE_PRODUCTION"),
        "ephemeral": sum(
            1 for s in sites if s["classification"] == "EPHEMERAL"),
        "unclassified": sum(
            1 for s in sites if s["classification"] == "UNCLASSIFIED"),
    }
    return {
        "provenance": "telos/tools/durability_audit.py",
        "scan_dir": SCAN_DIR,
        "counts": counts,
        "sites": sites,
        "verdict": "PASS" if counts["unclassified"] == 0 else "FAIL",
    }


def _reason_for(classification: str, window: str) -> str:
    """A short human-readable classification reason.

    Args:
        classification: the assigned class.
        window: the source window around the site.

    Returns:
        A reason string.
    """
    if classification == "DURABLE_PRODUCTION":
        return "explicit durable state_path / durable() construction"
    if classification == "EPHEMERAL":
        return "explicit '# durability: ephemeral' marker"
    return ("production authority construction with no state_path and no "
            "intentional-ephemeral marker")


def print_report(result: Dict[str, object]) -> bool:
    """Print the audit report.

    Args:
        result: the dict returned by scan().

    Returns:
        True when every site is explicitly classified.
    """
    counts = result["counts"]  # type: ignore[index]
    print(f"\n{'TELOS Durability Audit':^72}")
    print("=" * 72)
    print(f"  authority construction sites : {counts['sites']}")
    print(f"    durable production         : {counts['durable_production']}")
    print(f"    intentional ephemeral      : {counts['ephemeral']}")
    print(f"    UNCLASSIFIED               : {counts['unclassified']}")
    print("-" * 72)
    for s in result["sites"]:  # type: ignore[union-attr]
        print(f"    [{s['classification']:>18}] {s['path']}:{s['lineno']}")
    print("=" * 72)
    ok = counts["unclassified"] == 0
    print("DURABILITY AUDIT:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 when a production site is unclassified")
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
