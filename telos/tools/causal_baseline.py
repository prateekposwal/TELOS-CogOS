"""
Causal baseline freeze (v8 Phase 0) — one reproducible measurement of the kernel.

Runs the canonical GridWorld pipeline (the same shape the live producer builds:
10 worlds, horizon 5, declared mission, verified learning + curriculum, the 5
council validators with MemoryAdvisor connected to the failure ledger and the
KnowledgeGraph) for a fixed number of cycles under a fixed seed, and records a
durable baseline artifact. This is the comparison baseline for every later v8
phase: it measures the system as it is, it does not change behaviour.

The baseline is deliberately isolated: all persistence paths point into a fresh
temp directory so a prior run cannot leak state in. It does NOT warm the skill
library from `/tmp` checkpoints (the live producer does), so numbers differ
slightly from a warm live process; the config is printed and recorded so the
run is reproducible.

Usage:
    PYTHONPATH=. python3 telos/tools/causal_baseline.py --cycles 120
    PYTHONPATH=. python3 telos/tools/causal_baseline.py --cycles 120 \
        --json telos/audit/causal_baseline.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def build(workdir: str, seed: int = 42,
          config_overrides: Optional[Dict[str, Any]] = None
          ) -> Tuple[Any, Any, Dict[str, Any]]:
    """Build the canonical GridWorld pipeline in an isolated workdir.

    Args:
        workdir: directory for every persistence artifact (isolated).
        seed: deterministic seed for reproducible fingerprints.
        config_overrides: optional PipelineConfig keyword overrides (used by
            the ablation harness to toggle a supported switch, e.g.
            ``distributed_council_enabled=False``); None keeps the canonical
            config byte-identical.

    Returns:
        (pipeline, simulator, build_record) — the built pipeline, its
        simulator, and the exact config used (for reproducibility).
    """
    from telos_task import (
        GridSim, GridAdpt, DEFAULT_BLOCKED, DEFAULT_REWARDS,
        MISSION_NAME, MISSION_DESCRIPTION,
    )
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
    from telos.core.ledger.experience_manager import ExperienceManager, ExperienceConfig
    from telos.core.simulation import CounterfactualEngine

    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    cfg_kwargs: Dict[str, Any] = dict(
        adapter=GridAdpt(), simulator=sim, compute_budget_ms=100.0, state_dim=2,
        n_worlds=10, horizon=5,
        mission_name=MISSION_NAME, mission_description=MISSION_DESCRIPTION,
        checkpoint_path=os.path.join(workdir, "cp"),
        knowledge_path=os.path.join(workdir, "kg.json"),
        ledger_path=os.path.join(workdir, "ld.json"),
        identity_path=os.path.join(workdir, "id.json"),
        pattern_path=os.path.join(workdir, "pt.json"),
        memory_path=os.path.join(workdir, "mem.json"),
        reality_gap_state_path=os.path.join(workdir, "rg.json"),
        deterministic_seed=seed,
        verified_learning=True,
        learning_curriculum=True,
    )
    if config_overrides:
        cfg_kwargs.update(config_overrides)
    pipe = TelosV14Pipeline(PipelineConfig(**cfg_kwargs))
    skill_lib = SkillLibrary()
    ExperienceManager(skill_lib, ExperienceConfig(
        utility_threshold=0.1, index_interval=1, verified_acquisition=True))
    sim_engine = CounterfactualEngine(sim)
    for stream in [
        ReflexStream(skill_lib), PerceptionStream(skill_lib),
        MemoryStream(skill_lib), PlanningStream(skill_lib, sim_engine=sim_engine),
        InquiryStream(skill_lib),
        TheoryStream(skill_lib, theory_builder=getattr(pipe, "_theory_builder", None),
                     curriculum=getattr(pipe, "curriculum", None)),
    ]:
        pipe.register_stream(stream)
    memory_advisor = MemoryAdvisor(skill_lib)
    for validator in [RealityValidator(), ConstraintValidator(), memory_advisor,
                      MissionDriftDetector(drift_threshold=5.0),
                      EvidenceProvenanceValidator()]:
        pipe.register_validator(validator)
    im = pipe.infra_manager
    memory_advisor.connect(
        failure_ledger=getattr(im, "failures", None),
        knowledge_graph=im.knowledge if hasattr(im, "knowledge") else None,
    )
    build_record = {
        "adapter": "GridAdpt",
        "simulator": "GridSim",
        "n_worlds": 10,
        "horizon": 5,
        "compute_budget_ms": 100.0,
        "mission_name": MISSION_NAME,
        "verified_learning": True,
        "learning_curriculum": True,
        "deterministic_seed": seed,
        "validators": ["RealityValidator", "ConstraintValidator", "MemoryAdvisor",
                       "MissionDriftDetector", "EvidenceProvenanceValidator"],
        "memory_advisor_connected": True,
        "skill_library_warm_start": False,
        "config_overrides": dict(config_overrides or {}),
        "code_fingerprint": _code_fingerprint(),
    }
    return pipe, sim, build_record


def _code_fingerprint() -> str:
    """Hash the modules that define the block/decision path.

    Returns:
        A short hex digest; equal across runs of identical code, so the
        baseline artifact records which kernel produced it.
    """
    import hashlib
    h = hashlib.sha256()
    for mod in (
        "telos/core/governance/firewall.py",
        "telos/core/council/base.py",
        "telos/core/council/validators/memory.py",
        "telos/core/infra_manager/knowledge_manager.py",
        "telos/core/infra_manager/infrastructure_manager.py",
        "telos/core/governance/recovery_types.py",
        "telos/core/phases/act.py",
        "telos/core/runtime.py",
    ):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), mod)
        try:
            with open(path, "rb") as fh:
                h.update(mod.encode())
                h.update(fh.read())
        except OSError:
            h.update(mod.encode())
            h.update(b"<missing>")
    return h.hexdigest()[:16]


def _stats(vals: List[float]) -> Dict[str, Any]:
    """Summarize a numeric series.

    Args:
        vals: the numeric values.

    Returns:
        A dict with n/min/mean/max (empty -> {"n": 0}).
    """
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min": round(min(vals), 4),
            "mean": round(statistics.fmean(vals), 4),
            "max": round(max(vals), 4)}


def run(cycles: int = 120, seed: int = 42) -> Dict[str, Any]:
    """Run the causal baseline and aggregate its durable metrics.

    Args:
        cycles: number of pipeline cycles.
        seed: deterministic seed.

    Returns:
        The baseline report dict (JSON-ready).
    """
    from telos.tools.bench_loop import drive

    workdir = tempfile.mkdtemp(prefix="telos_causal_baseline_")
    pipe, sim, build_record = build(workdir, seed)

    di_vals: List[float] = []
    md_vals: List[float] = []
    duration_vals: List[float] = []
    acted = 0
    episodes = 0
    goal_reached = 0
    firewall_blocks: Counter = Counter()
    blocking_validators: Counter = Counter()
    dissenters: Counter = Counter()
    dissent_reasons: Counter = Counter()
    decision_modes: Counter = Counter()
    blocked_by_gate: Counter = Counter()
    intents: Counter = Counter()
    stream_activations: Counter = Counter()
    escalations = 0
    axiom_411_pass = 0
    axiom_411_fail = 0
    axiom_411_reasons: Counter = Counter()
    axiom_any_fail: Counter = Counter()
    kg_node_approaches: Counter = Counter()
    last_state = None

    for step in drive(pipe, cycles, user_name="causal-baseline"):
        trace = step["trace"]
        if trace is None:
            continue
        di_vals.append(float(trace.decision_integrity))
        md_vals.append(float(trace.mission_drift))
        duration_vals.append(float(trace.cycle_duration_ms))
        intents[trace.selected_intent.intent_type if trace.selected_intent else None] += 1
        for sa in (trace.stream_activations or []):
            if getattr(sa, "activated", False):
                stream_activations[sa.stream_name] += 1
        if trace.firewall_blocked:
            firewall_blocks[trace.firewall_blocked_by or "unknown"] += 1
        if trace.blocking_validator:
            blocking_validators[trace.blocking_validator] += 1
        cg = trace.council_gate or {}
        for d in (cg.get("dissenters") or []):
            dissenters[d.get("validator")] += 1
            dissent_reasons[str(d.get("reason"))[:120]] += 1
        if trace.escalation_requested:
            escalations += 1
        mode = trace.decision_mode
        decision_modes[getattr(mode, "value", mode) or "none"] += 1
        if getattr(trace, "blocked_by_gate", None):
            blocked_by_gate[trace.blocked_by_gate] += 1
        results = trace.axiom_results or {}
        row411 = results.get("4.11")
        if isinstance(row411, dict):
            if row411.get("passed"):
                axiom_411_pass += 1
            else:
                axiom_411_fail += 1
                axiom_411_reasons[str(row411.get("reason"))[:120]] += 1
        for aid, row in results.items():
            if isinstance(row, dict) and not row.get("passed"):
                axiom_any_fail[aid] += 1
        if trace.selected_action is not None and not step["result"].firewall_blocked:
            acted += 1
        if step["terminal"]:
            episodes += 1
            goal_reached += 1
        last_state = step["state_after"]

    # ── Reality Gap (the model's own falsification record) ──
    tracker = getattr(pipe, "_reality_gap_tracker", None)
    rg: Dict[str, Any] = {}
    try:
        model = tracker.model("world")
        rg = {
            "validation_count": int(model.validation_count),
            "recent_mean_gap": round(float(model.recent_mean_gap), 4),
            "total_gap": round(float(model.total_gap), 4),
            "tested": bool(model.tested),
            "ever_falsified": bool(model.ever_falsified),
            "last_validation_cycle": model.last_validation_cycle,
            "falsification_threshold": float(getattr(model, "falsification_threshold", 0.0)),
        }
    except Exception as exc:  # honesty: record why a metric is absent
        rg = {"error": repr(exc)}

    # ── KnowledgeGraph growth ──
    kg = getattr(pipe.infra_manager, "knowledge", None)
    kg_report: Dict[str, Any] = {}
    try:
        nodes = dict(getattr(kg, "_nodes", {}))
        edges = list(getattr(kg, "_edges", {}).values())
        edge_types: Counter = Counter()
        for e in edges:
            edge_types[getattr(e, "edge_type", "unknown")] += 1
        for n in nodes.values():
            kg_node_approaches[getattr(n, "approach", "unknown")] += 1
        kg_report = {
            "nodes": len(nodes),
            "archived_nodes": len(getattr(kg, "_archived_nodes", {})),
            "edges": len(edges),
            "edges_by_type": dict(edge_types.most_common()),
            "hot_node_approaches": dict(kg_node_approaches.most_common(10)),
            "failure_nodes": sum(
                1 for n in nodes.values()
                if float(getattr(n, "outcome", 1.0)) < 0.51),
        }
    except Exception as exc:
        kg_report = {"error": repr(exc)}

    # ── Memory + resource + council config ──
    memory_stats: Dict[str, Any] = {}
    try:
        _ms = pipe._memory_controller.stats
        memory_stats = dict(_ms() if callable(_ms) else _ms)
    except Exception as exc:
        memory_stats = {"error": repr(exc)}
    fw = pipe._firewall
    policy = getattr(pipe.infra_manager, "policy", None)
    policy_stats: Dict[str, Any] = {}
    try:
        policy_stats = {
            "firewall_di_threshold": round(float(policy.firewall_di_threshold), 4),
            "risk_tolerance": round(float(policy.current.risk_tolerance), 4),
        }
    except Exception as exc:
        policy_stats = {"error": repr(exc)}

    # ── Persistence state ──
    persisted: Dict[str, Any] = {}
    for name in ("cp", "kg.json", "ld.json", "id.json", "pt.json", "mem.json", "rg.json"):
        path = os.path.join(workdir, name)
        if os.path.isdir(path):
            files = sorted(os.listdir(path))
            persisted[name] = {"kind": "dir", "entries": len(files),
                               "latest": files[-1] if files else None}
        elif os.path.exists(path):
            persisted[name] = {"kind": "file", "bytes": os.path.getsize(path)}
        else:
            persisted[name] = {"kind": "absent"}

    return {
        "phase": "v8-phase0-causal-baseline",
        "cycles": cycles,
        "seed": seed,
        "build": build_record,
        "reproduction_command": (
            "PYTHONPATH=. python3 telos/tools/causal_baseline.py "
            f"--cycles {cycles} --seed {seed}"
        ),
        "acted_cycles": acted,
        "firewall_blocks": dict(firewall_blocks.most_common()),
        "firewall_block_count": sum(firewall_blocks.values()),
        "episodes": episodes,
        "goal_reached": goal_reached,
        "final_state": (last_state.tolist() if last_state is not None else None),
        "decision_integrity": _stats(di_vals),
        "mission_drift": _stats(md_vals),
        "decision_latency_ms": _stats(duration_vals),
        "council": {
            "blocking_validators": dict(blocking_validators.most_common()),
            "dissenters": dict(dissenters.most_common()),
            "top_dissent_reasons": dict(dissent_reasons.most_common(10)),
            "escalations": escalations,
        },
        "evidence": {
            "evidence_provenance_dissents": dissenters.get("EvidenceProvenanceValidator", 0),
        },
        "decision_modes": dict(decision_modes.most_common()),
        "blocked_by_gate": dict(blocked_by_gate.most_common()),
        "intents": dict(intents.most_common()),
        "stream_activations": dict(stream_activations.most_common()),
        "memory": memory_stats,
        "reality_gap": rg,
        "knowledge_graph": kg_report,
        "axioms": {
            "4.11_pass": axiom_411_pass,
            "4.11_fail": axiom_411_fail,
            "4.11_fail_reasons": dict(axiom_411_reasons.most_common(5)),
            "any_fail_by_axiom": dict(axiom_any_fail.most_common(10)),
        },
        "policy": policy_stats,
        "persistence": persisted,
        "workdir": workdir,
    }


def main(argv=None) -> int:
    """Run the Phase 0 baseline and write the durable artifact.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Process exit code (0 — informational).
    """
    parser = argparse.ArgumentParser(description="v8 Phase 0 causal baseline freeze")
    parser.add_argument("--cycles", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", help="write the baseline artifact to this path")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    report = run(args.cycles, args.seed)
    if not args.quiet:
        print("\n            TELOS v8 Phase 0 — causal baseline")
        print("=" * 74)
        print(f"  cycles={report['cycles']} seed={report['seed']} "
              f"fingerprint={report['build']['code_fingerprint']}")
        print(f"  acted_cycles         : {report['acted_cycles']}")
        print(f"  firewall_blocks      : {report['firewall_blocks']}")
        print(f"  episodes / goal      : {report['episodes']} / {report['goal_reached']}")
        print(f"  DI                   : {report['decision_integrity']}")
        print(f"  MD                   : {report['mission_drift']}")
        print(f"  dissenters           : {report['council']['dissenters']}")
        print(f"  blocking validators  : {report['council']['blocking_validators']}")
        print(f"  intents              : {report['intents']}")
        print(f"  stream activations   : {report['stream_activations']}")
        print(f"  reality gap          : {report['reality_gap']}")
        print(f"  knowledge graph      : {report['knowledge_graph']}")
        print(f"  axiom 4.11           : {report['axioms']['4.11_pass']} pass / "
              f"{report['axioms']['4.11_fail']} fail")
        print(f"  policy               : {report['policy']}")
        print("=" * 74)
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        if not args.quiet:
            print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
