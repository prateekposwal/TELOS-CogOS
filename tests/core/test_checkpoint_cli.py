"""Honest contract tests for telos/core/session/checkpoint_cli.py."""

import re

import pytest

from telos.core.session import checkpoint_cli
from telos.core.session.checkpoint import CheckpointCLI, SessionCheckpoint


def test_auto_session_name_format():
    name = checkpoint_cli._auto_session_name()
    assert re.match(r"session_\d{8}_\d{6}_\d{6}", name) is not None


def test_cmd_save_prints_saved_path(tmp_path, monkeypatch, capsys):
    cli = CheckpointCLI(session_root=str(tmp_path))
    monkeypatch.setattr(checkpoint_cli, "CheckpointCLI", lambda: cli)
    checkpoint_cli.cmd_save(["--name", "mysess"])
    out = capsys.readouterr().out
    assert "Session saved:" in out
    assert str(tmp_path / "mysess") in out


def test_cmd_save_uses_auto_name_when_no_name(tmp_path, monkeypatch, capsys):
    cli = CheckpointCLI(session_root=str(tmp_path))
    monkeypatch.setattr(checkpoint_cli, "CheckpointCLI", lambda: cli)
    checkpoint_cli.cmd_save([])
    out = capsys.readouterr().out
    assert re.search(r"session_\d{8}_\d{6}_\d{6}", out)


def test_cmd_list_empty_message(tmp_path, monkeypatch, capsys):
    cli = CheckpointCLI(session_root=str(tmp_path))
    monkeypatch.setattr(checkpoint_cli, "CheckpointCLI", lambda: cli)
    checkpoint_cli.cmd_list([])
    out = capsys.readouterr().out
    assert "No saved sessions found." in out


def test_cmd_list_prints_sessions(tmp_path, monkeypatch, capsys):
    cli = CheckpointCLI(session_root=str(tmp_path))
    cli.save(session_name="sess_a", cycle_count=4,
             chat_history=[{"role": "user", "content": "hi"}],
             summary="summary text")
    monkeypatch.setattr(checkpoint_cli, "CheckpointCLI", lambda: cli)
    checkpoint_cli.cmd_list([])
    out = capsys.readouterr().out
    assert "Saved Sessions" in out
    assert "sess_a" in out
    assert "summary text" in out


def test_cmd_load_prints_not_found(tmp_path, monkeypatch, capsys):
    cli = CheckpointCLI(session_root=str(tmp_path))
    monkeypatch.setattr(checkpoint_cli, "CheckpointCLI", lambda: cli)
    checkpoint_cli.cmd_load(["--name", "nope"])
    out = capsys.readouterr().out
    assert "not found" in out.lower()


def test_cmd_load_prints_continuation_prompt(tmp_path, monkeypatch, capsys):
    cli = CheckpointCLI(session_root=str(tmp_path))
    cli.save(session_name="sess_b", cycle_count=2,
             chat_history=[{"role": "user", "content": "hello"}],
             summary="two cycles")
    monkeypatch.setattr(checkpoint_cli, "CheckpointCLI", lambda: cli)
    checkpoint_cli.cmd_load(["--name", "sess_b"])
    out = capsys.readouterr().out
    assert "Session Restored" in out
    assert "two cycles" in out


def test_cmd_restore_aliases_load(tmp_path, monkeypatch, capsys):
    cli = CheckpointCLI(session_root=str(tmp_path))
    cli.save(session_name="sess_c", cycle_count=0, summary="restored session")
    monkeypatch.setattr(checkpoint_cli, "CheckpointCLI", lambda: cli)
    checkpoint_cli.cmd_restore(["--name", "sess_c"])
    out = capsys.readouterr().out
    assert "Session Restored" in out


def test_checkpoint_cli_load_returns_none_for_missing(tmp_path):
    cli = CheckpointCLI(session_root=str(tmp_path))
    assert cli.load("does_not_exist") is None
