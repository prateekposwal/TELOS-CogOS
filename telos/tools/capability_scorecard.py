#!/usr/bin/env python3
"""
Capability Scorecard CLI — prints the measured capability rubric and the four
uplift baselines, optionally asserting measurement integrity.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/capability_scorecard.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/capability_scorecard.py --ci

--ci asserts the scorecard itself is well-formed (all dimensions computed,
every score in [0, 5], the four uplift baselines present) — it does NOT assert
the targets are met, because those are the roadmap's outputs, not Phase-0
guarantees. Use the printed gaps to track progress.
"""

import argparse
import json
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.verifier.capability_scorecard import (  # noqa: E402
    DIMENSIONS, TARGETS, compute_scorecard, report_lines,
)


def main() -> None:
    """Print and (optionally) validate the capability scorecard."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="assert scorecard integrity (exit 1 on malformed)")
    ap.add_argument("--json", default="telos/audit/capability_scorecard.json",
                    help="path to write the scorecard JSON")
    args = ap.parse_args()

    for line in report_lines():
        print(line)

    card = compute_scorecard()
    payload = {name: r.to_dict() for name, r in card.items()}
    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(PROJECT, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"(scorecard saved: {out})")

    ok = (
        set(card) == set(DIMENSIONS)
        and set(TARGETS).issubset(card)
        and all(0.0 <= r.score <= 5.0 for r in card.values())
    )
    print("SCORECARD:", "PASS" if ok else "FAIL")
    if args.ci:
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
