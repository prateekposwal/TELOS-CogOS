"""
Tests for AgentsWriter — Auto-AGENTS.md session handoff generator.

Tests:
    1. AgentsWriter can be instantiated
    2. generate_markdown produces valid markdown with all sections
    3. detect_context_pressure returns a value in [0.0, 1.0]
    4. write_summary creates/updates the target file
    5. Empty SessionSummary produces valid fallback markdown
    6. Context pressure scales correctly with inputs
"""

import os
import tempfile
from typing import Dict, Optional

from telos.core.session.agents_writer import AgentsWriter, SessionSummary, write_handoff, build_handoff


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_minimal_pipeline(
    di: float = 0.95,
    md: float = 0.02,
    cycle_count: int = 10,
    budget_consumed: float = 50.0,
    budget_total: float = 100.0,
    checkpoint_path: Optional[str] = None,
) -> object:
    """Minimal mock pipeline for testing."""

    class MockBudgetManager:
        consumed_ms = budget_consumed
        total_budget_ms = budget_total

    class MockTrace:
        decision_integrity = di
        mission_drift = md

    class MockTelemetry:
        def get_stats(self):
            return {"total_cycles": cycle_count}

    class MockFailures:
        def __len__(self): return 0
        def __iter__(self): return iter([])

    class MockInfraManager:
        failures = MockFailures()

    class MockSkillLib:
        _skills = []

    pipeline = type('MockPipeline', (), {
        'budget_manager': MockBudgetManager(),
        '_telemetry': MockTelemetry(),
        '_infra_manager': MockInfraManager(),
        '_experience_manager': type('EM', (), {'skill_library': MockSkillLib()}),
        '_checkpointer': type('MC', (), {'latest_path': checkpoint_path})(),
    })()
    return pipeline


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestAgentsWriterInstantiation:

    def test_can_be_instantiated(self):
        """AgentsWriter can be constructed with a file path."""
        writer = AgentsWriter("/tmp/test_agents.md")
        assert writer is not None
        assert writer.agents_path == "/tmp/test_agents.md"


class TestGenerateMarkdown:

    def test_produces_all_sections(self):
        """generate_markdown includes every required heading."""
        writer = AgentsWriter()
        summary = SessionSummary(
            current_state=["Working on navigation", "User preference: dark mode"],
            decisions_made=["Implement A* pathfinding", "Skip obstacle at (2,2)"],
            open_issues=["Obstacle (3,1) needs bypass", "Test coverage for edge case"],
            metrics={
                "di": 0.92, "md": 0.03, "cycle_count": 42,
                "token_budget_pct": 63.0, "checkpoint_ref": "/tmp/chk_0042.json",
            },
            checkpoint_ref="/tmp/chk_0042.json",
            timestamp="2026-07-21 12:00:00",
        )
        md = writer.generate_markdown(summary)

        assert "## Session Handoff — 2026-07-21 12:00:00" in md
        assert "### Current State" in md
        assert "### Decisions Made" in md
        assert "### Open Issues" in md
        assert "### Metrics" in md
        assert "### Checkpoint" in md

    def test_content_appears_in_markdown(self):
        """generate_markdown includes the actual data passed in."""
        writer = AgentsWriter()
        summary = SessionSummary(
            current_state=["Working on: testing"],
            decisions_made=["Test decision Alpha"],
            open_issues=["Fix flaky test"],
            metrics={
                "di": 0.88, "md": 0.07, "cycle_count": 15,
                "token_budget_pct": 45.0, "checkpoint_ref": "/tmp/cp.json",
            },
            checkpoint_ref="/tmp/cp.json",
            timestamp="2026-07-21 13:00:00",
        )
        md = writer.generate_markdown(summary)

        assert "Working on: testing" in md
        assert "Test decision Alpha" in md
        assert "Fix flaky test" in md
        assert "DI: 0.880" in md or "DI: 0.88" in md
        assert "MD: 0.070" in md or "MD: 0.07" in md
        assert "Cycles: 15" in md
        assert "45.0%" in md
        assert "cp.json" in md

    def test_empty_summary_uses_fallbacks(self):
        """An empty SessionSummary uses placeholder text for each section."""
        writer = AgentsWriter()
        summary = SessionSummary()
        md = writer.generate_markdown(summary)

        assert "## Session Handoff" in md
        assert "*(No current state captured)*" in md
        assert "*(No decisions recorded)*" in md
        assert "*(No open issues)*" in md
        assert "N/A" in md  # checkpoint_ref defaults to empty → "N/A"


class TestDetectContextPressure:

    def test_returns_float_in_range(self):
        """detect_context_pressure always returns 0.0–1.0."""
        writer = AgentsWriter()
        pipeline = _make_minimal_pipeline()

        for cycles in (0, 1, 25, 100):
            p = writer.detect_context_pressure(pipeline, cycle_count=cycles)
            assert 0.0 <= p <= 1.0, f"Pressure out of range at cycle {cycles}: {p}"

    def test_pressure_scales_with_cycles_and_budget(self):
        """Higher cycle counts and budget usage produce higher pressure."""
        writer = AgentsWriter()

        low = _make_minimal_pipeline(budget_consumed=10.0, budget_total=100.0)
        high = _make_minimal_pipeline(budget_consumed=95.0, budget_total=100.0)

        p_low = writer.detect_context_pressure(low, cycle_count=1)
        p_high = writer.detect_context_pressure(high, cycle_count=100,
                                                 chat_history=[{"role": "user", "content": "x"} for _ in range(80)])

        assert p_high >= p_low, (
            f"Expected high pressure ({p_high:.3f}) >= low pressure ({p_low:.3f})"
        )


class TestWriteSummary:

    def test_write_summary_creates_file(self):
        """write_summary creates or appends to AGENTS.md correctly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write("# Existing Content\n\nSome content here.\n")

        try:
            writer = AgentsWriter(tmp_path)
            pipeline = _make_minimal_pipeline(
                checkpoint_path="/tmp/checkpoint_0010.json",
            )

            session_essence = {
                "key_decisions": ["Deploy v2", "Rollback fix"],
                "user_preferences": ["prefers verbose output"],
                "recurring_intents": ["deploy", "monitor"],
                "blockers_resolved": ["API timeout"],
                "mood_trajectory": "cautious",
            }

            markdown = writer.write_summary(
                pipeline=pipeline,
                cycle_count=10,
                chat_history=[{"role": "user", "content": "hello"}],
                session_essence=session_essence,
            )

            assert "## Session Handoff" in markdown

            with open(tmp_path, 'r') as f:
                content = f.read()

            assert "## Session Handoff" in content
            assert "Deploy v2" in content
            assert "DI:" in content
            assert "checkpoint_0010.json" in content

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_write_summary_no_essence(self):
        """write_summary works gracefully when session essence is None."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write("# Start\n")

        try:
            writer = AgentsWriter(tmp_path)
            pipeline = _make_minimal_pipeline()

            markdown = writer.write_summary(pipeline, cycle_count=3)

            assert "## Session Handoff" in markdown
            assert "*(No current state captured)*" in markdown
            assert "*(No decisions recorded)*" in markdown

            with open(tmp_path, 'r') as f:
                content = f.read()
            assert "## Session Handoff" in content
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_write_summary_appends_to_existing(self):
        """Multiple write_summary calls each produce a handoff block."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write("# Start\n\n")

        try:
            writer = AgentsWriter(tmp_path)
            pipeline = _make_minimal_pipeline()

            writer.write_summary(pipeline, cycle_count=1,
                                 session_essence={"key_decisions": ["First"]})
            writer.write_summary(pipeline, cycle_count=2,
                                 session_essence={"key_decisions": ["Second"]})

            with open(tmp_path, 'r') as f:
                content = f.read()

            assert content.count("## Session Handoff") == 2
            assert "First" in content
            assert "Second" in content
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_write_summary_respects_agents_path(self):
        """Custom agents_path is used, not a hard-coded path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='_custom.md', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            writer = AgentsWriter(tmp_path)
            pipeline = _make_minimal_pipeline()

            writer.write_summary(pipeline, cycle_count=1)

            assert os.path.exists(tmp_path)
            with open(tmp_path, 'r') as f:
                content = f.read()
            assert "## Session Handoff" in content
            assert tmp_path.endswith("_custom.md")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
