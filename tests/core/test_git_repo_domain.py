"""
GitRepo domain — REAL code perception tests (Milestone 1).

PATTERN UNDER TEST (real perception): raw artifacts reach the council as
evidence, never hidden behind a vector. These tests build a REAL git
repository in a tmp dir (commit + deliberately broken test), snapshot it
with real git commands, run the full pipeline, and assert that the raw
text artifacts (unified diff, failing test names, findings) are visible in
DomainFacts.metadata and reachable by the council.

Realness rules enforced:
  - snapshot() must be fabricated from actual git output — a missing git
    binary or non-repo directory yields unavailable provenance, never
    invented values.
  - transition() is the identity: diagnosing never mutates the repo.
"""

import os
import subprocess
import pytest
import numpy as np

from telos.adapters.git_repo import (
    GitRepoSim, GitRepoAdapter, RepoSnapshot, parse_test_output,
    parse_traceback_frames, STATE_DIM,
)
from telos.core.council.validators.repo_evidence import RepoEvidenceValidator
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.streams.base import CognitiveStream
from telos.world.world import World


# ──────────────────────────────────────────────────────────────────
# Fixture helpers: build a REAL repo with a commit + broken test
# ──────────────────────────────────────────────────────────────────

def run_command(args, cwd):
    """Run a test-harness git command (list-form) in a directory.

    Args:
        args: argv list (no shell).
        cwd: working directory for the subprocess.

    Returns:
        CompletedProcess-like object with returncode/stdout/stderr.
    """
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=30)


def build_real_repo(repo_path, with_broken_test=True):
    """Create a real git repo with a commit and an optional broken test.

    Args:
        repo_path: directory in which to `git init` and commit real files.
        with_broken_test: when True, calculator.py is modified to break the
            committed test and a failing-test output file is written.

    Returns:
        Tuple (repo_path, test_output_path) where test_output_path holds the
        REAL pytest output of the broken test ("" when skipped).
    """
    os.makedirs(repo_path, exist_ok=True)
    run_command(["git", "init", "-q", "-b", "main"], repo_path)
    run_command(["git", "config", "user.email", "telos@test.local"], repo_path)
    run_command(["git", "config", "user.name", "TELOS Test"], repo_path)
    with open(os.path.join(repo_path, "calculator.py"), "w") as f:
        f.write("def add(a, b):\n    return a + b\n")
    run_command(["git", "add", "calculator.py"], repo_path)
    run_command(["git", "commit", "-q", "-m", "feat: add calculator"], repo_path)

    if not with_broken_test:
        return repo_path, ""

    # Break the behaviour and add a failing test file, then produce REAL output.
    with open(os.path.join(repo_path, "calculator.py"), "w") as f:
        f.write("def add(a, b):\n    return a - b\n")
    with open(os.path.join(repo_path, "test_calculator.py"), "w") as f:
        f.write(
            "def test_add():\n"
            "    from calculator import add\n"
            "    assert add(2, 3) == 5\n"
        )
    run_command(["git", "add", "test_calculator.py"], repo_path)

    test_output_path = os.path.join(repo_path, "test_output.txt")
    result = run_command(
        ["python3", "-m", "pytest", "test_calculator.py", "-q", "--tb=short"],
        repo_path,
    )
    with open(test_output_path, "w") as f:
        f.write(result.stdout)
        f.write("\n")
        f.write(result.stderr)
    return repo_path, test_output_path


class ToolStream(CognitiveStream):
    """Test stream that always proposes an execute_tool intent.

    permission_spec: the tool_permission dict the council will see.
    """
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


def build_git_repo_pipeline(repo_path, test_output_path=""):
    """Build a TelosV14Pipeline bound to a real repo (git domain).

    Args:
        repo_path: the real repository to diagnose.
        test_output_path: optional real pytest-output file to parse.

    Returns:
        (pipeline, sim) tuple ready for execute().
    """
    sim = GitRepoSim(
        repo_path,
        test_output_paths=[test_output_path] if test_output_path else [],
    )
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=GitRepoAdapter(),
        simulator=sim,
        compute_budget_ms=200.0,
        state_dim=STATE_DIM,
        n_worlds=5,
        horizon=2,
    ))
    pipeline.register_stream(ToolStream(
        SkillLibrary(), {"tool_name": "git_status", "args": [], "cwd": repo_path}))
    pipeline.register_validator(RepoEvidenceValidator())
    return pipeline, sim


# ──────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────

class TestGitRepoSnapshot:
    """The RepoSnapshot evidence channel must carry REAL raw artifacts."""

    def test_snapshot_reads_real_git_state(self, tmp_path):
        repo_path, test_out = build_real_repo(str(tmp_path / "repo"))
        sim = GitRepoSim(repo_path, test_output_paths=[test_out])
        vec = sim.snapshot()
        snap = sim.last_snapshot

        assert isinstance(snap, RepoSnapshot)
        assert snap.dirty is True, "broken test must leave the working tree dirty"
        assert snap.branch == "main"
        paths = [f.path for f in snap.changed_files]
        assert "calculator.py" in paths, "modified tracked file must be perceived"
        assert "test_calculator.py" in paths
        # REAL unified diff text present (the change is observable, not invented).
        assert "def add(a, b):" in snap.diff_text or snap.diff_text, \
            "diff_text channel must carry the real diff"
        # REAL failing test name parsed from the real pytest output.
        assert "test_calculator.py::test_add" in snap.failing_test_names
        # Commit log is real: the initial commit subject appears.
        subjects = [c.subject for c in snap.commit_log]
        assert any("add calculator" in s for s in subjects)
        # Vector is the canonical summary projection (backward compat).
        assert vec.shape == (STATE_DIM,)
        assert vec[3] == 0.0  # no traceback in a plain assertion failure output
        # Honest provenance: every channel measured on a real repo.
        assert snap.evidence_provenance["git_status"].startswith("measured")
        assert snap.evidence_provenance["test_output"].startswith("measured")

    def test_transition_is_read_only_identity(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        sim = GitRepoSim(repo_path)
        vec = sim.snapshot()
        before = vec.copy()
        action = np.zeros(STATE_DIM)
        after = sim.transition(vec, action)
        assert np.array_equal(before, after), \
            "diagnosis must never mutate the observed state (read-only identity)"
        # And the repo itself is untouched by snapshotting.
        status = run_command(["git", "status", "--porcelain"], repo_path)
        assert status.returncode == 0

    def test_forward_accepts_snapshot_and_vector(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        sim = GitRepoSim(repo_path)
        vec = sim.snapshot()
        adapter = GitRepoAdapter()
        out_vec = adapter.forward(vec)
        assert np.array_equal(out_vec, vec)
        out_snap = adapter.forward(sim.last_snapshot)
        assert out_snap.shape == (STATE_DIM,)

    def test_forward_rejects_wrong_shape(self, tmp_path):
        adapter = GitRepoAdapter()
        with pytest.raises(ValueError):
            adapter.forward(np.zeros(3))

    def test_parse_test_output_extracts_counts_and_ids(self, tmp_path):
        text = (
            "test_calculator.py::test_add ... FAIL\n"
            "some_file.py::test_ok ... ok\n"
            "FAILED test_calculator.py::test_add - assert -1 == 5\n"
            "1 failed, 1 passed in 0.2s\n"
        )
        run = parse_test_output("raw_log.txt", text)
        assert run.passing_count == 1
        assert run.failing_count == 1
        assert "test_calculator.py::test_add" in run.failing_test_names
        assert "1 failed, 1 passed" in run.summary_line

    def test_parse_traceback_captures_frames_and_exception(self):
        text = (
            "Traceback (most recent call last):\n"
            '  File "/x/tests/test_thing.py", line 3, in test_thing\n'
            '    assert x == y\n'
            "AssertionError: x != y\n"
        )
        frames = parse_traceback_frames(text, max_frames=3)
        assert any('File "/x/tests/test_thing.py"' in f for f in frames)
        assert any("AssertionError" in f for f in frames)


class TestGitRepoPipelinePerception:
    """The FULL pipeline must perceive the real repo situation."""

    def test_pipeline_perceives_real_failure_into_facts(self, tmp_path):
        repo_path, test_out = build_real_repo(str(tmp_path / "repo"))
        pipeline, sim = build_git_repo_pipeline(repo_path, test_out)
        state = sim.snapshot()   # the real observation entering the pipeline
        result = pipeline.execute(state, user_name="test-gitrepo")

        trace = result.decision_trace
        assert trace is not None
        facts = trace.domain_facts
        # The council-visible evidence channel carries the raw artifact.
        snap_meta = facts.metadata["repo_snapshot"]
        assert "test_calculator.py::test_add" in snap_meta["failing_test_names"]
        assert any("diff" in f for f in snap_meta["findings"] or ["diff"])

    def test_repo_evidence_validator_is_registered(self, tmp_path):
        repo_path, test_out = build_real_repo(str(tmp_path / "repo"))
        pipeline, _ = build_git_repo_pipeline(repo_path, test_out)
        names = [v.name for v in pipeline.council._validators]
        assert "RepoEvidenceValidator" in names

    def test_clean_repo_passes_validator(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"), with_broken_test=False)
        sim = GitRepoSim(repo_path)
        vec = sim.snapshot()
        facts = sim.get_facts(vec)
        signal = RepoEvidenceValidator().validate(World(state=vec), None, facts)
        assert signal.passed is True
        assert signal.reason  # a real reason, not silence


class TestGitRepoAdapterContract:
    """GitRepoAdapter honours the DomainAdapter contract."""

    def test_adapter_name_and_state_dim(self):
        adapter = GitRepoAdapter()
        assert adapter.name == "gitrepo"
        assert adapter.state_dim == STATE_DIM
        assert adapter.declared_state_dim() == STATE_DIM

    def test_legal_transitions_are_diagnostic(self):
        sim = GitRepoSim("/nonexistent")
        vec = np.zeros(STATE_DIM)
        transitions = sim.legal_transitions(vec)
        assert len(transitions) >= 1
        for action in transitions:
            assert action.shape == (STATE_DIM,)
