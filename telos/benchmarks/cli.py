"""
Benchmark CLI — interactive benchmarking dashboard for TELOS.

Measures projections of hidden cognitive state X across 7 conserved processes:
  Perception, Learning, Identity, Knowledge, Resources, Projects, Social

Usage:
    python3 -m telos.benchmarks.cli          # Run on current pipeline
    python3 -m telos.benchmarks.cli --report  # Show latest report
    python3 -m telos.benchmarks.cli --save-baseline /tmp/baseline.json
    python3 -m telos.benchmarks.cli --compare /tmp/baseline.json
    python3 -m telos.benchmarks.cli --watch    # Live-watch (polls every 5s)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

# Ensure TELOS is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from telos.benchmarks.collector import BenchmarkCollector, BenchmarkReport, Trend


def header(text: str) -> None:
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def show_report(report: BenchmarkReport, verbose: bool = False) -> None:
    """Print a formatted benchmark report to stdout.
        Args:
            verbose: the verbose argument for this call.
    """
    header(f"TELOS Benchmark Report — {report.session_id}")
    print(f"  Cycles: {report.cycle_count}")
    print(f"  Duration: {report.total_duration_seconds:.1f}s")
    print(f"  System Score: {report.current_system_score:.4f} ({report.system_score_trend})")
    print(f"  Mission Score: {report.current_mission_score:.4f}")
    print()

    # Trends
    print("  ┌─ Metric Trends (projections of X(t)) ───────────────┐")
    for name, trend in sorted(report.trends.items()):
        arrows = {"rising": "↑", "stable": "→", "declining": "↓", "insufficient_data": "?"}
        arrow = arrows.get(trend, "?")
        print(f"  │ {name:30s} {arrow} {trend:18s} │")
    print("  └──────────────────────────────────────────────────────┘")
    print()

    # Epoch summaries
    for label, summary in report.epochs.items():
        agg = summary.aggregate()
        if not agg:
            continue
        print(f"  ┌─ Epoch: {label} ({summary.n_cycles} cycles) ─────────────────┐")

        # Perception
        p = agg["perception"]
        print(f"  │ Perception:  EstErr={p['avg_estimation_error']:.3f}  "
              f"Forecast={p['avg_forecast_accuracy']:.3f}  "
              f"Score={p['avg_score']:.3f}  │")

        # Learning
        l = agg["learning"]
        print(f"  │ Learning:    Cur={l['avg_curiosity']:.3f}  "
              f"Learn={l['avg_learning_rate']:.4f}  "
              f"Yield={l['latest_yield_validated']}v  "
              f"Score={l['avg_score']:.3f}  │")

        # Identity
        i = agg["identity"]
        print(f"  │ Identity:    Ent={i['avg_entropy']:.3f}  "
              f"Coh={i['avg_coherence']:.3f}  "
              f"Prop={i['avg_mission_alignment']:.3f}  "
              f"Score={i['avg_score']:.3f}  │")

        # Knowledge
        k = agg["knowledge"]
        print(f"  │ Knowledge:   Div={k['avg_representation_diversity']:.3f}  "
              f"Bridge={k['avg_bridge_potential']:.3f}  "
              f"Theory={k['latest_theory_nodes']}  "
              f"Score={k['avg_score']:.3f}  │")

        # Resources
        r = agg["resources"]
        print(f"  │ Resources:   CPU={r['avg_compute_util']:.1%}  "
              f"CROI={r['avg_croi']:.3f}  "
              f"Score={r['avg_score']:.3f}  │")

        # Projects
        pj = agg["projects"]
        print(f"  │ Projects:    Compl={pj['avg_completion_rate']:.1%}  "
              f"Align={pj['avg_mission_alignment']:.3f}  "
              f"Score={pj['avg_score']:.3f}  │")

        # Social
        s = agg["social"]
        print(f"  │ Social:      Niches={s['latest_niches']}  "
              f"Bridge={s['latest_bridges']}  "
              f"Collab={s['avg_collaboration']:.3f}  "
              f"Score={s['avg_score']:.3f}  │")

        # Hierarchy
        ss = agg["system_score"]
        ms = agg["mission_score"]
        print(f"  │ ── Hierarchy ─────────────────────────────────────── │")
        print(f"  │ System:  {ss['avg']:.3f} ({ss['trend']})  |  "
              f"Mission:  {ms['avg']:.3f} ({ms['trend']})  │")
        print("  └──────────────────────────────────────────────────────────┘")
        print()

    # Baseline comparison
    if report.baseline:
        print(f"  ┌─ Baseline: {report.baseline.baseline_label} ──────────────────────┐")
        for metric, delta in sorted(report.baseline.deltas.items()):
            emoji = "🟢" if delta > 0 else "🔴" if delta < 0 else "⚪"
            print(f"  │ {metric:30s} {emoji} {delta:+.4f} {'✓' if metric in report.baseline.improvements else '⚠'} │")
        print("  └──────────────────────────────────────────────────────────┘")
        print()
        if report.baseline.improvements:
            print(f"  ✅ Improvements ({len(report.baseline.improvements)}):")
            for m in report.baseline.improvements:
                print(f"     - {m}")
        if report.baseline.regressions:
            print(f"  ⚠️  Regressions ({len(report.baseline.regressions)}):")
            for m in report.baseline.regressions:
                print(f"     - {m}")

    if verbose:
        print()
        print(report.to_markdown())


def main():
    parser = argparse.ArgumentParser(
        description="TELOS Benchmark CLI — measure system performance across 7 cognitive processes"
    )
    parser.add_argument("--report", action="store_true",
                        help="Show latest benchmark report")
    parser.add_argument("--save-baseline", type=str, metavar="PATH",
                        help="Save current state as baseline")
    parser.add_argument("--compare", type=str, metavar="PATH",
                        help="Compare against a saved baseline")
    parser.add_argument("--watch", action="store_true",
                        help="Live-watch: poll every 5s and print summary")
    parser.add_argument("--markdown", action="store_true",
                        help="Output full markdown report")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON")
    parser.add_argument("--data-dir", type=str, default="telos/benchmarks/data",
                        help="Benchmark data directory")
    parser.add_argument("--load", type=str, metavar="PATH",
                        help="Load saved snapshot data")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed information")

    args = parser.parse_args()

    collector = BenchmarkCollector(output_dir=args.data_dir)

    # Load prior data if requested
    if args.load:
        loaded = collector.load_snapshot_data(args.load)
        print(f"Loaded {loaded} snapshots from {args.load}")

    # Try to collect from a running pipeline if snapshots are empty
    if not collector._snapshots and not args.load:
        try:
            from telos.core.runtime import TelosV14Pipeline
            pipeline = getattr(sys.modules.get('__main__'), '_pipeline', None)
            if pipeline is None:
                for name, obj in sys.modules.items():
                    if hasattr(obj, '_pipeline'):
                        pipeline = obj._pipeline
                        break
            if pipeline is not None and hasattr(pipeline, '_last_trace'):
                trace = pipeline._last_trace
                ctx = getattr(pipeline, '_last_ctx', None)
                if trace is not None:
                    collector.collect(pipeline, trace, ctx)
                    print(f"Collected from running pipeline: cycle {trace.cycle_id}")
        except Exception as e:
            if args.verbose:
                print(f"(No running pipeline found: {e})")

    # Generate report
    baseline_path = args.save_baseline or args.compare
    report = collector.get_report(baseline_path=args.compare)

    # Output
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    elif args.markdown:
        print(report.to_markdown())
    else:
        show_report(report, verbose=args.verbose)

    # Save baseline if requested
    if args.save_baseline:
        collector.save_baseline(args.save_baseline)
        print(f"\n✅ Baseline saved to {args.save_baseline}")

    # Watch mode
    if args.watch:
        print(f"\n📡 Live-watch mode (Ctrl+C to stop)...")
        try:
            while True:
                time.sleep(5)
                report = collector.get_report(baseline_path=args.compare)
                os.system('clear')
                show_report(report)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
