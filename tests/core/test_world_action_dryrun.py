"""
Dry-run execution (item 4) — the exact action, with zero external effect.

PATTERN UNDER TEST (dry-run is a real rehearsal, not a stub): a dry-run runs
observe() + validate_action() + the full action-authority chain and produces
the ACTION/AUTHORITY/MODE record and the exact would-be command, while
executing nothing — no subprocess, no network, no file write.
"""

import os
import pathlib
import subprocess

from telos.core.actions.certification import CapabilityCertification
from telos.core.actions.executor import ActionExecutor
from telos.core.actions.world_adapter import FilesystemWriteAdapter
from telos.core.actions.world_action import (
    ActionMode, LiveApproval, WorldActionProposal, WorldActionRunner,
)
from telos.core.governance.capability_authorization import (
    CapabilityStatus, from_dimensions,
)
from telos.core.governance.firewall import DecisionFirewall


def _workspace(tmp_path: pathlib.Path) -> str:
    """Create a harmless workspace with one target file.

    Args:
        tmp_path: the pytest temp directory.

    Returns:
        The workspace root path as a string.
    """
    sb = tmp_path / "ws"
    sb.mkdir()
    (sb / "notes.md").write_text("alpha\nbeta\ngamma\n")
    return str(sb)


def _proposal() -> WorldActionProposal:
    """Build a canonical filesystem-write proposal.

    Returns:
        The WorldActionProposal.
    """
    return WorldActionProposal(
        capability="filesystem.write", operation="write_file",
        target="notes.md",
        expected_result="alpha\nbeta-edited\ngamma\n",
        params={"old_lines": ["beta"], "new_lines": ["beta-edited"]},
        evidence={"source": "unit:predicted"}, confidence=0.9, risk=0.1,
    )


def _bomb(*args, **kwargs):
    """A subprocess.run replacement that fails loudly if ever called.

    Args:
        *args: ignored.
        **kwargs: ignored.

    Raises:
        AssertionError: always — a dry-run must spawn no subprocess.
    """
    raise AssertionError("dry-run must not spawn a subprocess")


def test_dry_run_produces_action_authority_mode_record(tmp_path):
    """A dry-run emits the ACTION/AUTHORITY/MODE record and the command."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.DRY_RUN)
    assert r.mode == "DRY_RUN"
    assert r.executed is False
    assert r.authorized is True
    assert "notes.md" in r.would_be_command
    rendered = r.render()
    assert rendered.startswith("ACTION:")
    assert "AUTHORITY:" in rendered and "MODE:      DRY_RUN" in rendered
    payload = r.to_dict()
    assert payload["action"]["operation"] == "write_file"
    assert payload["authority"]["capability"] == "filesystem.write"
    assert payload["mode"] == "DRY_RUN"


def test_dry_run_is_the_default_mode(tmp_path):
    """run() defaults to DRY_RUN — LIVE is never implicit."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, firewall=DecisionFirewall())
    r = runner.run(_proposal())
    assert r.mode == "DRY_RUN" and r.executed is False


def test_dry_run_executes_nothing(tmp_path, monkeypatch):
    """Monkeypatched subprocess.run and sandbox prove no external effect."""
    sb = _workspace(tmp_path)
    target = pathlib.Path(sb) / "notes.md"
    before_content = target.read_text()
    before_mtime = os.stat(target).st_mtime_ns

    monkeypatch.setattr(subprocess, "run", _bomb)

    def _sandbox_bomb(*args, **kwargs):
        raise AssertionError("dry-run must not touch the network sandbox")

    monkeypatch.setattr(
        "telos.core.actions.sandbox.NetworkSandbox.request", _sandbox_bomb)

    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.DRY_RUN)

    assert r.executed is False and r.action_allowed is False
    assert target.read_text() == before_content
    assert os.stat(target).st_mtime_ns == before_mtime


def test_dry_run_does_not_perturb_firewall_ledger(tmp_path):
    """A dry-run must not turn the firewall's loop ledger (no inspect)."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    fw = DecisionFirewall()
    runner = WorldActionRunner(ex, ad, firewall=fw)
    before = list(fw._action_history)
    runner.run(_proposal(), ActionMode.DRY_RUN)
    assert list(fw._action_history) == before


def test_dry_run_available_for_uncertified_capability(tmp_path):
    """Uncertified capabilities may dry-run but are refused LIVE."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    # An EXPLICITLY empty registry (independent of the canonical file, which
    # may hold legitimate LIVE certifications).
    runner = WorldActionRunner(ex, ad, firewall=DecisionFirewall(),
                               certification=CapabilityCertification(records={}))
    dry = runner.run(_proposal(), ActionMode.DRY_RUN)
    assert dry.executed is False and dry.authorized is True
    live = runner.run(
        _proposal(), ActionMode.LIVE,
        approval=LiveApproval("filesystem.write", "notes.md", "write_file",
                              "operator", "a1"))
    assert live.executed is False
    assert "not CERTIFIED" in live.blocked_reason


def test_dry_run_records_authority_chain_failure(tmp_path):
    """A capability gate FAIL is reported in the dry-run authority block."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, firewall=DecisionFirewall())
    cap = from_dimensions({"observability": CapabilityStatus.FAIL})
    r = runner.run(_proposal(), ActionMode.DRY_RUN,
                   capability_authorization=cap)
    assert r.authorized is False
    assert "capability gate failed" in r.authorization_reason
    assert r.executed is False


def test_dry_run_echoes_evidence_and_confidence(tmp_path):
    """The AUTHORITY block carries the evidence provenance and confidence."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.DRY_RUN)
    assert r.evidence == {"source": "unit:predicted"}
    assert r.confidence == 0.9 and r.risk == 0.1
