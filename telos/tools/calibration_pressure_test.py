"""
Calibration Pressure Test — evidence before authority.

The CalibrationValidator exists in two modes:

  * ``enforce=False`` (canonical) — measurement only. Zero-weight abstention;
    it can never change DI, voting, or escalation.
  * ``enforce=True`` — governance intervention. An overconfident +
    miscalibrated claim returns a BLOCK.

Before the blocking rule is granted authority in the canonical pipeline, this
tool establishes the TELOS evidence-bounded precondition:

    A validator should first demonstrate that it can reliably detect a failure
    before it is given authority to stop the system.

It does three things:

  1. **Scenario matrix** — controlled calibration states (well-calibrated,
     overconfident, underconfident, ECE below/above threshold, insufficient
     data) and the validator's verdict in each mode. Asserts that
     ``enforce=True`` blocks ONLY the intended overconfidence case.
  2. **Council effects** — DI / validated / escalation for each scenario.
  3. **Pipeline A/B** — advisory vs. enforce on the real GridWorld pipeline:
     action-emission rate, mean DI, escalation rate, and the validator's block
     count, so the downstream effect is measured, not assumed.

Run:
    PYTHONPATH=. ./.venv/bin/python telos/tools/calibration_pressure_test.py
    PYTHONPATH=. ./.venv/bin/python telos/tools/calibration_pressure_test.py --ci
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from telos.core.calibration import CalibrationTracker
from telos.core.council.base import Council
from telos.core.council.validators import CalibrationValidator
from telos.intent_ir import IntentIR
from telos.world.world import World

Pair = Tuple[float, float]


@dataclass
class Scenario:
    """One controlled calibration state and its expected verdict.

    Args:
        name: human-readable scenario name.
        pairs: the (predicted, realized) history seeded into the tracker.
        probe_claim: the confidence of the intent being validated.
        expect_block_enforce: whether enforce mode MUST block this probe.
    """
    name: str
    pairs: List[Pair]
    probe_claim: float
    expect_block_enforce: bool
    note: str = ""


def build_scenarios() -> List[Scenario]:
    """Construct the controlled calibration scenarios.

    Returns:
        The scenario list, each with an explicit expected enforce verdict.
    """
    scenarios: List[Scenario] = []

    # 1. Well calibrated: confidence matches accuracy in every bin.
    well: List[Pair] = []
    for conf in (0.1, 0.3, 0.5, 0.7, 0.9):
        well.extend([(conf, conf)] * 20)
    scenarios.append(Scenario(
        "well_calibrated", well, probe_claim=0.9, expect_block_enforce=False,
        note="ECE~0; high claim is honest",
    ))

    # 2. Overconfident: claims 0.9, never succeeds. The intended block case.
    over = [(0.9, 0.0)] * 100
    scenarios.append(Scenario(
        "overconfident", over, probe_claim=0.9, expect_block_enforce=True,
        note="ECE 0.9, gap 0.9, claim >= 0.7 -> BLOCK",
    ))

    # 3. Underconfident: claims 0.2, nearly always succeeds. A DIFFERENT
    #    failure mode — must NOT be punished by the overconfidence rule.
    under = [(0.2, 0.9)] * 100
    scenarios.append(Scenario(
        "underconfident", under, probe_claim=0.9, expect_block_enforce=False,
        note="miscalibrated the other way; high claim recalibrates UP",
    ))

    # 4. ECE below threshold: a miscalibrated slice diluted by a large
    #    well-calibrated mass -> ECE < 0.25 even though one bin is off.
    low_ece: List[Pair] = [(0.85, 0.85)] * 90 + [(0.75, 0.45)] * 10
    scenarios.append(Scenario(
        "ece_below_threshold", low_ece, probe_claim=0.75,
        expect_block_enforce=False,
        note="gap>0.2 but ECE 0.03 < 0.25 -> ECE gate holds",
    ))

    # 5. High ECE but low claim: miscalibrated, yet the claim is not
    #    overconfident -> no block.
    low_claim: List[Pair] = [(0.3, 0.0)] * 100
    scenarios.append(Scenario(
        "high_ece_low_claim", low_claim, probe_claim=0.3,
        expect_block_enforce=False,
        note="ECE 0.3 > 0.25 but claim 0.3 < 0.7 -> no block",
    ))

    # 6. Insufficient samples: must abstain regardless of mode.
    scenarios.append(Scenario(
        "insufficient_samples", [(0.9, 0.0)] * 3, probe_claim=0.9,
        expect_block_enforce=False,
        note="3 < min_samples 20 -> abstain",
    ))

    return scenarios


def _tracker_for(sc: Scenario, min_samples: int = 20,
                 min_bin_samples: int = 5) -> CalibrationTracker:
    """Seed a tracker with the scenario's pair history.

    Args:
        sc: the scenario.
        min_samples: tracker min_samples gate.
        min_bin_samples: tracker per-bin trust gate.

    Returns:
        A populated CalibrationTracker.
    """
    t = CalibrationTracker(min_samples=min_samples, min_bin_samples=min_bin_samples)
    for p, y in sc.pairs:
        t.record(p, y)
    return t


def evaluate_scenario(sc: Scenario, enforce: bool) -> Dict:
    """Run one scenario through a sole CalibrationValidator in a Council.

    Args:
        sc: the scenario.
        enforce: the validator mode.

    Returns:
        A dict with the verdict and the metrics behind it.
    """
    tracker = _tracker_for(sc)
    council = Council()
    council.register(CalibrationValidator(tracker, enforce=enforce))
    verdict = council.evaluate(
        World(state=np.array([0.0, 0.0])),
        IntentIR("probe", confidence=sc.probe_claim),
    )
    sig = verdict.signals[0]
    return {
        "scenario": sc.name,
        "enforce": enforce,
        "sample_count": tracker.sample_count,
        "ece": tracker.ece(),
        "calibrated_confidence": round(tracker.calibrated_confidence(sc.probe_claim), 4),
        "claimed": sc.probe_claim,
        "gap": round(sc.probe_claim - tracker.calibrated_confidence(sc.probe_claim), 4),
        "signal_passed": sig.passed,
        "signal_reason": sig.reason,
        "blocked": not verdict.validated,
        "decision_integrity": round(verdict.decision_integrity, 4),
        "escalation_requested": verdict.escalation_requested,
        "expect_block": sc.expect_block_enforce,
        "note": sc.note,
    }


def run_scenario_matrix() -> Tuple[List[Dict], bool]:
    """Evaluate every scenario in both modes and check the expectations.

    Returns:
        (rows, ok) where rows is one dict per (scenario, mode) and ok is True
        when enforce blocks exactly the intended overconfidence scenario and
        advisory blocks nothing.
    """
    rows: List[Dict] = []
    ok = True
    for sc in build_scenarios():
        adv = evaluate_scenario(sc, enforce=False)
        enf = evaluate_scenario(sc, enforce=True)
        rows.append(adv)
        rows.append(enf)
        # Advisory must NEVER block (measurement only).
        if adv["blocked"]:
            ok = False
        # Enforce must block iff the scenario expects it.
        if enf["blocked"] != sc.expect_block_enforce:
            ok = False
    return rows, ok


def _pipeline_metrics(pipeline, cycles: int) -> Dict:
    """Drive a pipeline and aggregate calibration-relevant metrics.

    Args:
        pipeline: a built GridWorld pipeline.
        cycles: number of cycles to run.

    Returns:
        Aggregate metrics dict.
    """
    from telos.tools.bench_loop import drive

    di_vals: List[float] = []
    emitted = 0
    escalations = 0
    calib_blocks = 0
    council_blocks = 0
    for step in drive(pipeline, cycles=cycles, user_name="pressure_test"):
        trace = step["trace"]
        res = step["result"]
        if trace is None:
            continue
        di_vals.append(float(trace.decision_integrity))
        if getattr(trace, "act_emitted_action", None):
            emitted += 1
        if getattr(trace, "escalation_requested", False):
            escalations += 1
        if not getattr(res, "council_blocked", False) and getattr(trace, "council_validated", True):
            pass
        if getattr(res, "council_blocked", False):
            council_blocks += 1
        for sig in (trace.council_signals or []):
            if sig.get("validator") == "CalibrationValidator" and not sig.get("passed", True):
                calib_blocks += 1
    n = max(1, len(di_vals))
    return {
        "cycles": len(di_vals),
        "action_emission_rate": round(emitted / n, 4),
        "mean_di": round(float(np.mean(di_vals)) if di_vals else 1.0, 4),
        "escalation_rate": round(escalations / n, 4),
        "council_block_rate": round(council_blocks / n, 4),
        "calibration_blocks": calib_blocks,
    }


def run_pipeline_ab(cycles: int = 40) -> Dict[str, Dict]:
    """A/B the real pipeline: advisory vs. enforce (canonical tracker).

    Also runs an "enforce + injected overconfident tracker" arm to show the
    validator CAN bite downstream when the failure mode is present.

    Args:
        cycles: cycles per arm.

    Returns:
        {arm_name: metrics}.
    """
    from telos.cli import _build_gridworld_pipeline

    out: Dict[str, Dict] = {}

    # Arm 1 — canonical advisory.
    p_adv = _build_gridworld_pipeline("/tmp/telos_pressure_adv")
    out["advisory"] = _pipeline_metrics(p_adv, cycles)
    p_adv.shutdown()

    # Arm 2 — enforce with the pipeline's own (real) tracker.
    p_enf = _build_gridworld_pipeline("/tmp/telos_pressure_enf")
    for v in p_enf.council._validators:
        if v.name == "CalibrationValidator":
            v.enforce = True
    out["enforce_real_tracker"] = _pipeline_metrics(p_enf, cycles)
    p_enf.shutdown()

    # Arm 3 — enforce with an injected OVERCONFIDENT tracker (the failure mode).
    p_over = _build_gridworld_pipeline("/tmp/telos_pressure_over")
    over = _tracker_for(Scenario("over", [(0.9, 0.0)] * 100, 0.9, True))
    for v in p_over.council._validators:
        if v.name == "CalibrationValidator":
            v.enforce = True
            v._tracker = over
    out["enforce_overconfident_tracker"] = _pipeline_metrics(p_over, cycles)
    p_over.shutdown()

    return out


def _fmt_matrix(rows: List[Dict]) -> str:
    """Render the scenario matrix as a text table.

    Args:
        rows: output of run_scenario_matrix.

    Returns:
        A printable table.
    """
    lines = [
        "Calibration Validator — scenario pressure matrix",
        "=" * 96,
        f"{'scenario':<26}{'mode':<10}{'n':>4}{'ECE':>8}{'claim':>7}{'cal':>7}{'gap':>8}{'signal':>8}{'block':>7}",
        "-" * 96,
    ]
    for r in rows:
        ece = "n/a" if r["ece"] is None else f"{r['ece']:.3f}"
        lines.append(
            f"{r['scenario']:<26}{'enforce' if r['enforce'] else 'advisory':<10}"
            f"{r['sample_count']:>4}{ece:>8}{r['claimed']:>7.2f}"
            f"{r['calibrated_confidence']:>7.2f}{r['gap']:>8.2f}"
            f"{('PASS' if r['signal_passed'] else 'BLOCK'):>8}"
            f"{('yes' if r['blocked'] else 'no'):>7}"
        )
    lines.append("-" * 96)
    return "\n".join(lines)


def _fmt_pipeline(ab: Dict[str, Dict]) -> str:
    """Render the pipeline A/B metrics as a text table.

    Args:
        ab: output of run_pipeline_ab.

    Returns:
        A printable table.
    """
    lines = [
        "Pipeline A/B — downstream effects (GridWorld)",
        "=" * 96,
        f"{'arm':<32}{'cycles':>7}{'action_emit':>12}{'mean_DI':>9}{'escal':>8}{'council_blk':>12}{'calib_blk':>11}",
        "-" * 96,
    ]
    for arm, m in ab.items():
        lines.append(
            f"{arm:<32}{m['cycles']:>7}{m['action_emission_rate']:>12.3f}"
            f"{m['mean_di']:>9.3f}{m['escalation_rate']:>8.3f}"
            f"{m['council_block_rate']:>12.3f}{m['calibration_blocks']:>11}"
        )
    lines.append("-" * 96)
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: optional argument list (defaults to sys.argv).

    Returns:
        Process exit code (0 when expectations hold, 1 otherwise).
    """
    parser = argparse.ArgumentParser(description="Calibration pressure test")
    parser.add_argument("--ci", action="store_true",
                        help="exit non-zero if expectations are not met")
    parser.add_argument("--cycles", type=int, default=40,
                        help="pipeline A/B cycles per arm (default 40)")
    parser.add_argument("--no-pipeline", action="store_true",
                        help="skip the pipeline A/B (matrix + council only)")
    args = parser.parse_args(argv)

    rows, ok = run_scenario_matrix()
    print(_fmt_matrix(rows))
    for r in rows:
        if r["enforce"] and r["blocked"]:
            print(f"  blocked: {r['scenario']:<26} -> {r['signal_reason']}")
    print()

    if not args.no_pipeline:
        ab = run_pipeline_ab(cycles=args.cycles)
        print(_fmt_pipeline(ab))
        print("  note: a lone Calibration BLOCK is diluted by the council's")
        print("        majority threshold — it stops the cycle only when other")
        print("        validators also dissent (or the name is a hard veto).")
        print()

    print(f"EXPECTATIONS: {'PASS' if ok else 'FAIL'} "
          f"(enforce blocks only overconfidence; advisory blocks nothing)")
    if args.ci and not ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
