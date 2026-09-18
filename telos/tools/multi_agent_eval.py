#!/usr/bin/env python3
"""
Multi-agent coordination evaluation — measures real agent-to-agent behavior.

PATTERN (measured, not asserted — Λ6.5): a multi-agent score must come from an
OBSERVED protocol run, not from the existence of files that mention agents. This
harness exercises the real ``CoordinationProtocol`` on a fixed scenario and
checks the behaviors that separate genuine multi-agent coordination from one
model wearing five hats:

  - DELEGATION: a handoff between two agents is recorded (who asked, who
    answered, what came back). Self-delegation is refused with a reason.
  - VERIFICATION: an independent agent REJECTS an invalid proposal with a
    recorded reason, ACCEPTS a valid one, and refuses to audit its own work.
  - CONFLICT RESOLUTION: a genuine disagreement resolves deterministically
    (a hard veto overrides a weighted majority; an exact tie breaks by
    authority then id).
  - BOUNDS: rounds and handoffs hit hard ceilings and the protocol refuses
    beyond them (no runaway agent-to-agent loops).
  - DETERMINISM: two independent runs produce byte-identical records.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/multi_agent_eval.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/multi_agent_eval.py --ci
"""

import argparse
import json
import os
import sys
from typing import Any, Dict

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.coordination.delegation import CoordinationProtocol  # noqa: E402

MAX_ROUNDS = 3
MAX_HANDOFFS = 4


def _scenario() -> Dict[str, Any]:
    """Run the fixed coordination scenario once.

    Returns:
        Dict with the serialized records, the audit snapshot, and the
        individual records used to compute the criteria.
    """
    protocol = CoordinationProtocol(max_rounds=MAX_ROUNDS,
                                    max_handoffs=MAX_HANDOFFS)
    protocol.register_agent("primary", "primary", 1.0)
    protocol.register_agent("skeptic", "skeptic", 0.8)
    protocol.register_agent("analyst", "analyst", 0.5)
    protocol.register_agent("explorer", "explorer", 0.6)
    protocol.register_agent("auditor_a", "analyst", 1.0)
    protocol.register_agent("auditor_b", "explorer", 1.0)
    protocol.advance_round()

    # Delegation (accepted), self-delegation (refused), then exhaust the
    # ACCEPTED handoff budget (4) and prove a 5th is refused.
    h_ok = protocol.delegate("audit the risk claim", "primary", "skeptic",
                             response={"risk": "high"})
    h_self = protocol.delegate("dead loop", "primary", "primary")
    protocol.delegate("collect evidence", "primary", "analyst")
    protocol.delegate("propose alternative", "primary", "explorer")
    protocol.delegate("cross-check the plan", "primary", "analyst")
    h_over = protocol.delegate("over budget", "primary", "analyst")

    # Verification: a violating proposal MUST be rejected with a reason.
    reject = protocol.verify({
        "proposal_id": "p-reject", "author": "primary",
        "evidence": ["signal"], "violates": ["reality_contradiction"],
        "confidence": 0.9,
    }, "skeptic")
    # Verification: a clean proposal MUST be accepted.
    accept = protocol.verify({
        "proposal_id": "p-accept", "author": "primary",
        "evidence": ["signal"], "violates": [], "confidence": 0.9,
    }, "skeptic")
    # Independence: a verifier may not audit its own proposal.
    self_verify = protocol.verify({
        "proposal_id": "p-self", "author": "skeptic",
        "evidence": ["signal"], "violates": [], "confidence": 0.9,
    }, "skeptic")

    # Genuine disagreement: skeptic (hard veto) against a weighted majority.
    conflict = protocol.resolve([
        {"agent_id": "primary", "role": "primary", "validated": True, "weight": 1.0},
        {"agent_id": "skeptic", "role": "skeptic", "validated": False, "weight": 0.8},
        {"agent_id": "analyst", "role": "analyst", "validated": True, "weight": 0.5},
        {"agent_id": "explorer", "role": "explorer", "validated": True, "weight": 0.6},
    ])
    # Tie: equal weight on both sides, neither a hard-veto role, must break
    # deterministically by authority then agent id.
    tie = protocol.resolve([
        {"agent_id": "auditor_a", "role": "analyst", "validated": True, "weight": 1.0},
        {"agent_id": "auditor_b", "role": "explorer", "validated": False, "weight": 1.0},
    ])

    # Exhaust the round ceiling (no more rounds may open).
    rounds_opened = 1
    while protocol.advance_round():
        rounds_opened += 1

    return {
        "records": protocol.records(),
        "audit": protocol.audit(),
        "h_ok": h_ok.to_dict(),
        "h_self": h_self.to_dict(),
        "h_over": h_over.to_dict(),
        "reject": reject.to_dict(),
        "accept": accept.to_dict(),
        "self_verify": self_verify.to_dict(),
        "conflict": conflict.to_dict(),
        "tie": tie.to_dict(),
        "rounds_opened": rounds_opened,
    }


def _criteria(run: Dict[str, Any], deterministic: bool) -> Dict[str, bool]:
    """Compute the behavioral criteria from one scenario run.

    Args:
        run: the dict returned by _scenario().
        deterministic: whether two independent runs were identical.

    Returns:
        Mapping criterion name -> passed.
    """
    reject = run["reject"]
    accept = run["accept"]
    self_verify = run["self_verify"]
    conflict = run["conflict"]
    tie = run["tie"]
    audit = run["audit"]
    return {
        "rejection_with_reason": (
            reject["accepted"] is False and bool(reject["reason"])
        ),
        "acceptance": accept["accepted"] is True,
        "independent_verifier": (
            self_verify["accepted"] is False
            and "independence" in self_verify["reason"]
        ),
        "deterministic_conflict_resolution": (
            conflict["conflict"] is True
            and conflict["method"] == "hard_veto"
            and conflict["validated"] is False
            and tie["method"] == "authority_tiebreak"
            and tie["weight_for"] == tie["weight_against"]
        ),
        "delegation_recorded": (
            run["h_ok"]["accepted"] is True
            and run["h_ok"]["from_agent"] == "primary"
            and run["h_ok"]["to_agent"] == "skeptic"
            and run["h_ok"]["response"] == {"risk": "high"}
            and run["h_self"]["accepted"] is False
            and "self-delegation" in run["h_self"]["reason"]
        ),
        "bounded": (
            audit["bounded"] is True
            and audit["rounds_used"] == audit["max_rounds"]
            and run["h_over"]["accepted"] is False
            and run["h_over"]["reason"] == "handoff_budget_exhausted"
        ),
        "determinism": deterministic,
    }


def evaluate() -> Dict[str, Any]:
    """Run the scenario twice and compute the measured criteria.

    Returns:
        Dict with the criteria, the overall verdict, and the required counts
        (delegations, rejections with reasons, conflicts resolved, rounds).
    """
    run1 = _scenario()
    run2 = _scenario()
    key = lambda r: json.dumps(r["records"], sort_keys=True)  # noqa: E731
    deterministic = key(run1) == key(run2)
    criteria = _criteria(run1, deterministic)
    audit = run1["audit"]
    return {
        "criteria": criteria,
        "beats_baseline": all(criteria.values()),
        "delegations": audit["delegations"],
        "handoffs_accepted": audit["handoffs_accepted"],
        "handoffs_rejected": audit["handoffs_rejected"],
        "acceptances": audit["acceptances"],
        "rejections_with_reason": audit["rejections_with_reason"],
        "conflicts_resolved": audit["conflicts_resolved"],
        "rounds_used": audit["rounds_used"],
        "max_rounds": audit["max_rounds"],
        "handoff_budget": audit["handoff_budget"],
        "bounded": audit["bounded"],
        "deterministic": deterministic,
    }


def print_report(result: Dict[str, Any]) -> bool:
    """Print the coordination evaluation report.

    Args:
        result: the dict returned by evaluate().

    Returns:
        True when every measured criterion passes.
    """
    print(f"\n{'TELOS Multi-Agent Coordination Evaluation':^74}")
    print("=" * 74)
    print("  scenario: 4 agents · delegation · adversarial verification ·"
          " conflict + tie resolution")
    print("-" * 74)
    print(f"  {'criterion':<34}{'result':>10}")
    for name, passed in result["criteria"].items():
        print(f"  {name:<34}{'PASS' if passed else 'FAIL':>10}")
    print("-" * 74)
    print(f"  delegations={result['delegations']} "
          f"rejections_with_reason={result['rejections_with_reason']} "
          f"conflicts_resolved={result['conflicts_resolved']} "
          f"rounds={result['rounds_used']}/{result['max_rounds']} "
          f"bounded={result['bounded']}")
    print("=" * 74)
    print("  verdict:", "REAL multi-agent coordination measured" if
          result["beats_baseline"] else "criteria NOT all met")
    return bool(result["beats_baseline"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless every coordination criterion passes")
    ap.add_argument("--json", default="telos/audit/multi_agent_eval.json",
                    help="path to write the evaluation JSON")
    args = ap.parse_args()
    res = evaluate()
    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(PROJECT, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(res, f, indent=2)
        print(f"(evaluation saved: {out})")
    ok = print_report(res)
    if args.ci:
        sys.exit(0 if ok else 1)
