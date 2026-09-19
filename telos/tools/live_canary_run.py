#!/usr/bin/env python3
"""
Live-canary runner — earn LIVE-CERTIFIED from LIVE evidence, or do not.

PATTERN (the two-tier transition, measured not asserted — Λ6.5): this tool runs
the bounded, reversible live-producer canary for ``filesystem.write`` against the
disposable sandbox target, records the full
``prediction -> execution -> observation -> Reality Gap -> authority -> admission``
trace, and evaluates that LIVE evidence against the certification invariants.
Only when the live evidence holds may ``filesystem.write`` be persisted to the
canonical LIVE registry — and that persistence is an explicit operator act
(``--persist``); the default is to report and leave the registry fail-closed.

The sandbox SANDBOX-CERTIFIED evidence is preserved separately and is NEVER
promoted by this tool unless the LIVE bar is actually met.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/live_canary_run.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/live_canary_run.py --ci
  PYTHONPATH=. ./.venv/bin/python telos/tools/live_canary_run.py --persist
"""

import argparse
import json
import os
import sys
from typing import Any, Dict

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.actions.live_canary import (  # noqa: E402
    CAPABILITY, CANARY_TARGET, DEFAULT_CANARY_ARTIFACT_PATH, DEFAULT_MAX_ACTIONS,
    DEFAULT_SANDBOX_ROOT, ORIGIN_RUNNER, CanaryOrigin, LiveCanary, new_run_id,
)

PRODUCER = "telos/tools/live_canary_run.py"


def _runner_origin() -> CanaryOrigin:
    """The runner's origin identity (NEVER the producer origin).

    Returns:
        A runner-source :class:`CanaryOrigin` bound to this process.
    """
    return CanaryOrigin.for_runner()


def _ensure_runner_origin(record: Dict[str, Any], cycle: int) -> Dict[str, Any]:
    """Force runner-origin provenance on the runner's emitted artifact.

    Defense-in-depth: the one-shot runner may NEVER emit
    ``source == "dashboard_producer"`` evidence — that source is reserved for
    the long-running producer process (checked by pid). This re-stamps the
    record so the runner's output is always runner-origin.

    Args:
        record: the canary record about to be persisted.
        cycle: the cycle the run was stamped with.

    Returns:
        The same record with canonical runner-origin provenance.
    """
    prov = dict(record.get("provenance") or {})
    prov["producer"] = "telos/core/actions/live_canary.py"
    prov["runner"] = PRODUCER
    prov["source"] = ORIGIN_RUNNER
    prov["pid"] = os.getpid()
    prov["run_id"] = prov.get("run_id") or new_run_id()
    prov["cycle"] = cycle
    record["provenance"] = prov
    return record


def _ensure_target(sandbox_root: str) -> None:
    """Seed the disposable canary target when the sandbox exists but is bare.

    Args:
        sandbox_root: the sandbox root path.
    """
    if not os.path.isdir(sandbox_root):
        return
    path = os.path.join(sandbox_root, CANARY_TARGET)
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("# TELOS canary target (disposable)\n\n"
                    "canary line one\ncanary line two\ncanary line three\n")


def run_canary(*, workspace: str, cycle: int = 0, max_actions: int = DEFAULT_MAX_ACTIONS,
               persist: bool = False,
               artifact_path: str = DEFAULT_CANARY_ARTIFACT_PATH) -> Dict[str, Any]:
    """Run the bounded canary once and evaluate the live evidence.

    Args:
        workspace: the governed tool workspace root (the sandbox).
        cycle: the cycle to stamp the run with.
        max_actions: the live-action bound for the run.
        persist: persist the canonical LIVE record iff the live bar is met.
        artifact_path: where the trace artifact is written.

    Returns:
        The canary record (with an attached persistence outcome).
    """
    canary = LiveCanary(
        workspace_root=workspace, enabled=True, max_actions=max_actions,
        artifact_path=artifact_path, persist_live=persist,
        origin=_runner_origin(),
    )
    record = canary.run_script(cycle)
    # The runner NEVER emits producer-origin evidence (structural boundary).
    record = _ensure_runner_origin(record, cycle)
    if persist:
        record["persistence"] = canary.persist_live_certification()
    return record


def print_report(record: Dict[str, Any]) -> bool:
    """Print the live-canary report and return whether the live bar was met.

    Args:
        record: the canary record.

    Returns:
        True only when the live evidence satisfied the certification invariants.
    """
    print(f"\n{'TELOS live canary — filesystem.write (disposable target)':^76}")
    print("=" * 76)
    print(f"  outcome: {record.get('outcome')}  executed_any="
          f"{record.get('executed_any')}")
    print(f"  config: {record.get('config')}")
    for c in record.get("cases", []):
        a = c.get("authority", {}).get("change", {})
        print(f"  case {c.get('kind'):<9} exec={c.get('execution', {}).get('executed')!s:<5}"
              f" allowed={c.get('execution', {}).get('allowed')!s:<5}"
              f" gap={c.get('reality_gap')} adm="
              f"{c.get('admission', {}).get('admitted')} "
              f"auth={a.get('status_before')}->{a.get('status_after')}")
    ev = record.get("live_evidence", {})
    print(f"  invariants: {ev.get('invariants')}")
    print(f"  families: {ev.get('families')}  gaps={ev.get('measured_gaps')}")
    print(f"  false_admits={ev.get('false_admits')} "
          f"fail_open={ev.get('fail_open_count')} "
          f"revocation={ev.get('revocation_demonstrated')}")
    rev = record.get("reversibility", {})
    print(f"  reversible={rev.get('reversible')}  {rev}")
    dec = record.get("live_certification", {})
    print("-" * 76)
    print(f"  live certification: {dec.get('action')}  "
          f"live_bar_met={dec.get('live_bar_met')}  "
          f"sandbox_certified={dec.get('sandbox_certified')}")
    if record.get("persistence"):
        print(f"  persistence: {record['persistence']}")
    ok = bool(dec.get("live_bar_met"))
    print("=" * 76)
    print(f"LIVE CANARY: {'LIVE-CERTIFIED (bar met)' if ok else 'NOT LIVE-CERTIFIED'}")
    return ok


def main() -> int:
    """CLI entry point.

    Returns:
        Process exit code (0 when the live bar is met, 1 otherwise under
        ``--ci``).
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless the live evidence meets the bar")
    ap.add_argument("--persist", action="store_true",
                    help="persist the canonical LIVE record iff the live bar is met")
    ap.add_argument("--workspace", default=os.environ.get(
        "TELOS_TOOL_WORKSPACE", DEFAULT_SANDBOX_ROOT))
    ap.add_argument("--cycle", type=int, default=0)
    ap.add_argument("--max-actions", type=int, default=DEFAULT_MAX_ACTIONS)
    ap.add_argument("--json", default=DEFAULT_CANARY_ARTIFACT_PATH)
    args = ap.parse_args()
    _ensure_target(args.workspace)
    record = run_canary(workspace=args.workspace, cycle=args.cycle,
                        max_actions=args.max_actions, persist=args.persist,
                        artifact_path=args.json)
    record = _ensure_runner_origin(record, args.cycle)
    if args.json:
        out = args.json if os.path.isabs(args.json) \
            else os.path.join(PROJECT, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str)
        print(f"(live canary saved: {out})")
    ok = print_report(record)
    if args.ci:
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
