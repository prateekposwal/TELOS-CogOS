"""
TELOS CLI — help/version exit cleanly, status runs, and `run` is a real cycle.

The CLI was previously broken: it imported a nonexistent `telos.GENESIS` symbol
and a nonexistent `telos.telos_task.run_pipeline`. These tests lock the fixes.
"""

import sys
from types import SimpleNamespace

import pytest

from telos.cli import main, _cmd_status, _cmd_run, _build_gridworld_pipeline


def test_help_exits_zero(monkeypatch, capsys):
    """`--help` prints usage and exits 0."""
    monkeypatch.setattr(sys, "argv", ["telos", "--help"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_version_exits_zero(monkeypatch, capsys):
    """`--version` prints the package version and exits 0."""
    import telos
    monkeypatch.setattr(sys, "argv", ["telos", "--version"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    combined = capsys.readouterr().out + capsys.readouterr().err
    assert telos.__version__ in combined


def test_no_command_prints_help(monkeypatch, capsys):
    """Bare invocation prints help rather than crashing."""
    monkeypatch.setattr(sys, "argv", ["telos"])
    main()
    assert "usage" in capsys.readouterr().out.lower()


def test_status_runs(capsys):
    """`status` completes and prints the status header + genesis line."""
    _cmd_status()
    out = capsys.readouterr().out
    assert "TELOS Status" in out
    assert "Genesis:" in out


class _FakeResult:
    decision_integrity = 1.0
    mission_drift = 0.0
    council_blocked = False
    firewall_blocked = False


class _FakePipeline:
    def execute(self, state, user_name=None):
        return _FakeResult()


def test_cmd_run_formats_without_crashing(monkeypatch, capsys):
    """`run` builds a pipeline and prints DI/MD (stubbed here for speed)."""
    monkeypatch.setattr("telos.cli._build_gridworld_pipeline",
                        lambda *a, **k: _FakePipeline())
    _cmd_run(SimpleNamespace(state=[0.0, 0.0]))
    out = capsys.readouterr().out
    assert "TELOS Run" in out
    assert "DI: 1.000" in out


def test_build_gridworld_pipeline_is_real(tmp_path):
    """The run builder produces a configured pipeline (real construction)."""
    pipeline = _build_gridworld_pipeline(checkpoint_dir=str(tmp_path / "cli"))
    assert hasattr(pipeline, "execute")
    assert hasattr(pipeline, "register_stream")
