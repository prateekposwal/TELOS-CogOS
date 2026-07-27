"""
TELOS Benchmark Demo — run a full benchmark suite on the pipeline.

Usage:
    python3 -m telos.benchmarks.demo [--cycles 10] [--save /tmp/benchmark.json]
    
This demonstrates:
  1. Wiring BenchmarkCollector into the pipeline
  2. Running N pipeline cycles with automatic collection
  3. Generating a structured BenchmarkReport
  4. Rendering as markdown
  5. Saving snapshots and baselines
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
    print("  TELOS Benchmark Demo")
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
    print(f"   Health Score: {report.current_health_score:.4f} ({report.health_score_trend})")
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
            print("6. Aggregate (all cycles):")
            ph = agg["pipeline_health"]
            print(f"   Pipeline:   DI={ph['avg_di']:.3f}  MD={ph['avg_md']:.3f}  "
                  f"Block={ph['block_rate']:.1%}  Axiom={ph['axiom_compliance_rate']:.1%}")
            cp = agg["cognitive_performance"]
            print(f"   Cognitive:  Cur={cp['avg_curiosity']:.3f}  "
                  f"Learn={cp['avg_learning_rate']:.4f}  "
                  f"Compress={cp['avg_compression']:.3f}")
            ih = agg["identity_health"]
            print(f"   Identity:   Entropy={ih['avg_entropy']:.3f}  "
                  f"Coherence={ih['avg_relational_coherence']:.3f}")
            eh = agg["ecosystem_health"]
            print(f"   Ecosystem:  Niches={eh['latest_niches']}  "
                  f"Exhaust={eh['avg_exhaustion_rate']:.1%}")
            rp = agg["research_productivity"]
            print(f"   Research:   Disc={rp['avg_discovery_rate']:.3f}  "
                  f"Debt={rp['latest_debt']:.3f}")
            sc = agg["strategic_coherence"]
            print(f"   Strategy:   Compl={sc['avg_completion_rate']:.1%}  "
                  f"Coher={sc['avg_strategic_coherence']:.3f}")
            hs = agg["health_score"]
            print(f"   Health:     Avg={hs['avg']:.3f}  "
                  f"Trend={hs['trend']}")
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
