"""Contract tests for telos/core/attention/projection.py."""

import numpy as np
import pytest

from telos.core.attention.projection import (
    AttentionProjectionEngine, AttentionAllocation, TrajectoryProjection,
)


def test_allocation_normalizes_ratios():
    a = AttentionAllocation(threat_ratio=0.6, opportunity_ratio=0.3,
                            maintenance_ratio=0.3)
    assert a.threat_ratio == pytest.approx(0.5)
    assert a.opportunity_ratio == pytest.approx(0.25)
    assert a.maintenance_ratio == pytest.approx(0.25)


def test_allocation_domination_properties():
    threat = AttentionAllocation(threat_ratio=0.8, opportunity_ratio=0.1,
                                 maintenance_ratio=0.1)
    assert threat.is_threat_dominated
    assert not threat.is_opportunity_dominated
    opp = AttentionAllocation(threat_ratio=0.2, opportunity_ratio=0.9,
                              maintenance_ratio=0.2)
    assert opp.is_opportunity_dominated


def test_allocation_budget_views():
    a = AttentionAllocation(threat_ratio=0.5, opportunity_ratio=0.25,
                            maintenance_ratio=0.25, total_budget=100.0)
    assert a.threat_budget == pytest.approx(50.0)
    assert a.opportunity_budget == pytest.approx(25.0)
    assert a.maintenance_budget == pytest.approx(25.0)


def test_empty_engine_defaults():
    e = AttentionProjectionEngine(window_size=5)
    assert e.current_allocation is None
    assert e.mean_threat_ratio == 0.0
    assert e.identity_entropy == 10.0
    assert e.counterfactual_diversity == 0.0
    assert e.attention_momentum == 0.0
    assert e.entropy_collapse_rate == 0.0
    assert not e.is_attention_locked
    assert not e.is_identity_collapse


def test_record_allocation_updates_means():
    e = AttentionProjectionEngine(window_size=5)
    e.record_allocation(AttentionAllocation(threat_ratio=0.8,
                                            opportunity_ratio=0.1,
                                            maintenance_ratio=0.1))
    e.record_allocation(AttentionAllocation(threat_ratio=0.4,
                                            opportunity_ratio=0.4,
                                            maintenance_ratio=0.2))
    assert e.current_allocation.threat_ratio == pytest.approx(0.4)
    assert e.mean_threat_ratio == pytest.approx(0.6)
    assert e.mean_opportunity_ratio == pytest.approx(0.25)


def test_record_action_space_drives_entropy():
    e = AttentionProjectionEngine(window_size=5)
    for s in [8, 8, 8, 8]:
        e.record_action_space(s)
    assert e.identity_entropy == pytest.approx(8.0)


def test_record_counterfactual_variance_diversity():
    e = AttentionProjectionEngine(window_size=5)
    e.record_counterfactual_variance(0.1)
    e.record_counterfactual_variance(0.3)
    assert e.counterfactual_diversity == pytest.approx(0.2)


def test_record_trajectory_divergence():
    e = AttentionProjectionEngine(window_size=5)
    e.record_trajectory_divergence(np.array([0.0, 0.0]),
                                   np.array([3.0, 4.0]))
    assert e._trajectory_divergences == [5.0]


def test_attention_locked_when_rigid_high_threat():
    e = AttentionProjectionEngine(window_size=10)
    for t in [0.3, 0.95] * 5:
        e.record_allocation(AttentionAllocation(threat_ratio=t,
                                                opportunity_ratio=(1 - t) * 0.5,
                                                maintenance_ratio=(1 - t) * 0.5))
    assert e.attention_momentum > 0.85
    assert e.mean_threat_ratio > 0.6
    assert e.is_attention_locked


def test_identity_collapse_when_contracting():
    e = AttentionProjectionEngine(window_size=10)
    for s in [10, 8, 6, 4, 2, 1, 1, 1, 1, 1]:
        e.record_action_space(s)
    assert e.entropy_collapse_rate < -0.5
    assert e.identity_entropy < 10 * 0.4
    assert e.is_identity_collapse


def test_project_trajectory_returns_projection():
    e = AttentionProjectionEngine(window_size=5)
    e.record_action_space(8)
    proj = e.project_trajectory(np.array([1.0, 0.0]), horizon=2)
    assert isinstance(proj, TrajectoryProjection)
    assert proj.expected_divergence > 0.0
    assert proj.attention_momentum == 0.0
    assert proj.diversity_budget >= 0.0
    assert proj.projected_identity_entropy >= 1.0


def test_stats_keys():
    e = AttentionProjectionEngine(window_size=5)
    e.record_allocation(AttentionAllocation(threat_ratio=0.5,
                                            opportunity_ratio=0.25,
                                            maintenance_ratio=0.25))
    e.record_action_space(8)
    keys = set(e.stats.keys())
    assert {
        'identity_entropy', 'entropy_collapse_rate', 'counterfactual_diversity',
        'attention_momentum', 'mean_threat_ratio', 'mean_opportunity_ratio',
        'mean_maintenance_ratio', 'is_attention_locked', 'is_identity_collapse',
        'trajectory_divergences', 'allocation_count', 'default_action_space',
    } <= keys
    assert e.stats['allocation_count'] == 1
    assert e.stats['default_action_space'] == 10
