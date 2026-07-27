"""Tests for BenchmarkCollector — comprehensive system measurement."""

import os
import numpy as np
import pytest

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import ReflexStream
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.benchmarks.collector import (
    BenchmarkCollector,
    BenchmarkSnapshot,
    BenchmarkReport,
    compute_health_score,
    classify_trend,
    Trend,
)


@pytest.fixture
def pipeline():
    """Minimal pipeline for benchmark testing."""
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


def make_ctx(state, trace, cycle=0):
    """Build a minimal PipelineContext-like object."""
    ctx = type('Ctx', (), {})()
    ctx.cycle_count = cycle
    ctx.council_blocked = False
    ctx.firewall_blocked = False
    ctx.state = np.asarray(state) if not isinstance(state, np.ndarray) else state
    ctx.selected_intent = trace.selected_intent if trace else None
    ctx.stream_activations = trace.stream_activations if trace else []
    ctx.verdict = None
    ctx.phases_completed = 9
    ctx.phases_total = 9
    return ctx


class TestTrendClassification:
    
    def test_rising_trend(self):
        assert classify_trend([1, 2, 3, 4, 5], threshold=0.01) == Trend.RISING
    
    def test_declining_trend(self):
        assert classify_trend([5, 4, 3, 2, 1], threshold=0.01) == Trend.DECLINING
    
    def test_stable_trend(self):
        assert classify_trend([5, 5, 5, 5, 5], threshold=0.1) == Trend.STABLE
    
    def test_insufficient_data(self):
        assert classify_trend([], threshold=0.1) == Trend.INSUFFICIENT_DATA
        assert classify_trend([1], threshold=0.1) == Trend.INSUFFICIENT_DATA


class TestHealthScore:
    
    def test_perfect_health(self):
        snap = BenchmarkSnapshot(
            cycle=0, timestamp=100.0,
            decision_integrity=1.0, mission_drift=0.0,
            cycle_duration_ms=50.0, council_blocked=False,
            axiom_pass_rate=1.0, phases_completed=9, phases_total=9,
            curiosity_level=0.5, learning_rate=0.2,
            compression_rate=0.5, boredom_count=0, exploration_ratio=0.5,
            identity_entropy=0.0, relational_coherence=1.0, identity_continuity=1.0,
            niche_count=10, exhausted_niches=0, bridge_count=3, ecosystem_relations=5,
            compute_utilization=0.5, memory_utilization=0.5,
            bandwidth_utilization=0.5, storage_utilization=0.5,
            discovery_marginal_rate=0.5, research_debt=0.0,
            debt_entries_open=0, belief_capital_ideas=5,
            belief_top_capital=0.8, theory_nodes=10, theory_roots=2,
            active_projects=3, total_projects=3, terminated_projects=0,
            strategic_coherence=1.0, abandonment_rate=0.0,
        )
        score = compute_health_score(snap)
        assert 0.8 <= score <= 1.0, f"Expected high health score, got {score}"
    
    def test_poor_health(self):
        snap = BenchmarkSnapshot(
            cycle=0, timestamp=100.0,
            decision_integrity=0.1, mission_drift=8.0,
            cycle_duration_ms=500.0, council_blocked=True,
            axiom_pass_rate=0.2, phases_completed=2, phases_total=9,
            curiosity_level=0.0, learning_rate=0.0,
            compression_rate=0.0, boredom_count=10, exploration_ratio=0.0,
            identity_entropy=0.8, relational_coherence=0.1, identity_continuity=0.1,
            niche_count=1, exhausted_niches=1, bridge_count=0, ecosystem_relations=0,
            compute_utilization=1.0, memory_utilization=1.0,
            bandwidth_utilization=1.0, storage_utilization=1.0,
            discovery_marginal_rate=0.0, research_debt=8.0,
            debt_entries_open=5, belief_capital_ideas=0,
            belief_top_capital=0.0, theory_nodes=1, theory_roots=1,
            active_projects=0, total_projects=3, terminated_projects=3,
            strategic_coherence=0.1, abandonment_rate=1.0,
        )
        score = compute_health_score(snap)
        assert 0.0 <= score <= 0.3, f"Expected low health score, got {score}"
    
    def test_health_bounded(self):
        snap = BenchmarkSnapshot(
            cycle=0, timestamp=100.0,
            decision_integrity=0.7, mission_drift=0.5,
            cycle_duration_ms=50.0, council_blocked=False,
            axiom_pass_rate=0.9, phases_completed=9, phases_total=9,
            curiosity_level=0.4, learning_rate=0.1,
            compression_rate=0.3, boredom_count=2, exploration_ratio=0.3,
            identity_entropy=0.2, relational_coherence=0.8, identity_continuity=0.7,
            niche_count=5, exhausted_niches=1, bridge_count=2, ecosystem_relations=3,
            compute_utilization=0.4, memory_utilization=0.3,
            bandwidth_utilization=0.2, storage_utilization=0.2,
            discovery_marginal_rate=0.3, research_debt=1.0,
            debt_entries_open=2, belief_capital_ideas=3,
            belief_top_capital=0.5, theory_nodes=5, theory_roots=2,
            active_projects=2, total_projects=3, terminated_projects=0,
            strategic_coherence=0.7, abandonment_rate=0.0,
        )
        score = compute_health_score(snap)
        assert 0.0 <= score <= 1.0, f"Health score must be in [0,1], got {score}"


class TestBenchmarkCollector:
    
    def test_collect_one_cycle(self, pipeline):
        """Collector auto-collects via pipeline_finalize hook."""
        collector = BenchmarkCollector()
        pipeline._benchmark_collector = collector
        
        state = np.array([0.5, -0.3])
        result = pipeline.execute(state)
        
        # The hook in pipeline_finalize should have auto-collected
        assert collector.cycle_count >= 1
        latest = collector.latest_snapshot()
        assert latest is not None
        assert 0.0 <= latest.health_score <= 1.0
    
    def test_multiple_cycles(self, pipeline):
        """Collector accumulates data across pipeline cycles."""
        collector = BenchmarkCollector()
        pipeline._benchmark_collector = collector
        
        for i in range(5):
            state = np.array([float(i) * 0.1, float(i) * 0.2])
            pipeline.execute(state)
        
        assert collector.cycle_count >= 5
        report = collector.get_report()
        assert isinstance(report, BenchmarkReport)
        assert report.cycle_count >= 5
        assert report.session_id.startswith("session_")
        assert "all" in report.epochs
    
    def test_report_trends(self, pipeline):
        """Report computes trends correctly."""
        collector = BenchmarkCollector()
        pipeline._benchmark_collector = collector
        
        for i in range(5):
            state = np.array([0.5, -0.3])
            pipeline.execute(state)
        
        report = collector.get_report()
        assert report.trends is not None
        assert "DI" in report.trends or "Health Score" in report.trends
        assert report.current_health_score > 0.0
    
    def test_save_and_load_snapshots(self, pipeline, tmp_path):
        """Snapshots can be persisted and reloaded."""
        collector = BenchmarkCollector(output_dir=str(tmp_path))
        pipeline._benchmark_collector = collector
        
        state = np.array([0.5, -0.3])
        pipeline.execute(state)
        
        # There should be at least 1 snapshot from auto-collection
        assert collector.cycle_count >= 1
        
        path = str(tmp_path / "snapshots.json")
        saved = collector.save_snapshot_data(path)
        assert saved == path
        assert os.path.exists(path)
        
        # Load into fresh collector
        collector2 = BenchmarkCollector(output_dir=str(tmp_path))
        loaded = collector2.load_snapshot_data(path)
        assert loaded >= 1
    
    def test_baseline_comparison(self, pipeline, tmp_path):
        """Baseline save/load/compare works."""
        collector = BenchmarkCollector()
        pipeline._benchmark_collector = collector
        
        state = np.array([0.5, -0.3])
        pipeline.execute(state)
        
        baseline_path = str(tmp_path / "baseline.json")
        collector.save_baseline(baseline_path)
        assert os.path.exists(baseline_path)
        
        # Get report with baseline comparison
        report = collector.get_report(baseline_path=baseline_path)
        assert report.baseline is not None
    
    def test_pipeline_hook_integration(self, pipeline):
        """pipeline_finalize hook auto-collects on every pipeline.execute()."""
        collector = BenchmarkCollector()
        pipeline._benchmark_collector = collector
        
        # Run 3 cycles — the hook should collect each time
        for i in range(3):
            state = np.array([float(i), 0.0])
            pipeline.execute(state)
        
        # The collector should have picked up all 3
        assert collector.cycle_count >= 3, f"Expected >=3, got {collector.cycle_count}"
        
        # Check snapshots are in order
        cycles = [s.cycle for s in collector._snapshots]
        assert cycles == sorted(cycles), f"Snapshots not in order: {cycles}"
