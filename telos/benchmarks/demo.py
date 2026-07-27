"""
TELOS Benchmark Demo — run a full benchmark suite on the pipeline.

Usage:
    python3 -m telos.benchmarks.demo [--cycles 10] [--save /tmp/benchmark.json]

Demonstrates:
  1. Wiring BenchmarkCollector into the pipeline
  2. Running N pipeline cycles with automatic collection
  3. Generating a structured BenchmarkReport
  4. Rendering as markdown
  5. Saving snapshots and baselines

Benchmark framework measures 7 conserved cognitive processes:
  Perception, Learning, Identity, Knowledge, Resources, Projects, Social
With 4-level hierarchical aggregation: Metrics → Subsystem → System → Mission
"""

from __future__ import annotations

import argparse
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from telos.benchmarks.collector import BenchmarkCollector
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import ReflexStream
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary


def create_minimal_pipeline() -> TelosV14Pipeline:
    """Create a minimal but functional TELOS pipeline."""
    from tests.core.conftest import MockSimulator

    sim = MockSimulator()
    sim.initialize()
    config = PipelineConfig(
        simulator=sim,
        compute_budget_ms=200.0,
        state_dim=2,
        n_worlds=5,
        horizon=3,
        quality_threshold=0.3,
    )
    pl = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    pl.register_stream(ReflexStream(skill_lib))
    pl.register_validator(RealityValidator())
    pl.register_validator(ConstraintValidator())
    pl.register_validator(MissionDriftDetector(drift_threshold=10.0))
    return pl


def main():
    parser = argparse.ArgumentParser(description="TELOS Benchmark Demo")
    parser.add_argument("--cycles", type=int, default=20,
                        help="Number of pipeline cycles to run")
    parser.add_argument("--save", type=str, default="/tmp/telos_benchmark.json",
                        help="Save snapshots to path")
    parser.add_argument("--save-baseline", type=str,
                        default="/tmp/telos_baseline.json",
                        help="Save baseline to path")
    parser.add_argument("--markdown", action="store_true",
                        help="Output full markdown report")
    args = parser.parse_args()

    print("=" * 60)
    print("  TELOS Benchmark Demo — 7 Conserved Cognitive Processes")
    print("=" * 60)
    print()

    # 1. Create pipeline
    print("1. Creating pipeline...")
    pipeline = create_minimal_pipeline()

    # 2. Wire collector
    print("2. Wiring BenchmarkCollector...")
    collector = BenchmarkCollector(output_dir="/tmp/telos_benchmark_data")
    pipeline._benchmark_collector = collector

    # 3. Run cycles
    print(f"3. Running {args.cycles} pipeline cycles...")
    start = time.time()
    for i in range(args.cycles):
        state = np.array([
            np.sin(i * 0.5) * 0.5,
            np.cos(i * 0.3) * 0.5,
        ])
        result = pipeline.execute(state)
        if result.council_blocked:
            print(f"   Cycle {i}: ⛔ BLOCKED (DI={result.decision_integrity:.3f}, "
                  f"MD={result.mission_drift:.3f})")
        else:
            if i < 3 or i >= args.cycles - 2:
                print(f"   Cycle {i}: ✅ OK (DI={result.decision_integrity:.3f}, "
                      f"MD={result.mission_drift:.3f})")
    elapsed = time.time() - start
    print(f"   Completed {args.cycles} cycles in {elapsed:.2f}s "
          f"({elapsed/max(args.cycles,1)*1000:.1f}ms/cycle)")
    print()

    # 4. Generate report
    print("4. Generating benchmark report...")
    report = collector.get_report()
    print(f"   System Score: {report.current_system_score:.4f} ({report.system_score_trend})")
    print(f"   Mission Score: {report.current_mission_score:.4f}")
    print(f"   Cycles: {report.cycle_count}")
    print()

    # 5. Trend summary
    print("5. Metric Trends:")
    print(f"   {'Metric':30s} {'Trend':15s}")
    print(f"   {'-'*30} {'-'*15}")
    for name, trend in sorted(report.trends.items()):
        arrow = {"rising": "↑", "stable": "→",
                 "declining": "↓", "insufficient_data": "?"}.get(trend, "?")
        print(f"   {name:30s} {arrow} {trend:15s}")
    print()

    # 6. Epoch summary (all cycles)
    if "all" in report.epochs:
        agg = report.epochs["all"].aggregate()
        if agg:
            print("6. Aggregate (all cycles) — Hidden Cognitive State Projections:")
            # Perception
            p = agg["perception"]
            print(f"   Perception:  EstErr={p['avg_estimation_error']:.3f}  "
                  f"Forecast={p['avg_forecast_accuracy']:.3f}  "
                  f"Counterfact={p['avg_counterfactual_accuracy']:.3f}  "
                  f"Score={p['avg_score']:.3f}")
            # Learning
            l = agg["learning"]
            print(f"   Learning:    Cur={l['avg_curiosity']:.3f}  "
                  f"Learn={l['avg_learning_rate']:.4f}  "
                  f"Compress={l['avg_compression']:.3f}  "
                  f"Score={l['avg_score']:.3f}")
            # Identity
            i = agg["identity"]
            print(f"   Identity:    Entropy={i['avg_entropy']:.3f}  "
                  f"Coherence={i['avg_coherence']:.3f}  "
                  f"MissionAlign={i['avg_mission_alignment']:.3f}  "
                  f"Score={i['avg_score']:.3f}")
            # Knowledge
            k = agg["knowledge"]
            print(f"   Knowledge:   RepDiv={k['avg_representation_diversity']:.3f}  "
                  f"BridgePot={k['avg_bridge_potential']:.3f}  "
                  f"Theories={k['latest_theory_nodes']}  "
                  f"Score={k['avg_score']:.3f}")
            # Resources
            r = agg["resources"]
            print(f"   Resources:   CPU={r['avg_compute_util']:.1%}  "
                  f"CROI={r['avg_croi']:.3f}  "
                  f"Score={r['avg_score']:.3f}")
            # Projects
            pj = agg["projects"]
            print(f"   Projects:    Compl={pj['avg_completion_rate']:.1%}  "
                  f"MissionAlign={pj['avg_mission_alignment']:.3f}  "
                  f"Score={pj['avg_score']:.3f}")
            # Social
            s = agg["social"]
            print(f"   Social:      Niches={s['latest_niches']}  "
                  f"Bridges={s['latest_bridges']}  "
                  f"Collab={s['avg_collaboration']:.3f}  "
                  f"Score={s['avg_score']:.3f}")
            # Hierarchy
            ss = agg["system_score"]
            ms = agg["mission_score"]
            print(f"   ── Hierarchy ──")
            print(f"   System:   Avg={ss['avg']:.3f}  Trend={ss['trend']}")
            print(f"   Mission:  Avg={ms['avg']:.3f}  Trend={ms['trend']}")
    print()

    # 7. Save
    if args.save:
        path = collector.save_snapshot_data(args.save)
        print(f"7. Saved snapshots: {path}")

    if args.save_baseline:
        collector.save_baseline(args.save_baseline)
        print(f"   Saved baseline: {args.save_baseline}")

    # 8. Optional markdown
    if args.markdown:
        print("\n" + "=" * 60)
        print("  Full Markdown Report")
        print("=" * 60)
        print(report.to_markdown())

    print()
    print("Done. ✅")


if __name__ == "__main__":
    main()
