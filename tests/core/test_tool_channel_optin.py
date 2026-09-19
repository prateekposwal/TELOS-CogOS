"""
Governed tool channel — opt-in, default-off, four gates intact.

PATTERN UNDER TEST (operator-authorised effect channel): the real tool
channel is OFF unless an operator explicitly names a workspace root. When a
root is named it must (a) not be the TELOS repo (guard), and (b) still route
every request through the four hard gates: allowlist + template validation,
firewall re-audit, operator permission, path containment.

These tests lock:
  - default-off inertness (no workspace -> no executor -> no channel);
  - the "workspace-inside-repo is refused" guard;
  - containment accept inside the sandbox / reject outside (path + cwd +
    structured write_file);
  - each of the four gates still holds.
"""

import os
import subprocess

import pytest

from telos.core.actions.executor import (
    ActionExecutor, ToolPermission, UnsafeWorkspaceRoot,
    build_tool_executor, validate_workspace_root, _TELOS_REPO_ROOT,
)
from telos.core.governance.firewall import DecisionFirewall
from telos.core.governance.capability_authorization import (
    CapabilityStatus, from_dimensions,
)
from telos.core.runtime import TelosV14Pipeline, PipelineConfig


@pytest.fixture
def sandbox(tmp_path):
    """A real git repo used as the operator-authorised workspace root."""
    sb = tmp_path / "tool_sandbox"
    sb.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(sb)], check=True)
    subprocess.run(["git", "-C", str(sb), "config", "user.email", "s@t.local"], check=True)
    subprocess.run(["git", "-C", str(sb), "config", "user.name", "T"], check=True)
    (sb / "notes.md").write_text("alpha\nbeta\ngamma\n")
    subprocess.run(["git", "-C", str(sb), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(sb), "commit", "-q", "-m", "seed"], check=True)
    return str(sb)


# ── Default-off inertness ───────────────────────────────────────────────────

def test_default_off_no_executor_no_channel():
    """No workspace named -> build_tool_executor returns None (channel OFF)."""
    assert build_tool_executor(None) is None
    assert build_tool_executor("") is None
    assert build_tool_executor("   ") is None


def test_default_config_has_no_executor_and_no_workspace():
    """A default PipelineConfig builds no executor and grants no permission."""
    p = TelosV14Pipeline(PipelineConfig())
    assert p.config.action_executor is None
    assert p.config.operator_tool_permission is False
    assert p.config.tool_workspace is None


def test_workspace_without_operator_permission_stays_off(sandbox):
    """A workspace named but NO operator grant -> still no executor (gate 3)."""
    p = TelosV14Pipeline(PipelineConfig(
        tool_workspace=sandbox, operator_tool_permission=False))
    assert p.config.action_executor is None


def test_workspace_with_operator_permission_builds_executor(sandbox):
    """The explicit opt-in (workspace + grant) builds a bound executor."""
    p = TelosV14Pipeline(PipelineConfig(
        tool_workspace=sandbox, operator_tool_permission=True))
    assert p.config.action_executor is not None
    assert p.config.action_executor.workspace_root == str(
        __import__("pathlib").Path(sandbox).resolve())


def test_env_var_opt_in(sandbox, monkeypatch):
    """TELOS_TOOL_WORKSPACE is the env-level opt-in path."""
    monkeypatch.setenv("TELOS_TOOL_WORKSPACE", sandbox)
    p = TelosV14Pipeline(PipelineConfig(operator_tool_permission=True))
    assert p.config.action_executor is not None


# ── Workspace-inside-repo guard ─────────────────────────────────────────────

def test_repo_workspace_is_refused_loudly():
    """A workspace equal to the TELOS repo is refused at construction."""
    with pytest.raises(UnsafeWorkspaceRoot):
        validate_workspace_root(str(_TELOS_REPO_ROOT))
    with pytest.raises(UnsafeWorkspaceRoot):
        build_tool_executor(str(_TELOS_REPO_ROOT))


def test_repo_nested_workspace_is_refused_loudly():
    """A workspace nested inside the TELOS repo is refused."""
    nested = _TELOS_REPO_ROOT / "telos" / "core"
    with pytest.raises(UnsafeWorkspaceRoot):
        validate_workspace_root(str(nested))


def test_repo_traversal_workspace_is_refused():
    """A traversal path that resolves into the repo is refused."""
    sneaky = str(_TELOS_REPO_ROOT) + "/..//" + _TELOS_REPO_ROOT.name
    with pytest.raises(UnsafeWorkspaceRoot):
        validate_workspace_root(sneaky)


def test_pipeline_construction_refuses_repo_workspace():
    """The pipeline itself refuses a repo workspace when opting in."""
    with pytest.raises(UnsafeWorkspaceRoot):
        TelosV14Pipeline(PipelineConfig(
            tool_workspace=str(_TELOS_REPO_ROOT),
            operator_tool_permission=True))


def test_nonexistent_workspace_is_refused(tmp_path):
    """A named workspace that does not exist is refused (fail early)."""
    with pytest.raises(UnsafeWorkspaceRoot):
        validate_workspace_root(str(tmp_path / "nope"))


# ── Containment ─────────────────────────────────────────────────────────────

def test_containment_allows_inside(sandbox):
    """A command inside the workspace root is allowed and really runs."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(tool_name="git_status", args=[], cwd=sandbox,
                                  permitted_by="operator"),
                   firewall=DecisionFirewall())
    assert r.allowed is True and r.returncode == 0


def test_containment_rejects_path_outside(sandbox):
    """git_add targeting a path outside the root is rejected with a reason."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(tool_name="git_add", args=["/etc/hosts"],
                                  cwd=sandbox, permitted_by="operator"),
                   firewall=DecisionFirewall())
    assert r.allowed is False and r.returncode is None
    assert "outside the workspace root" in r.blocked_reason


def test_containment_rejects_traversal(sandbox):
    """A ../ traversal out of the root is rejected."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(tool_name="git_add", args=["../../etc/hosts"],
                                  cwd=sandbox, permitted_by="operator"),
                   firewall=DecisionFirewall())
    assert r.allowed is False
    assert "outside the workspace root" in r.blocked_reason


def test_containment_rejects_cwd_outside(sandbox):
    """A cwd outside the root is rejected even for a read-only tool."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(tool_name="git_status", args=[], cwd="/etc",
                                  permitted_by="operator"),
                   firewall=DecisionFirewall())
    assert r.allowed is False
    assert "outside the workspace root" in r.blocked_reason


def test_write_file_outside_root_rejected(sandbox):
    """A structured write_file targeting a path outside the root is rejected."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(
        tool_name="write_file",
        args=[{"path": "/etc/hosts", "old_lines": ["x"], "new_lines": ["y"]}],
        cwd=sandbox, permitted_by="operator"),
        firewall=DecisionFirewall())
    assert r.allowed is False
    assert "outside the workspace root" in r.blocked_reason


def test_write_file_inside_root_allowed(sandbox):
    """A structured write_file inside the root applies cleanly."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(
        tool_name="write_file",
        args=[{"path": "notes.md", "old_lines": ["beta"],
               "new_lines": ["beta-edited"]}],
        cwd=sandbox, permitted_by="operator"),
        firewall=DecisionFirewall())
    assert r.allowed is True
    assert "beta-edited" in open(os.path.join(sandbox, "notes.md")).read()


# ── Four gates ──────────────────────────────────────────────────────────────

def test_gate1_allowlist_rejects_unlisted(sandbox):
    """Gate 1: an unlisted tool is rejected with a block record."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(tool_name="rm", args=["-rf", "/"],
                                  cwd=sandbox, permitted_by="operator"),
                   firewall=DecisionFirewall())
    assert r.allowed is False and r.returncode is None
    assert "not on the allowlist" in r.blocked_reason


def test_gate1_template_validation_rejects_bad_arg(sandbox):
    """Gate 1: a placeholder out of range (git_log n) is rejected."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(tool_name="git_log", args=["999"], cwd=sandbox,
                                  permitted_by="operator"),
                   firewall=DecisionFirewall())
    assert r.allowed is False
    assert "outside 1..30" in r.blocked_reason


def test_gate2_missing_firewall_blocks(sandbox):
    """Gate 2: no firewall available is itself a block."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(tool_name="git_status", args=[], cwd=sandbox,
                                  permitted_by="operator"), firewall=None)
    assert r.allowed is False
    assert "no DecisionFirewall" in r.blocked_reason


def test_gate3_unrecognized_authorizer_blocks(sandbox):
    """Gate 3: a non-operator/human permission source is rejected."""
    ex = ActionExecutor(workspace_root=sandbox)
    r = ex.execute(ToolPermission(tool_name="git_status", args=[], cwd=sandbox,
                                  permitted_by="self"),
                   firewall=DecisionFirewall())
    assert r.allowed is False
    assert "not a recognized authorizer" in r.blocked_reason


def test_per_tool_capability_gate_vetoes(sandbox):
    """A FAIL on a required capability gate vetoes the tool."""
    ex = ActionExecutor(workspace_root=sandbox)
    cap = from_dimensions({"observability": CapabilityStatus.FAIL})
    r = ex.execute(ToolPermission(tool_name="git_status", args=[], cwd=sandbox,
                                  permitted_by="operator"),
                   firewall=DecisionFirewall(), capability=cap)
    assert r.allowed is False
    assert "capability gate vetoed" in r.blocked_reason


def test_firewall_loop_refusal_blocks(sandbox):
    """Gate 2: the firewall's own loop guard refuses a repeated tool."""
    ex = ActionExecutor(workspace_root=sandbox)
    fw = DecisionFirewall()
    last = None
    for _ in range(5):
        last = ex.execute(ToolPermission(tool_name="git_status", args=[],
                                         cwd=sandbox, permitted_by="operator"),
                          firewall=fw)
    assert last.allowed is False
    assert "firewall blocked" in last.blocked_reason
