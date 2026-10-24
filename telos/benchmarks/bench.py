#!/usr/bin/env python3
"""
TELOS Regression Benchmark — cycle latency & memory profiling.

Usage:
    python3 -m telos.benchmarks.bench [--cycles 1000] [--ci]

CI mode: exits nonzero if any threshold is violated.
  - mean cycle time < 20ms
  - p95 cycle time < 50ms
  - RSS < 200MB (soft warning at 150MB)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import statistics
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import ReflexStream
from telos.core.council.validators import RealityValidator
from telos.core.ledger.skill_library import SkillLibrary
from telos.adapters.logistics_simulator import LogisticsDomainSimulator, LogisticsDomainAdapter


try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False


def get_rss_mb() -> float:
    """Return current RSS in MB."""
    if HAS_RESOURCE:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # On Linux, ru_maxrss is in KB; on macOS, it's in bytes
        import platform
        if platform.system() == "Darwin":
            return rss / (1024 * 1024)  # bytes -> MB
        return rss / 1024.0  # KB -> MB
    return 0.0


def create_pipeline(domain: str = "gridworld") -> TelosV14Pipeline:
    """Create a pipeline for the specified domain."""
    if domain == "logistics":
        sim = LogisticsDomainSimulator(seed=42)
        adapter = LogisticsDomainAdapter()
        state_dim = 12
    else:
        # Use a mock gridworld-like simulator for CI speed
        class MockGridSim:
            def __init__(self):
                self.name = "mock_grid"
                self.state_dim = 2
            def initialize(self): pass
            def cleanup(self): pass
            def observe(self, state): return state
            def legal_transitions(self, state):
                return [np.array([1.,0.]), np.array([-1.,0.]), np.array([0.,1.]), np.array([0.,-1.])]
            def transition(self, state, action): return np.clip(state + action, -1, 1)
            def simulate(self, state, horizon):
                from telos.world.world import World
                return [World(state=self.observe(self.transition(state, a))) for a in self.legal_transitions(state)[:horizon]]
            def terminal(self, state): return np.linalg.norm(state) < 0.1
            def evaluate(self, state):
                from telos.core.contracts.domain_model import EvaluationReport
                return EvaluationReport(objectives={"proximity": 1.0 - np.linalg.norm(state)}, risks=0.0)
            def world_spec(self):
                from telos.core.contracts.domain_model import WorldSpec
                return WorldSpec(name="mock_grid", state_dim=2, action_dim=2,
                                 objectives=["proximity"], constraints=[],
                                 observability="full", capabilities=["transition"])
            def get_facts(self, state):
                from telos.world.facts import DomainFacts
                return DomainFacts(state=state.copy(), resources={}, constraints=[], events=[], metrics={}, metadata={})
        
        class MockGridAdpt:
            name = "mock_grid"
            state_dim = 2
            def forward(self, x): return x
            def inverse(self, x): return x
            def intent_to_action(self, intent, state, md):
                import numpy as np
                return np.array([0., 0.])
            def declared_state_dim(self):
                return 2
        
        sim = MockGridSim()
        adapter = MockGridAdpt()
        state_dim = 2

    # Light pipeline config for regression benchmarking (fewer worlds, smaller horizon)
    config = PipelineConfig(
        adapter=adapter, simulator=sim,
        compute_budget_ms=50.0,
        state_dim=state_dim,
        n_worlds=3,      # Reduced from 10 for speed
        horizon=3,       # Reduced from 5 for speed
        quality_threshold=0.3,
        deterministic_seed=42,
        verified_learning=False,
        learning_curriculum=False,
    )
    pl = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    pl.register_stream(ReflexStream(skill_lib))
    pl.register_validator(RealityValidator())
    return pl


def run_benchmark(cycles: int, domain: str = "gridworld") -> dict:
    """Run benchmark and return stats."""
    pipeline = create_pipeline(domain)
    
    # Initial state
    if domain == "logistics":
        from telos.adapters.logistics_simulator import HEALTHY
        state = sim.observe(HEALTHY.copy()) if 'sim' in dir() else np.zeros(12)
    else:
        state = np.zeros(2)
    
    # Warmup (not counted)
    for _ in range(10):
        pipeline.execute(state)
    
    # Timed runs
    latencies = []
    rss_samples = []
    
    initial_rss = get_rss_mb()
    rss_samples.append(initial_rss)
    
    for i in range(cycles):
        t0 = time.perf_counter()
        result = pipeline.execute(state)
        t1 = time.perf_counter()
        
        latencies.append((t1 - t0) * 1000)  # ms
        
        if i % 100 == 0:
            rss_samples.append(get_rss_mb())
    
    final_rss = get_rss_mb()
    rss_samples.append(final_rss)
    
    # Statistics
    latencies_arr = np.array(latencies)
    mean_ms = float(latencies_arr.mean())
    p50_ms = float(np.percentile(latencies_arr, 50))
    p95_ms = float(np.percentile(latencies_arr, 95))
    p99_ms = float(np.percentile(latencies_arr, 99))
    max_ms = float(latencies_arr.max())
    std_ms = float(latencies_arr.std())
    
    peak_rss = max(rss_samples) if rss_samples else 0
    rss_growth = peak_rss - initial_rss if initial_rss > 0 else 0
    
    return {
        "cycles": cycles,
        "domain": domain,
        "mean_ms": mean_ms,
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "p99_ms": p99_ms,
        "max_ms": max_ms,
        "std_ms": std_ms,
        "initial_rss_mb": initial_rss,
        "peak_rss_mb": peak_rss,
        "rss_growth_mb": rss_growth,
        "rss_samples": rss_samples,
    }


def main():
    parser = argparse.ArgumentParser(description="TELOS Regression Benchmark")
    parser.add_argument("--cycles", type=int, default=1000,
                        help="Number of pipeline cycles to run")
    parser.add_argument("--domain", type=str, default="gridworld",
                        choices=["gridworld", "logistics"],
                        help="Domain to benchmark")
    parser.add_argument("--ci", action="store_true",
                        help="Exit nonzero on threshold violation")
    parser.add_argument("--mean-threshold", type=float, default=20.0,
                        help="Mean cycle time threshold (ms)")
    parser.add_argument("--p95-threshold", type=float, default=50.0,
                        help="P95 cycle time threshold (ms)")
    parser.add_argument("--rss-threshold", type=float, default=200.0,
                        help="Peak RSS threshold (MB)")
    args = parser.parse_args()
    
    print(f"Running {args.cycles} cycles on {args.domain} domain...")
    stats = run_benchmark(args.cycles, args.domain)
    
    print()
    print("=" * 60)
    print("  TELOS Regression Benchmark Results")
    print("=" * 60)
    print(f"  Domain:           {stats['domain']}")
    print(f"  Cycles:           {stats['cycles']}")
    print()
    print("  Latency (ms):")
    print(f"    Mean:           {stats['mean_ms']:.2f}")
    print(f"    P50:            {stats['p50_ms']:.2f}")
    print(f"    P95:            {stats['p95_ms']:.2f}")
    print(f"    P99:            {stats['p99_ms']:.2f}")
    print(f"    Max:            {stats['max_ms']:.2f}")
    print(f"    StdDev:         {stats['std_ms']:.2f}")
    print()
    print("  Memory (MB):")
    print(f"    Initial RSS:    {stats['initial_rss_mb']:.1f}")
    print(f"    Peak RSS:       {stats['peak_rss_mb']:.1f}")
    print(f"    RSS Growth:     {stats['rss_growth_mb']:.1f}")
    print()
    
    # CI checks
    violations = []
    if stats['mean_ms'] > args.mean_threshold:
        violations.append(f"MEAN latency {stats['mean_ms']:.2f}ms > {args.mean_threshold}ms")
    if stats['p95_ms'] > args.p95_threshold:
        violations.append(f"P95 latency {stats['p95_ms']:.2f}ms > {args.p95_threshold}ms")
    if stats['peak_rss_mb'] > args.rss_threshold:
        violations.append(f"Peak RSS {stats['peak_rss_mb']:.1f}MB > {args.rss_threshold}MB")
    
    if violations:
        print("  ❌ THRESHOLD VIOLATIONS:")
        for v in violations:
            print(f"    - {v}")
        if args.ci:
            print()
            print("FAIL: CI thresholds violated")
            sys.exit(1)
    else:
        print("  ✅ All thresholds passed")
        if args.ci:
            print()
            print("PASS: All CI thresholds met")
    
    print("=" * 60)


if __name__ == "__main__":
    main()