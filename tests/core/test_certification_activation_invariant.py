"""
The activation invariant: certification alone must NEVER activate a capability.

PATTERN UNDER TEST (authority is not activation): a LIVE-CERTIFIED record in the
canonical registry is DATA. It answers exactly one question — "has this
capability been certified to leave dry-run?" — and never constructs, enables, or
reaches an execution channel by itself. LIVE execution requires the conjunction
of (1) a configured executor (the operator-enabled channel), (2) a matching
adapter, (3) the per-action approval, and (4) the capability gates. Remove any
one and no execution seam is touched, however certified the capability is.

These tests spy EVERY execution seam (adapter.execute, executor.execute, the
structured write, subprocess, and the network sandbox) and the executor builder,
so a future change that let certification alone build or reach a channel trips
them. A positive control proves the spies are live, so the zero counters are
meaningful rather than vacuous.
"""

import pathlib
import subprocess

from telos.core.actions.certification import (
    CapabilityCertification, CertificationTier,
)
from telos.core.actions.executor import ActionExecutor
from telos.core.actions.registry import DEFAULT_REGISTRY, capability_profile_for
from telos.core.actions.world_adapter import FilesystemWriteAdapter
from telos.core.actions.world_action import (
    ActionMode, LiveApproval, WorldActionProposal, WorldActionRunner,
)
from telos.core.governance.firewall import DecisionFirewall

CAP = "filesystem.write"
TARGET = "notes.md"
ORIGINAL = "alpha\nbeta\ngamma\n"
EDITED = "alpha\nbeta-edited\ngamma\n"

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
    (sb / TARGET).write_text(ORIGINAL)
    return str(sb)


def _proposal(expected: str = EDITED) -> WorldActionProposal:
    """Build a canonical filesystem-write proposal.

    Args:
        expected: the predicted result content.

    Returns:
        The WorldActionProposal.
    """
    return WorldActionProposal(
        capability=CAP, operation="write_file", target=TARGET,
        expected_result=expected,
        params={"old_lines": ["beta"], "new_lines": ["beta-edited"]},
        evidence={"source": "activation-invariant"}, confidence=0.9, risk=0.1)


def _approval() -> LiveApproval:
    """A canonical per-action approval.

    Returns:
        The LiveApproval.
    """
    return LiveApproval(CAP, TARGET, "write_file", "operator", "act-1")


def _certified() -> CapabilityCertification:
    """A LIVE-tier registry certifying filesystem.write.

    Returns:
        The CapabilityCertification.
    """
    return CapabilityCertification.from_certified_set(
        {CAP}, certified_by="test", evidence="unit",
        reason="unit certification", tier=CertificationTier.LIVE.value)


def _install_spies(monkeypatch) -> dict:
    """Spy every execution seam AND the executor builder.

    Args:
        monkeypatch: the pytest monkeypatch fixture.

    Returns:
        A counter dict keyed by seam name.
    """
    counts = {name: 0 for name in SEAMS}
    counts["build_executor"] = 0
    real_adapter = FilesystemWriteAdapter.execute
    real_executor = ActionExecutor.execute
    real_write = ActionExecutor._execute_structured_write
    real_subprocess = subprocess.run
    real_build = __import__("telos.core.actions.executor",
                            fromlist=["build_tool_executor"]).build_tool_executor

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

    def build_executor(*a, **k):
        counts["build_executor"] += 1
        return real_build(*a, **k)

    monkeypatch.setattr(FilesystemWriteAdapter, "execute", adapter_execute)
    monkeypatch.setattr(ActionExecutor, "execute", executor_execute)
    monkeypatch.setattr(ActionExecutor, "_execute_structured_write",
                        structured_write)
    monkeypatch.setattr(subprocess, "run", subprocess_run)
    monkeypatch.setattr("telos.core.actions.sandbox.NetworkSandbox.request",
                        sandbox_request)
    monkeypatch.setattr("telos.core.actions.executor.build_tool_executor",
                        build_executor)
    return counts


def test_live_certified_but_channel_disabled_cannot_execute(tmp_path, monkeypatch):
    """Certification + approval, but NO executor (channel OFF) -> nothing runs."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    adapter = FilesystemWriteAdapter(ActionExecutor(workspace_root=sb), TARGET)
    # The operator never enabled the channel: executor is None. The capability
    # is LIVE-CERTIFIED and an approval is supplied — and it still cannot run.
    runner = WorldActionRunner(None, adapter, certification=_certified(),
                               firewall=DecisionFirewall())
    assert runner.certification.is_live_certified(CAP) is True
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.executed is False and r.action_allowed is False
    assert r.blocked_reason == "no_adapter_configured"
    assert all(counts[s] == 0 for s in SEAMS), counts
    # Certification must not have built a channel either.
    assert counts["build_executor"] == 0
    assert pathlib.Path(sb, TARGET).read_text() == ORIGINAL


def test_live_certified_without_per_action_approval_cannot_execute(
        tmp_path, monkeypatch):
    """Certification alone, channel ON, but NO approval -> nothing runs."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    ex = ActionExecutor(workspace_root=sb)
    adapter = FilesystemWriteAdapter(ex, TARGET)
    runner = WorldActionRunner(ex, adapter, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE)  # no approval
    assert r.executed is False and r.action_allowed is False
    assert "per-action approval" in r.blocked_reason
    assert all(counts[s] == 0 for s in SEAMS), counts
    assert pathlib.Path(sb, TARGET).read_text() == ORIGINAL


def test_standing_boolean_is_not_an_approval(tmp_path, monkeypatch):
    """A blanket ``approval=True`` is refused (no standing 'tools on')."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    ex = ActionExecutor(workspace_root=sb)
    adapter = FilesystemWriteAdapter(ex, TARGET)
    runner = WorldActionRunner(ex, adapter, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=True)
    assert r.executed is False
    assert "standing boolean" in r.blocked_reason
    assert all(counts[s] == 0 for s in SEAMS), counts


def test_revoked_certification_cannot_execute(tmp_path, monkeypatch):
    """A revoked capability is not certified -> LIVE refused."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    ex = ActionExecutor(workspace_root=sb)
    adapter = FilesystemWriteAdapter(ex, TARGET)
    registry = _certified()
    registry.revoke(CAP, reason="reality disproved the model")
    runner = WorldActionRunner(ex, adapter, certification=registry,
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.executed is False
    assert "not CERTIFIED" in r.blocked_reason
    assert all(counts[s] == 0 for s in SEAMS), counts


def test_certification_never_constructs_an_execution_channel(tmp_path):
    """Constructing/running with a LIVE cert never calls build_tool_executor."""
    calls = {"n": 0}

    def _bomb(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("certification must never build an executor")

    import telos.core.actions.executor as exmod
    real = exmod.build_tool_executor
    exmod.build_tool_executor = _bomb
    try:
        sb = _workspace(tmp_path)
        # Channel OFF: no executor is constructed anywhere. A certified runner
        # with executor=None must not manufacture one.
        runner = WorldActionRunner(
            None, FilesystemWriteAdapter(
                ActionExecutor(workspace_root=sb), TARGET),
            certification=_certified(), firewall=DecisionFirewall())
        r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
        assert r.executed is False
        assert runner.executor is None
    finally:
        exmod.build_tool_executor = real
    assert calls["n"] == 0


def test_authorized_control_proves_the_spies_are_live(tmp_path, monkeypatch):
    """Positive control: executor + adapter + cert + approval + gates trips them."""
    sb = _workspace(tmp_path)
    counts = _install_spies(monkeypatch)
    ex = ActionExecutor(workspace_root=sb)
    adapter = FilesystemWriteAdapter(ex, TARGET)
    runner = WorldActionRunner(ex, adapter, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.executed is True and r.action_allowed is True
    assert counts["adapter_execute"] == 1
    assert counts["executor_execute"] == 1
    assert counts["structured_write"] == 1
    assert counts["subprocess_run"] == 0 and counts["sandbox_request"] == 0


def test_write_capability_requires_model_fidelity_gate():
    """The write capability's profile binds model_fidelity (authority) to it."""
    profile = capability_profile_for(DEFAULT_REGISTRY.get("write_file"))
    assert "model_fidelity" in profile
    assert "authority" in profile
