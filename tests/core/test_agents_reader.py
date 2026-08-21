"""Honest contract tests for telos/core/session/agents_reader.py."""

import pytest

from telos.core.session import agents_reader
from telos.core.session.agents_reader import (
    SessionLearnings, read_latest_handoff, inject_into_context,
)

HANDOFF = """## Session Handoff — 2026-08-21 10:00:00

### Current State
- mood: deliberate
- shipped: something

### Decisions Made
- First decision
- Second decision

### Open Issues
- Open issue one

### Metrics
- DI: 0.950 | MD: 0.100 | Cycles: 12
"""


@pytest.fixture
def synthetic_agents(tmp_path, monkeypatch):
    p = tmp_path / "AGENTS.md"
    p.write_text(HANDOFF)
    monkeypatch.setattr(agents_reader, "AGENTS_PATH", str(p))
    return p


@pytest.fixture
def empty_agents(tmp_path, monkeypatch):
    p = tmp_path / "AGENTS.md"
    p.write_text("# No handoffs here\n")
    monkeypatch.setattr(agents_reader, "AGENTS_PATH", str(p))
    return p


def test_read_latest_handoff_parses_decisions(synthetic_agents):
    h = read_latest_handoff()
    assert h is not None
    assert h.learnings == ["First decision", "Second decision"]
    assert h.open_issues == ["Open issue one"]


def test_read_latest_handoff_parses_metrics(synthetic_agents):
    h = read_latest_handoff()
    assert h.metrics["di"] == 0.95
    assert h.metrics["md"] == 0.1
    assert h.metrics["cycles"] == 12.0


def test_read_latest_handoff_returns_none_when_only_one_block(empty_agents):
    assert read_latest_handoff() is None


def test_read_latest_handoff_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(agents_reader, "AGENTS_PATH",
                        str(tmp_path / "does_not_exist.md"))
    assert read_latest_handoff() is None


def test_read_latest_handoff_returns_none_when_no_learnings(tmp_path, monkeypatch):
    p = tmp_path / "AGENTS.md"
    p.write_text("## Session Handoff\n\n### Metrics\n- DI: 1.0\n")
    monkeypatch.setattr(agents_reader, "AGENTS_PATH", str(p))
    assert read_latest_handoff() is None


def test_session_learnings_is_a_dataclass():
    s = SessionLearnings(learnings=["x"], open_issues=[], metrics={})
    assert s.learnings == ["x"]
    assert s.open_issues == []
    assert s.metrics == {}


def test_inject_into_context_loads_learnings(synthetic_agents):
    class FakeContext:
        pass

    class FakePipeline:
        def __init__(self):
            self._context = FakeContext()

    pipe = FakePipeline()
    inject_into_context(pipe)
    assert pipe._context.previous_learnings == ["First decision", "Second decision"]
    assert pipe._context.previous_open_issues == ["Open issue one"]
    assert pipe._context.previous_metrics["di"] == 0.95


def test_inject_into_context_handles_missing_context(synthetic_agents):
    pipe = type("P", (), {"_context": None})()
    # Should not raise
    inject_into_context(pipe)


def test_inject_into_context_noop_when_no_handoff(empty_agents):
    class FakeContext:
        pass

    pipe = type("P", (), {"_context": FakeContext()})()
    inject_into_context(pipe)
    assert not hasattr(pipe._context, "previous_learnings")
