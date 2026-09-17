"""
Falsifiable Theorem Audit CLI — measures TELOS theorems against their nulls.

Runs a real GridWorld pipeline (twice, identically seeded) for N cycles,
collects the DecisionTraces, and evaluates the catalogue in
`telos/core/verifier/theorem_audit.py`. --ci exits 1 if any theorem fails.

Usage:
    PYTHONPATH=. python3 telos/tools/theorem_audit.py --cycles 40
    PYTHONPATH=. python3 telos/tools/theorem_audit.py --cycles 40 --ci
"""
import argparse
import hashlib
import os
import sys
import tempfile

import numpy as np

from telos.core.verifier.theorem_audit import run_audit


def _build(workdir: str, seed: int = 42):
    """Build a deterministic GridWorld pipeline and its start state.

    Args:
        workdir: directory for checkpoint/kg/ledger artifacts (isolated).
        seed: deterministic seed for reproducible fingerprints.

    Returns:
        (pipeline, start_state) tuple.
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
        knowledge_path=os.path.join(workdir, "kg.json"),
        ledger_path=os.path.join(workdir, "ld.json"),
        identity_path=os.path.join(workdir, "id.json"),
        pattern_path=os.path.join(workdir, "pt.json"),
        deterministic_seed=seed, mode="standard",
    ))
    sl = SkillLibrary()
    streams = [
        ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
        PlanningStream(sl, sim_engine=CounterfactualEngine(sim)),
        InquiryStream(sl),
        TheoryStream(sl, theory_builder=getattr(pipe, "_theory_builder", None)),
    ]
    for s in streams:
        pipe.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(), MemoryAdvisor(sl),
              MissionDriftDetector(drift_threshold=5.0), EvidenceProvenanceValidator()]:
        pipe.register_validator(v)
    return pipe, np.array([0.0, 0.0])


def _run(workdir: str, cycles: int, seed: int = 42):
    """Run the pipeline and collect traces + a determinism fingerprint.

    Args:
        workdir: isolated artifact directory.
        cycles: number of pipeline cycles.
        seed: deterministic seed.

    Returns:
        (config, traces, fingerprint) tuple.
    """
    pipe, state = _build(workdir, seed)
    traces = []
    digest = hashlib.sha256()
    for _ in range(cycles):
        result = pipe.execute(np.array(state, dtype=float), user_name="theorem-audit")
        trace = result.decision_trace
        if trace is None:
            continue
        traces.append(trace)
        si = getattr(trace, "selected_intent", None)
        digest.update((
            f"{trace.cycle_id}|{round(trace.decision_integrity, 6)}|"
            f"{round(trace.mission_drift, 6)}|"
            f"{getattr(si, 'intent_type', None)}|"
            f"{len(getattr(trace, 'strategic_options', []) or [])}"
        ).encode())
    return pipe.config, traces, digest.hexdigest()[:16]


def main(argv=None) -> int:
    """Run the theorem audit and print the falsifiable table.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Process exit code (0 = all theorems hold, 1 = a theorem failed).
    """
    parser = argparse.ArgumentParser(description="Falsifiable theorem audit")
    parser.add_argument("--cycles", type=int, default=40)
    parser.add_argument("--ci", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    with tempfile.TemporaryDirectory(prefix="telos_theorem_audit_a_") as wa, \
            tempfile.TemporaryDirectory(prefix="telos_theorem_audit_b_") as wb:
        config, traces_a, fp_a = _run(wa, args.cycles)
        _, traces_b, fp_b = _run(wb, args.cycles)

    report = run_audit(traces_a, config, fp_a, fp_b)

    print("\n              TELOS Falsifiable Theorem Audit")
    print("=" * 78)
    for row in report["rows"]:
        mark = "PASS" if row["passed"] else "FAIL"
        print(f"[{mark}] {row['id']:<22} {row['measured']}")
        print(f"        <{row['name']}> null: {row['null']}")
    print("=" * 78)
    print(f"THEOREM AUDIT: {'PASS' if report['passed'] else 'FAIL'}  "
          f"({sum(r['passed'] for r in report['rows'])}/{len(report['rows'])} theorems hold)")
    if not report["passed"] and args.ci:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
