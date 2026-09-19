"""
WorldActionRunner — dry-run (item 4) and controlled LIVE (item 5) execution.

PATTERN (predict, act through an authorized capability, observe, measure the
gap): the runner is the one place a WorldAdapter's action leaves the building.
It makes the ACTION / AUTHORITY / MODE record explicit and auditable, and it
makes LIVE structurally unreachable without ALL of:

    1. mode = LIVE                              (explicit, per call)
    2. the capability is CERTIFIED               (per-capability record)
    3. an explicit PER-ACTION approval           (LiveApproval or a genuine
                                                  fail-closed HumanGateway verdict)
    4. the action validates + the capability gates pass
    5. an adapter exists and matches the proposal

DRY-RUN (the default) runs ``observe()`` + ``validate_action()`` + the full
action-authority chain and produces the exact would-be command, but executes
NOTHING: no subprocess, no network, no file write. The firewall re-audit is an
execution-substrate gate applied only in LIVE because inspecting mutates the
firewall's own loop ledger — a dry-run must not perturb governance state.

LIVE captures the full feedback record: predicted result, actual result,
Reality Gap, evidence provenance, and the authority change (fidelity before ->
after, via the injected RealityGapTracker). The outcome then routes through the
existing verification-before-admission discipline: a skill candidate is
PROPOSED on execution and admitted ONLY when a later ``verify_result()`` holds
(``confirm_outcome``). Default remains OFF and DRY-RUN: with no certification
record, LIVE is refused.

Items 6-10 (post-action observation loops, Reality-Gap workflows, authority
recalibration, per-capability certification workflow, structural-impossibility
testing) attach at ``confirm_outcome`` / the authority sink without changing
this runner's contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

import numpy as np

from telos.core.actions.certification import CapabilityCertification
from telos.core.actions.world_adapter import WorldAdapter, WorldObservation


class ActionMode(str, Enum):
    """The execution mode of a world action."""

    DRY_RUN = "DRY_RUN"
    LIVE = "LIVE"


@dataclass(frozen=True)
class LiveApproval:
    """An explicit, PER-ACTION authorization for a LIVE world action.

    A standing boolean is deliberately not accepted: the approval is bound to
    one capability + target + operation, so authority is granted for exactly
    the action reviewed, never a blanket "tools on" switch.

    Attributes:
        capability: the capability name this approval authorizes.
        target: the action target this approval is bound to.
        operation: the operation this approval is bound to.
        approver: "operator" or "human_gateway" (a recognized authorizer).
        approval_id: the audit id linking the approval to its review.
        decision_source: provenance of the approval ("explicit" / "auto").
    """

    capability: str
    target: str
    operation: str
    approver: str
    approval_id: str
    decision_source: str = "explicit"

    def to_dict(self) -> Dict[str, Any]:
        """Serializable approval record.

        Returns:
            Dict of the approval's fields.
        """
        return {
            "capability": self.capability,
            "target": self.target,
            "operation": self.operation,
            "approver": self.approver,
            "approval_id": self.approval_id,
            "decision_source": self.decision_source,
        }

    @classmethod
    def from_human_verdict(cls, verdict: Any,
                           proposal: "WorldActionProposal") -> Optional["LiveApproval"]:
        """Convert an approved HumanVerdict into a per-action approval.

        Fail-closed: a None verdict, a non-approved verdict, or a verdict whose
        decision_source is "fail_closed" yields None (never an approval).

        Args:
            verdict: the HumanVerdict returned by the HumanGateway.
            proposal: the proposal the approval is bound to.

        Returns:
            A LiveApproval when the verdict is a genuine approval, else None.
        """
        if verdict is None or not getattr(verdict, "approved", False):
            return None
        if getattr(verdict, "decision_source", "") == "fail_closed":
            return None
        approval_id = f"hg_{getattr(verdict, 'timestamp', 0.0)}"
        return cls(
            capability=proposal.capability,
            target=proposal.target,
            operation=proposal.operation,
            approver="human_gateway",
            approval_id=approval_id,
            decision_source=getattr(verdict, "decision_source", "explicit"),
        )


@dataclass
class WorldActionProposal:
    """A proposed real-world action awaiting dry-run / LIVE execution.

    Attributes:
        capability: the capability name (must match the adapter).
        operation: the operation name (must match the adapter).
        target: what the action acts upon (e.g. the file path).
        expected_result: the predicted observable result.
        params: operation-specific parameters (e.g. the write hunks).
        evidence: the evidence provenance backing the prediction.
        confidence: 0..1 confidence in the prediction.
        risk: 0..1 assessed risk of the action.
    """

    capability: str
    operation: str
    target: str
    expected_result: Any = None
    params: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    risk: float = 0.0


@dataclass
class WorldActionResult:
    """The complete auditable record of a dry-run or LIVE world action.

    Attributes mirror the ACTION / AUTHORITY / MODE header the runner emits,
    plus the LIVE feedback fields (predicted/actual/gap/authority change).
    """

    capability: str
    operation: str
    target: str
    expected_result: Any = None
    mode: str = ActionMode.DRY_RUN.value
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    risk: float = 0.0
    would_be_command: str = ""
    authorized: bool = False
    authorization_reason: str = ""
    certification: Optional[Dict[str, Any]] = None
    approval: Optional[Dict[str, Any]] = None
    executed: bool = False
    action_allowed: bool = False
    actual_result: Any = None
    reality_gap: Optional[float] = None
    verification: Optional[Dict[str, Any]] = None
    blocked_reason: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    authority_change: Dict[str, Any] = field(default_factory=dict)
    skill_candidate_id: Optional[str] = None
    skill_admitted: bool = False
    observer: Optional[Dict[str, Any]] = None
    #: The GENUINE post-action observation (item 6): a fresh real-world read
    #: taken AFTER execute(), distinct from the execution's own return value.
    post_observation: Optional[Dict[str, Any]] = None
    #: The measured capability authority at authorization time (item 8).
    authority_state: Optional[Dict[str, Any]] = None
    cycle: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serializable audit record (trace/artifact-ready).

        Returns:
            Dict of every field (the ACTION/AUTHORITY/MODE record).
        """
        return {
            "action": {
                "target": self.target,
                "operation": self.operation,
                "expected_result": self.expected_result,
                "would_be_command": self.would_be_command,
            },
            "authority": {
                "capability": self.capability,
                "evidence": self.evidence,
                "confidence": self.confidence,
                "risk": self.risk,
                "authorized": self.authorized,
                "reason": self.authorization_reason,
                "certification": self.certification,
                "approval": self.approval,
            },
            "mode": self.mode,
            "executed": self.executed,
            "action_allowed": self.action_allowed,
            "actual_result": self.actual_result,
            "reality_gap": self.reality_gap,
            "verification": self.verification,
            "blocked_reason": self.blocked_reason,
            "provenance": self.provenance,
            "authority_change": self.authority_change,
            "skill_candidate_id": self.skill_candidate_id,
            "skill_admitted": self.skill_admitted,
            "observer": self.observer,
            "post_observation": self.post_observation,
            "authority_state": self.authority_state,
            "cycle": self.cycle,
        }

    def render(self) -> str:
        """Render the human-readable ACTION / AUTHORITY / MODE block.

        Returns:
            Multi-line string summarizing the decision record.
        """
        return (
            f"ACTION:    target: {self.target} · operation: {self.operation} · "
            f"expected_result: {self.expected_result!r}\n"
            f"AUTHORITY: capability: {self.capability} · "
            f"evidence: {self.evidence} · confidence: {self.confidence} · "
            f"risk: {self.risk}\n"
            f"MODE:      {self.mode}"
        )


def _failure_fingerprint(proposal: WorldActionProposal) -> str:
    """The stable situation fingerprint for a proposal's skill candidate.

    Args:
        proposal: the proposal to fingerprint.

    Returns:
        A deterministic fingerprint string.
    """
    return f"world_action:{proposal.capability}:{proposal.target}:{proposal.operation}"


class WorldActionRunner:
    """Executes world actions in DRY_RUN (default) or controlled LIVE."""

    def __init__(self, executor: Any, adapter: Optional[WorldAdapter], *,
                 certification: Optional[CapabilityCertification] = None,
                 firewall: Any = None,
                 acquisition: Any = None,
                 reality_gap_tracker: Any = None,
                 model_id: Optional[str] = None,
                 authority: Any = None):
        """Construct the runner over the execution substrate + an adapter.

        Args:
            executor: the governed ActionExecutor (may be None = channel OFF).
            adapter: the WorldAdapter realizing one capability (None = no
                action; the runner refuses every proposal).
            certification: the per-capability certification registry (default
                empty — LIVE is refused).
            firewall: the DecisionFirewall used for LIVE execution audits.
            acquisition: optional SkillAcquisition for verification-before-
                admission (candidate proposed on LIVE, admitted on a later
                hold of verify_result()).
            reality_gap_tracker: optional RealityGapTracker for the authority
                change (fidelity before -> after).
            model_id: the model id under which the action outcome is recorded
                in the RealityGapTracker.
            authority: optional CapabilityAuthority (item 8). When wired, the
                per-capability model_fidelity gate is DERIVED from the
                capability's measured Reality Gap, and the outcome
                recalibrates it. A FAIL blocks ACT through the existing
                CapabilityAuthorization machinery.
        """
        self.executor = executor
        self.adapter = adapter
        self.certification = certification or CapabilityCertification()
        self.firewall = firewall
        self.acquisition = acquisition
        self.reality_gap_tracker = reality_gap_tracker
        self.model_id = model_id
        self.authority = authority

    # ── authority helpers ────────────────────────────────────────────────

    def _check_approval(self, approval: Any,
                        proposal: WorldActionProposal) -> tuple:
        """Validate the LIVE per-action approval.

        Args:
            approval: a LiveApproval, a HumanVerdict, a bool, or None.
            proposal: the proposal being authorized.

        Returns:
            (ok, reason) — ok is True only for a matching per-action approval.
        """
        if approval is None:
            return False, "LIVE requires an explicit per-action approval (none provided)"
        if isinstance(approval, bool):
            return False, ("a standing boolean is not a per-action approval; "
                           "provide a LiveApproval")
        if not isinstance(approval, LiveApproval):
            converted = LiveApproval.from_human_verdict(approval, proposal)
            if converted is None:
                return False, "LIVE approval denied or fail-closed (no approval)"
            approval = converted
        if approval.capability != proposal.capability:
            return False, ("approval capability does not match the proposal "
                           "capability")
        if approval.target != proposal.target \
                or approval.operation != proposal.operation:
            return False, "approval is not bound to this target/operation"
        if approval.approver not in ("operator", "human_gateway"):
            return False, (f"approval source {approval.approver!r} is not a "
                           "recognized authorizer")
        if not approval.approval_id:
            return False, "approval lacks an approval_id (not auditable)"
        return True, "approved"

    def _capability_status(self, proposal: WorldActionProposal,
                           capability_authorization: Any) -> tuple:
        """Evaluate the capability-authorization gates for the proposal.

        Args:
            proposal: the proposal being authorized.
            capability_authorization: a CapabilityAuthorization, or None.

        Returns:
            (ok, reason, detail) — ok is False when any required gate is FAIL.
        """
        if capability_authorization is None:
            return True, "no capability authorization supplied", {"checked": False}
        required = self.adapter.required_gates() if self.adapter else []
        checked: Dict[str, str] = {}
        failed = []
        for gate_name in required:
            gate = capability_authorization.gate(gate_name) \
                if hasattr(capability_authorization, "gate") else None
            status = getattr(getattr(gate, "status", None), "value", None)
            checked[gate_name] = status or "UNKNOWN"
            if status == "FAIL":
                failed.append(gate_name)
        if failed:
            return (False, f"capability gate failed: {'/'.join(failed)}",
                    {"required": required, "observed": checked})
        return (True, "capability gates pass",
                {"required": required, "observed": checked})

    # ── the main entry point ─────────────────────────────────────────────

    def run(self, proposal: WorldActionProposal,
            mode: ActionMode = ActionMode.DRY_RUN, *,
            approval: Any = None,
            capability_authorization: Any = None,
            cycle: int = 0) -> WorldActionResult:
        """Run a proposal in DRY_RUN (no effect) or controlled LIVE.

        Args:
            proposal: the WorldActionProposal to run.
            mode: ActionMode.DRY_RUN (default) or ActionMode.LIVE.
            approval: per-action authorization (LiveApproval / HumanVerdict);
                required for LIVE.
            capability_authorization: optional CapabilityAuthorization gates.
            cycle: the pipeline cycle for provenance/authority stamping.

        Returns:
            The complete WorldActionResult audit record.
        """
        mode_value = (mode.value if isinstance(mode, ActionMode)
                      else str(mode).upper())
        record = WorldActionResult(
            capability=proposal.capability, operation=proposal.operation,
            target=proposal.target, expected_result=proposal.expected_result,
            mode=mode_value, evidence=dict(proposal.evidence),
            confidence=proposal.confidence, risk=proposal.risk, cycle=cycle,
        )
        if mode_value not in (ActionMode.DRY_RUN.value, ActionMode.LIVE.value):
            record.blocked_reason = f"unknown action mode {mode_value!r}"
            record.authorization_reason = record.blocked_reason
            return record

        # 0. No adapter -> no action (the adapter is the capability's existence).
        if self.adapter is None or self.executor is None:
            record.blocked_reason = "no_adapter_configured"
            record.authorization_reason = record.blocked_reason
            return record

        record.provenance["adapter"] = self.adapter.descriptor()

        # 1. Observe the real-world state (no effect) — always, both modes.
        observation = self.adapter.observe()
        record.observer = observation.to_dict()
        record.provenance["observed_source"] = observation.source

        # 2. Validate the action (pure; builds the would-be command).
        validation = self.adapter.validate_action(proposal)
        record.would_be_command = validation.command
        record.provenance["validation"] = validation.to_dict()

        # 3. Capability-authorization gates. When a CapabilityAuthority is
        #    wired, the model_fidelity gate is the capability's MEASURED
        #    authority (item 8) — a FAIL vetoes through the existing machinery.
        cap_auth = capability_authorization
        if self.authority is not None:
            record.authority_state = self.authority.state(
                proposal.capability, now_cycle=cycle).to_dict()
            if cap_auth is None:
                cap_auth = self.authority.capability_authorization(
                    proposal.capability, now_cycle=cycle)
        cap_ok, cap_reason, cap_detail = self._capability_status(
            proposal, cap_auth)
        record.provenance["capability_gates"] = cap_detail
        record.provenance["authority_gate"] = dict(record.authority_state or {})

        # 4. Certification (per capability).
        cert_rec = self.certification.record_for(proposal.capability)
        record.certification = (cert_rec.to_dict() if cert_rec is not None
                                else {"capability": proposal.capability,
                                      "certified": False,
                                      "reason": "no certification record"})
        certified = self.certification.is_certified(proposal.capability)

        # 5. Approval (per action) — evaluated for both modes so DRY_RUN shows
        #    the would-be LIVE readiness honestly.
        converted = approval
        if approval is not None and not isinstance(approval, (LiveApproval, bool)):
            converted = LiveApproval.from_human_verdict(approval, proposal)
        approval_ok, approval_reason = self._check_approval(converted, proposal)
        record.approval = (converted.to_dict()
                           if isinstance(converted, LiveApproval) else None)

        # 6. The combined action-authority decision.
        if not validation.valid:
            record.authorized = False
            record.authorization_reason = f"action invalid: {validation.reason}"
        elif not cap_ok:
            record.authorized = False
            record.authorization_reason = cap_reason
        elif mode_value == ActionMode.LIVE.value:
            if not certified:
                record.authorized = False
                record.authorization_reason = (
                    f"capability {proposal.capability!r} is not CERTIFIED "
                    "(LIVE refused)")
            elif not approval_ok:
                record.authorized = False
                record.authorization_reason = approval_reason
            else:
                record.authorized = True
                record.authorization_reason = "authorized"
        else:
            # DRY_RUN: authorized means "would be authorized"; execution still
            # never happens in this mode.
            record.authorized = validation.valid and cap_ok
            record.authorization_reason = "authorized (dry-run)"

        # 7. DRY-RUN stops here: no execution, no effect.
        if mode_value == ActionMode.DRY_RUN.value:
            record.executed = False
            return record

        # 8. LIVE: every gate must hold; refusal records a reason.
        if not validation.valid:
            record.blocked_reason = f"action invalid: {validation.reason}"
            return record
        if not cap_ok:
            record.blocked_reason = cap_reason
            return record
        if not certified:
            record.blocked_reason = (
                f"capability {proposal.capability!r} is not CERTIFIED "
                "(LIVE refused, dry-run allowed)")
            return record
        if not approval_ok:
            record.blocked_reason = approval_reason
            return record

        # 9. Execute through the governed executor (adapter delegates).
        approver = converted.approver if isinstance(converted, LiveApproval) \
            else "operator"
        execution = self.adapter.execute(
            proposal, firewall=self.firewall,
            capability=cap_auth,
            permitted_by=approver,
        )
        record.executed = True
        record.action_allowed = bool(execution.allowed)
        record.provenance["execution"] = {
            "tool": execution.tool_name,
            "command": execution.command,
            "allowed": execution.allowed,
            "blocked_reason": execution.blocked_reason,
            "returncode": execution.returncode,
            "stdout_tail": execution.stdout[-400:],
            "permitted_by": execution.permitted_by,
            "permission_id": execution.permission_id,
        }
        if not execution.allowed:
            record.blocked_reason = execution.blocked_reason
            return record

        # 10. Observe what actually happened (a GENUINE post-action read,
        #     item 6) and measure the Reality Gap (item 7).
        actual = self.adapter.observe()
        record.actual_result = actual.to_dict()
        record.post_observation = actual.to_dict()
        verification = self.adapter.verify_result(proposal.expected_result, actual)
        record.verification = verification.to_dict()
        record.reality_gap = float(verification.reality_gap)
        record.provenance["post_action_observation"] = {
            "source": actual.source,
            "sha256": (actual.state or {}).get("sha256")
            if isinstance(actual.state, dict) else None,
            "read_after_execute": True,
        }
        record.provenance["reality_gap"] = {
            "metric": verification.metric,
            "value": record.reality_gap,
            "matched": verification.matched,
        }

        # 11. Authority change (fidelity before -> after) when a tracker is
        #     wired; otherwise honestly recorded as deferred.
        record.authority_change = self._record_authority(
            proposal, verification, cycle)

        # 12. Verification-before-admission: PROPOSE only. Admission waits for
        #     a later verify_result() hold (confirm_outcome).
        if self.acquisition is not None:
            candidate = self.acquisition.propose(
                fingerprint=_failure_fingerprint(proposal),
                trajectory={
                    "capability": proposal.capability,
                    "operation": proposal.operation,
                    "target": proposal.target,
                    "expected_result": proposal.expected_result,
                    "would_be_command": record.would_be_command,
                },
                cycle=cycle,
                context={"reality_gap": record.reality_gap,
                         "evidence": proposal.evidence},
                source="world_action",
            )
            record.skill_candidate_id = candidate.candidate_id
            record.skill_admitted = False
        return record

    def _record_authority(self, proposal: WorldActionProposal,
                          verification: Any, cycle: int) -> Dict[str, Any]:
        """Record the outcome's authority (fidelity) change.

        Args:
            proposal: the executed proposal.
            verification: the VerificationResult of the action.
            cycle: the pipeline cycle of the observation.

        Returns:
            Dict describing the capability's authority change (or an honest
            "deferred" marker when no RealityGapTracker is wired).
        """
        measured = float(verification.reality_gap)
        if self.authority is not None:
            before = self.authority.state(proposal.capability, now_cycle=cycle)
            after = self.authority.record(
                proposal.capability, measured, cycle=cycle)
            changed = (before.status != after.status
                       or before.fidelity != after.fidelity)
            return {
                "capability": proposal.capability,
                "model_id": after.model_id,
                "status_before": before.status.value,
                "status_after": after.status.value,
                "fidelity_before": before.fidelity,
                "fidelity_after": after.fidelity,
                "changed": bool(changed),
                "observed_gap": measured,
                "authority_before": before.to_dict(),
                "authority_after": after.to_dict(),
                "reason": (f"authority recalibrated from measured Reality Gap "
                           f"{measured:.4f}: {before.status.value} -> "
                           f"{after.status.value}"
                           if changed else
                           f"authority unchanged after gap {measured:.4f}"),
            }
        if self.reality_gap_tracker is None or not self.model_id:
            return {
                "capability": proposal.capability,
                "changed": False,
                "reason": ("no RealityGapTracker/authority wired — authority "
                           "recalibration is the items 6-10 seam"),
            }
        tracker = self.reality_gap_tracker
        before = tracker.model_fidelity(self.model_id, now_cycle=cycle)
        # Encode the measured bounded gap so the tracker MD equals it.
        predicted = np.array([1.0])
        observed = np.array([float(np.clip(1.0 - measured, 0.0, 1.0))])
        gap = tracker.record(self.model_id, predicted, observed, cycle=cycle)
        after = tracker.model_fidelity(self.model_id, now_cycle=cycle)
        changed = (before != after)
        return {
            "capability": proposal.capability,
            "model_id": self.model_id,
            "fidelity_before": before,
            "fidelity_after": after,
            "changed": bool(changed),
            "observed_gap": float(gap),
            "reason": ("authority recalibrated from the measured Reality Gap"
                       if changed else "no authority change"),
        }

    def confirm_outcome(self, result: WorldActionResult, *,
                        observation: Optional[WorldObservation] = None,
                        cycle: int = 0) -> bool:
        """Admit a LIVE action's skill candidate on a LATER verified result.

        Verification-before-admission: the candidate proposed at execution is
        admitted ONLY when ``verify_result()`` holds against a later
        observation. A mismatch (or a non-LIVE/non-allowed result) admits
        nothing.

        Args:
            result: the WorldActionResult returned by ``run``.
            observation: the later observation to verify against (defaults to a
                fresh ``observe()``).
            cycle: the pipeline cycle of the later observation.

        Returns:
            True only when the candidate was verified and admitted.
        """
        if self.acquisition is None or not result.skill_candidate_id:
            return False
        if result.mode != ActionMode.LIVE.value or not result.action_allowed:
            return False
        if self.adapter is None:
            return False
        obs = observation if observation is not None else self.adapter.observe()
        verification = self.adapter.verify_result(result.expected_result, obs)
        result.verification = verification.to_dict()
        result.reality_gap = float(verification.reality_gap)
        if not verification.matched:
            return False
        outcome = 1.0 - float(verification.reality_gap)
        admitted = bool(self.acquisition.verify(
            result.skill_candidate_id, outcome=outcome, cycle=cycle))
        result.skill_admitted = admitted
        return admitted


__all__ = [
    "ActionMode", "LiveApproval", "WorldActionProposal", "WorldActionResult",
    "WorldActionRunner",
]
