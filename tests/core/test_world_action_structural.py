"""
Item 10: failed authorization makes ACT STRUCTURALLY impossible.

PATTERN UNDER TEST (refusal is structural, not a check that could be skipped):
under each refusal — uncertified capability, no per-action approval, no adapter,
a FAIL capability gate, or a determinism-gated config — no code path reaches
``WorldAdapter.execute``, ``ActionExecutor.execute``, the structured-write
effect, ``subprocess.run``, or ``NetworkSandbox.request``. Every one of those
seams is spied; a future bypass that reaches ANY of them trips these tests.
A positive control proves the spies are live (they fire on the authorized path),
so the zero counters are meaningful, not vacuous.
"""

import pathlib
import subprocess

import pytest

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
from telos.core.runtime import PipelineConfig, TelosV14Pipeline

SEAMS = ("adapter_execute", "executor_execute", "structured_write",
         "subprocess_run", "sandbox_request")


def _workspace(tmp_path: pathlib.Path) -> str:
    """Create a workspace with one target file.

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
        capability="filesystem.write", operation="write_file", target="notes.md",
        expected_result="alpha\nbeta-edited\ngamma\n",
        params={"old_lines": ["beta"], "new_lines": ["beta-edited"]},
        evidence={"source": "unit"}, confidence=0.9, risk=0.1)


def _approval() -> LiveApproval:
    """A canonical per-action approval.

    Returns:
        The LiveApproval.
    """
    return LiveApproval("filesystem.write", "notes.md", "write_file",
                        "operator", "a1")


def _certified() -> CapabilityCertification:
    """A registry certifying filesystem.write.

    Returns:
        The CapabilityCertification.
    """
    return CapabilityCertification.from_certified_set(
        {"filesystem.write"}, certified_by="test", evidence="unit",
        reason="unit certification")


def _install_spies(monkeypatch) -> dict:
    """Spy every execution seam, counting calls while delegating to the real one.

    Args:
        monkeypatch: the pytest monkeypatch fixture.

    Returns:
        A counter dict keyed by seam name.
    """
    counts = {name: 0 for name in SEAMS}
    real_adapter = FilesystemWriteAdapter.execute
    real_executor = ActionExecutor.execute
    real_write = ActionExecutor._execute_structured_write
    real_subprocess = subprocess.run

    def adapter_execute(self, *a, **k):
        counts["adapter_execute"] += 1
        return real_adapter(self, *a, **k)

    def executor_execute(self, *a, **k):
        counts["executor_execute"] += 1
        return real_executor(self, *a, **k)

    def structured_write(self, *a, **k):
        counts["structured_write"] += 1
        return real_write(self, *a, **k)

    def subprocess_run(*a, **k):
        counts["subprocess_run"] += 1
        return real_subprocess(*a, **k)

    def sandbox_request(self, *a, **k):
        counts["sandbox_request"] += 1
        raise AssertionError("a refused action must never use the network sandbox")

    monkeypatch.setattr(FilesystemWriteAdapter, "execute", adapter_execute)
    monkeypatch.setattr(ActionExecutor, "execute", executor_execute)
    monkeypatch.setattr(ActionExecutor, "_execute_structured_write",
                        structured_write)
    monkeypatch.setattr(subprocess, "run", subprocess_run)
    monkeypatch.setattr("telos.core.actions.sandbox.NetworkSandbox.request",
                        sandbox_request)
    return counts


def test_uncertified_capability_never_reaches_execute(tmp_path, monkeypatch):
    """Uncertified + approval -> execute/effect/capture seams all untouched."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.executed is False and r.action_allowed is False
    assert "not CERTIFIED" in r.blocked_reason
    assert all(counts[s] == 0 for s in SEAMS), counts
    assert pathlib.Path(sb, "notes.md").read_text() == "alpha\nbeta\ngamma\n"


def test_no_per_action_approval_never_reaches_execute(tmp_path, monkeypatch):
    """Certified but unapproved -> no execute seam is touched."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE)
    assert r.executed is False
    assert "per-action approval" in r.blocked_reason
    assert all(counts[s] == 0 for s in SEAMS), counts


def test_no_adapter_never_reaches_execute(tmp_path, monkeypatch):
    """No adapter -> no action, no seam touched (even with cert + approval)."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    ex = ActionExecutor(workspace_root=sb)
    runner = WorldActionRunner(ex, None, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.blocked_reason == "no_adapter_configured"
    assert all(counts[s] == 0 for s in SEAMS), counts


def test_capability_gate_fail_never_reaches_execute(tmp_path, monkeypatch):
    """A FAIL capability gate -> no execute seam is touched."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    cap = from_dimensions({"model_fidelity": CapabilityStatus.FAIL})
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval(),
                   capability_authorization=cap)
    assert r.executed is False
    assert "capability gate failed" in r.blocked_reason
    assert all(counts[s] == 0 for s in SEAMS), counts


def test_authorized_control_proves_the_spies_are_live(tmp_path, monkeypatch):
    """Negative control: the authorized path DOES trip the spies (so zero means zero)."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.executed is True and r.action_allowed is True
    assert counts["adapter_execute"] == 1
    assert counts["executor_execute"] == 1
    assert counts["structured_write"] == 1
    # A structured write never spawns a subprocess and never opens a socket.
    assert counts["subprocess_run"] == 0 and counts["sandbox_request"] == 0


def test_determinism_gate_raises_before_any_executor_exists(tmp_path, monkeypatch):
    """The config guard raises BEFORE build_tool_executor is ever called."""
    ws = str(tmp_path / "ws")
    pathlib.Path(ws).mkdir()

    def _bomb(*args, **kwargs):
        raise AssertionError(
            "determinism gate must raise before an executor is constructed")

    monkeypatch.setattr(
        "telos.core.actions.executor.build_tool_executor", _bomb)
    with pytest.raises(ValueError):
        TelosV14Pipeline(PipelineConfig(
            tool_workspace=ws, operator_tool_permission=True,
            determinism_gate=True))
    # The same bomb must NOT fire for a non-gated opt-in (it is not blanket-off).
    ex = __import__("telos.core.actions.executor", fromlist=["build_tool_executor"])
    monkeypatch.setattr(ex, "build_tool_executor", lambda root, **k: "EXECUTOR")
    p = TelosV14Pipeline(PipelineConfig(
        tool_workspace=ws, operator_tool_permission=True))
    assert p.config.action_executor == "EXECUTOR"


def test_default_config_builds_no_executor(tmp_path, monkeypatch):
    """Default config never constructs a tool executor (byte-identical)."""
    def _bomb(*args, **kwargs):
        raise AssertionError("default config must not build an executor")

    monkeypatch.setattr(
        "telos.core.actions.executor.build_tool_executor", _bomb)
    p = TelosV14Pipeline(PipelineConfig())
    assert p.config.action_executor is None
