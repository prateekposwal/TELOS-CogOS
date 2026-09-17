"""
TELOS Dev Agent — Autonomous codebase health monitor.

Scans a project, runs TELOS pipeline periodically, and surfaces suggestions
for improvements. Combines DevDomainAdapter + ProactiveScheduler + SuggestionChannel.

Usage:
    # Single scan of the current project
    PYTHONPATH=/path/to/telos python3 telos_dev_agent.py --scan

    # Watch mode (scan every 5 minutes)
    PYTHONPATH=/path/to/telos python3 telos_dev_agent.py --watch --project /path/to/project

    # One-shot scan with suggestions
    PYTHONPATH=/path/to/telos python3 telos_dev_agent.py --project /path/to/project
"""

import argparse
import logging
import sys
import os
import time

logging.basicConfig(level=logging.WARNING, format='%(levelname)s | %(message)s')

from telos.core.scheduler import ProactiveScheduler
from telos.core.suggestion_channel import SuggestionChannel


def scan_once(project_path: str, channel: SuggestionChannel):
    """Run a single scan of the project."""
    from telos.adapters.dev_domain_adapter import DevDomainSim

    print(f"\n🔍  Scanning {project_path}...")
    sim = DevDomainSim(project_path)
    state = sim.snapshot()

    if sim._last_snapshot:
        snap = sim._last_snapshot
        print(f"  📦 Dependencies: {snap.dep_count} ({snap.dep_outdated_count} outdated)")
        print(f"  🧪 Tests: {snap.test_count}")
        print(f"  📄 Files: {snap.file_count}")
        print(f"  ❌ TS errors: {snap.ts_error_count}")
        if snap.findings:
            channel.push_findings(snap.findings)

        # Deepen the scan: actually RUN the repo's discovered validation
        # commands (tests/typecheck/lint) and surface MEASURED results —
        # not just file counts. Bounded by TELOS_DEV_AGENT_TEST_TIMEOUT.
        from telos.adapters.dev_validation import discover_commands, validate_project
        commands = discover_commands(project_path)
        if commands:
            timeout = float(os.environ.get("TELOS_DEV_AGENT_TEST_TIMEOUT", "30"))
            try:
                ratio, _ts, _lint, runs, evidence = validate_project(
                    project_path, timeout=timeout)
                if ratio is not None:
                    channel.push("🧪", "Test pass ratio",
                                 f"{ratio:.2f} ({'measured' if evidence.is_measured else 'unvalidated'})",
                                 severity=2 if ratio < 1.0 else 1, domain="validation")
                for run in runs:
                    cls = getattr(run, "classification", None)
                    name = getattr(cls, "name", str(cls))
                    if name != "SUCCESS":
                        channel.push("⚠️", f"Command not clean: {run.name}",
                                     f"{name} (rc={run.returncode})",
                                     severity=2, domain="validation")
            except Exception as exc:  # advisory — never crash the scan
                channel.push("🧪", "Validation error", str(exc), severity=1,
                             domain="validation")

    return state


def run_pipeline(project_path: str, state, channel: SuggestionChannel):
    """Run TELOS pipeline on the scanned state."""
    from telos.core.runtime import PipelineConfig, TelosV14Pipeline
    from telos.core.streams.implementations import (
        ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
    )
    from telos.core.council.validators import (
        RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
    )
    from telos.core.ledger.skill_library import SkillLibrary
    from telos.core.simulation import CounterfactualEngine
    from telos.adapters.dev_domain_adapter import DevDomainSim, DevDomainAdpt

    sim = DevDomainSim(project_path)
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=DevDomainAdpt(), simulator=sim,
        compute_budget_ms=50.0, state_dim=11, n_worlds=5, horizon=3,
    ))
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)
    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=3.0))

    print("\n🧠  Running TELOS pipeline...")
    result = pipeline.execute(state, user_name="TELOS-DevAgent")
    trace = result.decision_trace

    if trace:
        intent = trace.selected_intent.intent_type if trace.selected_intent else "none"
        status = "APPROVED" if not (result.council_blocked or result.firewall_blocked) else "BLOCKED"
        print(f"\n  Intent:     {intent}")
        print(f"  Status:     {status}")
        print(f"  DI:         {trace.decision_integrity:.3f}")
        print(f"  MD:         {trace.mission_drift:.3f}")
        if result.council_blocked:
            print(f"  Blocked by: {trace.blocking_validator}")

    return pipeline, result


def main():
    parser = argparse.ArgumentParser(description="TELOS Dev Agent — Autonomous codebase health monitor")
    parser.add_argument('--project', '-p', default=os.getcwd(),
                        help='Path to the project to analyze')
    parser.add_argument('--watch', '-w', action='store_true',
                        help='Watch mode — scan periodically')
    parser.add_argument('--interval', '-i', type=int, default=5,
                        help='Scan interval in minutes (default: 5)')
    parser.add_argument('--scan', '-s', action='store_true',
                        help='Run a single scan and exit')

    args = parser.parse_args()
    project_path = os.path.abspath(args.project)

    if not os.path.exists(os.path.join(project_path, 'package.json')):
        print(f"⚠️  No package.json found at {project_path}")
        print(f"   TELOS works best on Node.js/TypeScript projects.")
        cont = input("   Continue anyway? (y/N): ")
        if cont.lower() != 'y':
            sys.exit(1)

    channel = SuggestionChannel()
    state = scan_once(project_path, channel)

    if args.scan:
        run_pipeline(project_path, state, channel)
        print("\n" + channel.display())
        return

    if args.watch:
        print(f"\n⏱️  Watch mode — scanning every {args.interval} minutes")
        print("   Press Ctrl+C to stop.\n")

        def on_findings(findings):
            channel.push_findings(findings)
            os.system('clear' if os.name == 'posix' else 'cls')
            print(f"⏱️  TELOS Dev Agent — {project_path}")
            print(f"   Last scan: {time.strftime('%H:%M:%S')}")
            print(f"   {len(findings)} findings\n")
            print(channel.display())
            print(channel.summary())

        scheduler = ProactiveScheduler(
            project_path=project_path,
            interval_minutes=args.interval,
            on_findings=on_findings,
        )
        scheduler.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            scheduler.stop()
        return

    # Default: one scan + pipeline + exit
    run_pipeline(project_path, state, channel)
    print("\n" + channel.display())

    # Summary
    pending = channel.get_pending()
    if pending:
        critical = sum(1 for s in pending if s.severity == 3)
        warnings = sum(1 for s in pending if s.severity == 2)
        print(f"\n📊  {len(pending)} suggestions ({critical} critical, {warnings} warnings)")
        print(f"   Run with --watch to monitor continuously.")
    else:
        print("\n✅  No issues found. Project looks healthy!")


if __name__ == "__main__":
    main()
