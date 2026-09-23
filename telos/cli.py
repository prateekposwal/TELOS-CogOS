"""
TELOS CLI — Query, diagnose, and run TELOS from the terminal.

Usage:
    telos consult "what works for tracking?"  → query KnowledgeGraph
    telos status                              → DI/MD, mood, cycle count
    telos run                                 → one-shot pipeline execution
"""

import argparse
import sys
import os
import json


def main():
    parser = argparse.ArgumentParser(
        description="TELOS Cognitive Operating System — CLI"
    )
    from telos import __version__
    parser.add_argument(
        "--version", action="version", version=f"TELOS CogOS {__version__}"
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # telos consult
    consult_p = sub.add_parser("consult", help="Query the KnowledgeGraph")
    consult_p.add_argument("query", nargs="?", help="Natural language query")
    consult_p.add_argument("--domain", "-d", default="gridworld", help="Domain to search")
    consult_p.add_argument("--top-k", "-k", type=int, default=3, help="Top K results")

    # telos status
    status_p = sub.add_parser("status", help="Show pipeline status")

    # telos run
    run_p = sub.add_parser("run", help="Run one pipeline cycle")
    run_p.add_argument("--state", nargs="*", type=float, default=[0.0, 0.0],
                       help="Initial state vector (space-separated floats)")
    run_p.add_argument("--cycles", "-n", type=int, default=1,
                       help="Number of cycles to run (default 1)")

    args = parser.parse_args()

    if args.command == "consult":
        _cmd_consult(args)
    elif args.command == "status":
        _cmd_status()
    elif args.command == "run":
        _cmd_run(args)
    else:
        parser.print_help()


def _cmd_consult(args):
    """Query the KnowledgeGraph for relevant knowledge.
        Args:
            args: the args argument for this call.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from telos.core.infra_manager.knowledge_manager import KnowledgeManager
    from telos.core.infra_manager.mission_policy import MissionPolicyManager
    from telos.core.identity.system_self import SystemSelf

    policy = MissionPolicyManager()
    system_self = SystemSelf()
    km = KnowledgeManager(policy, system_self, domain=args.domain)

    query = args.query or ""
    result = km.search_knowledge(args.domain, top_k=args.top_k)

    print(f"\n🧠 TELOS KnowledgeGraph — domain: {args.domain}")
    print(f"   Query: '{query or '(all)'}'")
    print(f"   Results: {len(result)} found\n")

    for i, node in enumerate(result, 1):
        outcome = getattr(node, "outcome", 0.0)
        approach = getattr(node, "approach", "?")
        provenance = getattr(node, "provenance", {})
        source = provenance.get("source", "unknown") if isinstance(provenance, dict) else "unknown"
        print(f"  {i}. [{outcome:.2f}] {approach}")
        print(f"     source: {source}")
        print()


def _cmd_status():
    """Show current TELOS pipeline status."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    checkpoint_dir = "/tmp/telos_checkpoints"
    latest_cp = None
    if os.path.isdir(checkpoint_dir):
        checkpoints = sorted(
            [f for f in os.listdir(checkpoint_dir) if f.startswith("checkpoint_")],
            reverse=True,
        )
        if checkpoints:
            latest_cp = checkpoints[0]
            cp_path = os.path.join(checkpoint_dir, latest_cp)
            try:
                with open(cp_path) as f:
                    cp_data = json.load(f)
            except Exception:
                cp_data = None
    else:
        cp_data = None

    print("\n🔍 TELOS Status\n")

    if latest_cp:
        print(f"  Latest checkpoint: {latest_cp}")
        if cp_data:
            print(f"  Cycle:            {cp_data.get('cycle', '?')}")
            mission = cp_data.get("mission_policy", {}).get("current", {})
            print(f"  Risk tolerance:   {mission.get('risk_tolerance', '?'):.2f}")
            print(f"  Explore budget:   {mission.get('exploration_budget', '?'):.2f}")
            mood = "?"
            ss_path = cp_data.get("system_self_path")
            if ss_path and os.path.isfile(ss_path):
                try:
                    with open(ss_path) as f:
                        ss = json.load(f)
                    mood = ss.get("state", {}).get("mood", "?")
                except Exception:
                    pass
            print(f"  Mood:             {mood}")
    else:
        print("  No checkpoints found.")

    print(f"  Python:           {sys.version}")
    try:
        from telos.core.genesis import ANCHOR
        print(f"  Genesis:          {ANCHOR.public_name} "
              f"(creator: {ANCHOR.creator})")
    except Exception:
        pass
    print()


def _build_gridworld_pipeline(checkpoint_dir="/tmp/telos_cli"):
    """Build a real GridWorld pipeline with the canonical streams + validators.

    Mirrors the pipeline construction used by telos_task.py and the perf
    profiler so `telos run` executes a genuine governed cycle (no stubs).

    Args:
        checkpoint_dir: directory for the pipeline's persisted state.

    Returns:
        A configured TelosV14Pipeline ready for execute().
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
        RealityValidator, ConstraintValidator, MemoryAdvisor,
        MissionDriftDetector, EvidenceProvenanceValidator, CalibrationValidator,
    )
    from telos.core.ledger.skill_library import SkillLibrary
    from telos.core.simulation import CounterfactualEngine

    os.makedirs(checkpoint_dir, exist_ok=True)
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=10, horizon=5,
        mission_name=MISSION_NAME, mission_description=MISSION_DESCRIPTION,
        checkpoint_path=checkpoint_dir,
        knowledge_path=os.path.join(checkpoint_dir, "kg.json"),
        ledger_path=os.path.join(checkpoint_dir, "ledger.json"),
        identity_path=os.path.join(checkpoint_dir, "identity.json"),
        pattern_path=os.path.join(checkpoint_dir, "patterns.json"),
        memory_path=os.path.join(checkpoint_dir, "memory.json"),
        # Governed tool channel (operator-authorised, default OFF):
        # TELOS_TOOL_WORKSPACE names the only tree the channel may
        # touch; unset => no executor, no real command can run.
        tool_workspace=os.environ.get("TELOS_TOOL_WORKSPACE") or None,
        operator_tool_permission=bool(os.environ.get("TELOS_TOOL_WORKSPACE")),
        deterministic_seed=42,  # reproducible one-shot runs
        verified_learning=True,
        learning_curriculum=True,
    ))
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)
    for stream in (
        ReflexStream(skill_lib), PerceptionStream(skill_lib),
        MemoryStream(skill_lib), PlanningStream(skill_lib, sim_engine=sim_engine),
        InquiryStream(skill_lib),
        TheoryStream(skill_lib,
                     theory_builder=getattr(pipeline, "_theory_builder", None),
                     curriculum=getattr(pipeline, "curriculum", None)),
    ):
        pipeline.register_stream(stream)
    for validator in (
        RealityValidator(), ConstraintValidator(), MemoryAdvisor(skill_lib),
        MissionDriftDetector(drift_threshold=5.0), EvidenceProvenanceValidator(),
        CalibrationValidator(pipeline.calibration_tracker),
    ):
        pipeline.register_validator(validator)
    return pipeline


def _cmd_run(args):
    """Execute a single pipeline cycle.

        Args:
            args: the args argument for this call.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    import numpy as np

    state = np.array(args.state, dtype=float)
    n_cycles = max(1, int(getattr(args, "cycles", 1) or 1))
    print(f"\n⚡ TELOS Run — state: {state.tolist()} ({n_cycles} cycle(s))\n")
    pipeline = _build_gridworld_pipeline()
    result = None
    for i in range(n_cycles):
        result = pipeline.execute(state, user_name="cli")
        act = getattr(pipeline, "_last_trace", None)
        selected = getattr(act, "selected_action", None) if act else None
        if selected is not None:
            try:
                nxt = pipeline.config.simulator.transition(state, selected)
                if 0.0 <= float(nxt[0]) <= 4.0 and 0.0 <= float(nxt[1]) <= 4.0:
                    state = nxt
            except Exception:
                pass
    print(f"   DI: {result.decision_integrity:.3f}")
    print(f"   MD: {result.mission_drift:.3f}")
    print(f"   Blocked: {result.council_blocked or result.firewall_blocked}")
    mem = pipeline.memory_report()
    if mem:
        print(f"   Memory: {mem.get('memory_consumed', 0)} recalled, "
              f"{mem.get('inserted', 0)} stored ({mem.get('total', 0)} live)")
    try:
        pipeline.shutdown()
    except Exception:
        pass
    print()


if __name__ == "__main__":
    main()
