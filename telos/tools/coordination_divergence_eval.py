#!/usr/bin/env python3
"""Coordination divergence evaluation — proves the advisory crew can disagree.

WHY THIS EXISTS (measured, not asserted — Λ6.5)
-----------------------------------------------
The Λ4.11 boundary fix (commit 08afe9b) observed that, in standard mode, every
role of the DistributedCouncil advisory crew reported
``decision_integrity = 1.0`` — so ``CooperativeCouncil`` computed
``diversity = 0.0`` on all measured cycles. A unanimous crew is *expected* when
the primary council's evidence genuinely all passes, but "diversity is always
0.0" is only honest if the crew is *capable* of diverging. This harness
measures that capability directly instead of assuming it.

WIDENED METRIC (this harness predated the fix): ``diversity`` now combines both
axes of crew dissent — the per-role decision-integrity spread (``di_spread``)
and the normalized validated-set split (``validation_disagreement``):

    diversity = min(1, max(di_spread, validation_disagreement))

so an all-pass crew whose conservative lens still blocks on ``md_cap`` now
reports non-zero diversity even though every role DI is identical.

It exercises the REAL crew (``DistributedCouncil.run_perspectives`` over a
primary ``CouncilVerdict``-shaped input) on four scenarios and records the
``CooperativeCouncil`` verdict for each:

  - HEALTHY:           all evidence passes → every role DI == 1.0, diversity 0.
  - VALIDATED_AXIS:    all evidence passes but mission_drift exceeds the
                       conservative role's ``md_cap`` → ``di_spread == 0``, yet
                       the crew disagrees on the validation axis, so the
                       widened ``diversity > 0`` and ``consensus < 1``. (This is
                       the exact live signature the old metric was blind to.)
  - MARGINAL:          mixed evidence with a heavy dissenting validator → the
                       role lenses (dissent multiplier / pass multiplier /
                       evidence weight) produce distinct DI values →
                       ``diversity > 0``.
  - MANIPULATED:       the binding primary verdict claims high DI while its own
                       evidence carries a block → PRIMARY mirrors the claim,
                       the other roles recompute from the evidence →
                       ``diversity > 0``.

Where the input genuinely all passes, unanimity is correct. Where it does not,
the crew diverges. The artifact records both, so "the crew is independent" is
evidenced rather than assumed.

Note on the shared DISSENT_FLOOR (scope honesty): when there is a block, every
role's reported DI is capped at ``DistributedCouncil.DISSENT_FLOOR`` (0.3),
mirroring the primary council's honesty floor. A *lone* dissenting validator
therefore leaves every role at exactly 0.3 — zero DI spread — even though the
roles disagree on ``validated``. The MARGINAL scenario uses a heavy dissent so
a role's pre-floor DI falls *below* the shared floor, which is where the
role-specific lenses become observable on the DI axis. Both axes are recorded;
nothing is manufactured.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/coordination_divergence_eval.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/coordination_divergence_eval.py --ci
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.council.distributed import DistributedCouncil  # noqa: E402
from telos.core.coordination.cooperative import CooperativeCouncil  # noqa: E402
from telos.core.verifier.measurement import provenance  # noqa: E402

PRODUCER = "telos/tools/coordination_divergence_eval.py"

# The honesty criteria this artifact reports. The reader (schema-linkage test)
# imports this exact list so a writer/reader key drift fails loudly.
CRITERIA: List[str] = [
    "healthy_unanimity",
    "validated_axis_disagreement",
    "marginal_evidence_divergence",
    "manipulated_primary_divergence",
    "lens_transform_active",
    "authority_weighting",
    "determinism",
]

# Every per-scenario record's exact field set. The reader-side schema-linkage
# test imports this so a writer/reader key drift (the recurring failure mode
# this project has hit) fails loudly instead of silently dropping an axis.
SCENARIO_FIELDS: List[str] = [
    "diversity",
    "di_spread",
    "validation_disagreement",
    "group_utility",
    "isolated_utility",
    "consensus",
    "resolved_validated",
    "n_agents",
]


class _Signal:
    """Minimal stand-in for a primary CouncilVerdict ValidationSignal."""

    def __init__(self, name: str, passed: bool, confidence: float,
                 evidence_weight: float) -> None:
        self.validator_name = name
        self.passed = passed
        self.confidence = confidence
        self.evidence_weight = evidence_weight
        self.reason = ""


class _Verdict:
    """Minimal stand-in for a primary CouncilVerdict."""

    def __init__(self, validated: bool, decision_integrity: float,
                 mission_drift: float, signals: List[_Signal]) -> None:
        self.validated = validated
        self.decision_integrity = decision_integrity
        self.mission_drift = mission_drift
        self.signals = signals


def _healthy_signals() -> List[_Signal]:
    """Uniformly passing evidence (the live standard-mode signature)."""
    return [
        _Signal("reality", True, 0.90, 0.30),
        _Signal("constraint", True, 0.95, 0.20),
        _Signal("evidence", True, 0.50, 0.10),
        _Signal("memory", True, 0.70, 0.40),
        _Signal("mission", True, 0.40, 0.20),
    ]


def _run_scenario(validated: bool, di: float, md: float,
                  signals: List[_Signal],
                  context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run one scenario through the real crew + cooperative aggregation.

    Args:
        validated: the primary council's binding validated flag.
        di: the primary council's reported decision integrity.
        md: the primary council's mission drift.
        signals: the primary council's ValidationSignals.
        context: the crew's role context (alternatives, curiosity, etc.).

    Returns:
        Dict with the per-agent utilities, consensus, and the CooperativeVerdict.
    """
    crew = DistributedCouncil()
    crew.register_default_crew()
    verdict = _Verdict(validated, di, md, signals)
    result = crew.run_perspectives(verdict, context or {})
    coop = CooperativeCouncil().evaluate(result["agents"]).to_dict()
    utilities = [a["decision_integrity"] for a in result["agents"]]
    return {
        "cooperative": coop,
        "utilities": utilities,
        "consensus": result["consensus"],
        "resolved_validated": result["validated"],
        "n_agents": result["n_agents"],
    }


def _scenarios() -> Dict[str, Dict[str, Any]]:
    """Run every scenario once (deterministic, no randomness).

    Returns:
        Mapping scenario name -> measured record.
    """
    return {
        # All evidence passes: genuine unanimity at DI == 1.0.
        "healthy": _run_scenario(True, 1.0, 0.0, _healthy_signals()),
        # All evidence passes but md exceeds the conservative md_cap (1.5):
        # DI spread is zero, yet the crew disagrees on the validation axis.
        "validated_axis": _run_scenario(True, 1.0, 2.5, _healthy_signals()),
        # Heavy dissent: the skeptic's 1.6x dissent multiplier pushes its
        # pre-floor DI below the shared 0.3 floor while others stay at it.
        "marginal": _run_scenario(False, 0.3, 0.0, [
            _Signal("reality", False, 0.95, 0.80),
            _Signal("constraint", True, 0.90, 0.20),
            _Signal("evidence", True, 0.60, 0.15),
        ]),
        # Adversarial: the binding verdict claims DI=0.9 while its own evidence
        # carries a block. PRIMARY mirrors 0.9; the crew recomputes.
        "manipulated_primary": _run_scenario(True, 0.9, 0.0, [
            _Signal("reality", False, 0.90, 0.50),
            _Signal("constraint", True, 0.80, 0.40),
        ]),
    }


def _criteria(run: Dict[str, Dict[str, Any]],
              deterministic: bool) -> Dict[str, bool]:
    """Compute the measured honesty criteria from a scenario run.

    Args:
        run: mapping scenario name -> record from _scenarios().
        deterministic: whether two independent runs were identical.

    Returns:
        Mapping criterion name -> passed.
    """
    healthy = run["healthy"]
    axis = run["validated_axis"]
    marginal = run["marginal"]
    manip = run["manipulated_primary"]

    def _div(rec: Dict[str, Any]) -> float:
        return float(rec["cooperative"]["diversity"])

    def _di_spread(rec: Dict[str, Any]) -> float:
        return float(rec["cooperative"]["di_spread"])

    def _val_disagree(rec: Dict[str, Any]) -> float:
        return float(rec["cooperative"]["validation_disagreement"])

    lens_active = (
        len(set(round(u, 6) for u in marginal["utilities"])) >= 2
        or len(set(round(u, 6) for u in manip["utilities"])) >= 2
    )
    # The authority weights must actually shape the group utility: in the
    # manipulated scenario the weighted group differs from the plain mean.
    utils = manip["utilities"]
    plain_mean = sum(utils) / len(utils)
    group = float(manip["cooperative"]["group_utility"])
    authority_weighting = abs(group - plain_mean) > 1e-6

    return {
        "healthy_unanimity": (
            _div(healthy) == 0.0 and healthy["n_agents"] >= 5
        ),
        # The widened metric must SEE this case: DI spread is zero but the
        # validated-set split is positive, so diversity is positive.
        "validated_axis_disagreement": (
            _div(axis) > 0.0
            and _di_spread(axis) == 0.0
            and _val_disagree(axis) > 0.0
            and float(axis["consensus"]) < 1.0
        ),
        "marginal_evidence_divergence": _div(marginal) > 0.0,
        "manipulated_primary_divergence": _div(manip) > 0.0,
        "lens_transform_active": lens_active,
        "authority_weighting": authority_weighting,
        "determinism": deterministic,
    }


def evaluate() -> Dict[str, Any]:
    """Run the scenarios twice and compute the measured divergence evidence.

    Returns:
        Dict with provenance, criteria, verdict, the per-scenario diversity
        values, and the determinism flag.
    """
    run1 = _scenarios()
    run2 = _scenarios()
    deterministic = (
        json.dumps(run1, sort_keys=True) == json.dumps(run2, sort_keys=True)
    )
    criteria = _criteria(run1, deterministic)
    return {
        "provenance": provenance(PRODUCER, list(criteria)),
        "criteria": criteria,
        "beats_baseline": all(criteria.values()),
        "verdict": {
            "passed": all(criteria.values()),
            "passed_count": sum(1 for v in criteria.values() if v),
            "total": len(criteria),
        },
        "scenarios": {
            name: {
                "diversity": round(rec["cooperative"]["diversity"], 6),
                "di_spread": round(rec["cooperative"]["di_spread"], 6),
                "validation_disagreement": round(
                    rec["cooperative"]["validation_disagreement"], 6),
                "group_utility": round(rec["cooperative"]["group_utility"], 6),
                "isolated_utility": round(rec["cooperative"]["isolated_utility"], 6),
                "consensus": rec["consensus"],
                "resolved_validated": rec["resolved_validated"],
                "n_agents": rec["n_agents"],
            }
            for name, rec in run1.items()
        },
        "deterministic": deterministic,
    }


def print_report(result: Dict[str, Any]) -> bool:
    """Print the divergence evaluation report.

    Args:
        result: the dict returned by evaluate().

    Returns:
        True when every measured criterion passes.
    """
    print(f"\n{'TELOS Coordination Divergence Evaluation':^74}")
    print("=" * 74)
    print("  crew: PRIMARY/SKEPTIC/EXPLORER/CONSERVATIVE/ANALYST (+DOMAIN_EXPERT)")
    print("-" * 74)
    print(f"  {'scenario':<22}{'diversity':>10}{'di_spread':>10}"
          f"{'val_split':>10}{'consensus':>10}{'agents':>7}")
    for name, rec in result["scenarios"].items():
        print(f"  {name:<22}{rec['diversity']:>10.4f}{rec['di_spread']:>10.4f}"
              f"{rec['validation_disagreement']:>10.4f}{rec['consensus']:>10}"
              f"{rec['n_agents']:>7}")
    print("-" * 74)
    print(f"  {'criterion':<40}{'result':>10}")
    for name, passed in result["criteria"].items():
        print(f"  {name:<40}{'PASS' if passed else 'FAIL':>10}")
    print("=" * 74)
    print("  verdict:", "crew divergence measured (independent lenses)" if
          result["beats_baseline"] else "criteria NOT all met")
    return bool(result["beats_baseline"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless every divergence criterion passes")
    ap.add_argument("--json", default="telos/audit/coordination_divergence.json",
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
