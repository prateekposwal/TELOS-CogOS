"""
Per-tool capability authorization (Phase 1).

The registry declares which CapabilityAuthorization gates each tool requires;
the executor's gate vetoes a tool whose required gate is FAIL — conjunctively,
exactly as the council vetoes an action. None skips the gate (pre-Phase-1
behavior).
"""

import os

import pytest

from telos.core.actions.executor import ActionExecutor, ToolPermission
from telos.core.actions.registry import (
    CAPABILITY_PROFILES, capability_profile_for, DEFAULT_REGISTRY,
)
from telos.core.governance.capability_authorization import (
    CapabilityAuthorization, CapabilityStatus, from_dimensions,
)
from telos.core.governance.firewall import DecisionFirewall
from tests.core.test_git_repo_domain import build_real_repo


def test_read_only_profile_requires_observability():
    """A read-only tool needs only the observability gate."""
    spec = DEFAULT_REGISTRY.get("git_status")
    assert capability_profile_for(spec) == ["observability"]


def test_write_profile_requires_authority():
    """A narrow-write tool requires action_validity + authority too."""
    spec = DEFAULT_REGISTRY.get("git_commit")
    profile = capability_profile_for(spec)
    assert "action_validity" in profile and "authority" in profile


def test_explicit_capability_overrides_kind():
    """An explicit spec.capability selects its named profile."""
    from telos.core.actions.registry import ToolSpec
    spec = ToolSpec(template=["x"], kind="read_only", description="d",
                    capability="network_write")
    assert capability_profile_for(spec) == CAPABILITY_PROFILES["network_write"]


def test_capability_gate_allows_when_authorized(tmp_path):
    """A read-only tool runs when observability is PASS."""
    repo_path, _ = build_real_repo(str(tmp_path / "repo"))
    ex = ActionExecutor(workspace_root=repo_path)
    cap = from_dimensions({"observability": CapabilityStatus.PASS})
    result = ex.execute(
        ToolPermission(tool_name="git_status", args=[], cwd=repo_path,
                       permitted_by="operator"),
        firewall=DecisionFirewall(), capability=cap,
    )
    assert result.allowed is True
    assert result.firewall_verdict["capability_gate"]["observed"]["observability"] == "PASS"


def test_capability_gate_vetoes_on_fail(tmp_path):
    """A FAIL on a required gate blocks the tool with a capability reason."""
    repo_path, _ = build_real_repo(str(tmp_path / "repo"))
    ex = ActionExecutor(workspace_root=repo_path)
    cap = from_dimensions({"observability": CapabilityStatus.FAIL})
    result = ex.execute(
        ToolPermission(tool_name="git_status", args=[], cwd=repo_path,
                       permitted_by="operator"),
        firewall=DecisionFirewall(), capability=cap,
    )
    assert result.allowed is False
    assert "capability gate vetoed" in result.blocked_reason
    assert result.returncode is None


def test_write_tool_vetoed_when_authority_fails(tmp_path):
    """A write tool with authority FAIL is vetoed even if observability passes."""
    repo_path, _ = build_real_repo(str(tmp_path / "repo"))
    ex = ActionExecutor(workspace_root=repo_path)
    cap = from_dimensions({
        "observability": CapabilityStatus.PASS,
        "action_validity": CapabilityStatus.PASS,
        "authority": CapabilityStatus.FAIL,
    })
    result = ex.execute(
        ToolPermission(tool_name="git_commit", args=["chore: x"],
                       cwd=repo_path, permitted_by="operator"),
        firewall=DecisionFirewall(), capability=cap,
    )
    assert result.allowed is False
    assert "authority" in result.blocked_reason


def test_none_capability_skips_gate(tmp_path):
    """None capability preserves pre-Phase-1 behavior (gate skipped)."""
    repo_path, _ = build_real_repo(str(tmp_path / "repo"))
    ex = ActionExecutor(workspace_root=repo_path)
    result = ex.execute(
        ToolPermission(tool_name="git_status", args=[], cwd=repo_path,
                       permitted_by="operator"),
        firewall=DecisionFirewall(), capability=None,
    )
    assert result.allowed is True


def test_gate_is_conjunctive():
    """authorized() is False when ANY mandatory gate is FAIL."""
    cap = CapabilityAuthorization(
        observability=CapabilityStatus.FAIL,
        model_fidelity=CapabilityStatus.PASS,
    )
    assert cap.authorized() is False
    assert "observability" in cap.failed_gates()
