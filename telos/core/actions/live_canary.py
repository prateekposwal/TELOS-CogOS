"""
LiveCanary — the tightly bounded live-producer canary for ``filesystem.write``.

PATTERN (earn LIVE from LIVE, bounded and reversible — Λ6.5): the sandbox
certification campaign proves the loop is correct UNDER VARIANCE, but that
evidence is SANDBOX-tier and is deliberately NOT promoted. This module wires ONE
canary into the live producer that exercises the SAME governed path
(``WorldActionRunner`` + per-action ``LiveApproval`` + the per-capability
certification) against a DISPOSABLE target inside the operator sandbox, records
the full ``prediction -> execution -> post-action observation -> Reality Gap ->
authority recalibration -> admission`` trace, and evaluates that LIVE evidence
against the same certification invariants. Only live evidence that holds may
transition the capability to LIVE-CERTIFIED, and even then the canonical write
is an explicit operator act.

It is fail-closed and tightly bounded:
  * opt-in, default OFF — ``TELOS_CANARY_ENABLED`` unset/unknown => never runs;
  * at most ``TELOS_CANARY_MAX`` live actions per session (default 3) and one
    invocation per session, with a cycle-interval floor
    (``TELOS_CANARY_MIN_INTERVAL_CYCLES``, default 40);
  * disposable target ONLY — the designated ``canary_target.md`` inside the
    sandbox root; a target outside the sandbox or not the designated file is
    refused (nothing runs);
  * reversible — the exact pre-canary bytes are snapshotted and restored, and
    the sandbox git status must be unchanged;
  * fail-closed — missing sandbox evidence / no executor / not-approved => a
    recorded refusal, zero execution seams reached.

The canary never bypasses a gate: each live action goes through the real
``WorldActionRunner`` (certification + per-action approval + capability gates +
the executor's four gates). The structural tests spy every execution seam.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from telos.core.actions.certification import (
    CertificationAction, CertificationRecord, CertificationTier,
    CertificationWorkflow, CapabilityCertification, VarianceEvidence,
    VerifiedOutcome, load_sandbox_evidence,
)
from telos.core.actions.reality_loop import CapabilityAuthority, observation_fingerprint
from telos.core.actions.world_action import (
    ActionMode, LiveApproval, WorldActionProposal, WorldActionRunner,
)
from telos.core.actions.world_adapter import FilesystemWriteAdapter

logger = logging.getLogger("telos_live_canary")

#: The capability this canary is scoped to (exactly one).
CAPABILITY = "filesystem.write"
#: The ONE designated disposable canary target (git-tracked in the sandbox).
CANARY_TARGET = "canary_target.md"
#: The default live-action bound per session (small by design).
DEFAULT_MAX_ACTIONS = 3
#: The default minimum cycle interval between canary actions.
DEFAULT_MIN_INTERVAL_CYCLES = 40
#: The default operator sandbox (the governed tool workspace root).
DEFAULT_SANDBOX_ROOT = "/tmp/telos_tool_sandbox"
#: The auditable live-canary trace artifact.
DEFAULT_CANARY_ARTIFACT_PATH = str(
    Path(__file__).resolve().parents[3] / "telos" / "audit" / "live_canary.json"
)

ENV_ENABLED = "TELOS_CANARY_ENABLED"
ENV_MAX = "TELOS_CANARY_MAX"
ENV_INTERVAL = "TELOS_CANARY_MIN_INTERVAL_CYCLES"

#: The fixed, bounded action script (positive, planted-mismatch, refusal).
SCRIPT: tuple = ("positive", "negative", "refusal")

_TRUE = ("1", "true", "yes", "on")


def canary_enabled(enabled: Optional[bool] = None) -> bool:
    """Whether the canary is opted in (default OFF, unknown => OFF).

    Args:
        enabled: explicit override (wins when not None).

    Returns:
        True only for an explicit opt-in.
    """
    if enabled is not None:
        return bool(enabled)
    return os.environ.get(ENV_ENABLED, "").strip().lower() in _TRUE


def _env_int(name: str, default: int, minimum: int) -> int:
    """Read a bounded positive int from the environment (fail to default).

    Args:
        name: the env var name.
        default: the default value.
        minimum: the smallest accepted value.

    Returns:
        The parsed bounded int, or the default on any parse failure.
    """
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(str(raw).strip()))
    except (TypeError, ValueError):
        return default


#: Bound on how many files the drift digest walks (the sandbox is tiny).
DIGEST_FILE_CAP = 500


def _sandbox_digest(root: str) -> str:
    """A content digest of every non-``.git`` file under the sandbox root.

    This is the subprocess-free reversibility proof: the exact same digest
    before and after a canary run means the canary accumulated NO drift (the
    sandbox is left byte-identical, hence git-clean whenever it started clean).

    Args:
        root: the sandbox root path.

    Returns:
        A sha256 hex digest over sorted (relative-path, bytes) pairs.
    """
    h = hashlib.sha256()
    base = Path(root)
    try:
        entries = sorted(base.rglob("*"))
    except OSError:
        return ""
    seen = 0
    for p in entries:
        if ".git" in p.parts:
            continue
        if not p.is_file():
            continue
        seen += 1
        if seen > DIGEST_FILE_CAP:
            h.update(b"<cap>")
            break
        try:
            rel = p.relative_to(base).as_posix()
        except ValueError:
            continue
        h.update(rel.encode("utf-8"))
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest()


def _inside(child: Path, parent: Path) -> bool:
    """Whether ``child`` resolves inside ``parent`` (symlink-safe).

    Args:
        child: the candidate path.
        parent: the containment anchor.

    Returns:
        True when child == parent or child is under parent.
    """
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


@dataclass
class CanaryConfig:
    """The resolved, tightly bounded canary configuration (auditable).

    Attributes:
        enabled: opt-in flag (default False).
        max_actions: live-action bound per session.
        min_interval_cycles: minimum cycles between canary invocations.
        max_invocations: hard cap on invocations per session (always 1).
        sandbox_root: the designated disposable sandbox root.
        workspace_root: the governed executor workspace root.
        target: the designated canary target (relative).
        artifact_path: where the trace artifact is written.
        sandbox_evidence_path: the preserved sandbox certification artifact.
        canonical_path: the canonical LIVE registry path (default: the canonical
            audit record). Injectable so tests never touch the repo artifact.
        persist_live: whether a satisfied live bar writes the canonical LIVE
            record (an explicit operator act; default False).
    """

    enabled: bool = False
    max_actions: int = DEFAULT_MAX_ACTIONS
    min_interval_cycles: int = DEFAULT_MIN_INTERVAL_CYCLES
    max_invocations: int = 1
    sandbox_root: str = DEFAULT_SANDBOX_ROOT
    workspace_root: Optional[str] = None
    target: str = CANARY_TARGET
    artifact_path: str = DEFAULT_CANARY_ARTIFACT_PATH
    sandbox_evidence_path: Optional[str] = None
    canonical_path: Optional[str] = None
    persist_live: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializable configuration record.

        Returns:
            Dict of the configuration fields.
        """
        return {
            "enabled": self.enabled,
            "capability": CAPABILITY,
            "max_actions": self.max_actions,
            "min_interval_cycles": self.min_interval_cycles,
            "max_invocations": self.max_invocations,
            "sandbox_root": self.sandbox_root,
            "workspace_root": self.workspace_root,
            "target": self.target,
            "artifact_path": self.artifact_path,
            "canonical_path": self.canonical_path,
            "persist_live": self.persist_live,
        }


class LiveCanary:
    """The bounded, reversible, fail-closed live-producer canary."""

    def __init__(self, *, workspace_root: Optional[str],
                 executor: Any = None, firewall: Any = None,
                 authority: Optional[CapabilityAuthority] = None,
                 target: str = CANARY_TARGET,
                 sandbox_root: Optional[str] = None,
                 enabled: Optional[bool] = None,
                 max_actions: Optional[int] = None,
                 min_interval_cycles: Optional[int] = None,
                 artifact_path: Optional[str] = None,
                 sandbox_evidence_path: Optional[str] = None,
                 canonical_path: Optional[str] = None,
                 persist_live: bool = False):
        """Construct the canary (it runs nothing until invoked).

        Args:
            workspace_root: the governed executor workspace root (the sandbox).
            executor: the ActionExecutor (built lazily when None).
            firewall: the DecisionFirewall for LIVE audits (built lazily).
            authority: optional CapabilityAuthority (built lazily).
            target: the designated canary target file.
            sandbox_root: the designated disposable sandbox root.
            enabled: explicit opt-in override (default: env).
            max_actions: explicit action bound override (default: env).
            min_interval_cycles: explicit interval override (default: env).
            artifact_path: explicit trace-artifact path.
            sandbox_evidence_path: explicit sandbox-evidence path.
            canonical_path: explicit canonical LIVE registry path.
            persist_live: write the canonical LIVE record when the live bar is
                met (explicit operator act).
        """
        env_ws = os.environ.get("TELOS_TOOL_WORKSPACE") or None
        resolved_ws = workspace_root or env_ws
        self.config = CanaryConfig(
            enabled=canary_enabled(enabled),
            max_actions=(_env_int(ENV_MAX, DEFAULT_MAX_ACTIONS, 1)
                         if max_actions is None
                         else max(1, int(max_actions))),
            min_interval_cycles=(
                _env_int(ENV_INTERVAL, DEFAULT_MIN_INTERVAL_CYCLES, 1)
                if min_interval_cycles is None
                else max(1, int(min_interval_cycles))),
            sandbox_root=str(sandbox_root or DEFAULT_SANDBOX_ROOT),
            workspace_root=resolved_ws,
            target=target or CANARY_TARGET,
            artifact_path=artifact_path or DEFAULT_CANARY_ARTIFACT_PATH,
            sandbox_evidence_path=sandbox_evidence_path,
            canonical_path=canonical_path,
            persist_live=bool(persist_live),
        )
        self._executor = executor
        self._firewall = firewall
        self._authority = authority or CapabilityAuthority()

        # ── per-session bounded state ──
        self._actions_done = 0
        self._invocations = 0
        self._last_cycle: Optional[int] = None
        self._cases: List[Dict[str, Any]] = []
        self._refusals: List[Dict[str, Any]] = []
        self._last_record: Optional[Dict[str, Any]] = None
        self._completed = False
        self._live_decision: Optional[Dict[str, Any]] = None

    # ── introspection ────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """The canary's current configuration + bounded session state.

        Returns:
            Dict of config, counters, and the last record.
        """
        return {
            "config": self.config.to_dict(),
            "state": {
                "actions_done": self._actions_done,
                "actions_remaining": max(
                    0, self.config.max_actions - self._actions_done),
                "invocations": self._invocations,
                "max_invocations": self.config.max_invocations,
                "last_cycle": self._last_cycle,
                "completed": self._completed,
                "cases": len(self._cases),
                "refusals": len(self._refusals),
            },
            "last_record": self._last_record,
        }

    # ── guards ───────────────────────────────────────────────────────────

    def _resolved_target(self) -> Optional[Path]:
        """Resolve the designated target strictly inside the sandbox.

        Returns:
            The resolved target path, or None when the workspace is unset.
        """
        if not self.config.workspace_root:
            return None
        return (Path(self.config.workspace_root) / self.config.target).resolve()

    def guard_refusal(self, cycle: int) -> Optional[str]:
        """The reason this invocation must NOT run (or None to proceed).

        Fail-closed: every structural precondition is checked BEFORE any
        execution seam. A refusal returns a machine-readable reason and runs
        nothing.

        Args:
            cycle: the current pipeline cycle.

        Returns:
            A refusal reason string, or None when the canary may run.
        """
        if not self.config.enabled:
            return "canary_disabled"
        if self._completed:
            return "canary_session_complete"
        if self._actions_done >= self.config.max_actions:
            return "action_bound_reached"
        if self._invocations >= self.config.max_invocations:
            return "invocation_bound_reached"
        if not self.config.workspace_root:
            return "no_tool_workspace"
        sandbox = Path(self.config.sandbox_root).resolve()
        if not sandbox.is_dir():
            return "sandbox_root_missing"
        ws = Path(self.config.workspace_root).resolve()
        if not _inside(ws, sandbox):
            return "workspace_outside_sandbox"
        if Path(self.config.target).name != CANARY_TARGET:
            return "target_not_designated_canary_file"
        target = self._resolved_target()
        if target is None or not _inside(target, ws):
            return "target_outside_workspace"
        self._ensure_components()
        if self._executor is None:
            return "no_executor"
        return None

    def next_case(self) -> Optional[str]:
        """The next pending case in the fixed bounded script (or None).

        Returns:
            One of ``positive`` / ``negative`` / ``refusal``, or None when the
            script is exhausted or the action bound is reached.
        """
        idx = self._actions_done
        if idx >= len(SCRIPT) or idx >= self.config.max_actions:
            return None
        return SCRIPT[idx]

    # ── execution ────────────────────────────────────────────────────────

    def _ensure_components(self) -> None:
        """Build the executor / firewall / adapter lazily (never on save)."""
        if self._executor is None and self.config.workspace_root:
            from telos.core.actions.executor import build_tool_executor
            self._executor = build_tool_executor(self.config.workspace_root)
        if self._firewall is None:
            from telos.core.governance.firewall import DecisionFirewall
            self._firewall = DecisionFirewall()

    def _sandbox_registry(self) -> CapabilityCertification:
        """Load the preserved SANDBOX-CERTIFIED evidence as a scoped registry.

        Returns:
            The sandbox-tier certification registry (empty when absent).
        """
        return load_sandbox_evidence(self.config.sandbox_evidence_path)

    def _line_edit(self, content: str, *, kind: str, cycle: int
                   ) -> Dict[str, Any]:
        """Build a one-line edit + expected result for a canary case.

        Args:
            content: the current target content.
            kind: the case kind (``positive`` / ``negative``).
            cycle: the pipeline cycle (stamped into the new line).

        Returns:
            Dict with ``old_line``, ``new_line``, and ``expected``.
        """
        had_trailing = content.endswith("\n")
        body = content[:-1] if had_trailing else content
        lines = body.split("\n")
        idx = min(2, len(lines) - 1) if lines else 0
        old_line = lines[idx] if lines else ""
        if kind == "positive":
            new_line = f"canary line two written by live canary @cycle {cycle}"
            expected_lines = lines[:idx] + [new_line] + lines[idx + 1:]
            expected = "\n".join(expected_lines) + ("\n" if had_trailing else "")
        else:
            new_line = old_line + " (planted-mismatch)"
            # The prediction is deliberately WRONG: the post-observation MUST
            # diverge so the Reality Gap proves genuine detection.
            expected = "PLANTED-CANARY-MISMATCH\n"
        return {"old_line": old_line, "new_line": new_line, "expected": expected}

    def _case_proposal(self, kind: str, content: str, cycle: int
                       ) -> WorldActionProposal:
        """Build the proposal for one canary case.

        Args:
            kind: the case kind.
            content: the current target content.
            cycle: the pipeline cycle.

        Returns:
            The WorldActionProposal.
        """
        edit = self._line_edit(content, kind=kind, cycle=cycle)
        return WorldActionProposal(
            capability=CAPABILITY, operation="write_file",
            target=self.config.target,
            expected_result=edit["expected"],
            params={"old_lines": [edit["old_line"]],
                    "new_lines": [edit["new_line"]]},
            evidence={"source": f"live_canary:{kind}"},
            confidence=(0.95 if kind == "positive" else 0.5),
            risk=0.05,
        )

    def _run_case(self, kind: str, cycle: int,
                  registry: CapabilityCertification,
                  before_bytes: bytes) -> Dict[str, Any]:
        """Run one bounded canary case and capture its full trace.

        Args:
            kind: the case kind (positive / negative / refusal).
            cycle: the pipeline cycle.
            registry: the sandbox-tier certification registry.
            before_bytes: the exact pre-case target bytes (for restore).

        Returns:
            The measured case trace dict.
        """
        self._ensure_components()
        from telos.core.learning.acquisition import SkillAcquisition
        from telos.core.ledger.skill_library import SkillLibrary
        target = self._resolved_target()
        content = target.read_text(encoding="utf-8")
        adapter = FilesystemWriteAdapter(self._executor, self.config.target)
        acquisition = SkillAcquisition(SkillLibrary())
        runner = WorldActionRunner(
            self._executor, adapter, certification=registry,
            firewall=self._firewall, authority=self._authority,
            acquisition=acquisition)
        approval = None
        if kind != "refusal":
            approval = LiveApproval(
                CAPABILITY, self.config.target, "write_file", "operator",
                f"canary-{kind}-{cycle}")
        proposal = self._case_proposal(kind, content, cycle)
        result = runner.run(proposal, ActionMode.LIVE, approval=approval,
                            cycle=cycle)
        admitted = False
        if kind != "refusal" and result.skill_candidate_id:
            admitted = bool(runner.confirm_outcome(result, cycle=cycle + 1))
        # An INDEPENDENT post-action read (before restore) so I2 can prove the
        # runner's observation is a genuine read of the bytes on disk.
        disk = target.read_text(encoding="utf-8")
        # ── restore the exact pre-case bytes (reversibility) ──
        target.write_bytes(before_bytes)
        post = result.post_observation or {}
        post_state = post.get("state") if isinstance(post, dict) else None
        observed = None
        if isinstance(post_state, dict) and post_state.get("exists"):
            observed = post_state.get("content")
        exec_prov = (result.provenance or {}).get("execution", {}) or {}
        return {
            "kind": kind,
            "cycle": cycle,
            "prediction": result.expected_result,
            "would_be_command": result.would_be_command,
            "mode": result.mode,
            "authorized": bool(result.authorized),
            "authorization_reason": result.authorization_reason,
            "execution": {
                "executed": bool(result.executed),
                "allowed": bool(result.action_allowed),
                "blocked_reason": result.blocked_reason,
                "tool": exec_prov.get("tool"),
                "command": exec_prov.get("command"),
                "permitted_by": exec_prov.get("permitted_by"),
                "permission_id": exec_prov.get("permission_id"),
            },
            "observation": {
                "source": post.get("source") if isinstance(post, dict) else None,
                "observed_content": observed,
                "observation_sha256": (
                    (post_state or {}).get("sha256")
                    if isinstance(post_state, dict) else None),
                "disk_sha256": observation_fingerprint(disk),
                "read_after_execute": bool(
                    (result.provenance or {}).get(
                        "post_action_observation", {}).get("read_after_execute")),
            },
            "reality_gap": (None if result.reality_gap is None
                            else float(result.reality_gap)),
            "verification": result.verification,
            "authority": {
                "change": result.authority_change,
                "state_at_authorization": result.authority_state,
            },
            "admission": {
                "skill_candidate_id": result.skill_candidate_id,
                "admitted": admitted,
                "skill_admitted": bool(result.skill_admitted),
            },
        }

    def run_script(self, cycle: int) -> Dict[str, Any]:
        """Run the whole bounded canary script in one invocation.

        Args:
            cycle: the pipeline cycle.

        Returns:
            The canary record (trace + live evidence + certification outcome).
        """
        refusal = self.guard_refusal(cycle)
        if refusal is not None:
            return self._record_refusal(refusal, cycle)
        registry = self._sandbox_registry()
        if not registry.is_certified_at(CAPABILITY, CertificationTier.SANDBOX):
            return self._record_refusal("sandbox_not_certified", cycle)
        target = self._resolved_target()
        if target is None or not target.is_file():
            return self._record_refusal("canary_target_missing", cycle)

        self._invocations += 1
        before_bytes = target.read_bytes()
        digest_before = _sandbox_digest(str(Path(self.config.workspace_root)))
        cases: List[Dict[str, Any]] = []
        while True:
            kind = self.next_case()
            if kind is None:
                break
            try:
                case = self._run_case(kind, cycle, registry, before_bytes)
            except Exception as e:  # Λ2.3: no silent swallow — recorded, loud
                logger.warning("canary case %r failed: %r", kind, e)
                case = {"kind": kind, "cycle": cycle, "error": repr(e)}
            cases.append(case)
            self._cases.append(case)
            self._actions_done += 1
        self._last_cycle = cycle
        self._completed = True

        # ── reversibility proof (byte-identity + whole-sandbox drift digest) ──
        restored = target.read_bytes() == before_bytes
        digest_after = _sandbox_digest(str(Path(self.config.workspace_root)))
        no_drift = bool(digest_before) and (digest_before == digest_after)
        reversibility = {
            "restored_exact_bytes": bool(restored),
            "sandbox_digest_before": digest_before,
            "sandbox_digest_after": digest_after,
            "no_drift": no_drift,
            "reversible": bool(restored and no_drift),
        }

        live_evidence, live_decision = self._evaluate(cases, registry, cycle)
        record = self._build_record(cycle, cases, reversibility,
                                    live_evidence, live_decision)
        self._last_record = record
        self._persist(record)
        return record

    def maybe_run(self, cycle: int) -> Optional[Dict[str, Any]]:
        """Run at most one bounded canary invocation, subject to every guard.

        Default OFF: when not enabled this returns None and touches nothing
        (byte-identical to a producer without a canary).

        Args:
            cycle: the current pipeline cycle.

        Returns:
            The canary record when it ran (or was refused), else None.
        """
        if not self.config.enabled:
            return None
        if self._completed:
            return None
        if self._last_cycle is not None \
                and (cycle - self._last_cycle) < self.config.min_interval_cycles:
            return None
        if self._invocations >= self.config.max_invocations:
            return None
        return self.run_script(cycle)

    # ── live-evidence evaluation ─────────────────────────────────────────

    def _evaluate(self, cases: List[Dict[str, Any]],
                  registry: CapabilityCertification, cycle: int
                  ) -> tuple:
        """Evaluate the live trace against the certification invariants.

        The live bar composes on top of the SANDBOX tier: the full strengthened
        battery (adversarial >= 3, revocation demonstrated) is the sandbox
        prerequisite; the live canary's bounded script re-checks the LIVE path
        with live-scaled family minimums (>=1 normal, >=1 divergent, >=1 refusal)
        through the SAME ``CertificationWorkflow`` machinery.

        Args:
            cases: the live case traces.
            registry: the sandbox-tier registry (the prerequisite).
            cycle: the pipeline cycle.

        Returns:
            (VarianceEvidence, decision_dict) for the live trace.
        """
        by_kind = {c.get("kind"): c for c in cases if "kind" in c}
        pos = by_kind.get("positive")
        neg = by_kind.get("negative")
        ref = by_kind.get("refusal")
        sandbox_artifact = self._sandbox_artifact()
        sandbox_ev = (sandbox_artifact.get("variance_evidence", {})
                      if isinstance(sandbox_artifact, dict) else {})
        # The SANDBOX tier is the prerequisite: the record must be certified AND
        # the preserved artifact must declare the earned SANDBOX-CERTIFIED state
        # (a record without the artifact is not enough).
        sandbox_certified = bool(
            registry.is_certified_at(CAPABILITY, CertificationTier.SANDBOX)
            and isinstance(sandbox_artifact, dict)
            and sandbox_artifact.get("state") == "SANDBOX-CERTIFIED")

        def _executed(c: Optional[Dict[str, Any]]) -> bool:
            return bool(c and c.get("execution", {}).get("executed"))

        pos_gap = (pos or {}).get("reality_gap")
        neg_gap = (neg or {}).get("reality_gap")
        obs_ok = all(
            (c.get("observation", {}).get("observation_sha256")
             == c.get("observation", {}).get("disk_sha256"))
            for c in cases if _executed(c))
        pred_ok = all(
            c.get("prediction") is not None
            for c in cases if _executed(c))
        neg_diverges = bool(
            neg and neg.get("observation", {}).get("observed_content")
            is not None
            and neg.get("observation", {}).get("observed_content")
            != neg.get("prediction"))
        authority_change = (pos or {}).get("authority", {}).get("change", {})
        neg_authority = (neg or {}).get("authority", {}).get("change", {})
        authority_recalibrated = bool(
            (authority_change.get("changed") is True)
            or (neg_authority.get("changed") is True))
        neg_admitted = bool((neg or {}).get("admission", {}).get("admitted"))
        pos_admitted = bool((pos or {}).get("admission", {}).get("admitted"))
        ref_clean = bool(
            ref is not None
            and ref.get("execution", {}).get("executed") is False
            and ref.get("execution", {}).get("allowed") is False
            and ref.get("reality_gap") is None)

        invariants = {
            "I1": bool(pred_ok and _executed(pos) and _executed(neg)),
            "I2": bool(obs_ok and neg_diverges),
            "I3": bool(pos_gap is not None and abs(float(pos_gap)) < 1e-12
                       and neg_gap is not None
                       and 0.0 < float(neg_gap) <= 1.0
                       and float(neg_gap) > 0.5),
            "I4": authority_recalibrated,
            "I5": bool(not neg_admitted),
            "I6": ref_clean,
            "I7": bool(sandbox_certified),  # revocation inherited from the battery
            "I8": bool(sandbox_certified and ref_clean),
        }
        families = {
            "normal": 1 if _executed(pos) else 0,
            "adversarial": 1 if _executed(neg) else 0,
            "refusal": 1 if ref is not None else 0,
        }
        gaps = [float(g) for g in (pos_gap, neg_gap) if g is not None]
        false_admits = sum(
            1 for c in cases
            if c.get("admission", {}).get("admitted")
            and c.get("kind") == "negative")
        fail_open = sum(
            1 for c in cases
            if c.get("kind") == "refusal"
            and (c.get("execution", {}).get("allowed") is True
                 or c.get("reality_gap") is not None))
        evidence = VarianceEvidence(
            capability=CAPABILITY,
            families=families,
            invariants=invariants,
            measured_gaps=gaps,
            normal_gap_max=(None if pos_gap is None else float(pos_gap)),
            adversarial_gap_min=(None if neg_gap is None else float(neg_gap)),
            adversarial_gap_max=(None if neg_gap is None else float(neg_gap)),
            false_admits=false_admits,
            fail_open_count=fail_open,
            revocation_demonstrated=bool(
                sandbox_ev.get("revocation_demonstrated", False)),
            min_normal_cases=1,
            min_adversarial_cases=1,
            min_refusal_cases=1,
            min_large_gap=0.5,
            source=self.config.artifact_path,
            detail={
                "tier": CertificationTier.LIVE.value,
                "composed_on": CertificationTier.SANDBOX.value,
                "live_scaled_families": True,
                "sandbox_certified": sandbox_certified,
                "pos_admitted": pos_admitted,
            },
        )
        outcomes = []
        if _executed(pos):
            outcomes.append(VerifiedOutcome(
                CAPABILITY, bool((pos.get("verification") or {}).get("matched")),
                float(pos_gap), cycle=cycle, source="live_canary:positive"))
        workflow = CertificationWorkflow(
            min_successes=1, max_gap=0.2, window=5, failure_streak=2,
            require_variance=True)
        decision = workflow.evaluate(CAPABILITY, outcomes, variance=evidence)
        live_bar_met = bool(
            sandbox_certified and decision.action is CertificationAction.CERTIFY)
        decision_dict = decision.to_dict()
        decision_dict["live_bar_met"] = live_bar_met
        decision_dict["sandbox_certified"] = sandbox_certified
        decision_dict["outcomes"] = [o.to_dict() for o in outcomes]
        return evidence, decision_dict

    def _sandbox_artifact(self) -> Dict[str, Any]:
        """Read the preserved sandbox evidence artifact (fail-closed to {}).

        Returns:
            The sandbox artifact dict, or {} when absent/unreadable.
        """
        from telos.core.actions.certification import DEFAULT_SANDBOX_EVIDENCE_PATH
        src = self.config.sandbox_evidence_path or DEFAULT_SANDBOX_EVIDENCE_PATH
        try:
            with open(src, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # ── record + artifact ────────────────────────────────────────────────

    def _record_refusal(self, reason: str, cycle: int) -> Dict[str, Any]:
        """Record a fail-closed refusal (runs nothing, persists the reason).

        Args:
            reason: the machine-readable refusal reason.
            cycle: the pipeline cycle.

        Returns:
            The refusal record.
        """
        rec = {
            "provenance": {"producer": "telos/core/actions/live_canary.py",
                           "source": "first_party"},
            "capability": CAPABILITY,
            "cycle": cycle,
            "outcome": "REFUSED",
            "refusal_reason": reason,
            "config": self.config.to_dict(),
            "executed_any": False,
            "timestamp": time.time(),
        }
        self._refusals.append(rec)
        self._last_record = rec
        # Throttle repeated refusals to the interval cadence (no per-cycle
        # artifact churn when the canary is enabled but not yet eligible).
        self._last_cycle = cycle
        self._persist(rec)
        return rec

    def _build_record(self, cycle: int, cases: List[Dict[str, Any]],
                      reversibility: Dict[str, Any],
                      live_evidence: VarianceEvidence,
                      live_decision: Dict[str, Any]) -> Dict[str, Any]:
        """Assemble the auditable live-canary record.

        Args:
            cycle: the pipeline cycle.
            cases: the case traces.
            reversibility: the reversibility proof.
            live_evidence: the live VarianceEvidence.
            live_decision: the live certification decision (dict).

        Returns:
            The canary record.
        """
        return {
            "provenance": {"producer": "telos/core/actions/live_canary.py",
                           "source": "first_party"},
            "capability": CAPABILITY,
            "cycle": cycle,
            "outcome": "RAN",
            "executed_any": any(
                c.get("execution", {}).get("executed") for c in cases),
            "config": self.config.to_dict(),
            "bounds": {
                "max_actions": self.config.max_actions,
                "actions_done": self._actions_done,
                "min_interval_cycles": self.config.min_interval_cycles,
                "max_invocations": self.config.max_invocations,
            },
            "target": {
                "sandbox_root": self.config.sandbox_root,
                "workspace_root": self.config.workspace_root,
                "target": self.config.target,
                "designated_canary_file": (
                    Path(self.config.target).name == CANARY_TARGET),
            },
            "cases": cases,
            "reversibility": reversibility,
            "live_evidence": live_evidence.to_dict(),
            "live_certification": live_decision,
            "refusals": list(self._refusals),
            "timestamp": time.time(),
        }

    def _persist(self, record: Dict[str, Any]) -> Optional[str]:
        """Write the trace artifact atomically (never raises into the caller).

        Args:
            record: the record to persist.

        Returns:
            The path written, or None on failure (logged loudly).
        """
        path = self.config.artifact_path
        if not path:
            return None
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f"{path}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, default=str)
            os.replace(tmp, path)
            return path
        except Exception as e:
            logger.warning("canary artifact persist failed: %r", e)
            return None

    # ── LIVE-CERTIFIED persistence (explicit operator act) ───────────────

    def persist_live_certification(self) -> Dict[str, Any]:
        """Write the canonical LIVE record iff the live bar was met.

        This NEVER runs automatically from the producer: it is an explicit
        operator act (``live_canary_run.py --persist``). It refuses unless the
        last live evaluation satisfied the bar AND the sandbox tier was held,
        and it always records the refusal otherwise (fail-closed).

        Returns:
            {persisted: bool, reason: str, path: Optional[str]}
        """
        dec = self._live_decision
        if dec is None and self._last_record is not None:
            dec = self._last_record.get("live_certification")
        if not dec or dec.get("live_bar_met") is not True:
            return {"persisted": False,
                    "reason": "live evidence did not satisfy the invariants "
                              "(LIVE-CERTIFIED not achieved; registry unchanged)",
                    "path": None}
        registry = (CapabilityCertification(path=self.config.canonical_path)
                    if self.config.canonical_path
                    else CapabilityCertification())  # canonical LIVE registry
        evidence_detail = dict(dec.get("evidence", {}))
        evidence_detail["tier"] = CertificationTier.LIVE.value
        evidence_detail["source"] = self.config.artifact_path
        record = CertificationRecord(
            capability=CAPABILITY, certified=True,
            certified_by="live_canary",
            evidence=str(dec.get("reason", "")),
            reason=("live producer canary satisfied the certification invariants "
                    "against a disposable sandbox target"),
            certified_cycle=self._last_cycle,
            evidence_detail=evidence_detail,
            tier=CertificationTier.LIVE.value,
        )
        registry.store(record)
        path = registry.save()
        return {"persisted": True, "reason": "LIVE-CERTIFIED persisted",
                "path": path}


__all__ = [
    "LiveCanary", "CanaryConfig", "CAPABILITY", "CANARY_TARGET",
    "DEFAULT_MAX_ACTIONS", "DEFAULT_MIN_INTERVAL_CYCLES", "DEFAULT_SANDBOX_ROOT",
    "DEFAULT_CANARY_ARTIFACT_PATH", "SCRIPT", "canary_enabled",
]
