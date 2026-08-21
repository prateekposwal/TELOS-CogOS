"""Tests for CapabilityRegistry — known detection envelopes and matching."""

import pytest

from telos.core.perception.capabilities import (
    CapabilityRegistry,
    DetectionCapability,
)


class TestDetectionCapability:
    def test_tags_default_to_empty(self):
        c = DetectionCapability(
            name="x", min_object_px=1, min_width=10, min_height=10,
            description="d",
        )
        assert c.tags == []

    def test_can_detect_ok_when_above_minima(self):
        c = DetectionCapability(
            name="x", min_object_px=5, min_width=100, min_height=50,
            description="d",
        )
        ok, reason = c.can_detect(200, 100, 10)
        assert ok is True
        assert reason == "OK"

    def test_rejects_resolution_below_minimum(self):
        c = DetectionCapability(
            name="x", min_object_px=5, min_width=100, min_height=50,
            description="d",
        )
        ok, reason = c.can_detect(90, 40, 10)
        assert ok is False
        assert "below minimum" in reason

    def test_rejects_target_below_minimum_px(self):
        c = DetectionCapability(
            name="x", min_object_px=10, min_width=100, min_height=50,
            description="d",
        )
        ok, reason = c.can_detect(200, 100, 4)
        assert ok is False
        assert "below" in reason and "px" in reason

    def test_target_none_skips_px_check(self):
        c = DetectionCapability(
            name="x", min_object_px=10, min_width=100, min_height=50,
            description="d",
        )
        ok, _ = c.can_detect(200, 100, None)
        assert ok is True

    def test_match_score_bounded(self):
        c = DetectionCapability(
            name="x", min_object_px=10, min_width=100, min_height=50,
            description="d",
        )
        assert c.match_score(200, 100, 10) == 1.0
        assert 0.0 <= c.match_score(10, 10, 1) <= 1.0


class TestRegistry:
    def test_preloads_known_capabilities(self):
        reg = CapabilityRegistry()
        assert reg.stats["total_capabilities"] == 5
        assert "color_threshold" in reg.stats["capabilities"]

    def test_register_appends(self):
        reg = CapabilityRegistry()
        reg.register(DetectionCapability(
            name="radar", min_object_px=3, min_width=80, min_height=60,
            description="custom",
        ))
        assert reg.stats["total_capabilities"] == 6
        assert reg.stats["capabilities"][-1] == "radar"

    def test_check_returns_sorted_results(self):
        reg = CapabilityRegistry()
        results = reg.check(1280, 720, 30)
        assert len(results) == 5
        scores = [r["match_score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        row = results[0]
        assert set(row) == {"name", "description", "feasible",
                            "match_score", "reason", "tags"}

    def test_high_resolution_all_feasible(self):
        reg = CapabilityRegistry()
        results = reg.check(1280, 720, 30)
        assert all(r["feasible"] for r in results)

    def test_low_resolution_only_optical_flow_feasible(self):
        reg = CapabilityRegistry()
        results = reg.check(320, 240, 5)
        feasible = [r["name"] for r in results if r["feasible"]]
        assert feasible == ["optical_flow_proxy"]

    def test_best_returns_feasible_when_possible(self):
        reg = CapabilityRegistry()
        best = reg.best(320, 240, 5)
        assert best["name"] == "optical_flow_proxy"
        assert best["feasible"] is True

    def test_best_returns_top_infeasible_when_none_feasible(self):
        reg = CapabilityRegistry()
        best = reg.best(100, 100, 2)
        assert best is not None
        assert best["feasible"] is False

    def test_best_empty_registry_returns_none(self):
        reg = CapabilityRegistry()
        reg._capabilities = []
        assert reg.best(100, 100, 2) is None

    def test_suggest_improvements_for_low_resolution(self):
        reg = CapabilityRegistry()
        suggestions = reg.suggest_improvements(100, 100, 5)
        assert any("Increase resolution" in s for s in suggestions)
        assert any("Ball needs to be at least" in s for s in suggestions)

    def test_no_suggestions_when_feasible(self):
        reg = CapabilityRegistry()
        assert reg.suggest_improvements(1280, 720, 30) == []