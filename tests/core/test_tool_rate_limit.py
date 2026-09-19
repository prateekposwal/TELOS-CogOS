"""
Tool rate limiting — per-tool sliding window + per-session budget.

An unenforced limit is not a limit. The registry declares
``ToolSpec.rate_limit_per_min``; ActionExecutor is the ONE boundary that
enforces it (plus a per-session global budget). These tests prove:
  - every canonical spec declares a real (non-None, positive) limit;
  - an undeclared limit fails loudly at registry construction;
  - exceeding a per-tool limit BLOCKS with a recorded reason and runs NO
    subprocess;
  - the sliding window resets after the window elapses;
  - the per-session budget blocks even across different tools;
  - the limiter is deterministic under an injected clock.
"""

import subprocess

import pytest

from telos.core.actions.executor import (
    ActionExecutor, ToolPermission, DEFAULT_MAX_TOOL_EXECUTIONS,
)
from telos.core.actions.rate_limit import (
    ToolRateLimiter, WINDOW_SECONDS,
)
from telos.core.actions.registry import ToolRegistry, ToolSpec, DEFAULT_REGISTRY
from telos.core.governance.firewall import DecisionFirewall
from tests.core.test_git_repo_domain import build_real_repo


class FakeClock:
    """A deterministic monotonic clock for window tests."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _executor(repo, limits, max_total=None, clock=None):
    limiter = ToolRateLimiter(limits=limits, max_total=max_total,
                              clock=clock or FakeClock())
    return ActionExecutor(workspace_root=repo, rate_limiter=limiter), limiter


def _perm(tool, repo, **kw):
    return ToolPermission(tool_name=tool, args=[], cwd=repo,
                          permitted_by="operator", **kw)


# ── Registry: declared limits are real ──────────────────────────────────────

def test_every_canonical_spec_declares_a_real_limit():
    for name, spec in DEFAULT_REGISTRY.as_allowlist().items():
        assert isinstance(spec.rate_limit_per_min, int) and \
            spec.rate_limit_per_min > 0, f"{name} has no real rate limit"


def test_registry_rejects_undeclared_limit():
    """A spec with no rate_limit_per_min is rejected at construction."""
    with pytest.raises(ValueError):
        ToolRegistry({"x": ToolSpec(template=["x"], kind="read_only",
                                    description="d")})


# ── Per-tool window: under / at / over ──────────────────────────────────────

def test_under_limit_executes(tmp_path):
    repo, _ = build_real_repo(str(tmp_path / "repo"))
    ex, _ = _executor(repo, {"git_status": 2}, max_total=None)
    fw = DecisionFirewall()
    for _ in range(2):
        r = ex.execute(_perm("git_status", repo), firewall=fw)
        assert r.allowed is True and r.returncode == 0


def test_over_limit_blocks_with_reason_and_no_subprocess(tmp_path, monkeypatch):
    repo, _ = build_real_repo(str(tmp_path / "repo"))
    ex, _ = _executor(repo, {"git_status": 2}, max_total=None)
    fw = DecisionFirewall()
    for _ in range(2):
        assert ex.execute(_perm("git_status", repo), firewall=fw).allowed is True

    calls = {"n": 0}

    def bomb(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("subprocess must NOT run on a rate-limit breach")

    monkeypatch.setattr("telos.core.actions.executor.subprocess.run", bomb)
    r = ex.execute(_perm("git_status", repo), firewall=fw)
    assert r.allowed is False
    assert r.returncode is None
    assert "rate_limit_exceeded" in r.blocked_reason
    assert "git_status" in r.blocked_reason
    assert calls["n"] == 0, "no subprocess may run once the limit is breached"


def test_window_resets_after_elapsed(tmp_path):
    repo, _ = build_real_repo(str(tmp_path / "repo"))
    clock = FakeClock()
    ex, _ = _executor(repo, {"git_status": 1}, max_total=None, clock=clock)
    fw = DecisionFirewall()
    assert ex.execute(_perm("git_status", repo), firewall=fw).allowed is True
    blocked = ex.execute(_perm("git_status", repo), firewall=fw)
    assert blocked.allowed is False and "rate_limit_exceeded" in blocked.blocked_reason
    clock.advance(WINDOW_SECONDS + 1.0)
    assert ex.execute(_perm("git_status", repo), firewall=fw).allowed is True


# ── Per-session global budget ───────────────────────────────────────────────

def test_global_budget_blocks_across_tools(tmp_path):
    repo, _ = build_real_repo(str(tmp_path / "repo"))
    ex, _ = _executor(repo, {}, max_total=2)
    fw = DecisionFirewall()
    assert ex.execute(_perm("git_status", repo), firewall=fw).allowed is True
    assert ex.execute(_perm("git_branch", repo), firewall=fw).allowed is True
    r = ex.execute(_perm("git_diff", repo), firewall=fw)
    assert r.allowed is False
    assert "global tool budget exhausted" in r.blocked_reason


def test_default_global_budget_is_sane():
    assert DEFAULT_MAX_TOOL_EXECUTIONS == 200


def test_default_executor_builds_enforcing_limiter(tmp_path):
    repo, _ = build_real_repo(str(tmp_path / "repo"))
    ex = ActionExecutor(workspace_root=repo)
    # The registry's per-tool limits are the ones enforced.
    assert ex._rate_limiter._limits["git_status"] == 60
    assert ex._rate_limiter._max_total == DEFAULT_MAX_TOOL_EXECUTIONS


# ── Limiter unit: determinism + decision shape ──────────────────────────────

def test_limiter_is_deterministic_under_injected_clock():
    clock = FakeClock()
    decisions = []
    for _ in range(3):
        lim = ToolRateLimiter(limits={"t": 1}, max_total=None, clock=clock)
        decisions.append([lim.check("t").allowed, lim.check("t").allowed])
    assert decisions == [[True, False], [True, False], [True, False]]


def test_limiter_denied_call_does_not_consume_budget():
    clock = FakeClock()
    lim = ToolRateLimiter(limits={"t": 1}, max_total=None, clock=clock)
    assert lim.check("t").allowed is True
    assert lim.check("t").allowed is False
    assert lim.snapshot()["total"] == 1
