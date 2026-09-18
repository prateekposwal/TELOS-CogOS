#!/usr/bin/env python3
"""Live axiom-compliance evaluation — measures per-cycle axiom compliance of a
REAL running pipeline, not a synthetic healthy prover input.

WHY THIS EXISTS (the measured-vs-claimed gap)
---------------------------------------------
`verification_eval.py` reports 4/4 because the *axiom falsifier baseline* is
42/42 on a fully-populated synthetic input. That proves the constitution is
falsifiable and green on healthy input; it does NOT prove that every live
pipeline trace obeys all 42 axioms. Those are different claims, and only the
first was measured.

This harness runs the REAL GridWorld pipeline for N cycles and records the
per-cycle result the runtime's own `run_axiom_prover` attaches to each
DecisionTrace (`trace.axiom_results`). It writes the honest distribution to
`telos/audit/axiom_compliance.json` — including the degraded tail — and a
machine-checkable verdict for the MEASUREMENT itself.

`--ci` exits 0 only when the measurement is well-formed (the requested cycles
were measured, every measured cycle carried a full 42-axiom result set). It
does NOT assert a compliance floor: the measured live compliance is written
verbatim, and a proposed constitutional floor is reported separately with its
pass/fail so the gap is visible rather than smoothed away.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/axiom_compliance_eval.py --cycles 40
  PYTHONPATH=. ./.venv/bin/python telos/tools/axiom_compliance_eval.py --cycles 40 --ci
  PYTHONPATH=. ./.venv/bin/python telos/tools/axiom_compliance_eval.py --cycles 10 --determinism
"""

import argparse
import collections
import hashlib
import json
import logging
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.axioms.registry import AXIOM_IDS  # noqa: E402
from telos.core.verifier.measurement import provenance, read_measurement  # noqa: E402

PRODUCER = "telos/tools/axiom_compliance_eval.py"

# The canonical axiom count (AXIOMS.md / genesis = 42). Locked to the writer by
# tests/core/test_axiom_compliance_eval.py.
EXPECTED_AXIOMS = 42
assert len(AXIOM_IDS) == EXPECTED_AXIOMS, "axiom registry drift"

# The measurement-integrity criteria the CI gate reads. These assert the
# MEASUREMENT is well-formed, not that compliance meets a floor.
CRITERIA: List[str] = [
    "cycles_measured",
    "traces_present",
    "axiom_set_complete",
]

# The constitutional ideal: every live cycle obeys all 42 axioms. Reported as a
# proposed gate (NOT wired to --ci) so the measured value is visible honestly.
PROPOSED_COMPLIANCE_FLOOR = 1.0

# Per-axiom diagnosis of the 14 axioms that fail on live cycles. Categories:
#   prover_input_incomplete — the real component is wired onto the pipeline,
#       but the live prover call never passes the kwarg the predicate reads and
#       the predicate has no `pipeline` fallback (wiring gap, not a violation).
#   exposure_gap — the real component exists but is not exposed where the
#       predicate looks (wrong attribute / return value discarded).
#   conditional_absence_fail_closed — the predicate fails when the telemetry
#       is absent, and the telemetry is only produced under a condition a
#       healthy run does not meet ("no valid trace ⇒ cannot verify ⇒ failed").
#   advisory_path_skipped — an advisory layer (DistributedCouncil) that would
#       populate the signal is skipped or returns early; fail-closed.
FAILING_AXIOM_DIAGNOSIS: Dict[str, Dict[str, str]] = {
    "2.7": {
        "category": "exposure_gap",
        "evidence": "runtime.py:1810 calls ErrorAttributionEngine.attribute(...) "
                    "but discards the returned attribution; neither ctx.error_attribution "
                    "nor trace.error_attribution is ever set (grep: no assignment).",
    },
    "4.5": {
        "category": "conditional_absence_fail_closed",
        "evidence": "ctx.local_optima_escape is set only in phases/streams.py:296 "
                    "when forced_exploration fires; a healthy run never triggers "
                    "stuck-escape, so the predicate reports failure by absence.",
    },
    "4.8": {
        "category": "prover_input_incomplete",
        "evidence": "pipeline._model_competition exists (runtime.py:350) but "
                    "pipeline_finalize.run_axiom_prover passes only stream_results+pipeline; "
                    "axiom_prover.py:299 reads kwargs['model_competition'] with no pipeline fallback.",
    },
    "4.9": {
        "category": "exposure_gap",
        "evidence": "RelationalContext exists (reasoning/relational.py) and is embedded in "
                    "ctx.identity_state['R_t'] (runtime.py:1973-1996) but ctx.relational_context "
                    "is never set; axiom_prover.py:312-314 checks only kwargs/ctx.relational_context.",
    },
    "4.10": {
        "category": "exposure_gap",
        "evidence": "The live SystemSelf is infra_manager.system_self (infrastructure_manager.py:60); "
                    "axiom_prover.py:347 reads pipeline._system_self (never assigned) — wrong attribute.",
    },
    "4.11": {
        "category": "advisory_path_skipped",
        "evidence": "ctx.cooperative_verdict is written in _run_distributed_council (runtime.py:2528); "
                    "fast mode sets skip_advisory_layers so the crew never runs, and the method also "
                    "returns early without a verdict/selected_intent — predicate stays fail-closed.",
    },
    "6.3": {
        "category": "prover_input_incomplete",
        "evidence": "pipeline._interpretation_engine exists but axiom_prover.py:417 reads only "
                    "kwargs['interpretation_engine'] with no pipeline fallback.",
    },
    "6.4": {
        "category": "prover_input_incomplete",
        "evidence": "pipeline._identity_compression exists but axiom_prover.py:426 reads only "
                    "kwargs['identity_compression'] with no pipeline fallback.",
    },
    "6.5": {
        "category": "prover_input_incomplete",
        "evidence": "pipeline._theory_builder exists but axiom_prover.py:435 reads only "
                    "kwargs['theory_builder'] with no pipeline fallback.",
    },
    "6.6": {
        "category": "prover_input_incomplete",
        "evidence": "pipeline._model_competition exists but axiom_prover.py:444 reads only "
                    "kwargs['model_competition'] with no pipeline fallback.",
    },
    "6.7": {
        "category": "prover_input_incomplete",
        "evidence": "pipeline._explanation_compression exists but axiom_prover.py:456 reads only "
                    "kwargs['explanation_compression'] with no pipeline fallback.",
    },
    "6.8": {
        "category": "exposure_gap",
        "evidence": "axiom_prover.py:463 reads only kwargs['system_self']; the live SystemSelf is "
                    "infra_manager.system_self and is never passed nor fallback-resolved.",
    },
    "6.9": {
        "category": "prover_input_incomplete",
        "evidence": "pipeline._curiosity_drive exists but axiom_prover.py:473 reads only "
                    "kwargs['curiosity_drive'] with no pipeline fallback.",
    },
    "6.10": {
        "category": "prover_input_incomplete",
        "evidence": "pipeline._unknown_unknown_detector exists but axiom_prover.py:482 reads only "
                    "kwargs['unknown_unknown_detector'] with no pipeline fallback.",
    },
}


def _build(workdir: str, mode: str, seed: int):
    """Build a deterministic GridWorld pipeline for an isolated run.

    Args:
        workdir: directory for checkpoint/kg/ledger artifacts (isolated).
        mode: PipelineConfig mode ("standard" or "fast").
        seed: deterministic seed for reproducible fingerprints.

    Returns:
        The configured TelosV14Pipeline.
    """
    from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS
    from telos.core.runtime import PipelineConfig, TelosV14Pipeline
    from telos.core.streams.implementations import (
        ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
    )
    from telos.core.streams.inquiry_stream import InquiryStream
    from telos.core.council.validators import (
        RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
        EvidenceProvenanceValidator,
    )
    from telos.core.ledger.skill_library import SkillLibrary
    from telos.core.simulation import CounterfactualEngine

    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim, compute_budget_ms=100.0,
        state_dim=2, n_worlds=8, horizon=5,
        checkpoint_path=os.path.join(workdir, "cp"),
        checkpoint_every_n=200,
        knowledge_path=os.path.join(workdir, "kg.json"),
        ledger_path=os.path.join(workdir, "ld.json"),
        identity_path=os.path.join(workdir, "id.json"),
        pattern_path=os.path.join(workdir, "pt.json"),
        deterministic_seed=seed, mode=mode,
    ))
    sl = SkillLibrary()
    for s in [ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
              PlanningStream(sl, sim_engine=CounterfactualEngine(sim)),
              InquiryStream(sl),
              TheoryStream(sl, theory_builder=getattr(pipe, "_theory_builder", None))]:
        pipe.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(), MemoryAdvisor(sl),
              MissionDriftDetector(drift_threshold=5.0), EvidenceProvenanceValidator()]:
        pipe.register_validator(v)
    return pipe


def _run_records(cycles: int, mode: str, seed: int) -> List[Optional[Dict[str, Any]]]:
    """Run the REAL pipeline and collect one axiom-result record per cycle.

    Args:
        cycles: number of pipeline cycles to execute.
        mode: PipelineConfig mode ("standard" or "fast").
        seed: deterministic seed.

    Returns:
        A list of per-cycle records (None when no trace was produced). Each
        record is {"passed": int|None, "failed": [...], "axiom_ids": [...],
        "reasons": {axiom_id: reason}} as attached by run_axiom_prover.
    """
    import numpy as np

    records: List[Optional[Dict[str, Any]]] = []
    with tempfile.TemporaryDirectory(prefix="telos_axiom_compliance_") as wd:
        pipe = _build(wd, mode, seed)
        state = np.array([0.0, 0.0])
        for _ in range(cycles):
            result = pipe.execute(np.array(state, dtype=float),
                                  user_name="axiom-compliance-eval")
            trace = result.decision_trace
            if trace is None:
                records.append(None)
            else:
                ax = getattr(trace, "axiom_results", None)
                if not ax:
                    records.append({"passed": None, "failed": [], "axiom_ids": [],
                                    "reasons": {}})
                else:
                    failed = [aid for aid, r in ax.items() if not r["passed"]]
                    records.append({
                        "passed": len(ax) - len(failed),
                        "failed": sorted(failed),
                        "axiom_ids": sorted(ax.keys()),
                        "reasons": {aid: ax[aid].get("reason", "")
                                    for aid in ax if not ax[aid]["passed"]},
                    })
            act = (pipe._last_trace.selected_action
                   if getattr(pipe, "_last_trace", None) else None)
            if act is not None:
                nxt = pipe.config.simulator.transition(state, act)
                if 0.0 <= float(nxt[0]) <= 4.0 and 0.0 <= float(nxt[1]) <= 4.0:
                    state = nxt
    return records


def _percentile(values: List[float], pct: float) -> float:
    """Nearest-rank percentile (no numpy dependency, deterministic).

    Args:
        values: non-empty list of numbers.
        pct: percentile in [0, 100].

    Returns:
        The nearest-rank percentile value.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = max(0, min(len(ordered) - 1,
                      int(round(pct / 100.0 * (len(ordered) - 1)))))
    return float(ordered[rank])


def _fingerprint(records: List[Optional[Dict[str, Any]]]) -> str:
    """Deterministic digest of the per-cycle compliance series.

    Args:
        records: the per-cycle records produced by `_run_records`.

    Returns:
        A 16-hex-char digest, stable across identical runs.
    """
    digest = hashlib.sha256()
    for i, r in enumerate(records):
        if r is None:
            digest.update(f"{i}:none|".encode())
        else:
            digest.update(f"{i}:{r['passed']}:{','.join(r['failed'])}|".encode())
    return digest.hexdigest()[:16]


def summarize(records: List[Optional[Dict[str, Any]]], requested_cycles: int,
              mode: str, seed: int) -> Dict[str, Any]:
    """Aggregate per-cycle records into the honest compliance payload.

    This is a PURE function (no pipeline) so the schema and the fail-closed
    verdict logic are testable without running a full pipeline.

    Args:
        records: per-cycle records from `_run_records`.
        requested_cycles: the number of cycles the caller asked for.
        mode: the PipelineConfig mode used.
        seed: the deterministic seed used.

    Returns:
        The measurement payload (without provenance/diagnosis, which
        `evaluate` attaches).
    """
    measured = [r for r in records if r is not None and r["passed"] is not None]
    with_trace = [r for r in records if r is not None]
    passed_counts = [float(r["passed"]) for r in measured]
    n_measured = len(measured)

    failed_counter: "collections.Counter[str]" = collections.Counter()
    for r in measured:
        failed_counter.update(r["failed"])

    healthy = sum(1 for r in measured if r["passed"] == EXPECTED_AXIOMS)
    degraded = sum(1 for r in measured if r["passed"] < EXPECTED_AXIOMS)

    seen_ids = set()
    for r in measured:
        seen_ids.update(r["axiom_ids"])

    last_reasons: Dict[str, str] = {}
    if measured:
        last_reasons = dict(measured[-1]["reasons"])

    mean_pct = (sum(passed_counts) / n_measured / EXPECTED_AXIOMS) if n_measured else 0.0
    min_pct = (min(passed_counts) / EXPECTED_AXIOMS) if passed_counts else 0.0
    p10_pct = (_percentile(passed_counts, 10) / EXPECTED_AXIOMS) if passed_counts else 0.0

    criteria = {
        # Well-formed only when ALL requested cycles produced a trace.
        "cycles_measured": requested_cycles > 0 and len(with_trace) == requested_cycles
                           and n_measured == requested_cycles,
        # Every measured cycle must carry a full axiom result set.
        "traces_present": n_measured > 0 and all(
            r is not None and r["passed"] is not None for r in records),
        # The union of seen ids must be the whole constitution.
        "axiom_set_complete": seen_ids == set(AXIOM_IDS),
    }
    passed_criteria = sum(1 for v in criteria.values() if v)

    worst = [
        {"axiom": aid, "failed_cycles": int(n),
         "fraction": round(n / n_measured, 4) if n_measured else 0.0,
         "reason": last_reasons.get(aid, "")}
        for aid, n in failed_counter.most_common()
    ]

    return {
        "mode": mode,
        "seed": seed,
        "cycles": requested_cycles,
        "cycles_with_trace": len(with_trace),
        "cycles_measured": n_measured,
        "expected_axioms": EXPECTED_AXIOMS,
        "mean_compliance": round(mean_pct, 6),
        "min_compliance": round(min_pct, 6),
        "p10_compliance": round(p10_pct, 6),
        "mean_passed_axioms": round(sum(passed_counts) / n_measured, 4) if n_measured else 0.0,
        "min_passed_axioms": int(min(passed_counts)) if passed_counts else 0,
        "healthy_cycles": healthy,
        "degraded_cycles": degraded,
        "worst_failed_axioms": worst,
        "fail_count": len(worst),
        "fingerprint": _fingerprint(records),
        "criteria": criteria,
        "verdict": {
            "passed": passed_criteria == len(CRITERIA),
            "passed_count": passed_criteria,
            "total": len(CRITERIA),
        },
        "proposed_compliance_gate": {
            "floor": PROPOSED_COMPLIANCE_FLOOR,
            "measured_mean": round(mean_pct, 6),
            "measured_min": round(min_pct, 6),
            "passes": bool(passed_counts) and min_pct >= PROPOSED_COMPLIANCE_FLOOR,
            "note": ("Not wired to --ci: --ci gates measurement well-formedness, "
                     "not a compliance floor. The gate is reported so the gap is "
                     "visible — the constitution is falsifiable and green on "
                     "healthy synthetic input, but live traces are not yet 42/42."),
        },
    }


def evaluate(cycles: int = 40, mode: str = "fast", seed: int = 42,
             determinism: bool = False) -> Dict[str, Any]:
    """Run the real pipeline and build the axiom-compliance artifact.

    Args:
        cycles: number of real pipeline cycles to measure.
        mode: PipelineConfig mode ("fast" or "standard").
        seed: deterministic seed.
        determinism: when True, run a second identical pipeline and record
            whether the per-cycle fingerprints match (documents repeatability).

    Returns:
        The full payload to write to telos/audit/axiom_compliance.json.
    """
    records = _run_records(cycles, mode, seed)
    payload = summarize(records, cycles, mode, seed)
    payload["provenance"] = provenance(PRODUCER, CRITERIA)
    payload["diagnosis"] = FAILING_AXIOM_DIAGNOSIS

    if determinism:
        second = _run_records(cycles, mode, seed)
        payload["determinism"] = {
            "runs": 2,
            "fingerprints": [payload["fingerprint"], _fingerprint(second)],
            "identical": payload["fingerprint"] == _fingerprint(second),
        }
    else:
        payload["determinism"] = {
            "runs": 1,
            "fingerprints": [payload["fingerprint"]],
            "identical": None,
            "note": "single run; pass --determinism to compare two identical-seed runs",
        }
    return payload


def ci_ok(payload: Dict[str, Any]) -> bool:
    """Fail-closed gate: True only when the measurement is well-formed.

    Args:
        payload: the dict returned by `summarize`/`evaluate`.

    Returns:
        True only when every measurement-integrity criterion passed. A missing
        or malformed verdict/criteria block returns False (never a silent pass).
    """
    verdict = payload.get("verdict")
    criteria = payload.get("criteria")
    if not isinstance(verdict, dict) or not isinstance(criteria, dict):
        return False
    if not isinstance(verdict.get("passed"), bool) or verdict.get("passed") is not True:
        return False
    return all(criteria.get(name) is True for name in CRITERIA)


def print_report(payload: Dict[str, Any]) -> None:
    """Print the honest compliance table and per-axiom diagnosis.

    Args:
        payload: the dict returned by `evaluate`.
    """
    print(f"\n{'TELOS Live Axiom-Compliance Evaluation':^78}")
    print("=" * 78)
    print(f"  mode={payload['mode']}  cycles={payload['cycles']}  "
          f"traces={payload['cycles_with_trace']}  "
          f"fingerprint={payload['fingerprint']}")
    print(f"  mean={payload['mean_compliance']:.3f} ({payload['mean_passed_axioms']:.1f}/42)  "
          f"min={payload['min_compliance']:.3f} ({payload['min_passed_axioms']}/42)  "
          f"p10={payload['p10_compliance']:.3f}")
    print(f"  healthy cycles (42/42): {payload['healthy_cycles']}   "
          f"degraded cycles (<42): {payload['degraded_cycles']}")
    print("-" * 78)
    if payload["worst_failed_axioms"]:
        print("  failing axioms (cycle counts):")
        for row in payload["worst_failed_axioms"]:
            diag = FAILING_AXIOM_DIAGNOSIS.get(row["axiom"], {})
            print(f"    {row['axiom']:<6} {row['failed_cycles']:>4}/{payload['cycles_measured']}  "
                  f"[{diag.get('category', 'unknown')}]")
    else:
        print("  no failing axioms — all measured cycles 42/42")
    print("-" * 78)
    for name, ok in payload["criteria"].items():
        print(f"  criterion {name:<24}{'PASS' if ok else 'FAIL':>6}")
    gate = payload["proposed_compliance_gate"]
    print(f"  proposed compliance floor {gate['floor']:.1f} (not wired to --ci): "
          f"mean={gate['measured_mean']:.3f} -> {'PASS' if gate['passes'] else 'FAIL'}")
    print("=" * 78)
    verdict = payload["verdict"]
    print(f"AXIOM-COMPLIANCE MEASUREMENT: {'WELL-FORMED' if verdict['passed'] else 'MALFORMED'} "
          f"({verdict['passed_count']}/{verdict['total']} criteria)")
    if gate["passes"]:
        print(f"CONSTITUTIONAL FLOOR: PASS (min {gate['measured_min']:.3f} >= {gate['floor']:.1f})")
    else:
        print(f"CONSTITUTIONAL FLOOR: FAIL (min {gate['measured_min']:.3f} < {gate['floor']:.1f}) "
              f"— {payload['fail_count']} axioms fail on live cycles")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Live axiom-compliance evaluation")
    ap.add_argument("--cycles", type=int, default=40,
                    help="real pipeline cycles to measure (default 40)")
    ap.add_argument("--mode", choices=("fast", "standard"), default="fast",
                    help="pipeline mode (default fast)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--determinism", action="store_true",
                    help="run a second identical pipeline and compare fingerprints")
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless the MEASUREMENT is well-formed (never a compliance floor)")
    ap.add_argument("--verbose", action="store_true", help="keep pipeline warnings")
    ap.add_argument("--json", default="telos/audit/axiom_compliance.json",
                    help="path to write the evaluation JSON")
    args = ap.parse_args()

    if not args.verbose:
        logging.disable(logging.WARNING)

    if args.cycles < 1:
        print("axiom_compliance_eval: --cycles must be >= 1", file=sys.stderr)
        if args.ci:
            sys.exit(1)

    payload = evaluate(cycles=max(1, args.cycles), mode=args.mode,
                       seed=args.seed, determinism=args.determinism)
    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(PROJECT, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"(evaluation saved: {out})")
    print_report(payload)

    if args.ci:
        # Validate by re-reading the artifact through the same contract the
        # scorecard uses (writer<->reader linkage), then gate on the measurement.
        if args.json and not os.path.isabs(args.json):
            reread = read_measurement(PROJECT, args.json, tuple(CRITERIA))
            if reread is None:
                print("axiom_compliance_eval: artifact failed read-back validation",
                      file=sys.stderr)
                sys.exit(1)
        sys.exit(0 if ci_ok(payload) else 1)
