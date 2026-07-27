"""
Benchmark CLI — interactive benchmarking dashboard for TELOS.

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
    """Print a formatted benchmark report to stdout."""
    header(f"TELOS Benchmark Report — {report.session_id}")
    print(f"  Cycles: {report.cycle_count}")
    print(f"  Duration: {report.total_duration_seconds:.1f}s")
    print(f"  Health Score: {report.current_health_score:.4f} ({report.health_score_trend})")
    print()
    
    # Trends
    print("  ┌─ Metric Trends ─────────────────────────────┐")
    for name, trend in sorted(report.trends.items()):
        arrows = {"rising": "↑", "stable": "→", "declining": "↓", "insufficient_data": "?"}
        arrow = arrows.get(trend, "?")
        print(f"  │ {name:30s} {arrow} {trend:18s} │")
    print("  └──────────────────────────────────────────────┘")
    print()

    # Epoch summaries
    for label, summary in report.epochs.items():
        agg = summary.aggregate()
        if not agg:
            continue
        print(f"  ┌─ Epoch: {label} ({summary.n_cycles} cycles) ─────────────────┐")
        
        ph = agg["pipeline_health"]
        print(f"  │ Pipeline:    DI={ph['avg_di']:.3f}  MD={ph['avg_md']:.3f}  "
              f"Block={ph['block_rate']:.1%}  Axiom={ph['axiom_compliance_rate']:.1%} │")
        
        cp = agg["cognitive_performance"]
        print(f"  │ Cognitive:   Cur={cp['avg_curiosity']:.3f}  "
              f"Learn={cp['avg_learning_rate']:.4f}  "
              f"Compress={cp['avg_compression']:.3f}  │")
        
        ih = agg["identity_health"]
        print(f"  │ Identity:    Entropy={ih['avg_entropy']:.3f}  "
              f"Coherence={ih['avg_relational_coherence']:.3f}  │")
        
        eh = agg["ecosystem_health"]
        print(f"  │ Ecosystem:   Niches={eh['latest_niches']}  "
              f"Exhaust={eh['avg_exhaustion_rate']:.1%}  "
              f"Bridges={eh['latest_bridges']}  │")
        
        re_agg = agg["resource_efficiency"]
        print(f"  │ Resources:   CPU={re_agg['avg_compute_util']:.1%}  "
              f"Mem={re_agg['avg_memory_util']:.1%}  │")
        
        rp = agg["research_productivity"]
        print(f"  │ Research:    Disc={rp['avg_discovery_rate']:.3f}  "
              f"Debt={rp['latest_debt']:.3f}  "
              f"Ideas={rp['latest_ideas']}  │")
        
        sc = agg["strategic_coherence"]
        print(f"  │ Strategy:    Compl={sc['avg_completion_rate']:.1%}  "
              f"Coher={sc['avg_strategic_coherence']:.3f}  │")
        
        hs = agg["health_score"]
        print(f"  │ Health:      Avg={hs['avg']:.3f}  "
              f"Min={hs['min']:.3f}  Max={hs['max']:.3f}  "
              f"Trend={hs['trend']}  │")
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
        description="TELOS Benchmark CLI — measure system performance"
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
        # Attempt to wire into running pipeline
        try:
            from telos.core.runtime import TelosV14Pipeline
            # Look for a global pipeline instance
            pipeline = getattr(sys.modules.get('__main__'), '_pipeline', None)
            if pipeline is None:
                # Try to find one via introspection
                for name, obj in sys.modules.items():
                    if hasattr(obj, '_pipeline'):
                        pipeline = obj._pipeline
                        break
            if pipeline is not None and hasattr(pipeline, '_last_trace'):
                # Do a one-shot collection
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
