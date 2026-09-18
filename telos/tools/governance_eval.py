#!/usr/bin/env python3
"""
Governance evaluation — measures whether the REAL governance machinery
actually blocks what it must block and admits what it must admit.

PATTERN (a capability must be behaviourally measured, not inferred from files
— Λ6.5): the self_governance score used to be a file-existence count (four
modules present = 5.0). That says the modules exist, not that governance
works. This harness drives the actual DecisionFirewall, CapabilityAuthorization
and DecisionGovernor on fixed adversarial scenarios and records, per scenario,
whether the gate behaved correctly AND the reason it gave.

Scenarios:
  * a low-integrity proposal is BLOCKED by the firewall (reason recorded);
  * a repeat-trap intent is BLOCKED after the loop threshold;
  * a council rejection is upheld by the firewall;
  * a legitimate, clean proposal is ADMITTED;
  * a low-fidelity capability gate is VETOED (authorization refuses ACT and
    the governor DEFERs);
  * a hard capability boundary (authority FAIL) makes the governor BLOCK;
  * the governor maps a clean capability+epistemic state to ACT;
  * it maps a capability gap to DEFER;
  * it maps an UNMODELED epistemic state to ABSTAIN;
  * it maps a required escalation to ESCALATE;
  * two independent runs produce identical verdicts (determinism).

Writes telos/audit/governance_eval.json with explicit criteria, per-scenario
reasons, a machine-checkable verdict and its own provenance.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/governance_eval.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/governance_eval.py --ci
"""

import argparse
import json
import os
import sys
from types import SimpleNamespace
from typing import Any, Dict, List

import numpy as np

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.governance.capability_authorization import (  # noqa: E402
    CapabilityStatus, all_pass, from_dimensions,
)
from telos.core.governance.firewall import (  # noqa: E402
    DecisionFirewall, FirewallConfig,
)
from telos.core.governance.governor import (  # noqa: E402
    DecisionGovernor, DecisionMode, GovernorInput,
)
from telos.core.verifier.measurement import provenance  # noqa: E402
from telos.intent_ir import IntentIR  # noqa: E402
from telos.world.world import World  # noqa: E402

PRODUCER = "telos/tools/governance_eval.py"

# The behavioural criteria the scorer reads. Locked to the writer by
# tests/core/test_governance_eval.py (schema-linkage guard).
GOVERNANCE_CRITERIA: List[str] = [
    "low_integrity_blocked",
    "repeat_trap_blocked",
    "council_rejection_blocked",
    "legitimate_admitted",
    "low_fidelity_vetoed",
    "hard_boundary_blocked",
    "governor_act_on_clean",
    "governor_defer_on_capability_gap",
    "governor_abstain_on_unmodeled",
    "governor_escalate_when_required",
    "deterministic_replay",
]


def _world() -> World:
    """A minimal world for the firewall's reality audit.

    Returns:
        A World with a fixed 2-element state.
    """
    return World(state=np.array([1.0, 2.0]))


def _unmodeled() -> SimpleNamespace:
    """An epistemic state the governor must treat as no-defensible-action.

    Returns:
        A stand-in carrying the `.value` attribute the governor reads.
    """
    return SimpleNamespace(value="UNMODELED")


def _scenario() -> Dict[str, Any]:
    """Run every governance scenario once and record the observed behaviour.

    Returns:
        Dict mapping scenario name -> {passed, reason}.
    """
    governor = DecisionGovernor()
    records: Dict[str, Dict[str, Any]] = {}

    # 1. Low integrity -> firewall BLOCKS with the reason recorded.
    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
    v = fw.inspect(_world(), IntentIR("navigate_to_goal", confidence=0.9),
                   council_validated=True, decision_integrity=0.2)
    records["low_integrity_blocked"] = {
        "passed": (v.passed is False and v.blocked_by == "low_integrity"
                   and bool(v.reason)),
        "reason": f"passed={v.passed} blocked_by={v.blocked_by} reason={v.reason}",
    }

    # 2. Repeat trap -> firewall BLOCKS after the loop threshold.
    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
    trap = None
    for _ in range(5):
        trap = fw.inspect(_world(), IntentIR("navigate_to_goal", confidence=0.9),
                          council_validated=True, decision_integrity=0.9)
    records["repeat_trap_blocked"] = {
        "passed": (trap is not None and trap.passed is False
                   and trap.blocked_by == "action_loop"),
        "reason": f"passed={trap.passed} blocked_by={trap.blocked_by}",
    }

    # 3. Council rejection is upheld.
    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
    v = fw.inspect(_world(), IntentIR("navigate_to_goal", confidence=0.9),
                   council_validated=False, decision_integrity=0.9)
    records["council_rejection_blocked"] = {
        "passed": v.passed is False and v.blocked_by == "council_rejection",
        "reason": f"passed={v.passed} blocked_by={v.blocked_by}",
    }

    # 4. A legitimate, clean proposal is ADMITTED.
    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
    v = fw.inspect(_world(), IntentIR("navigate_to_goal", confidence=0.9),
                   council_validated=True, decision_integrity=0.9)
    records["legitimate_admitted"] = {
        "passed": v.passed is True,
        "reason": f"passed={v.passed} reason={v.reason}",
    }

    # 5. Low fidelity -> capability authorization vetoes; governor DEFERs.
    cap = from_dimensions({"model_fidelity": CapabilityStatus.FAIL})
    decision = governor.evaluate(GovernorInput(capability=cap, DI=0.9))
    records["low_fidelity_vetoed"] = {
        "passed": (cap.authorized() is False
                   and "model_fidelity" in cap.failed_gates()
                   and decision.mode != DecisionMode.ACT),
        "reason": f"authorized={cap.authorized()} failed={cap.failed_gates()} "
                  f"mode={decision.mode.value}",
    }

    # 6. Hard capability boundary (authority FAIL) -> governor BLOCKs.
    cap = from_dimensions({"authority": CapabilityStatus.FAIL})
    decision = governor.evaluate(GovernorInput(
        capability=cap, DI=0.9,
        authorized_modes={DecisionMode.ACT, DecisionMode.BLOCK}))
    records["hard_boundary_blocked"] = {
        "passed": decision.mode == DecisionMode.BLOCK,
        "reason": f"mode={decision.mode.value} reason={decision.reason}",
    }

    # 7-10. Governor mode mapping on clean / gap / unmodeled / escalation.
    decision = governor.evaluate(GovernorInput(capability=all_pass(), DI=0.9))
    records["governor_act_on_clean"] = {
        "passed": decision.mode == DecisionMode.ACT,
        "reason": f"mode={decision.mode.value}",
    }

    decision = governor.evaluate(GovernorInput(
        capability=from_dimensions({"model_fidelity": CapabilityStatus.FAIL}),
        DI=0.9))
    records["governor_defer_on_capability_gap"] = {
        "passed": decision.mode == DecisionMode.DEFER,
        "reason": f"mode={decision.mode.value}",
    }

    decision = governor.evaluate(GovernorInput(
        capability=all_pass(), DI=0.9, epistemic_state=_unmodeled()))
    records["governor_abstain_on_unmodeled"] = {
        "passed": decision.mode == DecisionMode.ABSTAIN,
        "reason": f"mode={decision.mode.value}",
    }

    decision = governor.evaluate(GovernorInput(
        capability=all_pass(), DI=0.9, escalation_requested=True,
        escalation_policy="required", human_authorized=False))
    records["governor_escalate_when_required"] = {
        "passed": decision.mode == DecisionMode.ESCALATE,
        "reason": f"mode={decision.mode.value}",
    }

    return records


def _criteria() -> Dict[str, bool]:
    """Run the scenario twice and return the criteria with determinism.

    Returns:
        Mapping criterion name -> passed, including ``deterministic_replay``.
    """
    first = _scenario()
    second = _scenario()
    determinism = (
        json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    )
    criteria = {name: bool(first[name]["passed"]) for name in GOVERNANCE_CRITERIA
                if name != "deterministic_replay"}
    criteria["deterministic_replay"] = determinism
    return {name: criteria[name] for name in GOVERNANCE_CRITERIA}


def evaluate() -> Dict[str, Any]:
    """Evaluate the governance machinery and build the artifact payload.

    Returns:
        The measurement payload (provenance, criteria, verdict, scenarios).
    """
    run = _scenario()
    criteria = _criteria()
    passed = sum(1 for v in criteria.values() if v)
    return {
        "provenance": provenance(PRODUCER, GOVERNANCE_CRITERIA),
        "criteria": criteria,
        "verdict": {
            "passed": passed == len(GOVERNANCE_CRITERIA),
            "passed_count": passed,
            "total": len(GOVERNANCE_CRITERIA),
        },
        "scenarios": [
            {"name": name, "passed": bool(run[name]["passed"]),
             "reason": run[name]["reason"]}
            for name in GOVERNANCE_CRITERIA if name in run
        ],
    }


def print_report(result: Dict[str, Any]) -> bool:
    """Print the governance evaluation table.

    Args:
        result: the dict returned by evaluate().

    Returns:
        True when every governance criterion passes.
    """
    print(f"\n{'TELOS Governance Evaluation (behavioral)':^74}")
    print("=" * 74)
    print(f"  {'criterion':<40}{'result':>10}")
    for name, passed in result["criteria"].items():
        print(f"  {name:<40}{'PASS' if passed else 'FAIL':>10}")
    print("-" * 74)
    for scenario in result["scenarios"]:
        if not scenario["passed"]:
            print(f"  [detail] {scenario['name']}: {scenario['reason']}")
    print("=" * 74)
    verdict = result["verdict"]
    print(f"GOVERNANCE EVAL: {'PASS' if verdict['passed'] else 'FAIL'} "
          f"({verdict['passed_count']}/{verdict['total']} criteria)")
    return bool(verdict["passed"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless every governance criterion passes")
    ap.add_argument("--json", default="telos/audit/governance_eval.json",
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
