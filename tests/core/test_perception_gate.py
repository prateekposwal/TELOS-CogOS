"""Tests for ResolutionGate — governance-level block when input quality is
insufficient to detect the target."""

from telos.core.perception.gate import ResolutionGate, GateVerdict
from telos.core.perception.quality import QualityReport


def report(score, notes="note text"):
    return QualityReport(
        quality_score=score,
        resolution=(640, 480),
        target_size_px=20.0,
        notes=notes,
    )


class TestGateVerdict:
    def test_blocked_streams_defaults_to_empty(self):
        v = GateVerdict(passed=True, reason="ok")
        assert v.blocked_streams == []


class TestThreshold:
    def test_default_threshold(self):
        gate = ResolutionGate()
        assert gate.threshold == 0.35

    def test_setter_clamps_high(self):
        gate = ResolutionGate()
        gate.threshold = 5.0
        assert gate.threshold == 1.0

    def test_setter_clamps_low(self):
        gate = ResolutionGate()
        gate.threshold = -2.0
        assert gate.threshold == 0.0

    def test_custom_threshold(self):
        gate = ResolutionGate(threshold=0.5)
        assert gate.threshold == 0.5


class TestEvaluate:
    def test_passes_when_quality_at_or_above_threshold(self):
        gate = ResolutionGate(threshold=0.35)
        v = gate.evaluate(report(0.5))
        assert v.passed is True
        assert v.proxy_activated is False
        assert v.blocked_streams == []
        assert "≥" in v.reason

    def test_blocks_when_quality_below_threshold(self):
        gate = ResolutionGate(threshold=0.35)
        v = gate.evaluate(report(0.2))
        assert v.passed is False
        assert v.proxy_activated is True
        assert v.blocked_streams == []

    def test_blocked_streams_carried_through(self):
        gate = ResolutionGate()
        v = gate.evaluate(report(0.2), target_streams=["ball_detect", "referee"])
        assert v.blocked_streams == ["ball_detect", "referee"]

    def test_block_reason_embeds_report_notes(self):
        gate = ResolutionGate()
        v = gate.evaluate(report(0.1, notes="low resolution (160x120)"))
        assert "0.100" in v.reason
        assert "below threshold" in v.reason
        assert "low resolution (160x120)" in v.reason