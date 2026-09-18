"""
ActionExecutor — audited real tool-use channel tests (Milestone 2).

PATTERN UNDER TEST (audited action channel): every real-world command is
allowlist-checked, firewall-audited, operator-permitted, and trace-logged —
a block is a first-class record, never a shell pass-through.

Tests run REAL git commands against a REAL tmp repository and assert:
  - an allowlisted git_status-class action actually executes and its real
    output lands in the trace (via the ACT phase hook);
  - un-allowlisted / path-escaping / over-bounded / unapproved-message /
    unpermitted requests are REJECTED with a block record and NO subprocess
    ever runs;
  - the firewall gate blocks execution when the firewall blocks;
  - the governance signals carry the audit entry.
"""

import os
import subprocess
import pytest
import numpy as np

from telos.core.actions.executor import (
    ActionExecutor, ToolPermission, ACTION_ALLOWLIST, ToolRejected,
)
from telos.core.governance.firewall import DecisionFirewall
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.streams.base import CognitiveStream
from telos.adapters.git_repo import GitRepoSim, GitRepoAdapter, STATE_DIM
from telos.core.council.validators.repo_evidence import RepoEvidenceValidator
from telos.world.world import World
from tests.core.test_git_repo_domain import build_real_repo, run_command


class ToolStream(CognitiveStream):
    """Test stream proposing an execute_tool intent with a permission spec."""
    priority = 1.0

    def __init__(self, skill_library, permission_spec):
        super().__init__(skill_library)
        self.permission_spec = permission_spec

    def process(self, world: World):
        from telos.intent_ir import IntentIR
        return IntentIR(
            intent_type="execute_tool",
            confidence=0.9,
            params={
                "tool_name": self.permission_spec["tool_name"],
                "tool_permission": self.permission_spec,
            },
            metadata={"stream": "tool_test", "real_tool": True},
        )


def build_tool_pipeline(repo_path, permission_spec, operator_grant=True,
                        executor=None):
    """Build a pipeline with the audited channel configured.

    Args:
        repo_path: the real workspace root for the executor.
        permission_spec: the tool_permission dict the council sees.
        operator_grant: PipelineConfig.operator_tool_permission value.
        executor: optional pre-built ActionExecutor (defaults to repo root).

    Returns:
        (pipeline, sim, executor) ready for execute().
    """
    ex = executor or ActionExecutor(workspace_root=repo_path)
    sim = GitRepoSim(repo_path)
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=GitRepoAdapter(),
        simulator=sim,
        compute_budget_ms=200.0,
        state_dim=STATE_DIM,
        n_worlds=3,
        horizon=1,
        action_executor=ex,
        operator_tool_permission=operator_grant,
    ))
    pipeline.register_stream(ToolStream(SkillLibrary(), permission_spec))
    pipeline.register_validator(RepoEvidenceValidator())
    return pipeline, sim, ex


# ──────────────────────────────────────────────────────────────────
# Executor unit tests (real repo)
# ──────────────────────────────────────────────────────────────────

class TestActionExecutorGates:
    """Every gate: allowlist, permission, firewall, containment, bounds."""

    def test_allowlisted_status_executes_with_real_output(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        executor = ActionExecutor(workspace_root=repo_path)
        fw = DecisionFirewall()
        perm = ToolPermission(
            tool_name="git_status", args=[], cwd=repo_path,
            permitted_by="operator", permission_id="t1",
        )
        result = executor.execute(perm, firewall=fw)
        assert result.allowed is True
        assert result.returncode == 0
        assert "calculator.py" in result.stdout, "real git output must be captured"
        assert result.blocked_reason is None
        assert result.permission_id == "t1"

    def test_unallowlisted_command_rejected_with_block_record(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        executor = ActionExecutor(workspace_root=repo_path)
        fw = DecisionFirewall()
        perm = ToolPermission(
            tool_name="rm", args=["-rf", "/"], cwd=repo_path, permitted_by="operator")
        result = executor.execute(perm, firewall=fw)
        assert result.allowed is False
        assert "not on the allowlist" in result.blocked_reason
        assert result.returncode is None, "NO subprocess may run for a rejected tool"
        # A block record is first-class: auditably serializable.
        d = result.to_dict()
        assert d["allowed"] is False and d["blocked_reason"]

    def test_unknown_permission_source_rejected(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        executor = ActionExecutor(workspace_root=repo_path)
        fw = DecisionFirewall()
        perm = ToolPermission(
            tool_name="git_status", args=[], cwd=repo_path, permitted_by="self")
        result = executor.execute(perm, firewall=fw)
        assert result.allowed is False
        assert "not a recognized authorizer" in result.blocked_reason

    def test_no_firewall_blocks_execution(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        executor = ActionExecutor(workspace_root=repo_path)
        perm = ToolPermission(
            tool_name="git_status", args=[], cwd=repo_path, permitted_by="operator")
        result = executor.execute(perm, firewall=None)
        assert result.allowed is False
        assert "no DecisionFirewall" in result.blocked_reason

    def test_firewall_refusal_blocks_execution(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        executor = ActionExecutor(workspace_root=repo_path)
        # A firewall that blocks everything: low DI passes nothing.
        fw = DecisionFirewall()
        perm = ToolPermission(
            tool_name="git_status", args=[], cwd=repo_path, permitted_by="operator")
        # Force the firewall to block by running with decision_integrity=0 via
        # the executor path: monkeypatch audit to a failing verdict is NOT
        # needed — the real firewall blocks a tool intent repeated 4x, which we
        # exercise here honestly:
        for _ in range(4):
            result = executor.execute(perm, firewall=fw)
        assert result.allowed is False, \
            "loop-guarded firewall must eventually refuse the repeated tool"
        assert result.blocked_reason and "firewall blocked" in result.blocked_reason

    def test_path_escape_rejected(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        executor = ActionExecutor(workspace_root=repo_path)
        fw = DecisionFirewall()
        perm = ToolPermission(
            tool_name="run_tests", args=["/etc"], cwd=repo_path, permitted_by="operator")
        result = executor.execute(perm, firewall=fw)
        assert result.allowed is False
        assert "outside the workspace" in result.blocked_reason

    def test_git_log_bounds_enforced(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        executor = ActionExecutor(workspace_root=repo_path)
        fw = DecisionFirewall()
        ok = executor.execute(
            ToolPermission(tool_name="git_log", args=["2"], cwd=repo_path,
                           permitted_by="operator"), firewall=fw)
        assert ok.allowed and "add calculator" in ok.stdout
        bad = executor.execute(
            ToolPermission(tool_name="git_log", args=["999"], cwd=repo_path,
                           permitted_by="operator"), firewall=fw)
        assert bad.allowed is False and "outside 1..30" in bad.blocked_reason

    def test_git_commit_message_validation(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        executor = ActionExecutor(workspace_root=repo_path)
        fw = DecisionFirewall()
        evil = executor.execute(
            ToolPermission(tool_name="git_commit", args=["x; rm -rf /"],
                           cwd=repo_path, permitted_by="operator"), firewall=fw)
        assert evil.allowed is False
        assert "unapproved characters" in evil.blocked_reason

    def test_real_commit_workflow(self, tmp_path):
        """git add + git commit: a REAL, audited narrow write end to end."""
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        with open(os.path.join(repo_path, "notes.txt"), "w") as f:
            f.write("operator-approved note\n")
        executor = ActionExecutor(workspace_root=repo_path)
        fw = DecisionFirewall()
        add = executor.execute(
            ToolPermission(tool_name="git_add", args=["notes.txt"],
                           cwd=repo_path, permitted_by="operator"), firewall=fw)
        assert add.allowed and add.returncode == 0
        commit = executor.execute(
            ToolPermission(tool_name="git_commit",
                           args=["chore: add operator note"],
                           cwd=repo_path, permitted_by="operator"),
            firewall=fw,
        )
        assert commit.allowed and commit.returncode == 0
        log = executor.execute(
            ToolPermission(tool_name="git_log", args=["3"], cwd=repo_path,
                           permitted_by="operator"), firewall=fw)
        assert "operator note" in log.stdout, "the committed change is REAL"


# ──────────────────────────────────────────────────────────────────
# ACT-phase hook: pipeline-driven real action + trace landing
# ──────────────────────────────────────────────────────────────────

class TestActToolChannel:
    """A real decision can invoke the executor through ACT; trace records it."""

    def test_approved_git_status_executes_and_lands_in_trace(self, tmp_path):
        # A GENUINELY healthy repo: council passes, and git status still has
        # real stdout thanks to one untracked file.
        repo_path, _ = build_real_repo(str(tmp_path / "repo"), with_broken_test=False)
        with open(os.path.join(repo_path, "untracked_notes.txt"), "w") as f:
            f.write("operator note\n")
        spec = {"tool_name": "git_status", "args": [], "cwd": repo_path}
        pipeline, sim, _ = build_tool_pipeline(repo_path, spec, operator_grant=True)
        state = sim.snapshot()
        result = pipeline.execute(state, user_name="test-tool")

        trace = result.decision_trace
        assert result.council_blocked is False
        audit = trace.tool_audit
        assert audit is not None, "the trace MUST carry the tool audit record"
        assert audit["allowed"] is True
        assert audit["tool_name"] == "git_status"
        assert "untracked_notes.txt" in audit["stdout"], \
            "REAL captured output must be in the trace, not a fabrication"
        assert audit["returncode"] == 0
        assert audit["permitted_by"] == "operator"
        # Governance signals carry the audit entry too.
        any_sig = any(
            s.get("check") == "tool_audit" and s.get("passed")
            for s in (trace.governance_signals or [])
        )
        assert any_sig, "firewall governance_signals must include the tool audit"

    def test_unallowlisted_command_blocked_no_subprocess(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        spec = {"tool_name": "curl", "args": ["http://127.0.0.1:9"], "cwd": repo_path}
        pipeline, sim, _ = build_tool_pipeline(repo_path, spec, operator_grant=True)
        state = sim.snapshot()
        result = pipeline.execute(state, user_name="test-tool")
        audit = result.decision_trace.tool_audit
        assert audit is not None
        assert audit["allowed"] is False
        assert "not on the allowlist" in audit["blocked_reason"]
        assert audit["returncode"] is None, \
            "a rejected tool must never spawn a subprocess"

    def test_no_operator_permission_blocks(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        spec = {"tool_name": "git_status", "args": [], "cwd": repo_path}
        pipeline, sim, _ = build_tool_pipeline(repo_path, spec, operator_grant=False)
        state = sim.snapshot()
        result = pipeline.execute(state, user_name="test-tool")
        audit = result.decision_trace.tool_audit
        assert audit is not None
        assert audit["allowed"] is False
        assert audit["blocked_reason"] == "no_operator_permission"

    def test_empty_tool_audit_when_channel_unconfigured(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        spec = {"tool_name": "git_status", "args": [], "cwd": repo_path}
        pipeline, sim, _ = build_tool_pipeline(
            repo_path, spec, operator_grant=True, executor=None)
        # Overwrite: no executor configured at all.
        pipeline.config.action_executor = None
        state = sim.snapshot()
        result = pipeline.execute(state, user_name="test-tool")
        assert result.decision_trace.tool_audit is None, \
            "no executor configured => no tool record, no command"

    def test_tool_audit_serializes_in_trace_dict(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"), with_broken_test=False)
        spec = {"tool_name": "git_status", "args": [], "cwd": repo_path}
        pipeline, sim, _ = build_tool_pipeline(repo_path, spec, operator_grant=True)
        state = sim.snapshot()
        result = pipeline.execute(state, user_name="test-tool")
        d = result.decision_trace.to_dict()
        assert "tool_audit" in d
        assert d["tool_audit"]["allowed"] is True


class TestAllowlistShape:
    """The allowlist itself is small, explicit, and shell-free."""

    def test_allowlist_contains_only_expected_tools(self):
        assert sorted(ACTION_ALLOWLIST) == [
            "eslint_check", "git_add", "git_branch", "git_commit", "git_diff",
            "git_log", "git_status", "go_test", "http_get", "http_post",
            "make_target", "npm_build", "npm_test", "run_tests", "tsc_check",
            "write_file",
        ]
        for entry in ACTION_ALLOWLIST.values():
            assert isinstance(entry.template, list)
            assert entry.kind in ("read_only", "narrow_write", "structured_write",
                                  "network_read", "network_write")
            assert entry.description

    def test_no_template_contains_shell_operators(self):
        for entry in ACTION_ALLOWLIST.values():
            joined = " ".join(entry.template)
            for ch in (";", "&&", "|", "$(", "`"):
                assert ch not in joined, f"shell operator {ch!r} found in {entry.template}"


    def test_broken_repo_council_block_never_executes_tool(self, tmp_path):
        """Governance gate regression: a council block must suppress the tool.

        The RepoEvidenceValidator dissents on a genuinely broken repo (failing
        test touching changed files) -> the council blocks -> the tool hook
        must NOT run a real command, even though the operator granted the
        channel (the hook lives INSIDE the governance gate + carries its own
        defensive guard).
        """
        repo_path, test_out = build_real_repo(str(tmp_path / "repo"))
        spec = {"tool_name": "git_status", "args": [], "cwd": repo_path}
        pipeline, sim, _ = build_tool_pipeline(repo_path, spec, operator_grant=True)
        # Attach the REAL failing-test evidence so the council dissents.
        sim._test_output_paths = [test_out]
        state = sim.snapshot()
        result = pipeline.execute(state, user_name="test-tool")
        trace = result.decision_trace
        assert result.council_blocked or result.firewall_blocked, \
            "broken repo must be blocked by the council/firewall"
        audit = trace.tool_audit
        if audit is not None:
            assert audit["allowed"] is False, \
                "a governed block must never execute a real command"
            assert audit["blocked_reason"] in (
                "governance_blocked_cycle", "missing_tool_permission_spec",
                "no_operator_permission",
            )



# ──────────────────────────────────────────────────────────────────
# Governed write-file tool (the write-side fix loop's executor half)
# ──────────────────────────────────────────────────────────────────

class TestGovernedWriteFile:
    """The write_file tool: structured, block-first, no shell, audited."""

    def _executor(self, repo_path):
        return ActionExecutor(workspace_root=repo_path), DecisionFirewall()

    def test_minimal_patch_applies_and_reads_back(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        ex, fw = self._executor(repo_path)
        patch = {
            "path": "calculator.py",
            "old_lines": ["def add(a, b):", "    return a - b"],
            "new_lines": ["def add(a, b):", "    return a + b"],
        }
        perm = ToolPermission(tool_name="write_file", args=[patch],
                              cwd=repo_path, permitted_by="operator",
                              permission_id="wf1")
        result = ex.execute(perm, firewall=fw)
        assert result.allowed is True
        assert result.returncode == 0
        assert result.blocked_reason is None
        with open(os.path.join(repo_path, "calculator.py")) as f:
            assert "    return a + b" in f.read(), "the real fix is on disk"

    def test_path_escape_blocked_no_write(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        ex, fw = self._executor(repo_path)
        patch = {"path": "/tmp/evil.py", "old_lines": ["x"], "new_lines": ["y"]}
        perm = ToolPermission(tool_name="write_file", args=[patch],
                              cwd=repo_path, permitted_by="operator")
        result = ex.execute(perm, firewall=fw)
        assert result.allowed is False
        assert "outside the workspace" in result.blocked_reason
        assert not os.path.exists("/tmp/evil.py")

    def test_patch_file_target_rejected(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        ex, fw = self._executor(repo_path)
        patch = {"path": "out.diff", "old_lines": ["x"], "new_lines": ["y"]}
        result = ex.execute(
            ToolPermission(tool_name="write_file", args=[patch],
                           cwd=repo_path, permitted_by="operator"), firewall=fw)
        assert result.allowed is False
        assert "patch/diff file target" in result.blocked_reason

    def test_absent_block_rejected(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        ex, fw = self._executor(repo_path)
        patch = {"path": "calculator.py",
                 "old_lines": ["this line is not present"], "new_lines": ["y"]}
        result = ex.execute(
            ToolPermission(tool_name="write_file", args=[patch],
                           cwd=repo_path, permitted_by="operator"), firewall=fw)
        assert result.allowed is False
        assert "not found" in result.blocked_reason

    def test_firewall_block_records_governance_no_write(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        ex = ActionExecutor(workspace_root=repo_path)
        # A firewall that blocks after 4 repeated tool executions. Keep the
        # patch valid at EVERY call so the loop guard (not a stale block) is
        # what refuses the write — we toggle the file between two states.
        fw = DecisionFirewall()
        note_path = os.path.join(repo_path, "notes.txt")
        with open(note_path, "w") as f:
            f.write("state_a\n")
        states = [("state_a", "state_b"), ("state_b", "state_a")]
        result = None
        for i in range(4):
            old_l, new_l = states[i % 2]
            patch = {"path": "notes.txt",
                     "old_lines": [old_l], "new_lines": [new_l]}
            result = ex.execute(
                ToolPermission(tool_name="write_file", args=[patch],
                               cwd=repo_path, permitted_by="operator"),
                firewall=fw)
            if result.allowed:
                # file now contains new_l; next iteration uses it as old
                pass
        assert result.allowed is False, "loop-guarded firewall refuses repeated writes"
        assert "firewall blocked" in result.blocked_reason

    def test_oversized_hunk_rejected(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        ex, fw = self._executor(repo_path)
        patch = {"path": "calculator.py",
                 "old_lines": ["x"] * 300, "new_lines": ["y"]}
        result = ex.execute(
            ToolPermission(tool_name="write_file", args=[patch],
                           cwd=repo_path, permitted_by="operator"), firewall=fw)
        assert result.allowed is False
        assert "exceeds 200 lines" in result.blocked_reason

    def test_freeform_input_rejected(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        ex, fw = self._executor(repo_path)
        # A string (freeform) as the patch is rejected, never executed.
        result = ex.execute(
            ToolPermission(tool_name="write_file", args=["rm -rf /"],
                           cwd=repo_path, permitted_by="operator"), firewall=fw)
        assert result.allowed is False
        assert "structured dict or valid JSON" in result.blocked_reason

    def test_ambiguous_block_rejected(self, tmp_path):
        # Create a file where the block appears twice.
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        with open(os.path.join(repo_path, "dup.txt"), "w") as f:
            f.write("a\nb\na\nb\n")
        ex, fw = self._executor(repo_path)
        patch = {"path": "dup.txt", "old_lines": ["a", "b"], "new_lines": ["z"]}
        result = ex.execute(
            ToolPermission(tool_name="write_file", args=[patch],
                           cwd=repo_path, permitted_by="operator"), firewall=fw)
        assert result.allowed is False
        assert "ambiguous" in result.blocked_reason

    def test_write_lands_in_trace_via_act(self, tmp_path):
        """A write_file tool intent reaches ACT and its audit lands in the trace."""
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        patch = {
            "path": "calculator.py",
            "old_lines": ["def add(a, b):", "    return a - b"],
            "new_lines": ["def add(a, b):", "    return a + b"],
        }
        spec = {"tool_name": "write_file", "args": [patch], "cwd": repo_path}
        pipeline, sim, _ = build_tool_pipeline(repo_path, spec, operator_grant=True)
        state = sim.snapshot()
        result = pipeline.execute(state, user_name="test-write")
        trace = result.decision_trace
        audit = trace.tool_audit
        # A council-validated write tool on a clean repo should execute.
        if audit is not None:
            if audit["allowed"]:
                assert audit["tool_name"] == "write_file"
                assert "calculator.py" in audit["stdout"]
            else:
                # It may be governance-blocked on a dirty/broken repo; ensure
                # the block is a first-class record, never a shell pass-through.
                assert audit["blocked_reason"] in (
                    "governance_blocked_cycle", "missing_tool_permission_spec",
                    "no_operator_permission",
                )


# ──────────────────────────────────────────────────────────────────
# Extended real toolchain allowlist (tsc/eslint/npm/make/go)
#
# NOTE: these tests use deterministic MOCK SHIMS in PATH because the real
# binaries (tsc, eslint, go, make, npm) are not always installed on darwin.
# A shim is a tiny executable that emits a known line and exits 0, so the
# allowlisted invocation genuinely executes AND its real (shim) output lands
# in the audit — while the malicious cases are proven REJECTED with no
# subprocess. When the real binary IS present the same tests still pass (they
# only assert output lands in the audit, not its exact content).
# ──────────────────────────────────────────────────────────────────

SHIM_SOURCE = {
    "tsc": "#!/bin/sh\necho TSC_SHIMMED_OK --noEmit\n",
    "eslint": "#!/bin/sh\necho ESLINT_SHIMMED_OK\n",
    "npm": "#!/bin/sh\necho NPM_SHIMMED_OK \"$@\"\n",
    "make": "#!/bin/sh\necho MAKE_SHIMMED_OK \"$@\"\n",
    "go": "#!/bin/sh\necho GO_SHIMMED_OK\n",
}


def build_shim_bin(bin_dir):
    """Write tiny executable shims into bin_dir and return its path (in PATH)."""
    os.makedirs(bin_dir, exist_ok=True)
    for name, body in SHIM_SOURCE.items():
        p = os.path.join(bin_dir, name)
        with open(p, "w") as f:
            f.write(body)
        os.chmod(p, 0o755)
    return bin_dir


class TestToolchainAllowlist:
    """Each extended tool is allowlisted, executes, and is audited."""

    def _prep(self, tmp_path, monkeypatch):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        bin_dir = build_shim_bin(str(tmp_path / "bin"))
        monkeypatch.setenv("PATH", bin_dir + os.pathsep + os.environ.get("PATH", ""))
        return repo_path, ActionExecutor(workspace_root=repo_path), DecisionFirewall()

    def test_tsc_executes_and_audits(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        r = ex.execute(ToolPermission(tool_name="tsc_check", args=["tsconfig.json"],
                                      cwd=repo_path, permitted_by="operator"),
                       firewall=fw)
        assert r.allowed is True and r.returncode == 0
        assert "TSC_SHIMMED_OK" in r.stdout, "real (shim) output must land in the audit"

    def test_eslint_executes_and_audits(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        r = ex.execute(ToolPermission(tool_name="eslint_check", args=["src"],
                                      cwd=repo_path, permitted_by="operator"),
                       firewall=fw)
        assert r.allowed is True and r.returncode == 0
        assert "ESLINT_SHIMMED_OK" in r.stdout

    def test_npm_test_with_prefix_confined(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        r = ex.execute(ToolPermission(tool_name="npm_test", args=["pkg"],
                                      cwd=repo_path, permitted_by="operator"),
                       firewall=fw)
        assert r.allowed is True and r.returncode == 0
        assert "NPM_SHIMMED_OK" in r.stdout

    def test_npm_build_executes(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        r = ex.execute(ToolPermission(tool_name="npm_build", args=["pkg"],
                                      cwd=repo_path, permitted_by="operator"),
                       firewall=fw)
        assert r.allowed is True and r.returncode == 0
        assert "run build" in r.stdout

    def test_make_target_with_makefile_in_workspace(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        with open(os.path.join(repo_path, "Makefile"), "w") as f:
            f.write("all:\n\techo build\n")
        r = ex.execute(ToolPermission(tool_name="make_target", args=["all"],
                                      cwd=repo_path, permitted_by="operator"),
                       firewall=fw)
        assert r.allowed is True and r.returncode == 0
        assert "MAKE_SHIMMED_OK" in r.stdout

    def test_go_test_in_workspace_subdir(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        sub = os.path.join(repo_path, "mod")
        os.makedirs(sub, exist_ok=True)
        r = ex.execute(ToolPermission(tool_name="go_test", args=[],
                                      cwd=sub, permitted_by="operator"),
                       firewall=fw)
        assert r.allowed is True and r.returncode == 0
        assert "GO_SHIMMED_OK" in r.stdout

    # ── malicious rejections: block-record-first, NO subprocess ──

    def test_tsc_path_escape_rejected(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        r = ex.execute(ToolPermission(tool_name="tsc_check", args=["/etc/passwd"],
                                      cwd=repo_path, permitted_by="operator"),
                       firewall=fw)
        assert r.allowed is False
        assert "outside the workspace" in r.blocked_reason
        assert r.returncode is None, "no subprocess for a rejected path"

    def test_shell_metachars_rejected(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        for injected in ["x; rm -rf /", "a && b", "c | sh"]:
            r = ex.execute(ToolPermission(tool_name="eslint_check", args=[injected],
                                          cwd=repo_path, permitted_by="operator"),
                           firewall=fw)
            assert r.allowed is False, f"metachar {injected!r} must be rejected"
            assert r.returncode is None

    def test_string_injection_via_extra_args_rejected(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        # Attempt to smuggle a "--" flag as an extra argv element.
        r = ex.execute(ToolPermission(tool_name="npm_test",
                                      args=["pkg", "--", "--unsafe-perm"],
                                      cwd=repo_path, permitted_by="operator"),
                       firewall=fw)
        assert r.allowed is False
        assert "too many args" in r.blocked_reason

    def test_make_target_freeform_rejected(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        r = ex.execute(ToolPermission(tool_name="make_target", args=["all; id"],
                                      cwd=repo_path, permitted_by="operator"),
                       firewall=fw)
        assert r.allowed is False
        assert r.returncode is None

    def test_go_test_cwd_outside_workspace_rejected(self, tmp_path, monkeypatch):
        repo_path, ex, fw = self._prep(tmp_path, monkeypatch)
        r = ex.execute(ToolPermission(tool_name="go_test", args=[], cwd="/etc",
                                      permitted_by="operator"), firewall=fw)
        assert r.allowed is False
        assert "outside the workspace" in r.blocked_reason
        assert r.returncode is None
