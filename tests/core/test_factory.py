"""Contract tests for scale/factory — the canonical pipeline builder used by
the PipelineCoordinator and the ScaleVerifier (one deliberation law at any
granularity; Λ1.1 deliberate recursion)."""
from telos.core.scale.factory import build_standard_pipeline


def test_builds_pipeline_with_scale_scope():
    p = build_standard_pipeline("micro", budget_ms=12.0)
    assert p._scale_scope == "micro"
    assert p._scale_parent == "standard_factory"


def test_registers_default_streams():
    p = build_standard_pipeline("micro")
    names = sorted(s.__class__.__name__ for s in p.streams)
    assert "ReflexStream" in names
    assert "PlanningStream" in names


def test_stream_filter_only_registers_requested():
    p = build_standard_pipeline("micro", streams=["reflex"])
    assert all(s.__class__.__name__ == "ReflexStream" for s in p.streams)