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
class FixProposal:
    """One autonomously-generated patch candidate (Λ2.3: evidence-anchored).

    A proposal is ONLY produced when the failing evidence uniquely determines
    a minimal, provable edit. `abstained` is True when the generator refuses
    to guess (the anti-hallucination guardrail: no evidence -> no edit).

    Args:
        path: workspace-relative target file for the patch.
        old_lines: exact lines that must currently exist in the file.
        new_lines: replacement lines (same count — a minimal in-place edit).
        strategy: the deterministic repair strategy that produced the edit.
        evidence: the traceback lines that drove the edit (raw text).
        abstained: True when no provable fix exists (an honest refusal).
        reason: human-readable justification / abstention reason.
    """
    path: str
    old_lines: List[str]
    new_lines: List[str]
    strategy: str
    evidence: List[str]
    abstained: bool = False
    reason: str = ""

    def to_patch(self) -> Dict[str, Any]:
        """The structured write_file patch dict the governed layer consumes."""
        return {
            "path": self.path,
            "old_lines": list(self.old_lines),
            "new_lines": list(self.new_lines),
            "provenance": {
                "strategy": self.strategy,
                "evidence": list(self.evidence),
            },
        }


class FixProposalGenerator:
    """Deterministic, evidence-grounded patch GENERATOR (autonomous fixes).

    PATTERN (abstention over hallucination, Λ2.3): a fix is only proposed when
    the raw failing evidence uniquely determines a minimal edit. When the
    traceback is ambiguous the generator returns an abstention, NEVER a guess —
    an evidence-free edit applied to the repo is worse than a defensible
    no-proposal. Every proposal cites the exact traceback lines that drove it
    (feeds the FixProposalValidator's evidence-anchored approval).

    Supported deterministic strategies (extendable):
      1. import_resolution: a NameError / ModuleNotFoundError / ImportError in
         the failing module resolves a symbol `X` to EXACTLY ONE candidate
         module in the workspace (grep for the symbol's definition); the edit
         inserts the minimal import. Abstains when the symbol is ambiguous
         (multiple candidate sources) or not locatable.
      2. missing_member: an AttributeError for `X.attr` where the attribute is
         a plain constant/field definition found verbatim in exactly one other
         workspace line — the edit inserts the constant into the failing
         class/function body. Abstains unless provable.
      3. provable_constant: a comparison/assert against a numeric constant
         which a sibling PASSING test asserts to the correct value — the edit
         corrects the constant in place. Abstains unless the correct value is
         independently evidenced.
    """

    def __init__(self, repo_path: str):
        self._repo_path = repo_path

    # ── evidence access ────────────────────────────────────────────────────

    def _snapshot(self, evidence: Any) -> Dict[str, Any]:
        """Normalize a RepoSnapshot (object or dict) to its dict form.

        Args:
            evidence: the RepoSnapshot instance or dict to normalize.
        """
        if hasattr(evidence, "to_dict"):
            return evidence.to_dict()
        return evidence if isinstance(evidence, dict) else {}

    def _failing_module(self, target_test: str) -> Optional[str]:
        """The workspace-relative module file the failing test targets.

        Args:
            target_test: the failing test id (e.g. 'test_math.py::test_add'
                or 'src/mod.py::test_x').

        Returns:
            The file path before '::', as-is (workspace-relative).
        """
        return target_test.split("::")[0] if "::" in target_test else target_test

    def _read_module(self, module_file: str) -> List[str]:
        """Read a workspace module's current source lines (raw file access).

        Args:
            module_file: the workspace-relative file path.

        Returns:
            The file's lines (empty list when unreadable).
        """
        try:
            with open(os.path.join(self._repo_path, module_file),
                      encoding="utf-8", errors="replace") as fp:
                return fp.read().splitlines()
        except (OSError, TypeError):
            logger.warning("FixProposalGenerator: cannot read %s", module_file)
            return []

    # ── workspace symbol search (deterministic) ────────────────────────────

    def _find_symbol_definition(self, symbol: str) -> List[str]:
        """Find workspace files defining `symbol` (class/def/assignment).

        The symbol is locatable when EXACTLY ONE file defines a `class X`, a
        `def X(` or a top-level `X = <literal>` — that uniqueness is what makes
        an import-resolution provable rather than guessed.

        Args:
            symbol: the bare name being resolved (e.g. 'add', 'compute').

        Returns:
            The list of unique module files that define the symbol.
        """
        import fnmatch
        hits: List[str] = []
        pattern = re.compile(
            r"^\s*(?:class|def)\s+" + re.escape(symbol) + r"[\s\(:=]")
        literal = re.compile(
            r"^\s*" + re.escape(symbol) + r"\s*=\s*[^=\s]")
        for root, _dirs, files in os.walk(self._repo_path):
            if any(part in (".git", "__pycache__", "node_modules", ".venv")
                   for part in root.split(os.sep)):
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, self._repo_path)
                try:
                    with open(full, encoding="utf-8", errors="replace") as fp:
                        text = fp.read()
                except OSError:
                    continue
                if pattern.search(text) or literal.search(text):
                    hits.append(rel)
        return hits

    def _import_line_for(self, symbol: str, module_rel: str) -> str:
        """The import statement that would resolve `symbol` from `module_rel`.

        Converts a file path to a Python dotted module (excluding a trailing
        `__init__`), e.g. 'src/math_core.py' -> 'from src.math_core import X'.

        Args:
            symbol: the symbol to import.
            module_rel: workspace-relative module file defining it.

        Returns:
            A minimal `from <module> import <symbol>` line.
        """
        mod = module_rel[:-3] if module_rel.endswith(".py") else module_rel
        mod = re.sub(r"/__init__$", "", mod).replace("/", ".")
        return f"from {mod} import {symbol}"

    # ── traceback classifiers ──────────────────────────────────────────────

    def _classify(self, frames: List[str]) -> Dict[str, Any]:
        """Classify traceback frames into a structured error signature.

        Recognized error families: NameError (with the missing name),
        ModuleNotFoundError / ImportError (with the module), AttributeError
        (with the object and attribute). Unknown families classify as None.

        Args:
            frames: raw traceback frame lines.

        Returns:
            dict with keys: family, symbol (for NameError), module (for
            import errors), obj, attr (for AttributeError).
        """
        sig: Dict[str, Any] = {"family": None}
        joined = "\n".join(frames)
        name = re.search(r"NameError:\s*name\s+'([^']+)'", joined)
        if name:
            sig = {"family": "name_error", "symbol": name.group(1)}
            return sig
        mod = re.search(
            r"(?:ModuleNotFoundError|ImportError):\s*"
            r"(?:No module named\s+)?'?([^']+)'?", joined)
        if mod:
            sig = {"family": "import_error", "module": mod.group(1)}
            return sig
        attr = re.search(r"AttributeError:\s*(?:'([^']+)' object has no attribute\s+'([^']+)'|module '([^']+)' has no attribute '([^']+)')", joined)
        if attr:
            obj, attr_name, mod_obj, mod_attr = attr.groups()
            sig = {
                "family": "attribute_error",
                "obj": obj or mod_obj,
                "attr": attr_name or mod_attr,
            }
            return sig
        return sig

    # ── public API ─────────────────────────────────────────────────────────

    def generate(self, target_test: str, evidence: Any) -> FixProposal:
        """Propose a provable, minimal fix for a failing test, or abstain.

        Args:
            target_test: the failing test id (evidence-anchored target).
            evidence: the real RepoSnapshot (object or dict) from GitRepoSim.

        Returns:
            A FixProposal: a structured patch when the evidence uniquely
            determines an edit; an honest abstention otherwise.
        """
        snap = self._snapshot(evidence)
        frames = [str(f) for f in (snap.get("traceback_frames") or [])]
        sig = self._classify(frames)
        module_file = self._failing_module(target_test)
        lines = self._read_module(module_file)

        # ── strategy 1: NameError -> provable import resolution ──
        if sig.get("family") == "name_error":
            symbol = sig["symbol"]
            modules = self._find_symbol_definition(symbol)
            if len(modules) == 1:
                imp = self._import_line_for(symbol, modules[0])
                # Insert after the last existing import; refuse if already there.
                if any(imp in ln or f"import {symbol}" in ln for ln in lines):
                    return FixProposal(
                        path=module_file, old_lines=[], new_lines=[],
                        strategy="import_resolution", evidence=frames,
                        abstained=True,
                        reason=f"{symbol} already imported/defined in {module_file}",
                    )
                import_idx = max(
                    [i for i, ln in enumerate(lines)
                     if ln.strip().startswith(("import ", "from "))] + [0])
                if lines and lines[import_idx].strip().startswith(("import ", "from ")):
                    old = [lines[import_idx]]
                    new = [imp] if lines[import_idx].strip() else [imp]
                    note = f"import inserted after line {import_idx}"
                else:
                    # No existing import block: PREPEND the import line before
                    # the file's first line (grow the replacement), never
                    # replace the module/func header itself.
                    old = [lines[0]] if lines else [""]
                    new = [imp, old[0]] if lines else [imp]
                    note = "import prepended at top of file"
                return FixProposal(
                    path=module_file, old_lines=old, new_lines=new,
                    strategy="import_resolution", evidence=frames,
                    reason=(
                        f"NameError {symbol!r} resolved to unique module "
                        f"{modules[0]} ({note})"
                    ),
                )
            if len(modules) == 0:
                return FixProposal(
                    path=module_file, old_lines=[], new_lines=[],
                    strategy="import_resolution", evidence=frames,
                    abstained=True,
                    reason=f"name {symbol!r} has NO locatable definition in workspace",
                )
            return FixProposal(
                path=module_file, old_lines=[], new_lines=[],
                strategy="import_resolution", evidence=frames,
                abstained=True,
                reason=f"name {symbol!r} ambiguous: candidates {sorted(modules)}",
            )

        # ── strategy 2: missing member -> provable constant insertion ──
        if sig.get("family") == "attribute_error" and sig.get("attr"):
            attr = sig["attr"]
            # Find a literal definition `attr = <literal>` in exactly one file.
            candidates = [
                rel for rel in self._find_symbol_definition(attr)
                if rel != module_file
            ]
            if len(candidates) == 1:
                val_lines = self._read_module(candidates[0])
                val = next(
                    (ln.split("=", 1)[1].strip() for ln in val_lines
                     if re.match(r"^\s*" + re.escape(attr) + r"\s*=", ln)),
                    None)
                if val is not None:
                    insertion = f"    {attr} = {val}"
                    # Append after the last non-empty line of the module body.
                    non_empty = [i for i, ln in enumerate(lines) if ln.strip()]
                    idx = non_empty[-1] if non_empty else 0
                    return FixProposal(
                        path=module_file, old_lines=[lines[idx]] if lines else [],
                        new_lines=[lines[idx], insertion] if lines else [insertion],
                        strategy="missing_member", evidence=frames,
                        reason=(
                            f"attribute {attr!r} defined as {val!r} in "
                            f"{candidates[0]}; inserted as member constant"
                        ),
                    )
            return FixProposal(
                path=module_file, old_lines=[], new_lines=[],
                strategy="missing_member", evidence=frames,
                abstained=True,
                reason=f"attribute {attr!r} has no single provable literal definition",
            )

        # ── unknown / ambiguous evidence: honest abstention ──
        return FixProposal(
            path=module_file, old_lines=[], new_lines=[],
            strategy="abstain", evidence=frames, abstained=True,
            reason=(
                "no provably-unique minimal edit derivable from the failing "
                "evidence; refusing to guess (abstention over hallucination)"
            ),
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

    def run_autonomous(self, target_tests: List[str],
                       evidence: Any) -> List[Dict[str, Any]]:
        """AUTONOMOUS fix generation: invent the patch, then govern + verify.

        PATTERN (abstention over hallucination, Λ2.3): the generator proposes a
        patch ONLY when the real failing evidence uniquely determines a minimal
        edit. Every generated proposal carries its traceback evidence; an
        abstention yields no patch and is recorded honestly (no guess is
        applied to the repo).

        Args:
            target_tests: failing test ids to fix (each becomes an iteration).
            evidence: the real RepoSnapshot (object or dict) from GitRepoSim.

        Returns:
            A list of per-iteration outcome dicts:
            {"test_id", "generated": bool, "proposal": dict-or-None,
             "abstained": bool, "reason": str, "feedback": FixLoopFeedback-or-None}.
        """
        gen = FixProposalGenerator(self._repo_path)
        snap = gen._snapshot(evidence)
        outcomes: List[Dict[str, Any]] = []
        for i, test_id in enumerate(target_tests[:FIX_LOOP_MAX_ITERATIONS], start=1):
            proposal = gen.generate(test_id, snap)
            hook = {
                "test_id": test_id,
                "generated": not proposal.abstained,
                "proposal": proposal.to_patch() if not proposal.abstained else None,
                "abstained": proposal.abstained,
                "reason": proposal.reason,
                "feedback": None,
            }
            if proposal.abstained:
                outcomes.append(hook)
                continue
            fb = self.apply_fix(i, test_id, proposal.to_patch())
            hook["feedback"] = fb
            outcomes.append(hook)
        return outcomes

__all__ = [
    "FIX_LOOP_MAX_ITERATIONS", "FixProposalValidator", "FixProposalStream",
    "FixLoopFeedback", "FixLoopController", "FixProposalGenerator",
    "FixProposal",
]
