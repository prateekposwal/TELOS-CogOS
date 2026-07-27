"""Tests for BenchmarkCollector — redesigned with 7 conserved cognitive processes."""

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
    compute_subsystem_scores,
    compute_system_score,
    compute_mission_score,
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


class TestHierarchicalScores:

    def test_subsystem_scores_in_range(self):
        """All 7 subsystem scores should be in [0, 1]."""
        snap = BenchmarkSnapshot(
            cycle=0, timestamp=100.0,
            state_estimation_error=0.1, surprise_rate=0.05,
            unknown_unknown_discovery_rate=0.1, forecast_accuracy=0.9,
            counterfactual_accuracy=0.8,
            curiosity_level=0.5, learning_rate=0.2, compression_rate=0.5,
            boredom_count=0, exploration_ratio=0.5,
            knowledge_yield_observations=10, knowledge_yield_theories=5,
            knowledge_yield_predictions=20, knowledge_yield_validated=8,
            knowledge_yield_principles=3,
            identity_entropy=0.1, identity_continuity=0.9,
            relational_coherence=0.8,
            mission_alignment=0.8, project_alignment=0.7, decision_alignment=0.9,
            representation_age_mean=50.0, representation_diversity=0.6,
            retirement_rate=0.02, bridge_density=0.3, reuse_rate=0.7,
            compression_achieved=0.5,
            epistemic_ideas=5, epistemic_top_capital=0.8,
            theory_nodes=10, theory_roots=2, bridge_potential_avg=0.6,
            compute_utilization=0.5, memory_utilization=0.4,
            bandwidth_utilization=0.3, storage_utilization=0.2, croi=1.5,
            active_projects=3, total_projects=5,
            completed_projects=2, abandoned_projects=0,
            strategic_alignment_mission_projects=0.8,
            strategic_alignment_project_tasks=0.7,
            strategic_alignment_task_actions=0.6,
            mission_alignment_overall=0.75,
            niche_count=8, exhausted_niches=1, bridge_count=4,
            social_relations=12, collaboration_efficiency=0.7,
        )
        subscores = compute_subsystem_scores(snap)
        for name, score in subscores.items():
            assert 0.0 <= score <= 1.0, f"{name} score {score} out of [0,1]"

    def test_system_score_from_subscores(self):
        """System score aggregates subsystem scores."""
        subscores = {
            "perception": 0.8, "learning": 0.7, "identity": 0.9,
            "knowledge": 0.75, "resources": 0.6, "projects": 0.65,
            "social": 0.7,
        }
        ss = compute_system_score(subscores)
        assert 0.0 <= ss <= 1.0
        # Weighted average should be between min and max
        assert min(subscores.values()) <= ss <= max(subscores.values())

    def test_mission_score_default(self):
        """Default mission score equals system score."""
        subscores = {"perception": 0.8, "learning": 0.7, "identity": 0.9,
                     "knowledge": 0.75, "resources": 0.6, "projects": 0.65,
                     "social": 0.7}
        ss = compute_system_score(subscores)
        ms = compute_mission_score(ss, subscores, None)
        assert ms == ss

    def test_mission_score_contextualized(self):
        """Mission score re-weights subsystems."""
        subscores = {"perception": 0.95, "learning": 0.3, "identity": 0.9,
                     "knowledge": 0.9, "resources": 0.9, "projects": 0.9,
                     "social": 0.9}
        ss = compute_system_score(subscores)
        # If mission strongly prioritizes learning (which is low), mission score
        # should be lower than system score
        ctx = {"learning": 1.0}
        ms = compute_mission_score(ss, subscores, ctx)
        # Mission context should pull the score toward learning (0.3)
        assert ms < ss

    def test_health_score_backward_compat(self):
        """compute_health_score returns system_score."""
        snap = BenchmarkSnapshot(
            cycle=0, timestamp=100.0,
            state_estimation_error=0.1, surprise_rate=0.05,
            unknown_unknown_discovery_rate=0.1, forecast_accuracy=0.9,
            counterfactual_accuracy=0.8,
            curiosity_level=0.5, learning_rate=0.2, compression_rate=0.5,
            boredom_count=0, exploration_ratio=0.5,
            knowledge_yield_observations=10, knowledge_yield_theories=5,
            knowledge_yield_predictions=20, knowledge_yield_validated=8,
            knowledge_yield_principles=3,
            identity_entropy=0.1, identity_continuity=0.9,
            relational_coherence=0.8,
            mission_alignment=0.8, project_alignment=0.7, decision_alignment=0.9,
            representation_age_mean=50.0, representation_diversity=0.6,
            retirement_rate=0.02, bridge_density=0.3, reuse_rate=0.7,
            compression_achieved=0.5,
            epistemic_ideas=5, epistemic_top_capital=0.8,
            theory_nodes=10, theory_roots=2, bridge_potential_avg=0.6,
            compute_utilization=0.5, memory_utilization=0.4,
            bandwidth_utilization=0.3, storage_utilization=0.2, croi=1.5,
            active_projects=3, total_projects=5,
            completed_projects=2, abandoned_projects=0,
            strategic_alignment_mission_projects=0.8,
            strategic_alignment_project_tasks=0.7,
            strategic_alignment_task_actions=0.6,
            mission_alignment_overall=0.75,
            niche_count=8, exhausted_niches=1, bridge_count=4,
            social_relations=12, collaboration_efficiency=0.7,
        )
        # Compute the scores first
        subscores = compute_subsystem_scores(snap)
        snap.perception_score = subscores["perception"]
        snap.learning_score = subscores["learning"]
        snap.identity_score = subscores["identity"]
        snap.knowledge_score = subscores["knowledge"]
        snap.resource_score = subscores["resources"]
        snap.project_score = subscores["projects"]
        snap.social_score = subscores["social"]
        snap.system_score = compute_system_score(subscores)
        snap.mission_score = compute_mission_score(snap.system_score, subscores, None)
        # Backward compat
        hs = compute_health_score(snap)
        assert hs == snap.system_score

    def test_perfect_snapshot_high_scores(self):
        """A nearly-perfect snapshot should have high subsystem scores."""
        snap = BenchmarkSnapshot(
            cycle=0, timestamp=100.0,
            state_estimation_error=0.01, surprise_rate=0.01,
            unknown_unknown_discovery_rate=0.3, forecast_accuracy=0.98,
            counterfactual_accuracy=0.95,
            curiosity_level=0.9, learning_rate=0.4, compression_rate=0.8,
            boredom_count=0, exploration_ratio=0.6,
            knowledge_yield_observations=100, knowledge_yield_theories=30,
            knowledge_yield_predictions=200, knowledge_yield_validated=80,
            knowledge_yield_principles=20,
            identity_entropy=0.02, identity_continuity=0.98,
            relational_coherence=0.95,
            mission_alignment=0.95, project_alignment=0.9, decision_alignment=0.95,
            representation_age_mean=200.0, representation_diversity=0.9,
            retirement_rate=0.005, bridge_density=0.8, reuse_rate=0.9,
            compression_achieved=0.8,
            epistemic_ideas=20, epistemic_top_capital=0.95,
            theory_nodes=30, theory_roots=5, bridge_potential_avg=0.9,
            compute_utilization=0.5, memory_utilization=0.5,
            bandwidth_utilization=0.5, storage_utilization=0.5, croi=5.0,
            active_projects=5, total_projects=5,
            completed_projects=3, abandoned_projects=0,
            strategic_alignment_mission_projects=0.95,
            strategic_alignment_project_tasks=0.9,
            strategic_alignment_task_actions=0.85,
            mission_alignment_overall=0.9,
            niche_count=15, exhausted_niches=0, bridge_count=8,
            social_relations=25, collaboration_efficiency=0.9,
        )
        subscores = compute_subsystem_scores(snap)
        # All subsystem scores should be well above random for a near-perfect snapshot
        for name, score in subscores.items():
            assert score >= 0.55, f"{name} score {score} too low for perfect snapshot"
        ss = compute_system_score(subscores)
        assert ss >= 0.65, f"System score {ss} too low"

    def test_poor_snapshot_low_scores(self):
        """A very poor snapshot should have low subsystem scores."""
        snap = BenchmarkSnapshot(
            cycle=0, timestamp=100.0,
            state_estimation_error=2.0, surprise_rate=0.8,
            unknown_unknown_discovery_rate=0.0, forecast_accuracy=0.1,
            counterfactual_accuracy=0.1,
            curiosity_level=0.0, learning_rate=0.0, compression_rate=0.0,
            boredom_count=10, exploration_ratio=0.0,
            knowledge_yield_observations=0, knowledge_yield_theories=0,
            knowledge_yield_predictions=0, knowledge_yield_validated=0,
            knowledge_yield_principles=0,
            identity_entropy=0.9, identity_continuity=0.05,
            relational_coherence=0.1,
            mission_alignment=0.1, project_alignment=0.1, decision_alignment=0.1,
            representation_age_mean=0.0, representation_diversity=0.0,
            retirement_rate=0.9, bridge_density=0.0, reuse_rate=0.0,
            compression_achieved=0.0,
            epistemic_ideas=0, epistemic_top_capital=0.0,
            theory_nodes=1, theory_roots=1, bridge_potential_avg=0.0,
            compute_utilization=1.0, memory_utilization=1.0,
            bandwidth_utilization=1.0, storage_utilization=1.0, croi=0.0,
            active_projects=0, total_projects=5,
            completed_projects=0, abandoned_projects=5,
            strategic_alignment_mission_projects=0.1,
            strategic_alignment_project_tasks=0.1,
            strategic_alignment_task_actions=0.1,
            mission_alignment_overall=0.1,
            niche_count=1, exhausted_niches=1, bridge_count=0,
            social_relations=0, collaboration_efficiency=0.0,
        )
        subscores = compute_subsystem_scores(snap)
        ss = compute_system_score(subscores)
        assert ss <= 0.4, f"System score {ss} too high for poor snapshot"

    def test_all_scores_bounded(self):
        """All composite scores must be in [0, 1]."""
        snap = BenchmarkSnapshot(
            cycle=0, timestamp=100.0,
            state_estimation_error=0.5, surprise_rate=0.2,
            unknown_unknown_discovery_rate=0.1, forecast_accuracy=0.6,
            counterfactual_accuracy=0.5,
            curiosity_level=0.4, learning_rate=0.1, compression_rate=0.3,
            boredom_count=2, exploration_ratio=0.3,
            knowledge_yield_observations=5, knowledge_yield_theories=2,
            knowledge_yield_predictions=10, knowledge_yield_validated=3,
            knowledge_yield_principles=1,
            identity_entropy=0.3, identity_continuity=0.7,
            relational_coherence=0.7,
            mission_alignment=0.6, project_alignment=0.5, decision_alignment=0.7,
            representation_age_mean=30.0, representation_diversity=0.4,
            retirement_rate=0.05, bridge_density=0.2, reuse_rate=0.5,
            compression_achieved=0.3,
            epistemic_ideas=3, epistemic_top_capital=0.5,
            theory_nodes=5, theory_roots=2, bridge_potential_avg=0.4,
            compute_utilization=0.4, memory_utilization=0.3,
            bandwidth_utilization=0.2, storage_utilization=0.2, croi=0.5,
            active_projects=2, total_projects=3,
            completed_projects=1, abandoned_projects=0,
            strategic_alignment_mission_projects=0.7,
            strategic_alignment_project_tasks=0.6,
            strategic_alignment_task_actions=0.5,
            mission_alignment_overall=0.6,
            niche_count=5, exhausted_niches=1, bridge_count=2,
            social_relations=5, collaboration_efficiency=0.5,
        )
        subscores = compute_subsystem_scores(snap)
        for name, score in subscores.items():
            assert 0.0 <= score <= 1.0, f"{name} score {score} out of [0,1]"
        ss = compute_system_score(subscores)
        assert 0.0 <= ss <= 1.0
        ms = compute_mission_score(ss, subscores, None)
        assert 0.0 <= ms <= 1.0


class TestBenchmarkCollector:

    def test_collect_one_cycle(self, pipeline):
        """Collector auto-collects via pipeline_finalize hook."""
        collector = BenchmarkCollector()
        pipeline._benchmark_collector = collector

        state = np.array([0.5, -0.3])
        result = pipeline.execute(state)

        assert collector.cycle_count >= 1
        latest = collector.latest_snapshot()
        assert latest is not None
        assert 0.0 <= latest.system_score <= 1.0
        assert 0.0 <= latest.mission_score <= 1.0

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
        assert "System Score" in report.trends
        assert report.current_system_score > 0.0

    def test_save_and_load_snapshots(self, pipeline, tmp_path):
        """Snapshots can be persisted and reloaded."""
        collector = BenchmarkCollector(output_dir=str(tmp_path))
        pipeline._benchmark_collector = collector

        state = np.array([0.5, -0.3])
        pipeline.execute(state)

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

        for i in range(3):
            state = np.array([float(i), 0.0])
            pipeline.execute(state)

        assert collector.cycle_count >= 3
        cycles = [s.cycle for s in collector._snapshots]
        assert cycles == sorted(cycles), f"Snapshots not in order: {cycles}"

    def test_new_categories_present(self, pipeline):
        """Verify all 7 new categories are present in snapshot."""
        collector = BenchmarkCollector()
        pipeline._benchmark_collector = collector

        state = np.array([0.5, -0.3])
        pipeline.execute(state)

        snap = collector.latest_snapshot()
        assert snap is not None

        # Perception
        assert hasattr(snap, 'forecast_accuracy')
        assert hasattr(snap, 'counterfactual_accuracy')
        assert hasattr(snap, 'unknown_unknown_discovery_rate')

        # Learning - knowledge yield pipeline
        assert hasattr(snap, 'knowledge_yield_observations')
        assert hasattr(snap, 'knowledge_yield_principles')

        # Identity - propagation
        assert hasattr(snap, 'mission_alignment')
        assert hasattr(snap, 'project_alignment')
        assert hasattr(snap, 'decision_alignment')

        # Knowledge - representation ecology
        assert hasattr(snap, 'representation_diversity')
        assert hasattr(snap, 'retirement_rate')
        assert hasattr(snap, 'bridge_density')
        assert hasattr(snap, 'bridge_potential_avg')

        # Knowledge - epistemic capital (renamed)
        assert hasattr(snap, 'epistemic_ideas')
        assert hasattr(snap, 'epistemic_top_capital')

        # Resources - CROI
        assert hasattr(snap, 'croi')

        # Projects - strategic alignment hierarchy
        assert hasattr(snap, 'strategic_alignment_mission_projects')
        assert hasattr(snap, 'strategic_alignment_task_actions')

        # Social
        assert hasattr(snap, 'collaboration_efficiency')

        # 4-level hierarchy
        assert hasattr(snap, 'perception_score')
        assert hasattr(snap, 'learning_score')
        assert hasattr(snap, 'identity_score')
        assert hasattr(snap, 'knowledge_score')
        assert hasattr(snap, 'resource_score')
        assert hasattr(snap, 'project_score')
        assert hasattr(snap, 'social_score')
        assert hasattr(snap, 'system_score')
        assert hasattr(snap, 'mission_score')

    def test_to_dict_structure(self, pipeline):
        """Snapshot.to_dict() has the new nested structure."""
        collector = BenchmarkCollector()
        pipeline._benchmark_collector = collector

        state = np.array([0.5, -0.3])
        pipeline.execute(state)

        snap = collector.latest_snapshot()
        d = snap.to_dict()

        # Top-level categories
        assert "perception" in d
        assert "learning" in d
        assert "identity" in d
        assert "knowledge" in d
        assert "resources" in d
        assert "projects" in d
        assert "social" in d
        assert "hierarchy" in d

        # Nested sub-categories
        assert "knowledge_yield" in d["learning"]
        assert "propagation" in d["identity"]
        assert "representation_ecology" in d["knowledge"]
        assert "epistemic_capital" in d["knowledge"]
        assert "strategic_alignment" in d["projects"]

        # Hierarchy
        assert "subsystem_scores" in d["hierarchy"]
        assert "system_score" in d["hierarchy"]
        assert "mission_score" in d["hierarchy"]
