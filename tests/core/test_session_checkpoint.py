"""
Tests for Session Checkpoint CLI — lossless save/load/restore of session state.

Verifies:
  1. SessionCheckpoint dataclass fields and defaults
  2. Save creates correct directory structure with all files
  3. Load round-trips produce identical data
  4. List_sessions returns correct summary
  5. Delete removes session directory
  6. Generate continuation prompt produces expected output
  7. Auto-generated session names work
  8. Save with pipeline (checkpoint ref extraction)
  9. Save/load with truncated history
  10. Large chat history roundtrip
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from telos.core.session.checkpoint_cli import (
    SessionCheckpoint,
    CheckpointCLI,
    _auto_session_name,
    DEFAULT_SESSION_ROOT,
)


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def temp_session_root():
    """Provide a temporary session root for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_root = DEFAULT_SESSION_ROOT
        # Monkey-patch the default root by creating a CLI with our temp dir
        yield tmpdir


@pytest.fixture
def cli(temp_session_root):
    """CheckpointCLI with a temporary session root."""
    return CheckpointCLI(session_root=temp_session_root)


@pytest.fixture
def sample_essence():
    return {
        "key_decisions": ["Deploy v2", "Rollback to v1"],
        "user_preferences": ["prefers dark mode", "verbose output"],
        "blockers_resolved": ["API timeout"],
        "recurring_intents": ["deploy", "rollback"],
        "mood_trajectory": "cautious",
    }


@pytest.fixture
def sample_chat_history():
    return [
        {"role": "user", "content": "Let's start the deployment"},
        {"role": "assistant", "content": "I'll prepare the deployment plan."},
        {"role": "user", "content": "We need to roll back"},
        {"role": "assistant", "content": "Rolling back to previous version."},
    ]


@pytest.fixture
def sample_truncated_history():
    return [
        {"role": "user", "content": "We need to roll back"},
        {"role": "assistant", "content": "Rolling back to previous version."},
    ]


# ── Test SessionCheckpoint Dataclass ────────────────────────────────────

class TestSessionCheckpointDataclass:

    def test_default_fields(self):
        """Default SessionCheckpoint has correct field types."""
        cp = SessionCheckpoint(
            timestamp=1000.0,
            cycle_count=5,
        )
        assert cp.timestamp == 1000.0
        assert cp.cycle_count == 5
        assert cp.session_essence is None
        assert cp.truncated_history is None
        assert cp.chat_history == []
        assert cp.pipeline_checkpoint_path is None
        assert cp.agents_md_content is None
        assert cp.summary == ""

    def test_all_fields(self, sample_essence, sample_chat_history, sample_truncated_history):
        """All fields can be set and retrieved."""
        cp = SessionCheckpoint(
            timestamp=2000.0,
            cycle_count=42,
            session_essence=sample_essence,
            truncated_history=sample_truncated_history,
            chat_history=sample_chat_history,
            pipeline_checkpoint_path="/tmp/checkpoint_0042.json",
            agents_md_content="# Test AGENTS.md",
            summary="Working on deployment pipeline",
        )
        assert cp.timestamp == 2000.0
        assert cp.cycle_count == 42
        assert cp.session_essence["key_decisions"][0] == "Deploy v2"
        assert len(cp.truncated_history) == 2
        assert len(cp.chat_history) == 4
        assert cp.pipeline_checkpoint_path == "/tmp/checkpoint_0042.json"
        assert "Test AGENTS.md" in cp.agents_md_content
        assert cp.summary == "Working on deployment pipeline"

    def test_summary_auto_generation(self, sample_essence):
        """Summary can be auto-derived from essence."""
        cp = SessionCheckpoint(
            timestamp=3000.0,
            cycle_count=10,
            session_essence=sample_essence,
            summary="2 decisions; working on: deploy",
        )
        assert "2 decisions" in cp.summary


# ── Test CheckpointCLI Save ────────────────────────────────────────────

class TestCheckpointCLISave:

    def test_save_creates_directory_structure(self, cli, temp_session_root):
        """Save creates all expected files in the session directory."""
        session_name = "test_save_structure"
        path = cli.save(
            session_name=session_name,
            cycle_count=7,
            chat_history=[{"role": "user", "content": "hello"}],
            summary="Test save",
        )

        session_dir = Path(path)
        assert session_dir.exists()
        assert (session_dir / "session.json").exists()
        assert (session_dir / "chat_history.json").exists()
        assert (session_dir / "truncated_history.json").exists()
        assert (session_dir / "essence.json").exists()
        assert (session_dir / "checkpoint_ref.txt").exists()

    def test_save_with_all_data(
        self, cli, sample_essence, sample_chat_history, sample_truncated_history
    ):
        """Save with all optional data produces correct files."""
        session_name = "test_save_all"
        path = cli.save(
            session_name=session_name,
            cycle_count=42,
            chat_history=sample_chat_history,
            session_essence=sample_essence,
            truncated_history=sample_truncated_history,
            summary="Full data test",
        )

        session_dir = Path(path)

        # Verify session.json manifest
        with open(session_dir / "session.json") as f:
            manifest = json.load(f)
        assert manifest["cycle_count"] == 42
        assert manifest["summary"] == "Full data test"
        assert manifest["has_essence"] is True
        assert manifest["chat_history_count"] == 4

        # Verify chat_history.json
        with open(session_dir / "chat_history.json") as f:
            restored_chat = json.load(f)
        assert restored_chat == sample_chat_history

        # Verify truncated_history.json
        with open(session_dir / "truncated_history.json") as f:
            restored_trunc = json.load(f)
        assert restored_trunc == sample_truncated_history

        # Verify essence.json
        with open(session_dir / "essence.json") as f:
            restored_essence = json.load(f)
        assert restored_essence["key_decisions"] == sample_essence["key_decisions"]
        assert restored_essence["mood_trajectory"] == "cautious"

    def test_save_with_agents_snapshot(self, cli, temp_session_root):
        """Save captures AGENTS.md content when the file exists."""
        # Create a temporary AGENTS.md
        agents_path = os.path.join(temp_session_root, "TEST_AGENTS.md")
        with open(agents_path, 'w') as f:
            f.write("# Test Agents\n\n## Session Handoff — Test\n- Item 1\n")

        session_name = "test_with_agents"
        path = cli.save(
            session_name=session_name,
            cycle_count=1,
            chat_history=[],
            agents_path=agents_path,
            summary="With AGENTS.md",
        )

        session_dir = Path(path)
        assert (session_dir / "agents.md").exists()
        with open(session_dir / "agents.md") as f:
            content = f.read()
        assert "# Test Agents" in content
        assert "Session Handoff" in content

        # Clean up
        os.unlink(agents_path)

    def test_save_with_missing_agents(self, cli):
        """Save handles missing AGENTS.md gracefully."""
        session_name = "test_no_agents"
        path = cli.save(
            session_name=session_name,
            cycle_count=1,
            chat_history=[],
            agents_path="/nonexistent/AGENTS.md",
            summary="No agents file",
        )
        session_dir = Path(path)
        # agents.md should not be created when source doesn't exist
        assert not (session_dir / "agents.md").exists()

    def test_save_with_pipeline_checkpoint_ref(self, cli):
        """Save extracts checkpoint ref from pipeline object."""
        class FakeCheckpointer:
            latest_path = "/tmp/checkpoints/checkpoint_0042.json"

        class FakePipeline:
            _checkpointer = FakeCheckpointer()

        session_name = "test_with_pipeline"
        path = cli.save(
            session_name=session_name,
            pipeline=FakePipeline(),
            cycle_count=42,
            chat_history=[],
            summary="Pipeline test",
        )

        session_dir = Path(path)
        with open(session_dir / "checkpoint_ref.txt") as f:
            ref = f.read().strip()
        assert ref == "/tmp/checkpoints/checkpoint_0042.json"

    def test_save_without_pipeline(self, cli):
        """Save works without a pipeline object."""
        session_name = "test_no_pipeline"
        path = cli.save(
            session_name=session_name,
            cycle_count=0,
            chat_history=[],
            summary="No pipeline",
        )

        session_dir = Path(path)
        with open(session_dir / "checkpoint_ref.txt") as f:
            ref = f.read().strip()
        assert ref == ""  # empty ref

    def test_save_auto_summary_from_essence(self, cli, sample_essence):
        """Auto-generated summary uses essence data."""
        session_name = "test_auto_summary"
        path = cli.save(
            session_name=session_name,
            cycle_count=5,
            chat_history=[],
            session_essence=sample_essence,
            # no summary provided — should auto-generate
        )

        session_dir = Path(path)
        with open(session_dir / "session.json") as f:
            manifest = json.load(f)
        # Should contain essence-derived summary
        assert "decisions" in manifest["summary"] or "deploy" in manifest["summary"].lower()

    def test_save_auto_summary_fallback(self, cli):
        """Auto-generated summary falls back to cycle count."""
        session_name = "test_auto_summary_fallback"
        path = cli.save(
            session_name=session_name,
            cycle_count=10,
            chat_history=[{"role": "user", "content": "hi"}],
        )

        session_dir = Path(path)
        with open(session_dir / "session.json") as f:
            manifest = json.load(f)
        assert "Cycle 10" in manifest["summary"] or "1 messages" in manifest["summary"]


# ── Test CheckpointCLI Load ────────────────────────────────────────────

class TestCheckpointCLILoad:

    def test_load_returns_none_for_missing(self, cli):
        """Load returns None for non-existent session."""
        result = cli.load("nonexistent_session")
        assert result is None

    def test_load_roundtrip(
        self, cli, sample_essence, sample_chat_history, sample_truncated_history
    ):
        """Save then load produces identical data."""
        session_name = "test_roundtrip"
        cli.save(
            session_name=session_name,
            cycle_count=42,
            chat_history=sample_chat_history,
            session_essence=sample_essence,
            truncated_history=sample_truncated_history,
            summary="Roundtrip test",
        )

        cp = cli.load(session_name)
        assert cp is not None
        assert cp.cycle_count == 42
        assert cp.summary == "Roundtrip test"
        assert cp.chat_history == sample_chat_history
        assert cp.truncated_history == sample_truncated_history
        assert cp.session_essence["key_decisions"] == sample_essence["key_decisions"]

    def test_load_with_agents_and_ref(
        self, cli, temp_session_root
    ):
        """Load restores AGENTS.md content and checkpoint ref."""
        # Create a temporary AGENTS.md
        agents_path = os.path.join(temp_session_root, "LOAD_TEST_AGENTS.md")
        agents_content = "# Load Test Agents\n- Decision 1\n- Decision 2\n"
        with open(agents_path, 'w') as f:
            f.write(agents_content)

        class FakeCheckpointer:
            latest_path = "/tmp/load_test_checkpoint.json"

        class FakePipeline:
            _checkpointer = FakeCheckpointer()

        session_name = "test_load_full"
        cli.save(
            session_name=session_name,
            pipeline=FakePipeline(),
            cycle_count=7,
            chat_history=[{"role": "user", "content": "test"}],
            agents_path=agents_path,
            summary="Load full test",
        )

        cp = cli.load(session_name)
        assert cp is not None
        assert cp.agents_md_content == agents_content
        assert cp.pipeline_checkpoint_path == "/tmp/load_test_checkpoint.json"

        os.unlink(agents_path)

    def test_load_empty_session(self, cli):
        """Load handles empty save (no chat, no essence)."""
        session_name = "test_empty"
        cli.save(session_name=session_name, cycle_count=0, summary="Empty test")

        cp = cli.load(session_name)
        assert cp is not None
        assert cp.chat_history == []
        assert cp.session_essence is None
        assert cp.truncated_history is None

    def test_load_with_large_chat(self, cli):
        """Save/load with 100+ chat messages."""
        large_history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
            for i in range(150)
        ]
        session_name = "test_large_chat"
        cli.save(
            session_name=session_name,
            cycle_count=150,
            chat_history=large_history,
            summary="Large chat test",
        )

        cp = cli.load(session_name)
        assert cp is not None
        assert len(cp.chat_history) == 150
        assert cp.chat_history[0]["content"] == "Message 0"
        assert cp.chat_history[149]["content"] == "Message 149"

    def test_load_corrupted_manifest(self, cli):
        """Load handles corrupted manifest gracefully."""
        session_name = "test_corrupted"
        cli.save(session_name=session_name, cycle_count=1, summary="Corrupted test")

        # Corrupt the manifest
        session_dir = Path(cli.get_session_dir(session_name))
        with open(session_dir / "session.json", 'w') as f:
            f.write("not valid json{")

        cp = cli.load(session_name)
        assert cp is None


# ── Test CheckpointCLI List ────────────────────────────────────────────

class TestCheckpointCLIList:

    def test_list_empty(self, cli):
        """List returns empty for no sessions."""
        sessions = cli.list_sessions()
        assert sessions == []

    def test_list_after_save(self, cli):
        """List returns saved sessions."""
        cli.save(session_name="session_a", cycle_count=3, summary="First session")
        cli.save(session_name="session_b", cycle_count=7, summary="Second session")

        sessions = cli.list_sessions()
        assert len(sessions) == 2

        names = [s["name"] for s in sessions]
        assert "session_a" in names
        assert "session_b" in names

        # Most recent first
        assert sessions[0]["timestamp"] >= sessions[1]["timestamp"]

    def test_list_returns_summary_info(self, cli):
        """List entries contain summary, cycle_count, chat_count."""
        cli.save(
            session_name="test_list_info",
            cycle_count=10,
            chat_history=[{"role": "user", "content": "hi"}] * 5,
            summary="List info test",
        )

        sessions = cli.list_sessions()
        assert len(sessions) == 1
        s = sessions[0]
        assert s["name"] == "test_list_info"
        assert s["summary"] == "List info test"
        assert s["cycle_count"] == 10
        assert s["chat_count"] == 5
        assert "formatted_time" in s

    def test_list_ignores_non_session_dirs(self, cli, temp_session_root):
        """List ignores directories without session.json."""
        # Create a valid session
        cli.save(session_name="valid_session", cycle_count=1, summary="Valid")

        # Create a random directory without session.json
        junk_dir = Path(temp_session_root) / "junk_dir"
        junk_dir.mkdir(exist_ok=True)
        (junk_dir / "random_file.txt").write_text("not a session")

        sessions = cli.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["name"] == "valid_session"

    def test_list_multiple_saves_same_name(self, cli):
        """Saving to same name overwrites (only one entry in list)."""
        cli.save(session_name="overwrite_test", cycle_count=1, summary="First")
        cli.save(session_name="overwrite_test", cycle_count=2, summary="Second")

        sessions = cli.list_sessions()
        matching = [s for s in sessions if s["name"] == "overwrite_test"]
        assert len(matching) == 1
        assert matching[0]["cycle_count"] == 2


# ── Test CheckpointCLI Delete ──────────────────────────────────────────

class TestCheckpointCLIDelete:

    def test_delete_existing(self, cli):
        """Delete removes an existing session."""
        session_name = "test_delete_me"
        cli.save(session_name=session_name, cycle_count=1, summary="Delete me")

        assert Path(cli.get_session_dir(session_name)).exists()
        result = cli.delete(session_name)
        assert result is True
        assert not Path(cli.get_session_dir(session_name)).exists()

    def test_delete_nonexistent(self, cli):
        """Delete returns False for non-existent session."""
        result = cli.delete("does_not_exist")
        assert result is False

    def test_delete_removes_from_list(self, cli):
        """Deleted session no longer appears in list."""
        cli.save(session_name="keep_me", cycle_count=1, summary="Keep")
        cli.save(session_name="remove_me", cycle_count=2, summary="Remove")

        cli.delete("remove_me")

        sessions = cli.list_sessions()
        names = [s["name"] for s in sessions]
        assert "remove_me" not in names
        assert "keep_me" in names


# ── Test Continuation Prompt ────────────────────────────────────────────

class TestContinuationPrompt:

    def test_generate_prompt(self, cli, sample_essence, sample_chat_history):
        """Generate continuation prompt for existing session."""
        session_name = "test_prompt"
        cli.save(
            session_name=session_name,
            cycle_count=10,
            chat_history=sample_chat_history,
            session_essence=sample_essence,
            summary="Prompt test",
        )

        prompt = cli.generate_continuation_prompt(session_name)
        assert prompt is not None
        assert "Session Restored" in prompt
        assert "test_prompt" in prompt
        assert "Prompt test" in prompt
        assert "key_decisions" in prompt
        assert "Deploy v2" in prompt
        assert "4 messages" in prompt or "chat_count" in prompt

    def test_generate_prompt_nonexistent(self, cli):
        """Generate prompt returns None for missing session."""
        prompt = cli.generate_continuation_prompt("does_not_exist")
        assert prompt is None

    def test_prompt_contains_restore_instructions(self, cli):
        """Prompt includes actionable restore instructions."""
        session_name = "test_instructions"
        cli.save(
            session_name=session_name,
            cycle_count=5,
            chat_history=[{"role": "user", "content": "hello"}],
            summary="Instructions test",
        )

        prompt = cli.generate_continuation_prompt(session_name)
        assert prompt is not None
        assert "Restore Instructions" in prompt
        assert "CheckpointManager" in prompt
        assert "chat_history.json" in prompt
        assert "Load pipeline checkpoint" in prompt


# ── Test Auto Session Name ─────────────────────────────────────────────

class TestAutoSessionName:

    def test_auto_name_format(self):
        """Auto-generated name matches expected format."""
        name = _auto_session_name()
        assert name.startswith("session_")
        # Should have date-time parts
        parts = name.split("_")
        assert len(parts) == 4  # session_YYYYMMDD_HHMMSS_ffffff
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 6  # HHMMSS
        assert len(parts[3]) == 6  # ffffff (microseconds)

    def test_auto_names_are_unique(self):
        """Two calls produce different names (different timestamps)."""
        name1 = _auto_session_name()
        name2 = _auto_session_name()
        assert name1 != name2


# ── Test Full Roundtrip ────────────────────────────────────────────────

class TestFullRoundtrip:

    def test_complete_roundtrip(
        self, cli, sample_essence, sample_chat_history, sample_truncated_history
    ):
        """Save → load → verify all data matches."""
        # ── Save ─────────────────────────────────────────────────────
        session_name = "full_roundtrip"
        saved_path = cli.save(
            session_name=session_name,
            cycle_count=99,
            chat_history=sample_chat_history,
            session_essence=sample_essence,
            truncated_history=sample_truncated_history,
            summary="Full roundtrip verification",
        )
        assert saved_path is not None

        # ── Load ─────────────────────────────────────────────────────
        cp = cli.load(session_name)
        assert cp is not None

        # ── Verify all fields ─────────────────────────────────────────
        assert cp.cycle_count == 99
        assert cp.summary == "Full roundtrip verification"
        assert cp.chat_history == sample_chat_history
        assert cp.truncated_history == sample_truncated_history
        assert cp.session_essence is not None
        assert cp.session_essence["key_decisions"] == sample_essence["key_decisions"]
        assert cp.session_essence["mood_trajectory"] == "cautious"
        assert cp.session_essence["user_preferences"] == sample_essence["user_preferences"]

        # ── Verify timestamp is reasonable ────────────────────────────
        now = time.time()
        assert cp.timestamp > 0
        assert abs(now - cp.timestamp) < 60  # within 60 seconds

    def test_multiple_saves_independent(self, cli):
        """Multiple sessions don't interfere."""
        cli.save(
            session_name="session_a",
            cycle_count=1,
            chat_history=[{"role": "user", "content": "session a msg"}],
            summary="Session A",
        )
        cli.save(
            session_name="session_b",
            cycle_count=2,
            chat_history=[{"role": "user", "content": "session b msg"}],
            summary="Session B",
        )

        a = cli.load("session_a")
        b = cli.load("session_b")

        assert a is not None
        assert b is not None
        assert a.cycle_count == 1
        assert b.cycle_count == 2
        assert a.chat_history[0]["content"] == "session a msg"
        assert b.chat_history[0]["content"] == "session b msg"

    def test_save_with_overwrite(self, cli):
        """Saving same name overwrites previous data."""
        cli.save(
            session_name="overwrite",
            cycle_count=1,
            chat_history=[{"role": "user", "content": "old"}],
            summary="Old data",
        )
        cli.save(
            session_name="overwrite",
            cycle_count=2,
            chat_history=[{"role": "user", "content": "new"}],
            summary="New data",
        )

        cp = cli.load("overwrite")
        assert cp is not None
        assert cp.cycle_count == 2
        assert cp.chat_history[0]["content"] == "new"
        assert cp.summary == "New data"


# ── Test Edge Cases ────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_chat_history(self, cli):
        """Save and load with empty chat history."""
        session_name = "empty_chat"
        cli.save(session_name=session_name, cycle_count=0, summary="Empty chat")

        cp = cli.load(session_name)
        assert cp is not None
        assert cp.chat_history == []

    def test_none_values_in_fields(self, cli):
        """Save and load with None values for optional fields."""
        session_name = "none_values"
        cli.save(
            session_name=session_name,
            cycle_count=0,
            chat_history=[],
            session_essence=None,
            truncated_history=None,
            summary="None values",
        )

        cp = cli.load(session_name)
        assert cp is not None
        assert cp.session_essence is None or cp.session_essence == {}
        assert cp.truncated_history is None or cp.truncated_history == []

    def test_unicode_in_chat(self, cli):
        """Unicode characters survive roundtrip."""
        unicode_chat = [
            {"role": "user", "content": "Hello 👋 TELOS"},
            {"role": "assistant", "content": "नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?"},
            {"role": "user", "content": "こんにちは世界"},
        ]
        session_name = "unicode_test"
        cli.save(
            session_name=session_name,
            cycle_count=3,
            chat_history=unicode_chat,
            summary="Unicode test",
        )

        cp = cli.load(session_name)
        assert cp is not None
        assert cp.chat_history == unicode_chat

    def test_large_essence(self, cli):
        """Large session essence with many entries survives roundtrip."""
        large_essence = {
            "key_decisions": [f"Decision {i}" for i in range(200)],
            "user_preferences": [f"Preference {i}" for i in range(100)],
            "blockers_resolved": [f"Blocker {i}" for i in range(50)],
            "recurring_intents": [f"Intent {i}" for i in range(75)],
            "mood_trajectory": "analytical",
        }
        session_name = "large_essence"
        cli.save(
            session_name=session_name,
            cycle_count=1,
            chat_history=[],
            session_essence=large_essence,
            summary="Large essence test",
        )

        cp = cli.load(session_name)
        assert cp is not None
        assert len(cp.session_essence["key_decisions"]) == 200
        assert len(cp.session_essence["user_preferences"]) == 100
        assert cp.session_essence["mood_trajectory"] == "analytical"


# ── Test Module Imports ────────────────────────────────────────────────

class TestModuleImports:

    def test_checkpoint_cli_imports(self):
        """All public symbols import correctly."""
        from telos.core.session.checkpoint_cli import (
            SessionCheckpoint,
            CheckpointCLI,
            cmd_save,
            cmd_list,
            cmd_load,
            cmd_restore,
        )
        assert SessionCheckpoint is not None
        assert CheckpointCLI is not None
        assert callable(cmd_save)
        assert callable(cmd_list)
        assert callable(cmd_load)
        assert callable(cmd_restore)

    def test_session_package_imports(self):
        """Session package exports checkpoint CLI."""
        from telos.core.session import (
            SessionCheckpoint,
            CheckpointCLI,
            cmd_save,
            cmd_list,
        )
        assert SessionCheckpoint is not None
        assert CheckpointCLI is not None

    def test_telos_package_imports(self):
        """Top-level telos package exports checkpoint CLI."""
        import telos
        assert hasattr(telos, "SessionCheckpoint")
        assert hasattr(telos, "CheckpointCLI")
        assert hasattr(telos, "cmd_save")
        assert hasattr(telos, "cmd_list")
        assert hasattr(telos, "cmd_load")
        assert hasattr(telos, "cmd_restore")
        assert hasattr(telos, "checkpoint_cli_main")
