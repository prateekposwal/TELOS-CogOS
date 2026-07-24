"""Tests for TELOS Perception Layer (PerceptionQuality, ResolutionGate, ProxyStream)."""
import numpy as np
import pytest

from telos.core.perception.quality import PerceptionQuality, QualityReport
from telos.core.perception.gate import ResolutionGate, GateVerdict
from telos.core.perception.proxy import ProxyStream
from telos.core.perception.explainer import PerceptionExplainer
from telos.core.perception.capabilities import CapabilityRegistry, DetectionCapability
from telos.core.ledger.skill_library import SkillLibrary
from telos.world.world import World


class TestPerceptionQuality:

    def test_low_res_small_target_recommends_proxy(self):
        q = PerceptionQuality()
        report = q.assess(360, 640, 6)
        assert report.quality_score < 0.35
        assert report.proxy_recommended is True
        assert "low resolution" in report.notes
        assert "target too small" in report.notes

    def test_high_res_large_target_passes(self):
        q = PerceptionQuality()
        report = q.assess(1920, 1080, 50)
        assert report.quality_score > 0.7
        assert report.proxy_recommended is False
        assert "adequate quality" in report.notes or report.notes == "adequate quality"

    def test_invalid_dimensions(self):
        q = PerceptionQuality()
        report = q.assess(0, 0, None)
        assert report.quality_score == 0.0
        assert report.proxy_recommended is True

    def test_aspect_penalty(self):
        q = PerceptionQuality()
        tall = q.assess(360, 640, 50)
        wide = q.assess(640, 360, 50)
        sq = q.assess(640, 640, 50)
        assert tall.quality_score < sq.quality_score
        assert wide.quality_score < sq.quality_score

    def test_report_to_dict(self):
        q = PerceptionQuality()
        report = q.assess(360, 640, 6)
        d = report.to_dict()
        assert "quality_score" in d
        assert "resolution" in d
        assert "proxy_recommended" in d


class TestResolutionGate:

    def test_low_quality_blocked(self):
        q = PerceptionQuality()
        g = ResolutionGate()
        report = q.assess(360, 640, 6)
        verdict = g.evaluate(report)
        assert verdict.passed is False
        assert verdict.proxy_activated is True

    def test_high_quality_passes(self):
        q = PerceptionQuality()
        g = ResolutionGate()
        report = q.assess(1920, 1080, 50)
        verdict = g.evaluate(report)
        assert verdict.passed is True
        assert verdict.proxy_activated is False

    def test_blocked_streams_listed(self):
        q = PerceptionQuality()
        g = ResolutionGate()
        report = q.assess(360, 640, 6)
        verdict = g.evaluate(report, target_streams=["field_tracker", "yolo"])
        assert len(verdict.blocked_streams) == 2
        assert "field_tracker" in verdict.blocked_streams


class TestProxyStream:

    @pytest.fixture
    def stream(self):
        return ProxyStream(SkillLibrary())

    def test_priority(self, stream):
        assert stream.priority == 0.6

    def test_idle_when_not_proxy_mode(self, stream):
        world = World(state=np.zeros(3), metadata={"proxy_mode": False})
        intent = stream.process(world)
        assert intent.intent_type == "proxy_idle"

    def test_returns_proxy_track_in_proxy_mode(self, stream):
        world = World(
            state=np.zeros(3),
            metadata={
                "proxy_mode": True,
                "frame_width": 360,
                "frame_height": 640,
            },
        )
        intent = stream.process(world)
        assert intent.intent_type == "proxy_track"
        assert intent.confidence > 0

    def test_estimated_position_in_motion_mode(self, stream):
        frame = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        world = World(
            state=np.zeros(3),
            metadata={
                "proxy_mode": True,
                "frame_width": 100,
                "frame_height": 100,
                "frame_data": frame,
            },
        )
        intent = stream.process(world)
        assert intent.intent_type == "proxy_track"
        params = intent.params
        assert params.get("method") == "motion_hotspot" or params.get("method") == "state_estimate"

    def test_knowledge_graph_integration(self):
        from telos.core.knowledge.graph import KnowledgeGraph
        from telos.core.perception.quality import PerceptionQuality
        from telos.core.perception.gate import ResolutionGate

        kg = KnowledgeGraph()
        q = PerceptionQuality()
        g = ResolutionGate()

        report = q.assess(360, 640, 6)
        kg.record("video", "direct_detection", 0.0,
                  failure_reason=f"quality={report.quality_score:.3f}",
                  params={"resolution": "360x640", "quality": report.quality_score})

        recommendations = kg.search("video", top_k=3, min_outcome=0.51)
        assert len(recommendations) == 0  # all failures, no successes

        kg.record("video", "proxy_track", 0.85,
                  tags=["proxy"], params={"frames": 506})
        recommendations = kg.search("video", top_k=3, min_outcome=0.51)
        assert len(recommendations) >= 1
        assert recommendations[0].approach == "proxy_track"


class TestPerceptionExplainer:

    def test_explain_high_quality(self):
        e = PerceptionExplainer()
        q = PerceptionQuality()
        g = ResolutionGate()
        report = q.assess(1920, 1080, 100)
        verdict = g.evaluate(report)
        explanation = e.explain(report, verdict)
        assert "summary" in explanation
        assert explanation["quality_score"] > 0.7
        assert explanation["proxy_mode"] is False
        assert len(explanation["details"]) > 0
        assert len(explanation["suggestions"]) > 0

    def test_explain_low_quality_with_proxy(self):
        e = PerceptionExplainer()
        q = PerceptionQuality()
        g = ResolutionGate()
        report = q.assess(360, 640, 6)
        verdict = g.evaluate(report)
        explanation = e.explain(report, verdict)
        assert "summary" in explanation
        assert explanation["quality_score"] < 0.35
        assert explanation["proxy_mode"] is True
        assert "Below threshold" in explanation["summary"]
        assert len(explanation["suggestions"]) >= 2

    def test_explain_missing_target(self):
        e = PerceptionExplainer()
        q = PerceptionQuality()
        g = ResolutionGate()
        report = q.assess(640, 480, None)
        verdict = g.evaluate(report)
        explanation = e.explain(report, verdict)
        assert "quality_score" in explanation
        assert explanation["proxy_mode"] is True

    def test_summarize(self):
        e = PerceptionExplainer()
        q = PerceptionQuality()
        report = q.assess(1920, 1080, 100)
        verdict = ResolutionGate().evaluate(report)
        summary = e.summarize(report, verdict)
        assert isinstance(summary, str)
        assert len(summary) > 10
        assert summary.endswith(".")


class TestCapabilityRegistry:

    def test_default_capabilities(self):
        r = CapabilityRegistry()
        stats = r.stats
        assert stats["total_capabilities"] >= 5
        assert "color_threshold" in stats["capabilities"]
        assert "yolo_sports_ball" in stats["capabilities"]

    def test_check_high_res(self):
        r = CapabilityRegistry()
        results = r.check(1920, 1080, 100)
        assert len(results) >= 5
        feasible = [res for res in results if res["feasible"]]
        assert len(feasible) > 0
        assert feasible[0]["match_score"] > 0.5

    def test_check_low_res(self):
        r = CapabilityRegistry()
        results = r.check(320, 240, 5)
        feasible = [res for res in results if res["feasible"]]
        # Some capabilities won't be feasible at very low res
        assert any(not res["feasible"] for res in results)

    def test_best_feasible(self):
        r = CapabilityRegistry()
        best = r.best(1920, 1080, 100)
        assert best is not None
        assert best["feasible"] is True
        assert best["match_score"] > 0.5

    def test_best_infeasible_returns_top(self):
        r = CapabilityRegistry()
        best = r.best(10, 10, 1)
        assert best is not None

    def test_register_new(self):
        r = CapabilityRegistry()
        initial = r.stats["total_capabilities"]
        r.register(DetectionCapability(name="test_cap", min_object_px=5,
                                        min_width=100, min_height=100,
                                        description="test"))
        assert r.stats["total_capabilities"] == initial + 1

    def test_suggest_improvements(self):
        r = CapabilityRegistry()
        suggestions = r.suggest_improvements(320, 240, 5)
        assert isinstance(suggestions, list)

    def test_match_score_range(self):
        r = CapabilityRegistry()
        results = r.check(640, 480, 20)
        for res in results:
            assert 0.0 <= res["match_score"] <= 1.0
