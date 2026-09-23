"""
decision_records — query the file-backed decision exchange.

Read-only CLI over a `DecisionStore`: list/search decisions and show the full
reasoning (evidence, alternatives, revalidation conditions) of one record.

Usage:
    PYTHONPATH=. ./.venv/bin/python telos/tools/decision_records.py list
    PYTHONPATH=. ./.venv/bin/python telos/tools/decision_records.py list --status OPEN
    PYTHONPATH=. ./.venv/bin/python telos/tools/decision_records.py show <decision_id>

Root resolution: --root, else $TELOS_DECISION_STORE, else ./decision_records.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from telos.core.handoff import DecisionStore


def _cmd_list(store: DecisionStore, args: argparse.Namespace) -> int:
    """Print the record index (optionally filtered).

    Args:
        store: the decision store.
        args: parsed CLI args.

    Returns:
        Process exit code.
    """
    records = store.find(domain=args.domain, status=args.status,
                         intent_type=args.intent, owner=args.owner)
    if not records:
        print("No decision records.")
        return 0
    print(f"{'decision_id':<34}{'intent':<20}{'status':<11}{'cycle':>6}  objective")
    print("-" * 96)
    for r in records:
        print(f"{r.decision_id:<34}{str(r.decision.get('intent_type')):<20}"
              f"{r.status.value:<11}{str(r.provenance.get('cycle')):>6}  "
              f"{r.objective or '-'}")
    print(f"\n{len(records)} record(s).")
    return 0


def _cmd_show(store: DecisionStore, args: argparse.Namespace) -> int:
    """Print one record as markdown.

    Args:
        store: the decision store.
        args: parsed CLI args.

    Returns:
        Process exit code.
    """
    record = store.load(args.decision_id)
    if record is None:
        print(f"Decision '{args.decision_id}' not found.", file=sys.stderr)
        return 1
    print(record.to_markdown())
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point.

    Args:
        argv: optional argument list (defaults to sys.argv).

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description="Query the decision exchange")
    parser.add_argument("--root", default=os.environ.get("TELOS_DECISION_STORE",
                                                         "decision_records"))
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="List/search decision records")
    p_list.add_argument("--domain", default=None)
    p_list.add_argument("--status", default=None,
                        help="OPEN / VALIDATED / FALSIFIED / SUPERSEDED")
    p_list.add_argument("--intent", default=None)
    p_list.add_argument("--owner", default=None)

    p_show = sub.add_parser("show", help="Show one record's reasoning")
    p_show.add_argument("decision_id")

    args = parser.parse_args(argv)
    store = DecisionStore(args.root)

    if args.command == "show":
        return _cmd_show(store, args)
    return _cmd_list(store, args)


if __name__ == "__main__":
    sys.exit(main())
