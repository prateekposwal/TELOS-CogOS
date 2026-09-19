#!/usr/bin/env python3
"""
Certification campaign — loop-correctness under variance, measured not counted.

PATTERN (certify the LOOP, not a pass count — Λ6.5): the ``CertificationWorkflow``
used to decide certification from ">= 3 matching actions". A pass count proves a
capability *can* match; it never proves the loop *detects* divergence, recalibrates
authority, blocks on reduced authority, refuses to admit on a mismatch, or revokes.
This harness drives the REAL ``WorldActionRunner`` + ``FilesystemWriteAdapter``
across a deliberate variance matrix and asserts the loop's OUTCOME per case, then
evaluates the strengthened certification bar on the measured loop invariants.

Variance families exercised (sandbox only, never the repo or user files):
  * normal      — the exact expected result (gap 0.0).
  * near_match  — a one-token / whitespace / unicode divergence (small gap > 0).
  * adversarial — large divergence, wrong target, missing file, target changed
                  between prediction and observation, empty vs non-empty,
                  oversized content (blocked).
  * refusal     — no approval, uncertified, no adapter, capability gate FAIL,
                  adapter mismatch, rate-limit breach, subprocess timeout.

Loop invariants gated on (I1-I9) are defined in ``_loop_invariants``; every one is
measured from the real runs, never asserted.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/certification_campaign.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/certification_campaign.py --ci
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.actions.certification import (  # noqa: E402
    CERTIFICATION_INVARIANTS, CapabilityCertification, CertificationAction,
    CertificationWorkflow, VarianceEvidence, VerifiedOutcome,
)
from telos.core.actions.executor import (  # noqa: E402
    ActionExecutor, ToolPermission,
)
from telos.core.actions.rate_limit import ToolRateLimiter  # noqa: E402
from telos.core.actions.reality_loop import (  # noqa: E402
    CapabilityAuthority, observation_fingerprint, text_reality_gap,
)
from telos.core.actions.world_adapter import (  # noqa: E402
    FilesystemWriteAdapter,
)
from telos.core.actions.world_action import (  # noqa: E402
    ActionMode, LiveApproval, WorldActionProposal, WorldActionRunner,
)
from telos.core.governance.capability_authorization import (  # noqa: E402
    CapabilityStatus, from_dimensions,
)
from telos.core.governance.firewall import DecisionFirewall  # noqa: E402
from telos.core.learning.acquisition import SkillAcquisition  # noqa: E402
from telos.core.ledger.skill_library import SkillLibrary  # noqa: E402
from telos.core.verifier.measurement import provenance  # noqa: E402

PRODUCER = "telos/tools/certification_campaign.py"
ARTIFACT = "telos/audit/certification_campaign.json"
CAPABILITY = "filesystem.write"
TARGET = "notes.md"
OTHER_TARGET = "other.md"
ORIGINAL = "alpha\nbeta\ngamma\n"
EDITED = "alpha\nbeta-edited\ngamma\n"
OTHER_CONTENT = "other content for a different target\n"
NEAR = "alpha\nbeta-editX\ngamma\n"
LARGE = "totally-different\n"
UNICODE = "alpha\nbeta\u2013edited\ngamma\n"
#: The operator-designated throwaway sandbox used ONLY by the controlled LIVE
#: exercise (Part D). Overridable so a reviewer can point it elsewhere.
SANDBOX_ROOT = os.environ.get("TELOS_TOOL_SANDBOX", "/tmp/telos_tool_sandbox")
#: The committed default-off determinism fingerprint (reproducibility_eval.json).
BASELINE_FINGERPRINT = "4ce1a6f54f2e4378"

CAMPAIGN_CRITERIA: List[str] = [
    "I1_prediction_before_action",
    "I2_observation_is_post_action_read",
    "I3_gap_ordered_and_bounded",
    "I4_authority_rises_low_falls_high",
    "I5_reduced_authority_blocks_act",
    "I6_no_admit_on_mismatch",
    "I7_revocation_on_failure_streak",
    "I8_fail_closed_missing_evidence",
    "I9_determinism_preserved",
]


# ── sandbox + loop builders ──────────────────────────────────────────────────

def _mk_ws(*, other: bool = False, seed: bool = True) -> str:
    """Create an isolated throwaway workspace for one campaign case.

    Args:
        other: also create the ``other.md`` decoy target.
        seed: write the canonical target file.

    Returns:
        The workspace root path (inside the system temp dir, never the repo).
    """
    ws = tempfile.mkdtemp(prefix="telos_cert_campaign_")
    if seed:
        pathlib.Path(ws, TARGET).write_text(ORIGINAL)
    if other:
        pathlib.Path(ws, OTHER_TARGET).write_text(OTHER_CONTENT)
    return ws


def _reseed(ws: str, content: str = ORIGINAL) -> None:
    """Restore the canonical target file's content.

    Args:
        ws: the workspace root.
        content: the content to write.
    """
    pathlib.Path(ws, TARGET).write_text(content)


def _executor(ws: str, *, write_limit: int = 1000,
              timeout: float = 30.0) -> ActionExecutor:
    """Build a governed executor with a raised per-minute write ceiling.

    Args:
        ws: the workspace root.
        write_limit: per-minute ``write_file`` ceiling (campaign runs many).
        timeout: per-command timeout (used by the timeout case).

    Returns:
        An ActionExecutor bound to the workspace.
    """
    limiter = ToolRateLimiter(limits={"write_file": write_limit}, max_total=None)
    return ActionExecutor(workspace_root=ws, rate_limiter=limiter,
                          timeout=timeout)


class _RecordingAdapter(FilesystemWriteAdapter):
    """A write adapter that records what it saw at execute() entry (I1)."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.execute_calls = 0
        self.last_prediction: Any = None

    def execute(self, proposal: Any, **kwargs: Any):
        """Record the proposal's prediction, then execute the governed write.

        Args:
            proposal: the WorldActionProposal being executed.
            **kwargs: forwarded to the base adapter.

        Returns:
            The ActionExecution record.
        """
        self.execute_calls += 1
        self.last_prediction = getattr(proposal, "expected_result", None)
        return super().execute(proposal, **kwargs)


class _TamperingAdapter(_RecordingAdapter):
    """After a successful governed write, an EXTERNAL actor changes the target.

    This models "target changed between prediction and observation": the
    prediction was made against the pre-tamper state, so the post-action
    observation MUST differ from it (I2) and produce a non-zero gap.
    """

    def execute(self, proposal: Any, **kwargs: Any):
        """Execute, then tamper the target to simulate an external change.

        Args:
            proposal: the WorldActionProposal being executed.
            **kwargs: forwarded to the base adapter.

        Returns:
            The ActionExecution record.
        """
        result = super().execute(proposal, **kwargs)
        if getattr(result, "allowed", False):
            self._resolved_target().write_text("externally-changed-after-write\n")
        return result


def _proposal(expected: Any = EDITED, *, target: str = TARGET,
              params: Optional[Dict[str, Any]] = None,
              capability: str = CAPABILITY) -> WorldActionProposal:
    """Build a filesystem-write proposal for the campaign.

    Args:
        expected: the predicted full-content result.
        target: the proposal's declared target.
        params: write hunks (defaults to the canonical beta edit).
        capability: the declared capability.

    Returns:
        The WorldActionProposal.
    """
    return WorldActionProposal(
        capability=capability, operation="write_file", target=target,
        expected_result=expected,
        params=(params if params is not None else
                {"old_lines": ["beta"], "new_lines": ["beta-edited"]}),
        evidence={"source": "certification_campaign"}, confidence=0.9, risk=0.1)


def _approval(target: str = TARGET, ident: str = "campaign-1") -> LiveApproval:
    """Build a per-action approval bound to the target/operation.

    Args:
        target: the approval's bound target.
        ident: the approval id.

    Returns:
        The LiveApproval.
    """
    return LiveApproval(CAPABILITY, target, "write_file", "operator", ident)


def _certified_registry(*, by: str = "campaign_bootstrap",
                        evidence: str = "supervised sandbox trial") -> CapabilityCertification:
    """A registry certifying exactly filesystem.write (bootstrap for the battery).

    Args:
        by: the recorded certifier.
        evidence: the recorded evidence reference.

    Returns:
        The CapabilityCertification.
    """
    return CapabilityCertification.from_certified_set(
        {CAPABILITY}, certified_by=by, evidence=evidence,
        reason="certification campaign variance battery")


def _auth_state(authority: Optional[CapabilityAuthority], cycle: int) -> Dict[str, Any]:
    """Read a capability's authority state as a serializable dict.

    Args:
        authority: the authority ledger, or None.
        cycle: the recency cycle.

    Returns:
        The state dict, or an empty dict when no authority is wired.
    """
    if authority is None:
        return {}
    return authority.state(CAPABILITY, now_cycle=cycle).to_dict()


# ── per-case measurement + expectation checks ────────────────────────────────

def _measure(result: Any, *, ws: str, authority: Optional[CapabilityAuthority],
             cycle: int, adapter: Any, admitted: bool,
             before: Optional[Dict[str, Any]] = None,
             after: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extract the auditable measured facts from one runner result.

    Args:
        result: the WorldActionResult.
        ws: the workspace root.
        authority: the authority ledger (or None).
        cycle: the recency cycle.
        adapter: the adapter (for I1's execute-entry prediction).
        admitted: whether the action's skill candidate was admitted.
        before: authority state before the run (or None to read now).
        after: authority state after the run (or None to read now).

    Returns:
        A dict of measured fields.
    """
    path = pathlib.Path(ws, TARGET)
    try:
        disk = path.read_text(encoding="utf-8")
    except OSError:
        disk = None
    post = result.post_observation or {}
    post_state = post.get("state") if isinstance(post, dict) else None
    observed = None
    if isinstance(post_state, dict) and post_state.get("exists"):
        observed = post_state.get("content")
    b = before if before is not None else _auth_state(authority, cycle)
    a = after if after is not None else _auth_state(authority, cycle)
    return {
        "executed": bool(result.executed),
        "action_allowed": bool(result.action_allowed),
        "blocked_reason": result.blocked_reason,
        "expected_result": result.expected_result,
        "predicted": (result.verification or {}).get("predicted"),
        "observed": observed,
        "gap": (None if result.reality_gap is None else float(result.reality_gap)),
        "matched": (None if result.verification is None
                    else bool(result.verification.get("matched"))),
        "admitted": bool(admitted),
        "candidate_id": result.skill_candidate_id,
        "fidelity_before": b.get("fidelity"),
        "fidelity_after": a.get("fidelity"),
        "status_before": b.get("status"),
        "status_after": a.get("status"),
        "authority_before": b or None,
        "authority_after": a or None,
        "disk_content": disk,
        "observation_sha256": (post_state or {}).get("sha256"),
        "disk_sha256": (None if disk is None
                        else observation_fingerprint(disk)),
        "execute_entry_prediction": getattr(adapter, "last_prediction", None),
        "adapter_execute_calls": getattr(adapter, "execute_calls", None),
    }


def _record_case(*, name: str, family: str, description: str,
                 expect: Dict[str, Any],
                 measured: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate one case's declared expectations against its measured facts.

    Args:
        name: the case name.
        family: the variance family.
        description: what the case exercises.
        expect: declared expected outcome fields.
        measured: the measured facts from the real run.

    Returns:
        A case record carrying the per-check pass/fail (the harness fails when
        any check fails — recording is not enough).
    """
    checks: List[Dict[str, Any]] = []

    def chk(label: str, ok: bool, detail: str) -> None:
        checks.append({"name": label, "ok": bool(ok), "detail": detail})

    if "executed" in expect:
        chk("executed", measured["executed"] is expect["executed"],
            f"executed={measured['executed']}")
    if "action_allowed" in expect:
        chk("action_allowed",
            measured["action_allowed"] is expect["action_allowed"],
            f"action_allowed={measured['action_allowed']}")
    br = expect.get("blocked_reason_contains")
    if br is not None:
        got = measured.get("blocked_reason") or ""
        chk("blocked_reason", br in got, f"blocked_reason={got!r}")
    if "gap_band" in expect:
        band, g = expect["gap_band"], measured.get("gap")
        if band == "none":
            ok = g is None
        elif band == "zero":
            ok = g is not None and abs(g) < 1e-12
        elif band == "near":
            ok = g is not None and 0.0 < g <= 0.2
        elif band == "large":
            ok = g is not None and g > 0.2
        elif band == "nonzero":
            ok = g is not None and g > 0.0
        else:
            ok = False
        chk("gap_band", ok, f"band={band} gap={g}")
    if "matched" in expect:
        chk("matched", measured.get("matched") is expect["matched"],
            f"matched={measured.get('matched')}")
    if "admitted" in expect:
        chk("admitted", measured["admitted"] is expect["admitted"],
            f"admitted={measured['admitted']}")
    if "authority" in expect:
        direction = expect["authority"]
        before, after = measured.get("fidelity_before"), measured.get("fidelity_after")
        if direction == "up":
            base = -1.0 if before is None else float(before)
            ok = after is not None and float(after) > base
        elif direction == "down":
            base = 1.0 if before is None else float(before)
            ok = after is not None and float(after) < base
        elif direction == "none":
            ok = before == after
        else:
            ok = False
        chk("authority", ok,
            f"dir={direction} before={before} after={after}")
    if "disk_content" in expect:
        chk("disk_content", measured.get("disk_content") == expect["disk_content"],
            f"disk_content={measured.get('disk_content')!r}")
    if "observed_not_predicted" in expect and expect["observed_not_predicted"]:
        chk("observed_not_predicted",
            measured.get("observed") is not None
            and measured.get("observed") != measured.get("predicted"),
            f"observed={measured.get('observed')!r} "
            f"predicted={measured.get('predicted')!r}")
    if "executor_execute_calls" in expect:
        chk("executor_execute_calls",
            measured.get("adapter_execute_calls") == expect["executor_execute_calls"],
            f"adapter_execute_calls={measured.get('adapter_execute_calls')}")
    if "other_target_content" in expect:
        chk("other_target_content",
            measured.get("other_target_content") == expect["other_target_content"],
            f"other_target_content={measured.get('other_target_content')!r}")
    if "timed_out" in expect:
        chk("timed_out", measured.get("timed_out") is expect["timed_out"],
            f"timed_out={measured.get('timed_out')}")
    return {
        "name": name, "family": family, "description": description,
        "expected": expect, "measured": measured, "checks": checks,
        "passed": all(c["ok"] for c in checks),
    }


def _drive(*, ws: str, proposal: WorldActionProposal, certification: Any,
           approval: Any, mode: ActionMode = ActionMode.LIVE,
           authority: Optional[CapabilityAuthority] = None,
           acquisition: Optional[SkillAcquisition] = None,
           capability_authorization: Any = None,
           adapter: Optional[FilesystemWriteAdapter] = None,
           executor: Optional[ActionExecutor] = None,
           cycle: int = 1, admit: bool = True) -> Tuple[Any, Dict[str, Any], Any]:
    """Run one real loop iteration and measure it.

    Args:
        ws: the workspace root.
        proposal: the proposal to run.
        certification: the certification registry.
        approval: the per-action approval.
        mode: DRY_RUN or LIVE.
        authority: optional CapabilityAuthority.
        acquisition: optional SkillAcquisition for admission.
        capability_authorization: optional explicit capability gates.
        adapter: optional pre-built adapter (bootstrap cases).
        executor: optional pre-built executor.
        cycle: the recency cycle.
        admit: whether to hold confirm_outcome for the candidate.

    Returns:
        (result, measured, adapter)
    """
    ex = executor or _executor(ws)
    ad = adapter or _RecordingAdapter(ex, TARGET)
    runner = WorldActionRunner(
        ex, ad, certification=certification, firewall=DecisionFirewall(),
        authority=authority, acquisition=acquisition)
    before = _auth_state(authority, cycle)
    result = runner.run(proposal, mode, approval=approval,
                        capability_authorization=capability_authorization,
                        cycle=cycle)
    admitted = False
    if admit and acquisition is not None and result.skill_candidate_id:
        admitted = bool(runner.confirm_outcome(result, cycle=cycle + 1))
    after = _auth_state(authority, cycle)
    measured = _measure(result, ws=ws, authority=authority, cycle=cycle,
                        adapter=ad, admitted=admitted, before=before, after=after)
    return result, measured, ad


# ── the variance battery ─────────────────────────────────────────────────────

def _primed_authority(gap: float = 0.0) -> CapabilityAuthority:
    """Build an authority already validated at ``1 - gap`` fidelity.

    Args:
        gap: the priming Reality Gap (0.0 = full fidelity).

    Returns:
        A CapabilityAuthority with one recorded validation.
    """
    a = CapabilityAuthority()
    a.record(CAPABILITY, gap, cycle=0)
    return a


def _normal_window() -> Tuple[List[VerifiedOutcome], Dict[str, Any], Any, Any]:
    """Run three exact-match actions; return real success outcomes + the first.

    Returns:
        (outcomes, first_measured, authority, acquisition)
    """
    ws = _mk_ws()
    auth = CapabilityAuthority()
    acq = SkillAcquisition(SkillLibrary())
    outcomes: List[VerifiedOutcome] = []
    first: Optional[Dict[str, Any]] = None
    for i in range(3):
        _reseed(ws)
        _, m, _ = _drive(ws=ws, proposal=_proposal(EDITED),
                         certification=_certified_registry(),
                         approval=_approval(ident=f"normal-{i}"),
                         authority=auth, acquisition=acq, cycle=i)
        outcomes.append(VerifiedOutcome(
            CAPABILITY, bool(m["matched"]), float(m["gap"]), cycle=i,
            source=f"normal:{i}"))
        if first is None:
            first = m
    return outcomes, first, auth, acq


def _i4_sequence() -> List[Dict[str, Any]]:
    """Run low→high→low gaps and record the authority direction each time.

    Returns:
        Three {before, after, gap} records from the real runs.
    """
    ws = _mk_ws()
    auth = CapabilityAuthority()
    seq: List[Dict[str, Any]] = []
    for cycle, (expected, _tag) in enumerate(
            [(EDITED, "low"), (LARGE, "high"), (EDITED, "low")], start=1):
        _reseed(ws)
        _, m, _ = _drive(ws=ws, proposal=_proposal(expected),
                         certification=_certified_registry(),
                         approval=_approval(ident=f"i4-{cycle}"),
                         authority=auth, cycle=cycle)
        seq.append({"gap": m["gap"], "before": m["fidelity_before"],
                    "after": m["fidelity_after"],
                    "status_before": m["status_before"],
                    "status_after": m["status_after"]})
    return seq


def _i5_reduced_authority_blocks() -> Dict[str, Any]:
    """Drive authority to FAIL, then prove the next ACT is structurally blocked.

    Returns:
        Measured evidence: status, blocked reason, and the execute-seam call
        counts (all zero when the block is structural).
    """
    ws = _mk_ws()
    auth = CapabilityAuthority()
    # One large-divergence action FAILs the authority (fidelity 1-0.667).
    _, m1, _ = _drive(ws=ws, proposal=_proposal(LARGE),
                      certification=_certified_registry(),
                      approval=_approval(ident="i5-fail"),
                      authority=auth, cycle=1)
    status = auth.state(CAPABILITY, now_cycle=1).status
    # Now the next ACT must be blocked BEFORE any execute seam is reached.
    ex = _executor(ws)
    counts = {"structured": 0}
    original = ex._execute_structured_write

    def _spy(permission, record, started):
        counts["structured"] += 1
        return original(permission, record, started)

    ex._execute_structured_write = _spy  # type: ignore[assignment]
    ad = _RecordingAdapter(ex, TARGET)
    _reseed(ws)
    _, m2, _ = _drive(ws=ws, proposal=_proposal(EDITED),
                      certification=_certified_registry(),
                      approval=_approval(ident="i5-block"),
                      authority=auth, adapter=ad, executor=ex, cycle=2)
    return {
        "fail_gap": m1["gap"],
        "status_after_fail": status.value,
        "blocked_executed": m2["executed"],
        "blocked_reason": m2["blocked_reason"],
        "adapter_execute_calls": m2["adapter_execute_calls"],
        "structured_write_calls": counts["structured"],
    }


def _i6_no_admit_on_mismatch() -> Dict[str, Any]:
    """Run a mismatching action and prove the candidate is NOT admitted.

    Returns:
        Measured evidence: candidate id present, admission refused, acquired 0.
    """
    ws = _mk_ws()
    ex = _executor(ws)
    ad = _RecordingAdapter(ex, TARGET)
    acq = SkillAcquisition(SkillLibrary())
    auth = _primed_authority(0.0)
    runner = WorldActionRunner(
        ex, ad, certification=_certified_registry(),
        firewall=DecisionFirewall(), authority=auth, acquisition=acq)
    result = runner.run(_proposal(LARGE), ActionMode.LIVE,
                        approval=_approval(ident="i6"), cycle=1)
    admitted = runner.confirm_outcome(result, cycle=2)
    return {
        "gap": (None if result.reality_gap is None else float(result.reality_gap)),
        "candidate_id": result.skill_candidate_id,
        "admitted": bool(admitted),
        "skill_admitted_flag": bool(result.skill_admitted),
        "acquired": int(acq.stats().get("acquired", 0)),
        "candidates": int(acq.stats().get("candidates", 0)),
    }


def _revocation(revocation_outcomes: List[VerifiedOutcome],
                successes: List[VerifiedOutcome]) -> Dict[str, Any]:
    """Prove a trailing failure streak revokes a certified capability.

    Args:
        revocation_outcomes: real failure outcomes (mismatch, large gap).
        successes: real success outcomes for the window.

    Returns:
        Measured evidence of the revocation decision + applied state.
    """
    wf = CertificationWorkflow(min_successes=3, max_gap=0.2, window=5,
                               failure_streak=2)
    decision = wf.evaluate(CAPABILITY, list(successes) + list(revocation_outcomes))
    reg = _certified_registry()
    before = reg.is_certified(CAPABILITY)
    wf.apply(reg, decision)
    return {
        "action": decision.action.value,
        "after": reg.is_certified(CAPABILITY),
        "before": before,
        "failure_streak": decision.evidence.get("failure_streak"),
        "demonstrated": (decision.action is CertificationAction.REVOKE
                         and before is True
                         and reg.is_certified(CAPABILITY) is False),
    }


def _fail_closed_checks(refusal_cases: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
    """Direct fail-closed probes: missing/malformed evidence never passes.

    Args:
        refusal_cases: measured facts for the refusal cases (by name).

    Returns:
        Mapping of fail-closed probe -> held.
    """
    checks: Dict[str, bool] = {}
    checks["gap_none_observation_is_total_miss"] = (
        text_reality_gap(EDITED, None) == 1.0)
    checks["gap_none_prediction_is_total_miss"] = (
        text_reality_gap(None, EDITED) == 1.0)
    checks["untested_authority_is_unknown"] = (
        CapabilityAuthority().state(CAPABILITY).status
        is CapabilityStatus.UNKNOWN)
    wf = CertificationWorkflow(require_variance=True)
    checks["no_outcomes_holds"] = (
        wf.evaluate(CAPABILITY, []).action is CertificationAction.HOLD)
    checks["variance_missing_holds_even_with_successes"] = (
        wf.evaluate(CAPABILITY, [VerifiedOutcome(CAPABILITY, True, 0.0)
                                 for _ in range(3)]
                    ).action is CertificationAction.HOLD)
    bad = pathlib.Path(tempfile.mkdtemp(prefix="telos_cert_bad_"), "bad.json")
    bad.write_text("{not-json")
    checks["malformed_cert_file_fails_closed"] = (
        CapabilityCertification(path=str(bad)).certified_names() == [])
    checks["explicit_empty_registry_zero_certified"] = (
        CapabilityCertification(records={}).certified_names() == [])
    na = refusal_cases.get("refusal_no_adapter", {})
    checks["no_adapter_refused"] = (
        na.get("executed") is False
        and "no_adapter_configured" in (na.get("blocked_reason") or ""))
    uc = refusal_cases.get("refusal_uncertified", {})
    checks["uncertified_refused"] = (
        uc.get("executed") is False
        and "not CERTIFIED" in (uc.get("blocked_reason") or ""))
    return checks


def _determinism_checks() -> Dict[str, Any]:
    """Measure the default-off determinism fingerprint and structural OFF-state.

    Returns:
        {same_seed_identical, baseline_match, default_config_no_executor,
         explicit_empty_registry_zero_certified, fingerprint}
    """
    from telos.tools.reproducibility_eval import _fingerprint
    from telos.core.runtime import PipelineConfig, TelosV14Pipeline
    a = _fingerprint(15, 42)
    b = _fingerprint(15, 42)
    pipe = TelosV14Pipeline(PipelineConfig())
    return {
        "fingerprint": a[:16],
        "same_seed_identical": a == b,
        "baseline_match": a[:16] == BASELINE_FINGERPRINT,
        "default_config_no_executor": (
            pipe.config.action_executor is None
            and pipe.config.tool_workspace is None),
        "explicit_empty_registry_zero_certified": (
            CapabilityCertification(records={}).certified_names() == []),
    }


def _run_battery() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run the full variance matrix against the real loop.

    Returns:
        (cases, aux) — the per-case records and the auxiliary measured data
        (normal outcomes, I4 sequence, I5/I6 evidence, revocation, fail-closed,
        determinism).
    """
    cases: List[Dict[str, Any]] = []
    aux: Dict[str, Any] = {}

    # ── normal: exact match (3 runs -> real success outcomes) ───────────────
    normal_outcomes, first_normal, _, _ = _normal_window()
    cases.append(_record_case(
        name="normal_exact", family="normal",
        description="governed write with the exact predicted result",
        expect={"executed": True, "action_allowed": True, "gap_band": "zero",
                "matched": True, "admitted": True, "disk_content": EDITED},
        measured=first_normal))
    aux["normal_outcomes"] = normal_outcomes

    # ── near_match: one token changed -> small non-zero gap ─────────────────
    ws = _mk_ws()
    _, m, _ = _drive(ws=ws, proposal=_proposal(NEAR),
                     certification=_certified_registry(),
                     approval=_approval(ident="near"),
                     authority=_primed_authority(0.0),
                     acquisition=SkillAcquisition(SkillLibrary()), cycle=2)
    cases.append(_record_case(
        name="near_match_one_token", family="near_match",
        description="one token changed in the prediction -> small non-zero gap",
        expect={"executed": True, "action_allowed": True, "gap_band": "near",
                "matched": False, "admitted": False, "authority": "down"},
        measured=m))
    aux["near_gap"] = m["gap"]

    # ── adversarial: large divergence ───────────────────────────────────────
    ws = _mk_ws()
    _, m, _ = _drive(ws=ws, proposal=_proposal(LARGE),
                     certification=_certified_registry(),
                     approval=_approval(ident="large"),
                     authority=_primed_authority(0.0),
                     acquisition=SkillAcquisition(SkillLibrary()), cycle=3)
    cases.append(_record_case(
        name="adversarial_large_divergence", family="adversarial",
        description="prediction wholly unrelated to what the action writes",
        expect={"executed": True, "action_allowed": True, "gap_band": "large",
                "matched": False, "admitted": False, "authority": "down"},
        measured=m))
    aux["large_gap"] = m["gap"]
    aux["large_result"] = m

    # ── adversarial: wrong target (proposal names other.md) ─────────────────
    ws = _mk_ws(other=True)
    _, m, _ = _drive(ws=ws, proposal=_proposal(OTHER_CONTENT, target=OTHER_TARGET),
                     certification=_certified_registry(),
                     approval=_approval(target=OTHER_TARGET, ident="wrong-target"),
                     authority=_primed_authority(0.0),
                     acquisition=SkillAcquisition(SkillLibrary()), cycle=4)
    m["other_target_content"] = pathlib.Path(ws, OTHER_TARGET).read_text()
    cases.append(_record_case(
        name="adversarial_wrong_target", family="adversarial",
        description="proposal/approval name other.md; adapter acts on notes.md",
        expect={"executed": True, "action_allowed": True, "gap_band": "large",
                "matched": False, "admitted": False, "authority": "down",
                "other_target_content": OTHER_CONTENT, "disk_content": EDITED},
        measured=m))

    # ── adversarial: target file missing -> refused (nothing written) ───────
    ws = _mk_ws(seed=False)
    _, m, _ = _drive(ws=ws, proposal=_proposal(EDITED),
                     certification=_certified_registry(),
                     approval=_approval(ident="missing"),
                     authority=_primed_authority(0.0), cycle=5)
    cases.append(_record_case(
        name="adversarial_file_missing", family="adversarial",
        description="target file absent -> the governed write refuses",
        expect={"executed": False, "action_allowed": False, "gap_band": "none",
                "admitted": False, "blocked_reason_contains": "action invalid"},
        measured=m))

    # ── adversarial: target changed between prediction and observation ──────
    ws = _mk_ws()
    ex = _executor(ws)
    tamper = _TamperingAdapter(ex, TARGET)
    runner = WorldActionRunner(ex, tamper, certification=_certified_registry(),
                               firewall=DecisionFirewall(),
                               authority=_primed_authority(0.0),
                               acquisition=SkillAcquisition(SkillLibrary()))
    tamper_auth = runner.authority
    before = _auth_state(tamper_auth, 6)
    result = runner.run(_proposal(EDITED), ActionMode.LIVE,
                        approval=_approval(ident="tamper"), cycle=6)
    admitted = bool(runner.confirm_outcome(result, cycle=7)) \
        if result.skill_candidate_id else False
    m = _measure(result, ws=ws, authority=tamper_auth, cycle=6,
                 adapter=tamper, admitted=admitted, before=before,
                 after=_auth_state(tamper_auth, 6))
    cases.append(_record_case(
        name="adversarial_target_changed", family="adversarial",
        description="an external actor changes the target after the write",
        expect={"executed": True, "action_allowed": True, "gap_band": "large",
                "matched": False, "admitted": False, "authority": "down",
                "observed_not_predicted": True,
                "disk_content": "externally-changed-after-write\n"},
        measured=m))

    # ── adversarial: empty vs non-empty prediction ──────────────────────────
    ws = _mk_ws()
    _, m, _ = _drive(ws=ws, proposal=_proposal(""),
                     certification=_certified_registry(),
                     approval=_approval(ident="empty"),
                     authority=_primed_authority(0.0),
                     acquisition=SkillAcquisition(SkillLibrary()), cycle=8)
    cases.append(_record_case(
        name="adversarial_empty_vs_nonempty", family="adversarial",
        description="empty prediction vs a non-empty real result",
        expect={"executed": True, "action_allowed": True, "gap_band": "large",
                "matched": False, "admitted": False, "authority": "down"},
        measured=m))

    # ── adversarial: unicode / whitespace edge ──────────────────────────────
    ws = _mk_ws()
    _, m, _ = _drive(ws=ws, proposal=_proposal(UNICODE),
                     certification=_certified_registry(),
                     approval=_approval(ident="unicode"),
                     authority=_primed_authority(0.0),
                     acquisition=SkillAcquisition(SkillLibrary()), cycle=9)
    cases.append(_record_case(
        name="adversarial_unicode_edge", family="adversarial",
        description="hyphen vs en-dash -> a small, correctly-detected gap",
        expect={"executed": True, "action_allowed": True, "gap_band": "nonzero",
                "matched": False, "admitted": False, "authority": "down"},
        measured=m))

    # ── adversarial: oversized content -> refused by the hunk bound ─────────
    ws = _mk_ws()
    big = {"old_lines": [f"line{i}" for i in range(201)], "new_lines": ["x"]}
    _, m, _ = _drive(ws=ws, proposal=_proposal(EDITED, params=big),
                     certification=_certified_registry(),
                     approval=_approval(ident="oversized"),
                     authority=_primed_authority(0.0), cycle=10)
    cases.append(_record_case(
        name="adversarial_oversized", family="adversarial",
        description="a >200-line hunk is refused before any effect",
        expect={"executed": False, "action_allowed": False, "gap_band": "none",
                "admitted": False, "blocked_reason_contains": "exceeds",
                "disk_content": ORIGINAL},
        measured=m))

    # ── refusal: no per-action approval ─────────────────────────────────────
    ws = _mk_ws()
    _, m, _ = _drive(ws=ws, proposal=_proposal(EDITED),
                     certification=_certified_registry(), approval=None,
                     authority=_primed_authority(0.0), cycle=11)
    cases.append(_record_case(
        name="refusal_no_approval", family="refusal",
        description="certified but no per-action approval -> refused",
        expect={"executed": False, "action_allowed": False, "gap_band": "none",
                "admitted": False,
                "blocked_reason_contains": "per-action approval"},
        measured=m))

    # ── refusal: uncertified capability ─────────────────────────────────────
    ws = _mk_ws()
    _, m, _ = _drive(ws=ws, proposal=_proposal(EDITED),
                     certification=CapabilityCertification(records={}),
                     approval=_approval(ident="uncert"), cycle=12)
    cases.append(_record_case(
        name="refusal_uncertified", family="refusal",
        description="uncertified capability at mode=LIVE -> refused",
        expect={"executed": False, "action_allowed": False, "gap_band": "none",
                "admitted": False, "blocked_reason_contains": "not CERTIFIED"},
        measured=m))

    # ── refusal: no adapter ─────────────────────────────────────────────────
    ws = _mk_ws()
    ex = _executor(ws)
    runner = WorldActionRunner(ex, None, certification=_certified_registry(),
                               firewall=DecisionFirewall())
    result = runner.run(_proposal(EDITED), ActionMode.LIVE,
                        approval=_approval(ident="noadapter"), cycle=13)
    m = _measure(result, ws=ws, authority=None, cycle=13, adapter=None,
                 admitted=False)
    cases.append(_record_case(
        name="refusal_no_adapter", family="refusal",
        description="no adapter configured -> no action path exists",
        expect={"executed": False, "action_allowed": False, "gap_band": "none",
                "admitted": False,
                "blocked_reason_contains": "no_adapter_configured"},
        measured=m))

    # ── refusal: capability gate FAIL ───────────────────────────────────────
    ws = _mk_ws()
    cap_fail = from_dimensions({"model_fidelity": CapabilityStatus.FAIL})
    _, m, _ = _drive(ws=ws, proposal=_proposal(EDITED),
                     certification=_certified_registry(),
                     approval=_approval(ident="gatefail"),
                     capability_authorization=cap_fail, cycle=14)
    cases.append(_record_case(
        name="refusal_capability_gate_fail", family="refusal",
        description="a FAIL capability gate vetoes LIVE (conjunctive gate)",
        expect={"executed": False, "action_allowed": False, "gap_band": "none",
                "admitted": False,
                "blocked_reason_contains": "capability gate failed"},
        measured=m))

    # ── refusal: adapter/capability mismatch ────────────────────────────────
    ws = _mk_ws()
    _, m, _ = _drive(ws=ws, proposal=_proposal(EDITED, capability="other.cap"),
                     certification=_certified_registry(),
                     approval=_approval(ident="mismatch"), cycle=15)
    cases.append(_record_case(
        name="refusal_adapter_mismatch", family="refusal",
        description="proposal capability does not match the adapter",
        expect={"executed": False, "action_allowed": False, "gap_band": "none",
                "admitted": False, "blocked_reason_contains": "action invalid"},
        measured=m))

    # ── refusal: rate-limit breach (2nd write in the window) ────────────────
    ws = _mk_ws()
    ex_rl = ActionExecutor(workspace_root=ws, rate_limiter=ToolRateLimiter(
        limits={"write_file": 1}, max_total=None))
    _, m1, _ = _drive(ws=ws, proposal=_proposal(EDITED),
                      certification=_certified_registry(),
                      approval=_approval(ident="rl-1"), executor=ex_rl, cycle=16)
    _reseed(ws)
    _, m2, _ = _drive(ws=ws, proposal=_proposal(EDITED),
                      certification=_certified_registry(),
                      approval=_approval(ident="rl-2"), executor=ex_rl,
                      adapter=_RecordingAdapter(ex_rl, TARGET), cycle=17)
    cases.append(_record_case(
        name="refusal_rate_limit", family="refusal",
        description="second write in the minute is blocked, no effect",
        expect={"executed": True, "action_allowed": False, "gap_band": "none",
                "admitted": False,
                "blocked_reason_contains": "rate_limit_exceeded",
                "disk_content": ORIGINAL},
        measured=m2))

    # ── refusal: subprocess timeout (same governed executor) ────────────────
    cases.append(_timeout_case())

    return cases, aux


def _timeout_case() -> Dict[str, Any]:
    """Exercise the governed executor's per-command timeout on a real command.

    The structured-write capability spawns no subprocess, so the timeout gate is
    measured on the subprocess tool family through the SAME governed executor.

    Returns:
        The case record for the timeout refusal.
    """
    ws = _mk_ws()
    pathlib.Path(ws, "Makefile").write_text("hang:\n\tsleep 5\n")
    ex = _executor(ws, timeout=0.4)
    execution = ex.execute(
        ToolPermission(tool_name="make_target", args=["hang"], cwd=ws,
                       permitted_by="operator"),
        firewall=DecisionFirewall())
    measured = {
        "executed": False,
        "action_allowed": bool(execution.allowed),
        "blocked_reason": execution.blocked_reason,
        "timed_out": bool(execution.timed_out),
        "returncode": execution.returncode,
        "gap": None, "admitted": False,
        "expected_result": "make hang",
        "disk_content": pathlib.Path(ws, TARGET).read_text(),
    }
    return _record_case(
        name="refusal_timeout", family="refusal",
        description="a hanging command is blocked by the timeout gate",
        expect={"executed": False, "action_allowed": False, "timed_out": True,
                "blocked_reason_contains": "timed out"},
        measured=measured)


# ── loop invariants (the certification bar) ──────────────────────────────────

def _loop_invariants(cases: List[Dict[str, Any]],
                     aux: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Measure the loop invariants I1-I9 from the real battery runs.

    Invariants (each is measured, never asserted):
      I1 a prediction is recorded BEFORE the action (present at execute entry);
      I2 the observation is a genuine post-action read (equals the bytes read
         off disk afterwards and its sha256), and differs from the prediction
         wherever the target changed;
      I3 the gap is correctly ordered (exact < near-match < large divergence)
         and bounded to [0, 1];
      I4 authority RISES on a low gap and FALLS on a high gap;
      I5 reduced authority STRUCTURALLY blocks the next ACT (no execute seam is
         reached);
      I6 no skill is admitted on a mismatch;
      I7 certification is REVOKED on a failure streak;
      I8 the loop is FAIL-CLOSED on missing/malformed evidence;
      I9 determinism is preserved (same-seed fingerprint unchanged; default-OFF).

    Args:
        cases: the per-case records from the battery.
        aux: the auxiliary measured data.

    Returns:
        Mapping invariant name -> {"held": bool, "detail": str}.
    """
    by_name = {c["name"]: c for c in cases}
    executed = [c for c in cases if c["measured"].get("executed")]
    inv: Dict[str, Dict[str, Any]] = {}

    pred_present = all(c["measured"].get("expected_result") is not None
                       for c in cases)
    attempted = [c for c in cases
                 if c["measured"].get("execute_entry_prediction") is not None]
    entry_ok = all(
        c["measured"].get("execute_entry_prediction")
        == c["measured"].get("expected_result")
        for c in attempted)
    inv["I1"] = {
        "held": bool(pred_present and entry_ok and attempted),
        "detail": (f"prediction present for all {len(cases)} cases and equal "
                   f"at execute entry for all {len(attempted)} attempted cases"),
    }

    allowed = [c for c in cases if c["measured"].get("action_allowed") is True]
    sha_ok = all(
        c["measured"].get("observation_sha256") == c["measured"].get("disk_sha256")
        for c in allowed)
    obs_ok = all(
        c["measured"].get("observed") == c["measured"].get("disk_content")
        for c in allowed)
    tamper = by_name["adversarial_target_changed"]["measured"]
    not_echo = tamper.get("observed") != tamper.get("predicted")
    inv["I2"] = {
        "held": bool(sha_ok and obs_ok and not_echo),
        "detail": (f"post-observation == on-disk bytes + sha256 for all "
                   f"{len(allowed)} allowed cases; tampered-target "
                   f"observation {tamper.get('observed')!r} != prediction "
                   f"{tamper.get('predicted')!r}"),
    }

    exact = by_name["normal_exact"]["measured"]["gap"]
    near = by_name["near_match_one_token"]["measured"]["gap"]
    large = by_name["adversarial_large_divergence"]["measured"]["gap"]
    all_gaps = [c["measured"]["gap"] for c in cases
                if c["measured"].get("gap") is not None]
    ordered = (exact == 0.0 and near is not None and large is not None
               and 0.0 < float(near) < float(large))
    bounded = all(0.0 <= float(g) <= 1.0 for g in all_gaps)
    inv["I3"] = {
        "held": bool(ordered and bounded),
        "detail": (f"exact={exact} < near={near} < large={large}; all "
                   f"{len(all_gaps)} measured gaps bounded [0,1]"),
    }

    seq = aux.get("i4_sequence") or []
    fall = bool(seq) and seq[1]["after"] < seq[1]["before"]
    rise = len(seq) > 2 and seq[2]["after"] > seq[2]["before"]
    inv["I4"] = {
        "held": bool(seq and seq[0]["after"] is not None and fall and rise),
        "detail": (f"fidelity sequence {[ (s['before'], s['after']) for s in seq ]}"
                   f" (fall={fall}, rise={rise})"),
    }

    i5 = aux.get("i5") or {}
    i5_held = bool(
        i5.get("status_after_fail") == "FAIL"
        and i5.get("blocked_executed") is False
        and "model_fidelity" in (i5.get("blocked_reason") or "")
        and i5.get("adapter_execute_calls") == 0
        and i5.get("structured_write_calls") == 0)
    inv["I5"] = {
        "held": i5_held,
        "detail": (f"authority {i5.get('status_after_fail')}; next ACT "
                   f"executed={i5.get('blocked_executed')} reason="
                   f"{i5.get('blocked_reason')!r}; execute seams "
                   f"adapter={i5.get('adapter_execute_calls')} "
                   f"structured={i5.get('structured_write_calls')}"),
    }

    i6 = aux.get("i6") or {}
    i6_held = bool(i6.get("candidate_id") and i6.get("admitted") is False
                   and i6.get("skill_admitted_flag") is False
                   and int(i6.get("acquired", 0)) == 0)
    inv["I6"] = {
        "held": i6_held,
        "detail": (f"mismatch gap={i6.get('gap')} candidate="
                   f"{i6.get('candidate_id')} admitted={i6.get('admitted')} "
                   f"acquired={i6.get('acquired')}"),
    }

    rev = aux.get("revocation") or {}
    inv["I7"] = {
        "held": bool(rev.get("demonstrated")),
        "detail": (f"decision={rev.get('action')} certified_before="
                   f"{rev.get('before')} certified_after={rev.get('after')} "
                   f"streak={rev.get('failure_streak')}"),
    }

    fc = aux.get("fail_closed") or {}
    inv["I8"] = {
        "held": bool(fc) and all(fc.values()),
        "detail": f"fail-closed probes {fc}",
    }

    det = aux.get("determinism") or {}
    i9_held = bool(det.get("same_seed_identical") and det.get("baseline_match")
                   and det.get("default_config_no_executor")
                   and det.get("explicit_empty_registry_zero_certified"))
    inv["I9"] = {
        "held": i9_held,
        "detail": (f"fingerprint={det.get('fingerprint')} baseline_match="
                   f"{det.get('baseline_match')} identical="
                   f"{det.get('same_seed_identical')} default_off="
                   f"{det.get('default_config_no_executor')}"),
    }
    return inv


# ── certification decision under the strengthened bar ────────────────────────

def _variance_evidence(cases: List[Dict[str, Any]],
                       invariants: Dict[str, Dict[str, Any]],
                       rev: Dict[str, Any]) -> VarianceEvidence:
    """Build the VarianceEvidence the strengthened workflow judges.

    Args:
        cases: the per-case records.
        invariants: the invariant results (I1..I9).
        rev: the revocation evidence.

    Returns:
        The VarianceEvidence.
    """
    families: Dict[str, int] = {}
    for c in cases:
        families[c["family"]] = families.get(c["family"], 0) + 1
    gaps = [float(c["measured"]["gap"]) for c in cases
            if c["measured"].get("gap") is not None]
    normal_gaps = [float(c["measured"]["gap"]) for c in cases
                   if c["family"] == "normal"
                   and c["measured"].get("gap") is not None]
    divergent = [float(c["measured"]["gap"]) for c in cases
                 if c["family"] in ("near_match", "adversarial")
                 and c["measured"].get("gap") is not None
                 and float(c["measured"]["gap"]) > 0.0]
    false_admits = sum(
        1 for c in cases
        if c["measured"].get("admitted") and c["measured"].get("matched") is False)
    fail_open = sum(
        1 for c in cases
        if c["family"] == "refusal"
        and (c["measured"].get("action_allowed") is True
             or c["measured"].get("gap") is not None))
    return VarianceEvidence(
        capability=CAPABILITY,
        families=families,
        invariants={k: bool(v["held"]) for k, v in invariants.items()},
        measured_gaps=gaps,
        normal_gap_max=(max(normal_gaps) if normal_gaps else None),
        adversarial_gap_min=(min(divergent) if divergent else None),
        adversarial_gap_max=(max(divergent) if divergent else None),
        false_admits=false_admits,
        fail_open_count=fail_open,
        revocation_demonstrated=bool(rev.get("demonstrated")),
        source=ARTIFACT,
    )


def _real_failure_outcomes() -> List[VerifiedOutcome]:
    """Run two real large-divergence actions; return their mismatch outcomes.

    Returns:
        List of two VerifiedOutcome records (matched False, gap > 0).
    """
    ws = _mk_ws()
    out: List[VerifiedOutcome] = []
    for i in range(2):
        _reseed(ws)
        # A fresh authority per failure: the first large-divergence action
        # already drives authority to FAIL, which would (correctly) block the
        # next attempt before it could record anything.
        _, m, _ = _drive(ws=ws, proposal=_proposal(LARGE),
                         certification=_certified_registry(),
                         approval=_approval(ident=f"revoke-{i}"),
                         authority=CapabilityAuthority(), cycle=100 + i)
        out.append(VerifiedOutcome(
            CAPABILITY, bool(m["matched"]), float(m["gap"]), cycle=100 + i,
            source=f"fail:{i}"))
    return out


# ── controlled LIVE exercise (Part D) ────────────────────────────────────────

def _git_status(root: str) -> str:
    """Return ``git status --short`` for a directory (or "" on any failure).

    Args:
        root: the directory to inspect.

    Returns:
        The porcelain status text, or "" when git is unavailable.
    """
    try:
        proc = subprocess.run(["git", "-C", root, "status", "--short"],
                              capture_output=True, text=True, timeout=10)
        return proc.stdout.strip()
    except Exception:
        return ""


def _live_exercise() -> Dict[str, Any]:
    """Run one positive and one negative controlled LIVE action in the sandbox.

    The exercise uses the operator-designated throwaway sandbox (reversible: the
    exact pre-exercise bytes are snapshotted and restored, and the git status is
    compared before/after).

    Returns:
        The live-exercise record (positive + negative + reversibility proof).
    """
    root = SANDBOX_ROOT
    target = "sandbox_notes.md"
    created = False
    if not os.path.isdir(root):
        root = tempfile.mkdtemp(prefix="telos_cert_live_")
        created = True
        pathlib.Path(root, target).write_text(
            "seed line one\nseed line two\nseed line three\n")
    path = pathlib.Path(root, target)
    if not path.is_file():
        path.write_text("seed line one\nseed line two\nseed line three\n")
    original_bytes = path.read_bytes()
    git_before = _git_status(root)

    ex = ActionExecutor(
        workspace_root=root,
        rate_limiter=ToolRateLimiter(limits={"write_file": 1000}, max_total=None))
    adapter = FilesystemWriteAdapter(ex, target)
    registry = _certified_registry(
        by="certification_campaign", evidence=ARTIFACT)
    authority = CapabilityAuthority()
    acq = SkillAcquisition(SkillLibrary())
    runner = WorldActionRunner(
        ex, adapter, certification=registry, firewall=DecisionFirewall(),
        authority=authority, acquisition=acq)

    content = path.read_text(encoding="utf-8")
    had_trailing = content.endswith("\n")
    body = content[:-1] if had_trailing else content
    blines = body.split("\n")
    idx = 1 if len(blines) > 1 else 0
    old_line = blines[idx]
    new_line = "seed line two edited by certification campaign"
    expected_lines = blines[:idx] + [new_line] + blines[idx + 1:]
    expected = "\n".join(expected_lines) + ("\n" if had_trailing else "")

    # ── POSITIVE: correct prediction ────────────────────────────────────────
    pos_authority_before = authority.state(CAPABILITY, now_cycle=1).to_dict()
    pos_prop = WorldActionProposal(
        capability=CAPABILITY, operation="write_file", target=target,
        expected_result=expected,
        params={"old_lines": [old_line], "new_lines": [new_line]},
        evidence={"source": "live_exercise:positive"}, confidence=0.95, risk=0.05)
    pos = runner.run(pos_prop, ActionMode.LIVE,
                     approval=LiveApproval(CAPABILITY, target, "write_file",
                                           "operator", "cert-live-positive"),
                     cycle=1)
    pos_admitted = bool(runner.confirm_outcome(pos, cycle=2)) \
        if pos.skill_candidate_id else False
    pos_after = authority.state(CAPABILITY, now_cycle=1).to_dict()

    # ── NEGATIVE: planted mismatch (wrong prediction) ───────────────────────
    neg_authority_before = authority.state(CAPABILITY, now_cycle=3).to_dict()
    neg_prop = WorldActionProposal(
        capability=CAPABILITY, operation="write_file", target=target,
        expected_result="PLANTED-MISMATCH\n",
        params={"old_lines": [new_line], "new_lines": [new_line + " (v2)"]},
        evidence={"source": "live_exercise:negative"}, confidence=0.95, risk=0.05)
    neg = runner.run(neg_prop, ActionMode.LIVE,
                     approval=LiveApproval(CAPABILITY, target, "write_file",
                                           "operator", "cert-live-negative"),
                     cycle=3)
    neg_admitted = bool(runner.confirm_outcome(neg, cycle=4)) \
        if neg.skill_candidate_id else False
    neg_after = authority.state(CAPABILITY, now_cycle=3).to_dict()

    # ── REVERSIBILITY: restore the exact pre-exercise bytes ─────────────────
    path.write_bytes(original_bytes)
    restored = path.read_bytes() == original_bytes
    git_after = _git_status(root)

    return {
        "capability": CAPABILITY,
        "sandbox_root": root,
        "sandbox_created": created,
        "target": target,
        "positive": {
            "mode": pos.mode,
            "predicted": (pos.verification or {}).get("predicted"),
            "actual_gap": pos.reality_gap,
            "observed": (pos.post_observation or {}).get("state", {}).get("content")
            if isinstance(pos.post_observation, dict) else None,
            "action_allowed": pos.action_allowed,
            "admitted": pos_admitted,
            "authority_fidelity_before": pos_authority_before.get("fidelity"),
            "authority_fidelity_after": pos_after.get("fidelity"),
            "authority_status_before": pos_authority_before.get("status"),
            "authority_status_after": pos_after.get("status"),
        },
        "negative": {
            "mode": neg.mode,
            "predicted": (neg.verification or {}).get("predicted"),
            "actual_gap": neg.reality_gap,
            "observed": (neg.post_observation or {}).get("state", {}).get("content")
            if isinstance(neg.post_observation, dict) else None,
            "action_allowed": neg.action_allowed,
            "admitted": neg_admitted,
            "authority_fidelity_before": neg_authority_before.get("fidelity"),
            "authority_fidelity_after": neg_after.get("fidelity"),
            "authority_status_before": neg_authority_before.get("status"),
            "authority_status_after": neg_after.get("status"),
        },
        "reversibility": {
            "git_status_before": git_before,
            "git_status_after": git_after,
            "restored_exact_bytes": bool(restored),
            "reversible": bool(restored and git_after == git_before),
        },
    }


# ── orchestration + artifact ─────────────────────────────────────────────────

def run_campaign(*, live: bool = True,
                 persist: bool = False) -> Dict[str, Any]:
    """Run the campaign: variance battery -> invariants -> certification -> LIVE.

    Args:
        live: run the controlled LIVE exercise when certification is achieved.
        persist: write the canonical certification record when certification is
            achieved. Default False — the campaign NEVER auto-certifies the
            canonical registry: it reports the evidence-backed decision and
            exercises it in a controlled, in-memory scope for the LIVE run.
            Persisting is an explicit operator act (``--persist``).

    Returns:
        The campaign artifact dict.
    """
    cases, aux = _run_battery()
    aux["i4_sequence"] = _i4_sequence()
    aux["i5"] = _i5_reduced_authority_blocks()
    aux["i6"] = _i6_no_admit_on_mismatch()
    aux["revocation"] = _revocation(
        _real_failure_outcomes(), list(aux["normal_outcomes"]))
    aux["fail_closed"] = _fail_closed_checks(
        {c["name"]: c["measured"] for c in cases if c["family"] == "refusal"})
    aux["determinism"] = _determinism_checks()

    invariants = _loop_invariants(cases, aux)
    evidence = _variance_evidence(cases, invariants, aux["revocation"])

    workflow = CertificationWorkflow(
        min_successes=3, max_gap=0.2, window=5, failure_streak=2,
        require_variance=True)
    decision = workflow.evaluate(CAPABILITY, aux["normal_outcomes"],
                                 variance=evidence)
    certified = decision.action is CertificationAction.CERTIFY

    canonical_written = False
    if certified and persist:
        registry = CapabilityCertification()
        workflow.apply(registry, decision)
        registry.save()
        canonical_written = True

    live_record: Optional[Dict[str, Any]] = None
    if certified and live:
        live_record = _live_exercise()

    criteria = {
        name: bool(invariants[key]["held"])
        for name, key in zip(CAMPAIGN_CRITERIA,
                             ["I1", "I2", "I3", "I4", "I5", "I6", "I7",
                              "I8", "I9"])
    }
    passed = sum(1 for v in criteria.values() if v)
    return {
        "provenance": provenance(PRODUCER, CAMPAIGN_CRITERIA,
                                 source="first_party"),
        "criteria": criteria,
        "verdict": {"passed": passed == len(CAMPAIGN_CRITERIA),
                    "passed_count": passed, "total": len(CAMPAIGN_CRITERIA)},
        "capability": CAPABILITY,
        "sandbox_only": True,
        "variance_matrix": cases,
        "invariants": invariants,
        "variance_evidence": evidence.to_dict(),
        "certification": {
            "decision": decision.to_dict(),
            "certified": certified,
            "canonical_record_written": canonical_written,
            "criteria_strengthened": [
                "battery_exercised_normal_and_divergent",
                "loop_invariants_I1_I8_hold",
                "gap_bounded_normal_and_discriminating_divergent",
                "zero_false_admits",
                "zero_fail_open",
                "revocation_demonstrated",
                "verified_outcome_window",
            ],
        },
        "live_exercise": live_record,
    }


def print_report(artifact: Dict[str, Any]) -> bool:
    """Print the campaign report (variance matrix + invariants + certification).

    Args:
        artifact: the campaign artifact.

    Returns:
        True when every loop invariant held.
    """
    print(f"\n{'TELOS Certification Campaign — loop under variance':^76}")
    print("=" * 76)
    print(f"  {'case':<34}{'family':<12}{'gap':>8}{'ok':>6}")
    for c in artifact["variance_matrix"]:
        gap = c["measured"].get("gap")
        g = "n/a" if gap is None else f"{float(gap):.4f}"
        print(f"  {c['name']:<34}{c['family']:<12}{g:>8}"
              f"{'PASS' if c['passed'] else 'FAIL':>6}")
    print("-" * 76)
    for name, rec in artifact["invariants"].items():
        print(f"  {name:<4}{'PASS' if rec['held'] else 'FAIL':>6}  "
              f"{rec['detail'][:80]}")
    print("-" * 76)
    cert = artifact["certification"]
    dec = cert["decision"]
    print(f"  certification: {dec['action']}  certified={cert['certified']}  "
          f"canonical_written={cert['canonical_record_written']}")
    print(f"    reason: {dec['reason'][:140]}")
    if artifact.get("live_exercise"):
        lv = artifact["live_exercise"]
        print(f"  LIVE exercise: +gap={lv['positive']['actual_gap']} "
              f"admitted={lv['positive']['admitted']} | "
              f"-gap={lv['negative']['actual_gap']} "
              f"admitted={lv['negative']['admitted']} | "
              f"reversible={lv['reversibility']['reversible']}")
    verdict = artifact["verdict"]
    print("=" * 76)
    print(f"CERTIFICATION CAMPAIGN: {'PASS' if verdict['passed'] else 'FAIL'} "
          f"({verdict['passed_count']}/{verdict['total']} loop invariants)")
    return bool(verdict["passed"])


def main() -> int:
    """CLI entry point.

    Returns:
        Process exit code (0 when every loop invariant held).
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless every loop invariant holds")
    ap.add_argument("--json", default=ARTIFACT,
                    help="path to write the campaign JSON")
    ap.add_argument("--no-live", action="store_true",
                    help="skip the controlled LIVE exercise (Part D)")
    ap.add_argument("--persist", action="store_true",
                    help=("explicitly write the canonical certification record "
                          "(operator act; default is NOT to auto-certify)"))
    args = ap.parse_args()
    artifact = run_campaign(live=not args.no_live, persist=args.persist)
    if args.json:
        out = args.json if os.path.isabs(args.json) \
            else os.path.join(PROJECT, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2, default=str)
        print(f"(campaign saved: {out})")
    ok = print_report(artifact)
    if args.ci:
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
