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
        from telos import GENESIS
        print(f"  Genesis:          {GENESIS}")
    except ImportError:
        pass
    print()


def _cmd_run(args):
    """Execute a single pipeline cycle.
        Args:
            args: the args argument for this call.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    import numpy as np
    from telos.telos_task import run_pipeline

    state = np.array(args.state)
    print(f"\n⚡ TELOS Run — state: {state.tolist()}\n")
    result = run_pipeline(state)
    print(f"   DI: {result.decision_integrity:.3f}")
    print(f"   MD: {result.mission_drift:.3f}")
    print(f"   Blocked: {result.council_blocked or result.firewall_blocked}")
    print()


if __name__ == "__main__":
    main()
