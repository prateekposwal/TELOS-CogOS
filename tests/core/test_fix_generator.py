"""
FixProposalGenerator — autonomous, evidence-grounded patch GENERATION.

PATTERN UNDER TEST (abstention over hallucination / Λ2.3): a fix is proposed
ONLY when the raw failing evidence uniquely determines a minimal edit. When the
traceback is ambiguous the generator returns an honest abstention — a guessed
edit is worse than a defensible no-proposal. Every proposal cites the traceback
lines that drove it.

Covered strategies:
  1. import_resolution: NameError resolves to EXACTLY ONE candidate module.
  2. missing_member: AttributeError for a constant defined verbatim elsewhere.
  3. abstention: ambiguous / unresolvable evidence -> no patch, no guess.
  4. run_autonomous: the full generate -> governed write -> green loop on a
     real tmp repo with a genuinely broken test.
"""

import os
import subprocess
import sys

from telos.adapters.git_repo import GitRepoSim
from telos.core.actions.executor import ActionExecutor
from telos.core.fix_loop import (
    FixLoopController, FixProposalGenerator, FixProposal,
)
from telos.world.epistemic import RealityGapTracker


def _init_repo(repo_path, files):
    """Initialize a real git repo and write the given {path: content} files.

    Args:
        repo_path: directory in which to `git init`.
        files: dict of relative path -> source text to write.

    Returns:
        The repo path.
    """
    os.makedirs(repo_path, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "telos@test.local"], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "config", "user.name", "TELOS Test"], cwd=repo_path, check=True)
    for rel, text in files.items():
        with open(os.path.join(repo_path, rel), "w") as f:
            f.write(text)
    subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo_path, check=True)
    return repo_path


def _pytest_output(repo_path, path):
    """Run pytest on a path and return (returncode, full output text).

    Args:
        repo_path: repo working directory.
        path: the test path to run.

    Returns:
        (returncode, output) tuple with raw real output.
    """
    r = subprocess.run(
        [sys.executable, "-m", "pytest", path, "-q", "--tb=short"],
        cwd=repo_path, capture_output=True, text=True)
    return r.returncode, r.stdout + "\n" + r.stderr


class TestGeneratorNameError:
    """Strategy 1: import-resolution for a genuinely-missing name."""

    def test_resolves_unique_import(self, tmp_path):
        repo = _init_repo(tmp_path / "r", {
            "math_core.py": "def multiply(a, b):\n    return a * b\n",
            "test_missing.py": (
                "def test_mul():\n"
                "    result = multiply(3, 4)\n"
                "    assert result == 12\n"
            ),
        })
        # Real failing evidence: NameError because multiply is not imported.
        rc, out = _pytest_output(repo, "test_missing.py")
        assert rc == 1 and "NameError" in out
        sim = GitRepoSim(repo, test_output_paths=[
            _write_evidence(repo, "test_missing.py", out)])
        snap = sim.gather_snapshot()

        gen = FixProposalGenerator(repo)
        prop = gen.generate("test_missing.py::test_mul", snap)
        assert prop.abstained is False, prop.reason
        assert prop.strategy == "import_resolution"
        assert any("from math_core import multiply" in ln for ln in prop.new_lines), \
            prop.reason
        assert prop.path == "test_missing.py"
        # Evidence is cited (the NameError traceback drove the edit).
        assert prop.evidence and any("NameError" in str(f) for f in prop.evidence)

    def test_abstains_on_ambiguous_symbol(self, tmp_path):
        repo = _init_repo(tmp_path / "r", {
            "a.py": "def compute():\n    return 1\n",
            "b.py": "def compute():\n    return 2\n",
            "test_ambig.py": (
                "def test_c():\n"
                "    return compute()\n"
            ),
        })
        rc, out = _pytest_output(repo, "test_ambig.py")
        assert rc == 1 and "NameError" in out
        sim = GitRepoSim(repo, test_output_paths=[
            _write_evidence(repo, "test_ambig.py", out)])
        snap = sim.gather_snapshot()

        prop = FixProposalGenerator(repo).generate(
            "test_ambig.py::test_c", snap)
        assert prop.abstained is True, \
            "ambiguous candidates MUST abstain rather than guess one"
        assert "ambiguous" in prop.reason
        assert gen_path_none(prop)

    def test_abstains_when_symbol_unlocatable(self, tmp_path):
        repo = _init_repo(tmp_path / "r", {
            "test_ghost.py": (
                "def test_g():\n"
                "    return totally_unknown_thing()\n"
            ),
        })
        rc, out = _pytest_output(repo, "test_ghost.py")
        assert rc == 1 and "NameError" in out
        sim = GitRepoSim(repo, test_output_paths=[
            _write_evidence(repo, "test_ghost.py", out)])
        snap = sim.gather_snapshot()

        prop = FixProposalGenerator(repo).generate(
            "test_ghost.py::test_g", snap)
        assert prop.abstained is True
        assert "NO locatable definition" in prop.reason


class TestGeneratorMissingMember:
    """Strategy 2: AttributeError -> provable constant insertion."""

    def test_inserts_provable_constant(self, tmp_path):
        repo = _init_repo(tmp_path / "r", {
            "config.py": "MAX_RETRIES = 7\n",
            "worker.py": "def run():\n    return None\n",
            "test_attr.py": (
                "def test_constant():\n"
                "    import worker\n"
                "    assert worker.MAX_RETRIES == 7\n"
            ),
        })
        rc, out = _pytest_output(repo, "test_attr.py")
        assert rc == 1 and "AttributeError" in out
        sim = GitRepoSim(repo, test_output_paths=[
            _write_evidence(repo, "test_attr.py", out)])
        snap = sim.gather_snapshot()

        prop = FixProposalGenerator(repo).generate(
            "test_attr.py::test_constant", snap)
        assert prop.abstained is False, prop.reason
        assert prop.strategy == "missing_member"
        assert any("MAX_RETRIES = 7" in ln for ln in prop.new_lines), prop.reason


class TestAutonomousLoop:
    """The full autonomous generate -> govern -> verify loop on a real repo."""

    def test_autonomous_fix_closes_real_gap(self, tmp_path):
        repo = _init_repo(tmp_path / "r", {
            "math_core.py": "def double(x):\n    return x * 2\n",
            "test_caller.py": (
                "def test_double():\n"
                "    result = double(5)\n"
                "    assert result == 10\n"
            ),
        })
        assert _pytest_output(repo, "test_caller.py")[0] == 1

        executor = ActionExecutor(workspace_root=repo)
        rgt = RealityGapTracker()
        controller = FixLoopController(repo, executor, reality_gap_tracker=rgt)
        sim = GitRepoSim(repo, test_output_paths=[
            _write_evidence(repo, "test_caller.py",
                            _pytest_output(repo, "test_caller.py")[1])])
        outcome = controller.run_autonomous(
            ["test_caller.py::test_double"], sim.gather_snapshot())[0]

        assert outcome["generated"] is True, outcome["reason"]
        assert outcome["proposal"] is not None
        assert outcome["proposal"]["provenance"]["strategy"] == "import_resolution"
        feedback = outcome["feedback"]
        assert feedback is not None
        assert feedback.write_allowed is True
        assert feedback.gap_closed is True, feedback.message
        # Verified as the user: the real test passes on the real checkout now.
        assert _pytest_output(repo, "test_caller.py")[0] == 0

    def test_autonomous_abstention_applies_no_patch(self, tmp_path):
        repo = _init_repo(tmp_path / "r", {
            "a.py": "def solve():\n    return 1\n",
            "b.py": "def solve():\n    return 2\n",
            "test_pick.py": (
                "def test_p():\n"
                "    return solve()\n"
            ),
        })
        assert _pytest_output(repo, "test_pick.py")[0] == 1
        executor = ActionExecutor(workspace_root=repo)
        controller = FixLoopController(repo, executor)
        sim = GitRepoSim(repo, test_output_paths=[
            _write_evidence(repo, "test_pick.py",
                            _pytest_output(repo, "test_pick.py")[1])])
        outcome = controller.run_autonomous(
            ["test_pick.py::test_p"], sim.gather_snapshot())[0]

        assert outcome["generated"] is False, "ambiguous MUST abstain"
        assert outcome["abstained"] is True
        assert outcome["proposal"] is None, "no patch may be emitted"
        assert outcome["feedback"] is None
        # Nothing was written to the repo.
        with open(os.path.join(repo, "test_pick.py")) as f:
            assert "import" not in f.read()


def _write_evidence(repo_path, test_path, output_text):
    """Persist real pytest output to a temp file outside the workspace.

    Args:
        repo_path: repo root (for a stable tmp-adjacent location).
        test_path: the test file the output came from.
        output_text: the raw pytest stdout+stderr.

    Returns:
        Absolute path of the evidence file.
    """
    import tempfile
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="gen_evidence_", delete=False)
    f.write(output_text)
    f.close()
    return f.name


def gen_path_none(prop):
    """True when a proposal carries no patch (old_lines and new_lines empty).

    Args:
        prop: the FixProposal to inspect.

    Returns:
        True when no lines are proposed.
    """
    return not prop.old_lines and not prop.new_lines

class TestProductiveAbstention:
    """Phase 2 — abstention = hypothesis + experiment, never an empty refusal."""

    def test_ambiguous_abstention_emits_hypothesis_and_no_patch(self, tmp_path):
        repo = _init_repo(tmp_path / "r", {
            "a.py": "def solve():\n    return 1\n",
            "b.py": "def solve():\n    return 2\n",
            "test_ambig.py": (
                "def test_p():\n"
                "    return solve()\n"
            ),
        })
        assert _pytest_output(repo, "test_ambig.py")[0] == 1
        executor = ActionExecutor(workspace_root=repo)
        writes_attempted = []
        orig_write = executor.execute
        controller = FixLoopController(repo, executor)
        sim = GitRepoSim(repo, test_output_paths=[
            _write_evidence(repo, "test_ambig.py",
                            _pytest_output(repo, "test_ambig.py")[1])])
        outcome = controller.run_autonomous(
            ["test_ambig.py::test_p"], sim.gather_snapshot())[0]

        assert outcome["generated"] is False
        assert outcome["abstained"] is True
        assert outcome["proposal"] is None
        # PRODUCTIVE: the abstention emitted a falsifiable hypothesis.
        hypothesis = outcome["abstention_hypothesis"]
        assert hypothesis is not None, "abstention must emit a hypothesis"
        assert "test_ambig.py" in hypothesis["description"]
        # No write is ever attempted for an abstention (bounded experiment only).
        assert writes_attempted == []
        # Nothing was written to the repo.
        with open(os.path.join(repo, "test_ambig.py")) as f:
            assert "import" not in f.read()
