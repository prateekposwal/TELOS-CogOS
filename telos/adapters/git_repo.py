"""
GitRepoAdapter / GitRepoSim — REAL code perception for TELOS.

PATTERN (real perception): raw artifacts reach the council as evidence,
NEVER hidden behind a vector.

Previously TELOS could only hear the world as `np.ndarray` (DomainAdapter.
forward(domain_state: np.ndarray), runtime.execute(state: np.ndarray)).
This adapter ingests a REAL repository path and turns `git status`,
`git diff` (unified), recent `git log`, and any supplied test-output /
traceback files into:

  1. a `RepoSnapshot` — a structured, HUMAN-READABLE evidence channel
     (changed_files, added/removed line counts, unified diff text,
     commit log entries, failing test names, first-N traceback frames,
     key tokens, findings) that council validators genuinely READ, and
  2. a canonical numeric state vector (backward compat with the pipeline's
     execute(state: np.ndarray) contract).

This is a READ-ONLY DIAGNOSIS domain: `transition()` is the identity —
observing a repository never mutates it (documented in the WorldSpec
constraint `read_only_diagnosis`). The only "actions" are diagnostic
vectors whose effect is to re-observe.

Realness guarantees (Lambda 2.3 — never fabricated data):
  - Every field in the snapshot is PRODUCED by an actual git command that
    ran against the repo, or by parsing a file the operator supplied.
  - Channels that could not be measured are reported as unavailable
    (evidence_provenance), never as zero/empty-means-clean.
  - No subprocess uses a shell; all git invocation is list-form with
    bounded capture.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from telos.core.contracts.domain_model import (
    DomainSimulator, DomainAdapter, EvaluationReport, WorldSpec,
)
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.world.evidence import (
    EvidenceInfo, EvidenceSource, ValidationStatus, measured,
)
from telos.intent_ir import IntentIR
from telos.adapters.dev_validation import _safe_run, CommandRun

# ─── State vector layout (SUMMARY projection; the evidence lives in RepoSnapshot) ───
# [0] dirty_ratio           changed tracked files / total tracked files (capped 1.0)
# [1] diff_intensity        (added + removed lines) / 1000 capped 1.0
# [2] failing_test_ratio    failing / (passing + failing) when tests ran, else 0.0
# [3] has_traceback         1.0 when traceback frames were parsed, else 0.0
# [4] commit_activity       commits in window / 10 capped 1.0
# [5] branch_divergence     (ahead + behind) / 20 capped 1.0
# [6] evidence_completeness measured evidence channels / total channels (honest 0.0-1.0)
STATE_DIM = 7

# Channels tracked for evidence_completeness (honest coverage of what we measured).
EVIDENCE_CHANNELS = [
    "git_status", "git_diff", "git_log", "git_branch", "test_output",
]

DIFF_TEXT_LIMIT = 60_000      # bounded unified-diff capture per snapshot
LOG_ENTRIES = 10              # recent commits surfaced
TRACEBACK_FRAMES = 3          # first N frames per traceback block
OUTPUT_LIMIT = 1024 * 1024    # bounded subprocess capture (same as dev_validation)

_INTENT_STATUS_RE = re.compile(r"^([ MADRCU?!]{1,2})\s+(.+)$")
# Exception lines inside a traceback block (e.g. "AssertionError: x != y",
# "ValueError: ...", "ModuleNotFoundError: No module named 'x'").
_EXCEPTION_LINE_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Exit):\s+.*$"
)
_NUMSTAT_RE = re.compile(r"^(\d+|-)\s+(\d+|-)\s+(.+)$")
_SUMMARY_RE = re.compile(r"(\d+)\s+passed,\s*(\d+)\s+failed")
_FAILED_ONLY_RE = re.compile(r"(\d+)\s+failed\s+in")
_PASSED_ONLY_RE = re.compile(r"(\d+)\s+passed\s+in")
_FAILED_Q_RE = re.compile(r"^FAILED\s+(.+?)(?:\s+-\s+(.*))?$")


@dataclass
class ChangedFile:
    """One changed file in the working tree or index (from `git status`).

    status: the porcelain status letter(s), e.g. "M", "??", "A".
    added / removed: line counts from `git diff --numstat` (None = unknown).
    """
    path: str
    status: str
    added: Optional[int] = None
    removed: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "added": self.added,
            "removed": self.removed,
        }


@dataclass
class CommitInfo:
    """One recent commit entry from `git log`."""
    commit_hash: str
    subject: str
    author: str
    date: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hash": self.commit_hash,
            "subject": self.subject,
            "author": self.author,
            "date": self.date,
        }


@dataclass
class TestRunEvidence:
    """Parsed evidence from a supplied test-output / CI-log file.

    source_path: the file the evidence was parsed from.
    failing_test_names: test ids whose line contained FAILED (raw text).
    passing_count / failing_count: parsed from "X passed, Y failed".
    summary_line: the matched summary line verbatim.
    """
    source_path: str
    failing_test_names: List[str] = field(default_factory=list)
    passing_count: int = 0
    failing_count: int = 0
    summary_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_path": self.source_path,
            "failing_test_names": list(self.failing_test_names),
            "passing_count": self.passing_count,
            "failing_count": self.failing_count,
            "summary_line": self.summary_line,
        }


@dataclass
class RepoSnapshot:
    """The structured, human-readable evidence channel for a real repository.

    This is the object the council and validators GENUINELY READ: it carries
    the raw text artifacts (unified diff, commit subjects, failing test
    names, traceback frames, key tokens) — not just numbers. The numeric
    state vector (`to_vector`) is a backward-compatible SUMMARY; the truth
    lives here.
    """
    repo_path: str
    branch: str = ""
    dirty: bool = False
    tracked_file_count: int = 0
    changed_files: List[ChangedFile] = field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0
    diff_text: str = ""
    commit_log: List[CommitInfo] = field(default_factory=list)
    ahead: int = 0
    behind: int = 0
    test_runs: List[TestRunEvidence] = field(default_factory=list)
    traceback_frames: List[str] = field(default_factory=list)
    key_tokens: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    evidence_provenance: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.evidence_provenance = dict(self.evidence_provenance)

    # ── structured accessors the validators read ──────────────────────────
    @property
    def failing_test_names(self) -> List[str]:
        """All failing test ids across every parsed test run, deduplicated."""
        seen: List[str] = []
        for run in self.test_runs:
            for name in run.failing_test_names:
                if name not in seen:
                    seen.append(name)
        return seen

    @property
    def total_failing(self) -> int:
        """Total failing tests across parsed runs (deduplicated by name)."""
        return len(self.failing_test_names)

    @property
    def first_exception(self) -> str:
        """The first traceback's final exception line, if any (raw text)."""
        for frame in self.traceback_frames:
            if frame.strip():
                return frame.strip()
        return ""

    def to_dict(self) -> Dict[str, Any]:
        """Full serializable evidence record (the raw-artifact channel)."""
        return {
            "repo_path": self.repo_path,
            "branch": self.branch,
            "dirty": self.dirty,
            "tracked_file_count": self.tracked_file_count,
            "changed_files": [f.to_dict() for f in self.changed_files],
            "added_lines": self.added_lines,
            "removed_lines": self.removed_lines,
            "diff_text": self.diff_text,
            "commit_log": [c.to_dict() for c in self.commit_log],
            "ahead": self.ahead,
            "behind": self.behind,
            "test_runs": [r.to_dict() for r in self.test_runs],
            "failing_test_names": self.failing_test_names,
            "traceback_frames": list(self.traceback_frames),
            "key_tokens": list(self.key_tokens),
            "findings": list(self.findings),
            "evidence_provenance": dict(self.evidence_provenance),
        }

    def to_vector(self) -> np.ndarray:
        """Canonical numeric summary projection (backward compat)."""
        dirty_ratio = min(
            len(self.changed_files) / max(self.tracked_file_count, 1), 1.0
        )
        diff_intensity = min((self.added_lines + self.removed_lines) / 1000.0, 1.0)
        total_tests = sum(r.passing_count + r.failing_count for r in self.test_runs)
        failing_total = sum(r.failing_count for r in self.test_runs)
        failing_ratio = (failing_total / total_tests) if total_tests > 0 else 0.0
        has_tb = 1.0 if self.traceback_frames else 0.0
        commit_activity = min(len(self.commit_log) / 10.0, 1.0)
        branch_divergence = min((self.ahead + self.behind) / 20.0, 1.0)
        measured_channels = sum(
            1 for v in self.evidence_provenance.values() if v.startswith("measured")
        )
        completeness = measured_channels / len(EVIDENCE_CHANNELS)
        return np.array([
            dirty_ratio, diff_intensity, failing_ratio, has_tb,
            commit_activity, branch_divergence, completeness,
        ], dtype=float)


def _safe_limit(text: str, limit: int) -> str:
    """Truncate raw command output to a bounded size.

    Args:
        text: the raw captured output to bound.
        limit: maximum retained characters.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated at {limit} chars]"


def _parse_porcelain_status(text: str) -> List[ChangedFile]:
    """Parse `git status --porcelain` lines into ChangedFile entries.

    Args:
        text: porcelain status output (one 'XY path' per line).

    Returns:
        List of ChangedFile entries preserving status letters and paths.
    """
    files: List[ChangedFile] = []
    for line in text.splitlines():
        line = line.rstrip("\n")
        if not line.strip():
            continue
        m = _INTENT_STATUS_RE.match(line)
        if not m:
            continue
        status = m.group(1)
        if status.strip() == "":
            # Not an XY status pair at all (should not happen on porcelain).
            continue
        files.append(ChangedFile(path=m.group(2).strip(), status=status.strip()))
    return files


def _parse_numstat(text: str) -> Dict[str, Tuple[int, int]]:
    """Parse `git diff --numstat` output into path -> (added, removed).

    Args:
        text: numstat output ('added\tremoved\tpath' per line).

    Returns:
        Mapping of file path to (added_lines, removed_lines) integer counts.
    """
    counts: Dict[str, Tuple[int, int]] = {}
    for line in text.splitlines():
        m = _NUMSTAT_RE.match(line.strip())
        if not m:
            continue
        added = 0 if m.group(1) == "-" else int(m.group(1))
        removed = 0 if m.group(2) == "-" else int(m.group(2))
        counts[m.group(3).strip()] = (added, removed)
    return counts


def _parse_log(text: str) -> List[CommitInfo]:
    """Parse `git log --format=...` output into CommitInfo entries.

    Args:
        text: git log output using the %h|%s|%an|%ad separator format.

    Returns:
        List of CommitInfo entries in log order (newest first).
    """
    commits: List[CommitInfo] = []
    for line in text.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append(CommitInfo(
                commit_hash=parts[0], subject=parts[1],
                author=parts[2], date=parts[3],
            ))
    return commits


def parse_test_output(source_path: str, text: str) -> TestRunEvidence:
    """Parse a test-output / CI-log file into TestRunEvidence.

    Recognizes pytest-style "N passed, M failed" summaries and FAILED lines
    (including `FAILED path::test_name - Error`), and extracts traceback
    blocks' first frames. Raw text is never invented: entries only come from
    lines that actually appear in the supplied text.

    Args:
        source_path: the file the output was read from.
        text: the raw captured/read test output.

    Returns:
        TestRunEvidence with parsed counts, failing ids and summary.
    """
    run = TestRunEvidence(source_path=source_path)
    for line in text.splitlines():
        m = _SUMMARY_RE.search(line)
        if m:
            run.passing_count = int(m.group(1))
            run.failing_count = int(m.group(2))
            run.summary_line = line.strip()
        else:
            mf = _FAILED_ONLY_RE.search(line)
            if mf:
                run.failing_count = int(mf.group(1))
                run.summary_line = line.strip()
            else:
                mp = _PASSED_ONLY_RE.search(line)
                if mp:
                    run.passing_count = int(mp.group(1))
                    run.summary_line = line.strip()
        mq = _FAILED_Q_RE.match(line)
        if mq:
            test_id = mq.group(1).strip()
            if test_id not in run.failing_test_names:
                run.failing_test_names.append(test_id)
    if run.failing_count == 0 and run.failing_test_names:
        # FAILED lines were parsed but no summary: count is the number of ids.
        run.failing_count = len(run.failing_test_names)
    return run


def parse_traceback_frames(text: str, max_frames: int = TRACEBACK_FRAMES) -> List[str]:
    """Extract the first frames + exception line from traceback blocks.

    A traceback block starts with 'Traceback (most recent call last):'; the
    first `max_frames` '  File "...' frame lines and the trailing exception
    line (e.g. 'AssertionError: ...') are captured verbatim.

    Args:
        text: raw output possibly containing one or more tracebacks.
        max_frames: how many frame lines to keep per traceback block.

    Returns:
        List of raw frame/exception strings, in occurrence order.
    """
    frames: List[str] = []
    in_traceback = False
    frame_count = 0
    for line in text.splitlines():
        if "Traceback (most recent call last):" in line:
            in_traceback = True
            frame_count = 0
            continue
        if in_traceback:
            stripped = line.strip()
            if stripped.startswith('File "'):
                if frame_count < max_frames:
                    frames.append(line.rstrip())
                    frame_count += 1
                continue
            if _EXCEPTION_LINE_RE.match(stripped):
                frames.append(line.rstrip())
                in_traceback = False
            elif stripped == "":
                in_traceback = False
    return frames


class GitRepoSim(DomainSimulator):
    """Simulates a REAL git repository as a TELOS read-only diagnosis domain.

    snapshot() runs real git commands against `repo_path` and parses any
    operator-supplied test-output/traceback files, producing both the
    RepoSnapshot evidence channel and the canonical numeric state vector.

    transition() is the IDENTITY: diagnosing a repository never mutates it
    (WorldSpec constraint read_only_diagnosis). simulate() projects the
    identity, terminal() is always False (the diagnosis can keep observing).
    """

    name = "gitrepo"
    state_dim = STATE_DIM

    def __init__(self, repo_path: str, seed: Optional[int] = None,
                 test_output_paths: Optional[List[str]] = None,
                 traceback_paths: Optional[List[str]] = None,
                 git_timeout: float = 10.0):
        """Construct a GitRepoSim over a real repository.

        Args:
            repo_path: absolute path to the git repository to diagnose.
            seed: optional RNG seed (private RandomState, one authority per engine).
            test_output_paths: files whose content is parsed as test/CI output.
            traceback_paths: files whose content is parsed for traceback frames.
            git_timeout: per-git-command timeout in seconds.
        """
        self.repo_path = str(repo_path)
        self._rng = np.random.RandomState(seed)
        self._test_output_paths = list(test_output_paths or [])
        self._traceback_paths = list(traceback_paths or [])
        self._git_timeout = git_timeout
        self._last_snapshot: Optional[RepoSnapshot] = None
        self._last_evidence: Optional[EvidenceInfo] = None

    # ── lifecycle ──────────────────────────────────────────────────────────
    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    # ── real gathering ─────────────────────────────────────────────────────
    def _git(self, args: List[str]) -> CommandRun:
        """Run a read-only git command list-form against the repo.

        Args:
            args: git subcommand argv (e.g. ["status", "--porcelain"]).

        Returns:
            CommandRun with bounded captured stdout/stderr and classification.
        """
        return _safe_run(["git"] + args, cwd=self.repo_path, timeout=self._git_timeout)

    def gather_snapshot(self) -> RepoSnapshot:
        """Run the real git commands and parse supplied files into a RepoSnapshot.

        Returns:
            RepoSnapshot carrying the raw text artifacts and provenance.
        """
        prov: Dict[str, str] = {}
        snap = RepoSnapshot(repo_path=self.repo_path)

        st = self._git(["status", "--porcelain"])
        if st.returncode == 0:
            prov["git_status"] = "measured"
            changed = _parse_porcelain_status(st.stdout)
            snap.changed_files = changed
            snap.dirty = len(changed) > 0
        else:
            prov["git_status"] = "unavailable:" + st.classification

        br = self._git(["branch", "--show-current"])
        if br.returncode == 0 and br.stdout.strip():
            prov["git_branch"] = "measured"
            snap.branch = br.stdout.strip()
        else:
            prov["git_branch"] = "unavailable"

        tr = self._git(["ls-files"])
        if tr.returncode == 0:
            snap.tracked_file_count = len([l for l in tr.stdout.splitlines() if l.strip()])

        numstat = self._git(["diff", "--numstat"])
        numstat_cached = self._git(["diff", "--cached", "--numstat"])
        added = removed = 0
        if numstat.returncode == 0 or numstat_cached.returncode == 0:
            combined: Dict[str, Tuple[int, int]] = {}
            for run in (numstat, numstat_cached):
                if run.returncode == 0:
                    for path, (a, r) in _parse_numstat(run.stdout).items():
                        ea, er = combined.get(path, (0, 0))
                        combined[path] = (ea + a, er + r)
            for f in snap.changed_files:
                if f.path in combined:
                    f.added, f.removed = combined[f.path]
                    added += f.added
                    removed += f.removed
            snap.added_lines = added
            snap.removed_lines = removed
            prov["git_diff"] = "measured"
        else:
            prov["git_diff"] = "unavailable:" + numstat.classification

        diff_run = self._git(["diff"])
        cached_run = self._git(["diff", "--cached"])
        diff_parts = []
        for run in (diff_run, cached_run):
            if run.returncode == 0 and run.stdout.strip():
                diff_parts.append(run.stdout)
        snap.diff_text = _safe_limit("\n".join(diff_parts), DIFF_TEXT_LIMIT)
        if not prov.get("git_diff"):
            prov["git_diff"] = "measured" if diff_parts else "unavailable:clean"

        log = self._git(["log", "-n", str(LOG_ENTRIES),
                         "--format=%h|%s|%an|%ad", "--date=short"])
        if log.returncode == 0:
            prov["git_log"] = "measured"
            snap.commit_log = _parse_log(log.stdout)
        else:
            prov["git_log"] = "unavailable:" + log.classification

        rev = self._git(["rev-list", "--left-right", "--count", "HEAD...@{upstream}"])
        if rev.returncode == 0 and rev.stdout.strip():
            parts = rev.stdout.split()
            if len(parts) == 2:
                snap.ahead = int(parts[0])
                snap.behind = int(parts[1])

        # ── test-output / traceback files (operator-supplied evidence) ──
        for path in self._test_output_paths:
            p = Path(path)
            if p.is_file():
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                run = parse_test_output(str(path), text)
                snap.test_runs.append(run)
                prov["test_output"] = "measured"
            else:
                prov["test_output"] = f"unavailable:missing {path}"
        for path in self._traceback_paths:
            p = Path(path)
            if p.is_file():
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                frames = parse_traceback_frames(text)
                for fr in frames:
                    if fr not in snap.traceback_frames:
                        snap.traceback_frames.append(fr)
                prov.setdefault("test_output", "measured")

        # ── key tokens: filenames + failure vocabulary actually present ──
        tokens: List[str] = []
        for f in snap.changed_files:
            if f.path not in tokens:
                tokens.append(f.path)
        for run in snap.test_runs:
            for name in run.failing_test_names:
                tok = name.split("::")[-1]
                if tok not in tokens:
                    tokens.append(tok)
        for fr in snap.traceback_frames:
            tok = fr.strip().split(":")[-1].strip()
            if tok and tok not in tokens:
                tokens.append(tok)
        snap.key_tokens = tokens[:40]

        # ── honest findings built ONLY from measured evidence ──
        findings: List[str] = []
        if snap.dirty:
            findings.append(f"working tree dirty: {len(snap.changed_files)} changed files")
        if snap.added_lines + snap.removed_lines > 0:
            findings.append(
                f"diff magnitude: +{snap.added_lines}/-{snap.removed_lines} lines")
        for run in snap.test_runs:
            if run.failing_count > 0:
                findings.append(
                    f"test failure: {run.failing_count} failing in {run.source_path}")
            elif run.passing_count > 0:
                findings.append(
                    f"tests measured: {run.passing_count} passed in {run.source_path}")
        if snap.total_failing:
            findings.append(f"failing test ids: {snap.total_failing}")
        if snap.traceback_frames:
            findings.append(f"traceback observed: {snap.first_exception}")
        snap.findings = findings
        snap.evidence_provenance = prov
        return snap

    def snapshot(self) -> np.ndarray:
        """Take a fresh real-command snapshot and return the canonical vector.

        Returns:
            Numeric state vector (STATE_DIM) summarizing the RepoSnapshot.
        """
        snap = self.gather_snapshot()
        self._last_snapshot = snap
        n_measured = sum(1 for v in snap.evidence_provenance.values()
                         if v.startswith("measured"))
        confidence = min(1.0, n_measured / len(EVIDENCE_CHANNELS))
        if n_measured > 0:
            self._last_evidence = measured(
                source=EvidenceSource.EXTERNAL_SOLVER,
                confidence=confidence,
            )
        else:
            self._last_evidence = EvidenceInfo(
                source=EvidenceSource.SIMULATION,
                validation_status=ValidationStatus.UNVALIDATED,
            )
        return snap.to_vector()

    @property
    def last_snapshot(self) -> Optional[RepoSnapshot]:
        """The most recent RepoSnapshot evidence channel (None before first call)."""
        return self._last_snapshot

    # ── DomainSimulator contract ───────────────────────────────────────────
    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        """Diagnostic action space: re-observe / inspect / run tests vectors.

        Args:
            state: the current git-repo state vector.

        Returns:
            List of legal diagnostic action vectors (identity-shaped).
        """
        base = np.zeros(STATE_DIM, dtype=float)
        return [
            base.copy(),                              # observe again
            np.array([0, 0, 1.0, 0, 0, 0, 0]),        # surface test evidence
            np.array([0, 0, 0, 1.0, 0, 0, 0]),        # surface traceback evidence
            np.array([0, 0, 0, 0, 0, 0, 1.0]),        # complete the evidence
        ]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        """READ-ONLY identity: diagnosing a repo never mutates it.

        Args:
            state: the current state vector.
            action: the diagnostic action vector (ignored by the identity).

        Returns:
            An identical copy of the input state.
        """
        return np.array(state, dtype=float).copy()

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        """Project read-only futures: every step lands on the same state.

        Args:
            state: the state to begin the simulation from.
            horizon: number of future identity steps to project.

        Returns:
            List of Worlds, each a snapshot of the unchanged diagnosis state.
        """
        futures: List[World] = []
        s = np.array(state, dtype=float)
        for _ in range(max(0, int(horizon))):
            action = self.legal_transitions(s)[int(self._rng.randint(len(self.legal_transitions(s))))]
            s = self.transition(s, action)
            futures.append(World(state=s.copy(), metadata={"simulated": True, "read_only": True}))
        return futures

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        """DomainFacts with resources/metrics + the raw RepoSnapshot evidence.

        Args:
            state: the current git-repo state vector.

        Returns:
            DomainFacts whose metadata.repo_snapshot carries the raw text
            artifacts the council can genuinely read.
        """
        snap = self._last_snapshot or RepoSnapshot(repo_path=self.repo_path)
        return DomainFacts(
            state=np.array(state, dtype=float).copy(),
            resources={
                "evidence_completeness": float(state[6]) if len(state) > 6 else 0.0,
                "dirty_ratio": float(state[0]) if len(state) > 0 else 0.0,
                "test_health": float(1.0 - state[2]) if len(state) > 2 else 1.0,
            },
            constraints=["read_only_diagnosis", "no_mutation"],
            events=snap.findings[:5],
            metrics={
                "diff_intensity": float(state[1]) if len(state) > 1 else 0.0,
                "failing_test_ratio": float(state[2]) if len(state) > 2 else 0.0,
                "has_traceback": float(state[3]) if len(state) > 3 else 0.0,
                "commit_activity": float(state[4]) if len(state) > 4 else 0.0,
                "branch_divergence": float(state[5]) if len(state) > 5 else 0.0,
            },
            metadata={
                "repo_path": self.repo_path,
                "repo_snapshot": snap.to_dict(),
                "domain": "gitrepo",
            },
            evidence=self._last_evidence,
        )

    def terminal(self, state: np.ndarray) -> bool:
        """A read-only diagnosis domain has no terminal state.

        Args:
            state: the current state vector (ignored).

        Returns:
            Always False — the diagnosis can keep observing.
        """
        return False

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        """Score the diagnosis state for trajectory ranking.

        Args:
            state: the current state vector.

        Returns:
            EvaluationReport favoring complete, clean evidence.
        """
        completeness = float(state[6]) if len(state) > 6 else 0.0
        test_risk = float(state[2]) if len(state) > 2 else 0.0
        traceback_risk = float(state[3]) if len(state) > 3 else 0.0
        return EvaluationReport(
            objectives={
                "diagnosis_completeness": completeness,
                "evidence_quality": 1.0 - test_risk - traceback_risk,
                "repo_orderliness": 1.0 - float(state[0]) if len(state) > 0 else 1.0,
            },
            risks=test_risk * 1.0 + traceback_risk * 1.5,
        )

    def world_spec(self) -> WorldSpec:
        """Self-describing world manifest for the git-repo domain.

        Returns:
            WorldSpec declaring read-only constraints and real capabilities.
        """
        return WorldSpec(
            name=self.name,
            state_dim=self.state_dim,
            action_dim=self.state_dim,
            objectives=["diagnosis_completeness", "evidence_quality", "repo_orderliness"],
            constraints=[
                "read_only_diagnosis",
                "no_mutation",
                "actions_are_observations",
            ],
            observability="high",
            capabilities=[
                "perceive_git_status", "perceive_git_diff", "perceive_git_log",
                "perceive_test_output", "diagnose",
            ],
            authorized_modes={"ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK"},
            escalation_policy="advisory",
        )


class GitRepoAdapter(DomainAdapter):
    """Maps the git-repo domain into TELOS latent space.

    forward() accepts either the canonical numeric state vector or a
    RepoSnapshot (converted via to_vector) so callers may pass the raw
    evidence channel directly. intent_to_action() maps diagnostic intents
    to identity-shaped observation vectors — the only legal "actions" in a
    read-only diagnosis domain.
    """

    @property
    def name(self) -> str:
        return "gitrepo"

    @property
    def state_dim(self) -> int:
        return STATE_DIM

    def forward(self, domain_state: Any) -> np.ndarray:
        """Encode raw domain data into the canonical state vector.

        Args:
            domain_state: np.ndarray state vector, or a RepoSnapshot
                evidence channel to project via to_vector().

        Returns:
            Canonical STATE_DIM vector for the pipeline.
        """
        if isinstance(domain_state, RepoSnapshot):
            vec = domain_state.to_vector()
        else:
            vec = np.asarray(domain_state, dtype=float)
        if vec.shape == (STATE_DIM,):
            return vec.copy()
        if vec.ndim == 1 and vec.shape[0] == STATE_DIM:
            return vec.copy()
        # Honest failure: never silently reshape a wrong-sized vector.
        raise ValueError(
            f"GitRepoAdapter.forward expected state_dim={STATE_DIM}, got shape {vec.shape}"
        )

    def inverse(self, telos_action: np.ndarray) -> np.ndarray:
        """Map a TELOS action vector back to the domain (identity here).

        Args:
            telos_action: the TELOS action vector to map back to the domain.

        Returns:
            The same vector — diagnostic actions are observations.
        """
        return np.asarray(telos_action, dtype=float).copy()

    def intent_to_action(self, intent: IntentIR, state: np.ndarray,
                         mission_dir: np.ndarray) -> np.ndarray:
        """Map a TELOS intent to a diagnostic action vector.

        Args:
            intent: the selected TELOS intent to execute.
            state: the current domain state.
            mission_dir: the direction toward the mission goal.

        Returns:
            An identity-shaped diagnostic vector (observing never mutates).
        """
        if "action_vector" in intent.params:
            vec = np.asarray(intent.params["action_vector"], dtype=float)
            if vec.shape == (STATE_DIM,):
                return vec.copy()
            return np.zeros(STATE_DIM, dtype=float)
        if intent.intent_type == "tool_execute":
            return np.zeros(STATE_DIM, dtype=float)
        # Diagnosis direction: push the evidence-completeness channel up.
        vec = np.zeros(STATE_DIM, dtype=float)
        vec[6] = 1.0
        return vec


__all__ = [
    "STATE_DIM", "EVIDENCE_CHANNELS", "ChangedFile", "CommitInfo",
    "TestRunEvidence", "RepoSnapshot", "GitRepoSim", "GitRepoAdapter",
    "parse_test_output", "parse_traceback_frames",
]
