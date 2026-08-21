"""Contract tests for telos.core.perception.explainer.PerceptionExplainer.

Covers the explain()/summarize() contract that translates a QualityReport
+ GateVerdict into human-readable explanations and actionable suggestions.
"""
import pytest

from telos.core.perception.explainer import PerceptionExplainer
from telos.core.perception.quality import QualityReport, PerceptionQuality
from telos.core.perception.gate import GateVerdict


def _report(**kw):
    defaults = dict(
        quality_score=0.4, resolution=(1280, 720), target_size_px=None,
        notes="adequate quality", proxy_recommended=False, params={},
    )
    defaults.update(kw)
    return QualityReport(**defaults)


def test_explain_basic_summary_and_details():
    explainer = PerceptionExplainer()
    report = _report(resolution=(1280, 720), quality_score=0.4)
    verdict = GateVerdict(passed=True, reason="ok")
    result = explainer.explain(report, verdict)
    assert "summary" in result and result["summary"].endswith(".")
    assert "Input is HD (1280x720)" in result["summary"]
    assert "Quality score: 40%" in result["summary"]
    details_axes = {d["aspect"] for d in result["details"]}
    assert "resolution" in details_axes
    assert result["proxy_mode"] is False
    assert result["quality_score"] == pytest.approx(0.4)
    assert isinstance(result["suggestions"], list)


def test_explain_proxy_blocked_path():
    explainer = PerceptionExplainer()
    report = _report(resolution=(640, 480), quality_score=0.2)
    verdict = GateVerdict(passed=False, reason="blocked", proxy_activated=True)
    result = explainer.explain(report, verdict)
    assert "blocked direct detection, using proxy mode" in result["summary"]
    assert result["proxy_mode"] is True
    gate_detail = next(d for d in result["details"] if d["aspect"] == "gate")
    assert gate_detail["proxy_mode"] is True


def test_explain_target_below_minimum():
    explainer = PerceptionExplainer()
    report = _report(resolution=(1280, 720), target_size_px=8.0, quality_score=0.2)
    verdict = GateVerdict(passed=False, reason="low", proxy_activated=True)
    result = explainer.explain(report, verdict)
    # target 8px < MIN_PX 15 -> gap reported
    assert "Target is 8px" in result["summary"]
    assert "needs >= 15px" in result["summary"]
    td = next(d for d in result["details"] if d["aspect"] == "target_size")
    assert td["minimum"] == "15px"
    assert td["gap"] == pytest.approx(7.0)


def test_explain_target_adequate_no_gap_detail():
    explainer = PerceptionExplainer()
    report = _report(resolution=(1280, 720), target_size_px=40.0, quality_score=0.8)
    verdict = GateVerdict(passed=True, reason="ok")
    result = explainer.explain(report, verdict)
    assert "Target is 40px (adequate)" in result["summary"]
    assert all(d["aspect"] != "target_size" for d in result["details"])


def test_suggest_higher_resolution_for_low_pixel_count():
    explainer = PerceptionExplainer()
    report = _report(resolution=(640, 480), quality_score=0.2)
    suggestions = explainer._suggest(report)
    actions = {s["action"] for s in suggestions}
    assert "higher_resolution" in actions
    sr = next(s for s in suggestions if s["action"] == "higher_resolution")
    assert sr["impact"] == "high"


def test_suggest_closer_camera_when_target_too_small():
    explainer = PerceptionExplainer()
    report = _report(resolution=(1920, 1080), target_size_px=8.0, quality_score=0.2)
    suggestions = explainer._suggest(report)
    actions = {s["action"] for s in suggestions}
    assert "closer_camera" in actions


def test_suggest_proxy_mode_always_present():
    explainer = PerceptionExplainer()
    report = _report(resolution=(1920, 1080), quality_score=0.9)
    suggestions = explainer._suggest(report)
    actions = {s["action"] for s in suggestions}
    assert "proxy_mode" in actions


def test_suggest_super_resolution_for_narrow_width():
    explainer = PerceptionExplainer()
    report = _report(resolution=(320, 240), quality_score=0.1)
    suggestions = explainer._suggest(report)
    actions = {s["action"] for s in suggestions}
    assert "super_resolution" in actions
    sr = next(s for s in suggestions if s["action"] == "super_resolution")
    assert sr["impact"] == "low"


def test_suggest_high_resolution_omits_upscale():
    explainer = PerceptionExplainer()
    report = _report(resolution=(1920, 1080), quality_score=0.9)
    suggestions = explainer._suggest(report)
    actions = {s["action"] for s in suggestions}
    assert "super_resolution" not in actions
    assert "higher_resolution" not in actions


def test_summarize_returns_summary_string():
    explainer = PerceptionExplainer()
    report = _report(resolution=(1280, 720), quality_score=0.4)
    verdict = GateVerdict(passed=True, reason="ok")
    assert explainer.summarize(report, verdict) == explainer.explain(report, verdict)["summary"]


@pytest.mark.parametrize("w,h,label", [
    (1920, 1080, "Full HD"),
    (1280, 720, "HD"),
    (854, 480, "SD (480p)"),
    (640, 360, "low (360p)"),
    (320, 240, "very low"),
])
def test_resolution_name(w, h, label):
    assert PerceptionExplainer._resolution_name(w, h) == label


def test_min_px_matches_perception_quality():
    assert PerceptionExplainer.MIN_PX == PerceptionQuality.MIN_PX_FOR_DETECTION == 15.0


def test_explain_includes_resolution_scores_from_params():
    explainer = PerceptionExplainer()
    report = _report(
        resolution=(1280, 720), quality_score=0.4,
        params={"resolution_score": 0.8, "size_score": 0.5},
    )
    verdict = GateVerdict(passed=True, reason="ok")
    result = explainer.explain(report, verdict)
    axes = {d["aspect"] for d in result["details"]}
    assert "resolution_score" in axes
    assert "size_score" in axes
