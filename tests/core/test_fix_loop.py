"""
FixLoop — the governed write-side fix loop, end-to-end on a REAL tmp repo.

PATTERN UNDER TEST (measured outcome feedback / Λ2.3): a fix is DONE only when
the allowlisted pytest rerun proves the failing test green AND the reality-gap
tracker records the close. The loop routes the fix through perceive -> council
(FixProposalValidator reads REPO_evidence) -> governed write_file -> allowlisted
pytest rerun -> RealityGapTracker feed, with every step a real command/evidence.

Tests build a genuinely broken repo, drive the loop, and assert:
  - the real failing test genuinely fails before the fix;
  - the governed write_file applies and the real rerun passes;
  - FixLoopFeedback.gap_closed is True and recorded in the RealityGapTracker;
  - the bounded iteration ceiling holds.
"""

import os
import subprocess
import pytest

from tests.core.test_git_repo_domain import build_real_repo, run_command
from telos.core.actions.executor import ActionExecutor
from telos.core.fix_loop import (
    FixLoopController, FIX_LOOP_MAX_ITERATIONS, FixProposalValidator,
)
from telos.world.epistemic import RealityGapTracker


def run_pytest_rc(repo_path, path):
    """Run pytest via subprocess and return its returncode.

    Args:
        repo_path: the repository working directory.
        path: the test path to run.

    Returns:
        pytest returncode (0 = all passed).
    """
    return run_command(
        ["python3", "-m", "pytest", path, "-q", "--tb=short"], repo_path).returncode


class TestWriteLoopEndToEnd:
    """The full fixed loop closes a real reality gap."""

    def test_loop_closes_real_gap(self, tmp_path):
        repo_path, test_out = build_real_repo(str(tmp_path / "repo"))

        # 0) The broken test genuinely fails BEFORE any fix.
        assert run_pytest_rc(repo_path, "test_calculator.py") == 1, \
            "the real test must fail before the fix"

        executor = ActionExecutor(workspace_root=repo_path)
        rgt = RealityGapTracker()
        controller = FixLoopController(repo_path, executor, reality_gap_tracker=rgt)

        patch = {
            "path": "calculator.py",
            "old_lines": ["def add(a, b):", "    return a - b"],
            "new_lines": ["def add(a, b):", "    return a + b"],
        }
        fixes = [{"test_id": "test_calculator.py::test_add", "patch": patch}]
        results = controller.run_loop(fixes)

        assert len(results) == 1
        fb = results[0]
        assert fb.write_allowed is True, fb.write_blocked_reason
        assert fb.gap_closed is True, fb.message
        assert fb.rerun_returncode == 0
        # The real test now passes on the real checkout.
        assert run_pytest_rc(repo_path, "test_calculator.py") == 0
        # The reality-gap tracker recorded the model with a closed gap.
        assert rgt.model_fidelity("fix_loop:test_calculator.py::test_add") is not None
        # Every step is audited (write + rerun went through the executor).
        assert controller.history[0].write_allowed
        # The line really changed on disk (verify as the user).
        with open(os.path.join(repo_path, "calculator.py")) as f:
            assert "    return a + b" in f.read()

    def test_blocked_loop_records_honest_failure(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"))
        executor = ActionExecutor(workspace_root=repo_path)
        rgt = RealityGapTracker()
        controller = FixLoopController(repo_path, executor, reality_gap_tracker=rgt)
        # A fix that does NOT actually repair the test (block absent from file):
        patch = {
            "path": "calculator.py",
            "old_lines": ["no such block present at all"],
            "new_lines": ["return a + b"],
        }
        fixes = [{"test_id": "test_calculator.py::test_add", "patch": patch}]
        results = controller.run_loop(fixes)
        fb = results[0]
        # The governed write is REJECTED (no match) -> the loop records an
        # honest OPEN gap, never a fabricated close.
        assert fb.gap_closed is False
        assert run_pytest_rc(repo_path, "test_calculator.py") == 1


class TestFixLoopBounding:
    """The loop's iteration ceiling is hard and honest."""

    def test_loop_respects_max_iterations(self, tmp_path):
        repo_path, _ = build_real_repo(str(tmp_path / "repo"), with_broken_test=False)
        executor = ActionExecutor(workspace_root=repo_path)
        controller = FixLoopController(repo_path, executor)
        fixes = [
            {"test_id": f"t{i}", "patch": {"path": f"f{i}.py",
                                           "old_lines": ["x"], "new_lines": ["y"]}}
            for i in range(FIX_LOOP_MAX_ITERATIONS + 5)
        ]
        results = controller.run_loop(fixes)
        assert len(results) == FIX_LOOP_MAX_ITERATIONS, \
            "the loop must never exceed its configured ceiling"
        assert len(controller.history) == FIX_LOOP_MAX_ITERATIONS


class TestFixProposalValidator:
    """The council advisor reads REPO_evidence and gates the fix."""

    def _facts_for(self, repo_path, test_out):
        from telos.adapters.git_repo import GitRepoSim
        import numpy as np
        sim = GitRepoSim(repo_path, test_output_paths=[test_out] if test_out else [])
        vec = sim.snapshot()
        return sim.get_facts(vec)

    def test_approves_fix_targeting_failing_test(self, tmp_path):
        from telos.world.world import World
        import numpy as np
        repo_path, test_out = build_real_repo(str(tmp_path / "repo"))
        v = FixProposalValidator(expected_test_id="test_calculator.py::test_add")
        from telos.intent_ir import IntentIR
        intent = IntentIR(
            intent_type="execute_tool", confidence=0.9,
            params={"tool_permission": {
                "tool_name": "write_file",
                "args": [{"path": "calculator.py"}]}},
        )
        sig = v.validate(World(state=np.zeros(1)), intent,
                        self._facts_for(repo_path, test_out))
        assert sig.passed is True
        assert "test_add" in sig.reason

    def test_dissents_when_no_failing_test(self, tmp_path):
        from telos.world.world import World
        import numpy as np
        repo_path, _ = build_real_repo(str(tmp_path / "repo"), with_broken_test=False)
        v = FixProposalValidator()
        sig = v.validate(World(state=np.zeros(1)), None, self._facts_for(repo_path, ""))
        assert sig.passed is False
        assert "refusing an unforced write" in sig.reason


class TestIterationLoop:
    """Two broken tests fixed in sequence; bounded ceiling holds (item #3)."""

    def _two_failing_repo(self, repo_path):
        """Real repo with TWO distinct broken modules/tests.

    Args:
        repo_path: the directory in which to init the git repo.
    """
        from tests.core.test_git_repo_domain import run_command
        os.makedirs(repo_path, exist_ok=True)
        run_command(["git", "init", "-q", "-b", "main"], repo_path)
        run_command(["git", "config", "user.email", "telos@t"], repo_path)
        run_command(["git", "config", "user.name", "T"], repo_path)
        with open(os.path.join(repo_path, "math1.py"), "w") as f:
            f.write("def sub(a, b):\n    return a - b\n")
        with open(os.path.join(repo_path, "math2.py"), "w") as f:
            f.write("def mul(a, b):\n    return a * b\n")
        run_command(["git", "add", "."], repo_path)
        run_command(["git", "commit", "-qm", "init math"], repo_path)
        # Break BOTH modules and add BOTH failing tests.
        with open(os.path.join(repo_path, "math1.py"), "w") as f:
            f.write("def sub(a, b):\n    return a + b\n")
        with open(os.path.join(repo_path, "math2.py"), "w") as f:
            f.write("def mul(a, b):\n    return a / b\n")
        with open(os.path.join(repo_path, "test_math1.py"), "w") as f:
            f.write("def test_sub():\n    from math1 import sub\n    assert sub(5, 3) == 2\n")
        with open(os.path.join(repo_path, "test_math2.py"), "w") as f:
            f.write("def test_mul():\n    from math2 import mul\n    assert mul(4, 3) == 12\n")
        run_command(["git", "add", "."], repo_path)
        return repo_path

    def test_two_fixes_in_sequence(self, tmp_path):
        repo_path = self._two_failing_repo(str(tmp_path / "repo"))
        assert run_pytest_rc(repo_path, "test_math1.py") == 1
        assert run_pytest_rc(repo_path, "test_math2.py") == 1

        executor = ActionExecutor(workspace_root=repo_path)
        controller = FixLoopController(repo_path, executor)
        fixes = [
            {"test_id": "test_math1.py::test_sub",
             "patch": {"path": "math1.py",
                       "old_lines": ["def sub(a, b):", "    return a + b"],
                       "new_lines": ["def sub(a, b):", "    return a - b"]}},
            {"test_id": "test_math2.py::test_mul",
             "patch": {"path": "math2.py",
                       "old_lines": ["def mul(a, b):", "    return a / b"],
                       "new_lines": ["def mul(a, b):", "    return a * b"]}},
        ]
        results = controller.run_loop(fixes)
        assert len(results) == 2
        for fb in results:
            assert fb.write_allowed is True, fb.write_blocked_reason
            assert fb.gap_closed is True, fb.message
        # Both real tests now pass on the real checkout (verify as the user).
        assert run_pytest_rc(repo_path, "test_math1.py") == 0
        assert run_pytest_rc(repo_path, "test_math2.py") == 0
        # The loop recorded both iterations.
        assert len(controller.history) == 2
        assert controller.history[0].target_test == "test_math1.py::test_sub"
        assert controller.history[1].target_test == "test_math2.py::test_mul"
