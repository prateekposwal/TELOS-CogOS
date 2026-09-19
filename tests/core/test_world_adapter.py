"""
WorldAdapter contract (item 3) — capability declaration, validation, verification.

PATTERN UNDER TEST (one governed capability contract): an adapter declares a
capability name, validates an action by REUSING the executor's own allowlist +
containment gate, executes only through the governed executor, and verifies a
prediction against a later observation. No adapter -> no action.
"""

import pathlib

from telos.core.actions.executor import ActionExecutor
from telos.core.actions.world_adapter import (
    FilesystemWriteAdapter, WorldAdapter, WorldObservation,
)
from telos.core.actions.world_action import (
    ActionMode, WorldActionProposal, WorldActionRunner,
)


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


def _proposal(**overrides) -> WorldActionProposal:
    """Build a canonical filesystem-write proposal.

    Args:
        **overrides: fields to override on the default proposal.

    Returns:
        The WorldActionProposal.
    """
    base = dict(
        capability="filesystem.write", operation="write_file",
        target="notes.md",
        expected_result="alpha\nbeta-edited\ngamma\n",
        params={"old_lines": ["beta"], "new_lines": ["beta-edited"]},
        evidence={"source": "unit"}, confidence=0.9, risk=0.1,
    )
    base.update(overrides)
    return WorldActionProposal(**base)


def test_adapter_declares_capability_and_descriptor(tmp_path):
    """The concrete adapter declares its capability/operation/tool identity."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    assert isinstance(ad, WorldAdapter)
    assert ad.capability_name == "filesystem.write"
    assert ad.operation_name == "write_file"
    assert ad.tool_name == "write_file"
    desc = ad.descriptor()
    assert desc["capability"] == "filesystem.write"
    assert desc["workspace_root"] == ex.workspace_root
    assert "observability" in desc["required_gates"]


def test_validate_action_accepts_well_formed(tmp_path):
    """A well-formed, contained write validates and yields a would-be command."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    v = ad.validate_action(_proposal())
    assert v.valid is True
    assert "notes.md" in v.command


def test_validate_action_rejects_capability_mismatch(tmp_path):
    """A proposal declaring another capability is refused (per-capability)."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    v = ad.validate_action(_proposal(capability="http.post"))
    assert v.valid is False and "capability mismatch" in v.reason


def test_validate_action_rejects_operation_mismatch(tmp_path):
    """A proposal declaring another operation is refused."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    v = ad.validate_action(_proposal(operation="git_commit"))
    assert v.valid is False and "operation mismatch" in v.reason


def test_validate_action_rejects_out_of_workspace_target(tmp_path):
    """A target outside the workspace is refused by the executor containment."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "/etc/hosts")
    v = ad.validate_action(_proposal(target="/etc/hosts"))
    assert v.valid is False
    assert "outside the workspace root" in v.reason


def test_validate_action_rejects_missing_block(tmp_path):
    """A hunk whose old_lines are absent is refused (no-op rejected)."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    v = ad.validate_action(_proposal(params={"old_lines": ["nope"],
                                            "new_lines": ["x"]}))
    assert v.valid is False
    assert "not found" in v.reason


def test_observe_reads_file_content(tmp_path):
    """observe() returns the file's current content (no effect)."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    obs = ad.observe()
    assert isinstance(obs, WorldObservation)
    assert obs.state["exists"] is True
    assert obs.state["content"] == "alpha\nbeta\ngamma\n"


def test_observe_missing_file_reports_absent(tmp_path):
    """observe() on a missing target reports exists=False (never raises)."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "missing.md")
    obs = ad.observe()
    assert obs.state["exists"] is False


def test_verify_result_match_and_mismatch(tmp_path):
    """verify_result matches exact content (gap 0) and mismatches (gap 1)."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    ad = FilesystemWriteAdapter(ex, "notes.md")
    obs = ad.observe()
    ok = ad.verify_result("alpha\nbeta\ngamma\n", obs)
    assert ok.matched is True and ok.reality_gap == 0.0
    bad = ad.verify_result("different\n", obs)
    assert bad.matched is False and bad.reality_gap == 1.0
    assert bad.to_dict()["predicted"] == "different\n"


def test_no_adapter_refuses_every_proposal(tmp_path):
    """No adapter -> no action, for every mode (no parallel ungoverned path)."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    runner = WorldActionRunner(ex, None)
    r = runner.run(_proposal(), ActionMode.DRY_RUN)
    assert r.blocked_reason == "no_adapter_configured"
    live = runner.run(_proposal(), ActionMode.LIVE)
    assert live.blocked_reason == "no_adapter_configured"


def test_default_off_no_executor_refuses(tmp_path):
    """No executor (channel OFF) -> the runner refuses every proposal."""
    runner = WorldActionRunner(None, None)
    r = runner.run(_proposal())
    assert r.blocked_reason == "no_adapter_configured"
