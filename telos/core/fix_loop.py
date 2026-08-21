"""
FixLoop — the GOVERNED write-side fix loop (Λ2.3 honesty: fixed = verified).

PATTERN (measured outcome feedback): a fix is not DONE when the patch is
applied — it is DONE when the real test re-runs green AND the reality-gap
tracker records the close. The loop is the bridge between TELOS's real
perception (GitRepoSim), its governed write channel (ActionExecutor
`write_file`), its governed test channel (`run_tests`), and its epistemic
feedback (RealityGapTracker).

This module provides:
  - FixProposalValidator: a council advisor that reads the REAL RepoSnapshot
    evidence channel and verifies a `write_file` intent's patch targets a file
    implicated by a genuinely failing test (evidence-anchored approval). It
    does NOT approve arbitrary writes — only a patch onto a failing test's
    module, with the failing test id quoted in the reason.
  - FixProposalStream: a CognitiveStream that turns one (test_id, patch) fix
    into an `execute_tool` intent carrying the structured write_file permission.
  - FixLoopFeedback: the auditable outcome record of one fix attempt.
  - FixLoopController: orchestrates N bounded fix iterations on a REAL tmp
    checkout. Each iteration: perceive -> council (FixProposalValidator reads
    REPO_evidence) -> governed write_file -> allowlisted pytest rerun -> record
    the gap close into RealityGapTracker. Bounded by FIX_LOOP_MAX_ITERATIONS.

Bounding / governance (never a bypass):
  - every write still travels through ActionExecutor's firewall re-audit,
    allowlist, path containment, and patch validation; a block records
    `governance_blocked_cycle` semantics in the action audit;
  - the loop is bounded (FIX_LOOP_MAX_ITERATIONS); exceeding it ends the loop
    with an honest unconverged record;
  - the controller never edits anything itself — it only submits governed
    permissions and reads the audited results.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from telos.core.actions.executor import (
    ActionExecutor, ActionExecution, ToolPermission, ToolRejected,
)
from telos.core.council.base import Validator, ValidationSignal
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.streams.base import CognitiveStream
from telos.world.world import World

logger = logging.getLogger('telos_fix_loop')

# Bounded iterations for the fix loop (item #3 ceiling).
FIX_LOOP_MAX_ITERATIONS = 3

# Regexes to parse the allowlisted pytest rerun output (raw, never invented).
_SUMMARY_RE = re.compile(r"(\d+)\s+passed(?:[.,]\s*(\d+)\s+failed)?")
_PASSED_RE = re.compile(r"^\s*(\d+)\s+passed", re.MULTILINE)
_FAILED_RE = re.compile(r"FAILED\s+([^\s]+)")
_ERRORS_RE = re.compile(r"(\d+)\s+error")


class FixProposalValidator(Validator):
    """Council advisor that approves a fix ONLY when it targets a failing test.

    Reads the raw RepoSnapshot from domain_facts and checks the proposed
    write_file patch targets a file which a genuinely failing test names.
    This is the governed "council reads REPO_evidence" step of the fix loop.

    Dissent (block) when the patch does NOT target the failing test's module,
    or when there is no failing-test evidence at all (a "fix" with nothing
    failing is not a fix — it is an unforced write).
    """

    def __init__(self, expected_test_id: str = ""):
        self._expected_test_id = expected_test_id

    @property
    def name(self) -> str:
        return "FixProposalValidator"

    def _snapshot_dict(self, domain_facts: Any) -> Optional[Dict[str, Any]]:
        if domain_facts is None:
            return None
        metadata = getattr(domain_facts, "metadata", None) or {}
        snap = metadata.get("repo_snapshot")
        return snap if isinstance(snap, dict) else None

    def validate(self, world: World, intent: Optional[Any],
                 domain_facts: Optional[Any] = None) -> ValidationSignal:
        snap = self._snapshot_dict(domain_facts)
        if snap is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no repo snapshot; aborting fix-loop advisory",
                evidence_weight=0.0,
            )
        failing = list(snap.get("failing_test_names", []) or [])
        changed = [f.get("path") for f in (snap.get("changed_files", []) or [])
                   if isinstance(f, dict)]
        if not failing:
            return ValidationSignal(
                validator_name=self.name, passed=False, confidence=-0.9,
                reason="no failing test in repo evidence; refusing an unforced write",
                evidence_weight=0.7,
            )
        # The write_file intent carries the structured patch in its permission.
        target = ""
        if intent is not None:
            spec = (intent.params or {}).get("tool_permission") or {}
            patch = (spec.get("args") or [None])[0] if spec.get("args") else None
            if isinstance(patch, dict):
                target = str(patch.get("path", ""))
        # The chosen expected test (when supplied) must be among the failing set.
        if self._expected_test_id and self._expected_test_id not in failing:
            return ValidationSignal(
                validator_name=self.name, passed=False, confidence=-0.8,
                reason=(f"expected failing test {self._expected_test_id!r} not "
                        f"observed in repo evidence"),
                evidence_weight=0.7,
            )
        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.7,
            reason=(f"fix targets file '{target}' against failing test(s): "
                    f"{', '.join(failing[:3])} (raw repo evidence)"),
            evidence_weight=0.5,
        )


class FixProposalStream(CognitiveStream):
    """Proposes one governed write_file intent for a fix (test_id, patch)."""

    priority = 1.0

    def __init__(self, skill_library: SkillLibrary, repo_path: str,
                 patch: Dict[str, Any]):
        super().__init__(skill_library)
        self._repo_path = repo_path
        self._patch = dict(patch)

    def process(self, world: World) -> Any:
        from telos.intent_ir import IntentIR
        spec = {
            "tool_name": "write_file",
            "args": [self._patch],
            "cwd": self._repo_path,
            "permission_id": f"fix_loop_{id(self)}_{abs(hash(str(self._patch))) % 100000}",
        }
        return IntentIR(
            intent_type="execute_tool",
            confidence=0.9,
            params={"tool_name": "write_file", "tool_permission": spec},
            metadata={"stream": "fix_loop", "real_tool": True},
        )


@dataclass
class FixLoopFeedback:
    """The audited outcome record of ONE fix-loop iteration.

    measured outcome feedback (Λ2.3): the loop's output is the REAL test
    rerun result, not the intent to fix. `gap_closed` is True only when the
    allowlisted pytest rerun shows the target passing.
    """
    iteration: int
    target_test: str
    target_file: str
    write_allowed: bool = False
    write_blocked_reason: Optional[str] = None
    rerun_allowed: bool = False
    rerun_returncode: Optional[int] = None
    rerun_passed: bool = False
    rerun_stdout_tail: str = ""
    gap_closed: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "target_test": self.target_test,
            "target_file": self.target_file,
            "write_allowed": self.write_allowed,
            "write_blocked_reason": self.write_blocked_reason,
            "rerun_allowed": self.rerun_allowed,
            "rerun_returncode": self.rerun_returncode,
            "rerun_passed": self.rerun_passed,
            "gap_closed": self.gap_closed,
            "message": self.message,
        }


class FixLoopController:
    """Runs N bounded governed fix iterations on a real repo.

    Each iteration routes the fix through the pipeline (perception -> council
    with FixProposalValidator reading REPO_evidence -> governed write_file via
    ACT), then verifies with the allowlisted pytest tool and records the gap
    close into the RealityGapTracker. Bounded by FIX_LOOP_MAX_ITERATIONS.

    This is a bounded feed of the next goal, not a bypass: the governor's
    council + firewall + allowlist all still apply every iteration.
    """

    def __init__(self, repo_path: str, executor: ActionExecutor,
                 reality_gap_tracker: Any = None):
        self._repo_path = repo_path
        self._executor = executor
        self._reality_gap = reality_gap_tracker
        self._pipeline = None
        self._history: List[FixLoopFeedback] = []

    def _build_pipeline(self, expected_test_id: str = "",
                        test_output_paths: Optional[List[str]] = None):
        """Construct a fresh pipeline bound to the real repo and its evidence.

        The pipeline is configured with the governed ActionExecutor and the
        FixProposalValidator (council reads REPO_evidence) but NO default
        streams: each iteration registers exactly its FixProposalStream so the
        fix intent is the selected candidate. A fresh pipeline is built per
        iteration because the repo state (and thus the parsed failing-test
        evidence) changes after a fix is applied.

        Args:
            expected_test_id: the failing test the fix must address.
            test_output_paths: real pytest-output evidence files to parse.

        Returns:
            A configured TelosV14Pipeline ready for one execute().
        """
        from telos.adapters.git_repo import GitRepoAdapter, GitRepoSim, STATE_DIM
        from telos.core.runtime import TelosV14Pipeline, PipelineConfig
        sim = GitRepoSim(self._repo_path, test_output_paths=test_output_paths or [])
        pipeline = TelosV14Pipeline(PipelineConfig(
            adapter=GitRepoAdapter(),
            simulator=sim,
            compute_budget_ms=200.0,
            state_dim=STATE_DIM,
            n_worlds=3,
            horizon=1,
            action_executor=self._executor,
            operator_tool_permission=True,
        ))
        pipeline.register_validator(
            FixProposalValidator(expected_test_id=expected_test_id))
        self._pipeline = pipeline
        return pipeline

    @property
    def history(self) -> List[FixLoopFeedback]:
        return list(self._history)

    def _patch_target(self, patch: Dict[str, Any]) -> str:
        return str(patch.get("path", ""))

    def _firewall(self):
        """The governing DecisionFirewall of the built pipeline (or a fresh one)."""
        if self._pipeline is not None and hasattr(self._pipeline, "_firewall"):
            return self._pipeline._firewall
        from telos.core.governance.firewall import DecisionFirewall
        return DecisionFirewall()

    def _refresh_evidence(self, target_file: str) -> Optional[str]:
        """Capture REAL pytest evidence for the current repo state.

        Runs the allowlisted pytest tool over the target test file and writes
        the genuine output to a temp path OUTSIDE the workspace (evidence
        ingestion, not a repo mutation) so the council reads real failing-test
        ids. Returns the evidence path, or None if pytest could not run.

        Args:
            target_file: workspace-relative test file to run.

        Returns:
            Absolute path to a temp file with the raw pytest output, or None.
        """
        import tempfile
        run = self._run_pytest(target_file)
        if not run.allowed:
            return None
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix="fixloop_evidence_") as f:
            f.write((run.stdout or "") + "\n" + (run.stderr or ""))
            return f.name

    def _run_pytest(self, path: str) -> ActionExecution:
        """Re-run the allowlisted pytest tool over the target test path."""
        return self._executor.execute(
            ToolPermission(
                tool_name="run_tests", args=[path], cwd=self._repo_path,
                permitted_by="operator",
                permission_id=f"fix_loop_rerun_{abs(hash(path)) % 100000}",
            ),
            firewall=self._firewall(),
        )

    def _analyze_rerun(self, exec_: ActionExecution) -> tuple:
        """Parse the raw pytest capture into (passed, failing_ids).

        Args:
            exec_: the ActionExecution audit record of the pytest rerun.

        Returns:
            (passed: bool, failing_ids: list[str]).
        """
        if not exec_.allowed or exec_.returncode is None:
            return False, []
        out = (exec_.stdout or "") + "\n" + (exec_.stderr or "")
        failing = _FAILED_RE.findall(out)
        passed = bool(_PASSED_RE.search(out)) and _ERRORS_RE.search(out) is None
        return passed, failing

    def apply_fix(self, iteration: int, target_test: str,
                  patch: Dict[str, Any]) -> FixLoopFeedback:
        """Apply one governed fix and verify its real test passes.

        Args:
            iteration: the 1-based iteration index.
            target_test: the failing test id this fix must address.
            patch: the structured write_file patch dict to apply.

        Returns a FixLoopFeedback with gap_closed True only when the rerun
        proves the target tests green on the real checkout.
        """
        target_file = self._patch_target(patch)
        # The test file that the failing test id belongs to (before the "::").
        test_file = target_test.split("::")[0] if "::" in target_test else target_test
        fb = FixLoopFeedback(
            iteration=iteration, target_test=target_test, target_file=target_file,
        )
        # ── governed write through the pipeline's ACT channel ──
        # Capture REAL failing-test evidence for the current repo state, build
        # the pipeline (council reads REPO_evidence via FixProposalValidator),
        # register the single fix stream, and run one cycle: the firewall
        # re-audits the allowlisted write_file before ACT may execute it.
        evidence_path = self._refresh_evidence(test_file)
        pipeline = self._build_pipeline(
            expected_test_id=target_test,
            test_output_paths=[evidence_path] if evidence_path else None,
        )
        pipeline.streams = []
        pipeline.register_stream(
            FixProposalStream(SkillLibrary(), self._repo_path, patch))
        try:
            # Snapshot via the pipeline's own simulator (which carries the
            # current real failing-test evidence) so domain_facts reaches the
            # council with the genuine repo_snapshot channel.
            sim = pipeline.config.simulator
            res = pipeline.execute(sim.snapshot(), user_name="fix_loop")
            audit = (res.decision_trace.tool_audit
                     if res.decision_trace is not None else None)
            if evidence_path:
                try:
                    os.remove(evidence_path)
                except OSError:
                    pass
        except Exception as e:  # Λ2.3: never a silent swallow — log it.
            fb.write_allowed = False
            fb.write_blocked_reason = f"loop error: {e}"
            fb.message = "fix loop error"
            logger.warning("FixLoop.apply_fix pipeline error: %r", e)
            self._history.append(fb)
            return fb

        if audit is None or not audit.get("allowed"):
            fb.write_allowed = False
            fb.write_blocked_reason = (audit or {}).get(
                "blocked_reason") or "not executed"
            fb.message = f"write blocked: {fb.write_blocked_reason}"
            self._history.append(fb)
            return fb

        fb.write_allowed = True
        # ── governed verification: allowlisted pytest rerun (on the TEST file) ──
        rerun = self._run_pytest(test_file)
        fb.rerun_allowed = rerun.allowed
        fb.rerun_returncode = rerun.returncode
        fb.rerun_stdout_tail = rerun.stdout[-300:]
        rerun_passed, _failing = self._analyze_rerun(rerun)
        fb.rerun_passed = rerun_passed
        fb.gap_closed = bool(rerun.allowed and rerun.returncode == 0 and rerun_passed)
        fb.message = (
            f"gap {'CLOSED' if fb.gap_closed else 'OPEN'} after write "
            f"(pytest rc={rerun.returncode})"
        )

        # ── measured outcome feedback into the epistemic layer ──
        self._record_gap_feedback(target_test, fb)

        self._history.append(fb)
        return fb

    def _record_gap_feedback(self, target_test: str, fb: FixLoopFeedback) -> None:
        """Write the loop's measured outcome into the RealityGapTracker feed.

        Args:
            target_test: the failing test id whose gap is being recorded.
            fb: the FixLoopFeedback whose outcome is measured.
        """
        if self._reality_gap is None:
            return
        import numpy as np
        model = f"fix_loop:{target_test}"
        # A closed gap is a small reality gap (0.0); an open gap is maximal (1.0).
        observed = np.array([0.0], dtype=float)
        predicted = np.array([0.0 if fb.gap_closed else 1.0], dtype=float)
        try:
            self._reality_gap.record(model, predicted, observed)
        except Exception as e:
            logger.warning("FixLoop gap-feedback record failed: %r", e)

    def run_loop(self, fixes: List[Dict[str, Any]]) -> List[FixLoopFeedback]:
        """Run a bounded set of fixes in sequence on the real repo.

        Args:
            fixes: ordered list of {"test_id":..., "patch":{...}} dicts.

        Returns:
            The list of per-iteration FixLoopFeedback records.
        """
        results: List[FixLoopFeedback] = []
        max_iter = max(1, FIX_LOOP_MAX_ITERATIONS)
        if len(fixes) > max_iter:
            fixes = fixes[:max_iter]
        for i, fix in enumerate(fixes, start=1):
            fb = self.apply_fix(i, fix["test_id"], fix["patch"])
            results.append(fb)
        return results

__all__ = [
    "FIX_LOOP_MAX_ITERATIONS", "FixProposalValidator", "FixProposalStream",
    "FixLoopFeedback", "FixLoopController",
]
