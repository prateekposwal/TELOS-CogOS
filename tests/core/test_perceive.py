"""Contract tests for the Perceive phase — attention budget allocation and
phase execution. The phase splits attention across threat / opportunity /
maintenance and drives the perception pipeline. allocate_attention_budget is
a pure function of (uncertainty, safety, metrics)."""
import numpy as np
import pytest

from telos.core.phases.perceive import PerceivePhase, allocate_attention_budget


class TestAttentionBudget:
    """The threat/opportunity/maintenance split is zero-sum and bounded."""

    def test_ratios_sum_to_one(self):
        alloc = allocate_attention_budget(uncertainty=0.5, safety_score=0.5,
                                          domain_metrics={})
        total = (alloc.threat_ratio + alloc.opportunity_ratio
                 + alloc.maintenance_ratio)
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_high_uncertainty_is_threat_dominated(self):
        alloc = allocate_attention_budget(uncertainty=0.9, safety_score=0.1,
                                          domain_metrics={})
        assert alloc.threat_ratio > alloc.opportunity_ratio

    def test_high_safety_is_opportunity_dominated(self):
        alloc = allocate_attention_budget(uncertainty=0.1, safety_score=0.9,
                                          domain_metrics={})
        assert alloc.opportunity_ratio > alloc.threat_ratio

    def test_stream_breakdown_has_all_streams(self):
        alloc = allocate_attention_budget(uncertainty=0.5, safety_score=0.5,
                                          domain_metrics={})
        assert set(alloc.stream_breakdown) >= {"reflex", "perception", "memory",
                                               "planning"}
        for v in alloc.stream_breakdown.values():
            assert v >= 5.0  # every stream keeps a floor

    def test_total_budget_respected(self):
        alloc = allocate_attention_budget(uncertainty=0.5, safety_score=0.5,
                                          domain_metrics={}, total_budget=200.0)
        assert alloc.total_budget == 200.0


class TestPerceivePhase:
    """The phase object is registered by its canonical name."""

    def test_phase_name_is_canonical(self):
        assert PerceivePhase.name == "perceive"