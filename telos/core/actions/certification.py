"""
CapabilityCertification — the per-capability LIVE-execution certification record.

PATTERN (per-capability authority, explicit and individual): a capability name
(e.g. ``"filesystem.write"``) may leave DRY-RUN and perform a controlled LIVE
action ONLY when it is individually CERTIFIED. Certification is a reviewed,
recorded decision — never a global boolean and never inferred from the mere
existence of an adapter. The default registry is EMPTY: at this stage ZERO
capabilities are certified, so LIVE is structurally unreachable until an
operator certifies one by name.

The record is data, not authority: the WorldActionRunner still requires a
per-action approval and the governed executor's four gates. Certification only
answers "has this capability been explicitly certified to leave dry-run?".

Loading fails CLOSED: a missing or malformed record file yields an empty
registry (nothing certified), never a permissive default.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("telos_capability_certification")

# The canonical certification record: a repo-relative JSON file under the audit
# tree. It is a REVIEWED artifact (an operator commits it), not a runtime write.
DEFAULT_CERTIFICATION_PATH = str(
    Path(__file__).resolve().parents[3] / "telos" / "audit" / "capability_certification.json"
)


@dataclass(frozen=True)
class CertificationRecord:
    """The certification state of ONE capability name.

    Attributes:
        capability: the capability name this record certifies (e.g.
            ``"filesystem.write"``).
        certified: True only when an operator explicitly certified it. Default
            False — absence of a record is not certification.
        certified_by: who certified it (operator identity / review reference).
        evidence: the evidence backing the certification (test run, review id).
        reason: the recorded rationale for certifying (or revoking).
        certified_cycle: optional pipeline cycle of certification.
        evidence_detail: optional STRUCTURED evidence (counts / cycles /
            criteria) produced by the certification workflow — the machine-
            readable half of ``evidence``.
    """

    capability: str
    certified: bool = False
    certified_by: str = ""
    evidence: str = ""
    reason: str = ""
    certified_cycle: Optional[int] = None
    evidence_detail: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializable audit record.

        Returns:
            Dict of the record's fields.
        """
        return {
            "capability": self.capability,
            "certified": self.certified,
            "certified_by": self.certified_by,
            "evidence": self.evidence,
            "reason": self.reason,
            "certified_cycle": self.certified_cycle,
            "evidence_detail": self.evidence_detail,
        }


class CapabilityCertification:
    """The registry of per-capability certification records.

    One registry instance is consulted by the WorldActionRunner. An empty
    registry (the default) certifies nothing, so ``mode=LIVE`` is always
    refused. Records can be loaded from the canonical audit JSON or supplied
    explicitly (tests / an operator session).
    """

    def __init__(self, records: Optional[Dict[str, CertificationRecord]] = None,
                 path: Optional[str] = None):
        """Construct a certification registry.

        Args:
            records: explicit mapping capability -> CertificationRecord. When
                provided it WINS (no file load). When None, the canonical file
                at ``path`` (or DEFAULT_CERTIFICATION_PATH) is loaded.
            path: optional record file path (defaults to the canonical audit
                JSON). A missing/malformed file yields an empty registry.
        """
        if records is not None:
            self._records: Dict[str, CertificationRecord] = dict(records)
            self._path: Optional[str] = path
        else:
            self._path = path or DEFAULT_CERTIFICATION_PATH
            self._records = self._load(self._path)

    @classmethod
    def from_certified_set(cls, capabilities, *,
                           certified_by: str = "test",
                           evidence: str = "",
                           reason: str = "explicitly certified",
                           path: Optional[str] = None) -> "CapabilityCertification":
        """Build a registry certifying exactly the named capabilities.

        Args:
            capabilities: iterable of capability names to certify.
            certified_by: identity recorded on each record.
            evidence: evidence recorded on each record.
            reason: rationale recorded on each record.
            path: optional path recorded on the registry (not written).

        Returns:
            A CapabilityCertification certifying only the supplied names.
        """
        records = {
            name: CertificationRecord(
                capability=name, certified=True, certified_by=certified_by,
                evidence=evidence, reason=reason,
            )
            for name in capabilities
        }
        return cls(records=records, path=path)

    @staticmethod
    def _load(path: str) -> Dict[str, CertificationRecord]:
        """Load records from a JSON file, failing CLOSED on any problem.

        Args:
            path: the record file path.

        Returns:
            Mapping capability -> CertificationRecord; empty when the file is
            absent, unreadable, malformed, or declares no certified entries.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning(
                "capability certification file %r unreadable (%s); failing "
                "closed to ZERO certified capabilities", path, e)
            return {}
        records: Dict[str, CertificationRecord] = {}
        if not isinstance(data, dict):
            logger.warning("certification file %r is not a JSON object; "
                           "failing closed", path)
            return records
        for entry in data.get("records", []) or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("capability")
            if not isinstance(name, str) or not name.strip():
                continue
            records[name] = CertificationRecord(
                capability=name,
                certified=bool(entry.get("certified", False)),
                certified_by=str(entry.get("certified_by", "")),
                evidence=str(entry.get("evidence", "")),
                reason=str(entry.get("reason", "")),
                certified_cycle=entry.get("certified_cycle"),
                evidence_detail=(entry.get("evidence_detail")
                                 if isinstance(entry.get("evidence_detail"), dict)
                                 else None),
            )
        # A bare `certified` name-list is also honoured (operator shorthand).
        for name in data.get("certified", []) or []:
            if isinstance(name, str) and name.strip() and name not in records:
                records[name] = CertificationRecord(
                    capability=name, certified=True,
                    certified_by=str(data.get("certified_by", "")),
                    evidence=str(data.get("evidence", "")),
                    reason=str(data.get("reason", "listed as certified")),
                )
        certified = {k: v for k, v in records.items() if v.certified}
        logger.info("capability certification loaded: %d certified (%s)",
                    len(certified), sorted(certified))
        return records

    def is_certified(self, capability: str) -> bool:
        """Whether a capability name is explicitly certified.

        Args:
            capability: the capability name to query.

        Returns:
            True only for a record whose ``certified`` flag is set.
        """
        rec = self._records.get(capability)
        return bool(rec is not None and rec.certified)

    def record_for(self, capability: str) -> Optional[CertificationRecord]:
        """Return the record for a capability, or None when none exists.

        Args:
            capability: the capability name to query.

        Returns:
            The CertificationRecord, or None.
        """
        return self._records.get(capability)

    def certified_names(self) -> List[str]:
        """The sorted capability names currently certified.

        Returns:
            Sorted list of certified capability names.
        """
        return sorted(n for n, r in self._records.items() if r.certified)

    def certify(self, capability: str, *, certified_by: str, evidence: str,
                reason: str, cycle: Optional[int] = None) -> CertificationRecord:
        """Explicitly certify one capability (an operator decision).

        Args:
            capability: the capability name to certify.
            certified_by: who is certifying it.
            evidence: the evidence reference backing the decision.
            reason: the recorded rationale.
            cycle: optional pipeline cycle of certification.

        Returns:
            The written CertificationRecord.
        """
        rec = CertificationRecord(
            capability=capability, certified=True, certified_by=certified_by,
            evidence=evidence, reason=reason, certified_cycle=cycle,
        )
        self._records[capability] = rec
        return rec

    def revoke(self, capability: str, *, reason: str = "",
               certified_by: str = "operator") -> CertificationRecord:
        """Revoke a capability's certification (default not-certified).

        Args:
            capability: the capability name to revoke.
            reason: the recorded rationale for the revocation.
            certified_by: who revoked it.

        Returns:
            The written (not-certified) CertificationRecord.
        """
        rec = CertificationRecord(
            capability=capability, certified=False, certified_by=certified_by,
            reason=reason,
        )
        self._records[capability] = rec
        return rec

    def to_dict(self) -> Dict[str, Any]:
        """Serializable registry state (records + certified set).

        Returns:
            Dict with the per-capability records and the certified name list.
        """
        return {
            "path": self._path,
            "certified": self.certified_names(),
            "records": [r.to_dict() for r in self._records.values()],
        }

    def save(self, path: Optional[str] = None) -> str:
        """Persist the registry to the canonical JSON (operator action).

        Args:
            path: optional destination (defaults to the loaded path).

        Returns:
            The path written.

        Raises:
            ValueError: when no destination path is known.
        """
        dest = path or self._path
        if not dest:
            raise ValueError("no certification path configured")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return dest


class CertificationAction(str, Enum):
    """The action a certification evaluation recommends."""

    CERTIFY = "CERTIFY"
    REVOKE = "REVOKE"
    HOLD = "HOLD"


@dataclass(frozen=True)
class VerifiedOutcome:
    """One verified world-action outcome (the unit of certification evidence).

    Attributes:
        capability: the capability that was exercised.
        matched: whether the post-action observation matched the prediction.
        gap: the measured bounded Reality Gap for the action.
        cycle: the pipeline cycle the action ran at.
        source: provenance of the outcome (e.g. the approval id).
    """

    capability: str
    matched: bool
    gap: float
    cycle: int = 0
    source: str = ""

    @property
    def successful(self) -> bool:
        """Whether this outcome counts as a success (matched)."""
        return bool(self.matched)

    def to_dict(self) -> Dict[str, Any]:
        """Serializable outcome record.

        Returns:
            Dict of the outcome's fields.
        """
        return {
            "capability": self.capability,
            "matched": self.matched,
            "gap": self.gap,
            "cycle": self.cycle,
            "source": self.source,
        }


@dataclass(frozen=True)
class CertificationDecision:
    """The evidence-backed certification recommendation for one capability.

    Attributes:
        capability: the capability evaluated.
        action: CERTIFY / REVOKE / HOLD.
        reason: the human-readable rationale.
        evidence: the structured evidence (counts, window, criteria, cycles).
        certified: the proposed certification state (True only for CERTIFY).
    """

    capability: str
    action: CertificationAction
    reason: str
    evidence: Dict[str, Any]
    certified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializable decision record.

        Returns:
            Dict of the decision's fields (action as its string value).
        """
        return {
            "capability": self.capability,
            "action": self.action.value,
            "reason": self.reason,
            "evidence": dict(self.evidence),
            "certified": self.certified,
        }


class CertificationWorkflow:
    """The principled, fail-closed path from measured behaviour to certification.

    A capability is CERTIFIED only when a bounded window of its MOST RECENT
    verified LIVE outcomes contains at least ``min_successes`` successes (a
    success = ``matched`` AND ``gap <= max_gap``) with NO active failure streak.
    A trailing failure streak of ``failure_streak`` or more REVOKES an existing
    certification. Anything else HOLDs (fail-closed: no evidence is never a
    pass).

    The workflow is a PURE evaluator: it never mutates a registry on its own.
    ``apply`` performs the explicit mutation, and only for a CERTIFY/REVOKE
    decision — a HOLD changes nothing.
    """

    def __init__(self, *, min_successes: int = 3, max_gap: float = 0.2,
                 window: int = 5, failure_streak: int = 2):
        """Configure the certification criteria.

        Args:
            min_successes: successful outcomes required within the window.
            max_gap: the largest gap that still counts as a success.
            window: how many most-recent outcomes are considered.
            failure_streak: trailing failures that force revocation.
        """
        self.min_successes = max(1, int(min_successes))
        self.max_gap = float(max_gap)
        self.window = max(self.min_successes, int(window))
        self.failure_streak = max(1, int(failure_streak))

    def evaluate(self, capability: str,
                 outcomes: Iterable[VerifiedOutcome]) -> CertificationDecision:
        """Evaluate recent outcomes into a certification decision.

        Args:
            capability: the capability being evaluated.
            outcomes: the recorded outcomes (chronological; only the tail
                ``window`` outcomes are considered).

        Returns:
            A CertificationDecision citing the exact counts that justified it.
        """
        rows = [o for o in outcomes if o.capability == capability]
        recent = rows[-self.window:]
        successes = sum(
            1 for o in recent if o.matched and float(o.gap) <= self.max_gap)
        failures = len(recent) - successes
        streak = 0
        for o in reversed(rows):
            if o.matched and float(o.gap) <= self.max_gap:
                break
            streak += 1
        evidence: Dict[str, Any] = {
            "criteria": {
                "min_successes": self.min_successes,
                "max_gap": self.max_gap,
                "window": self.window,
                "failure_streak": self.failure_streak,
            },
            "sample_size": len(recent),
            "total_recorded": len(rows),
            "successes": successes,
            "failures": failures,
            "failure_streak": streak,
            "success_cycles": [o.cycle for o in recent
                               if o.matched and float(o.gap) <= self.max_gap],
            "max_observed_gap": (max((float(o.gap) for o in recent),
                                     default=None)),
        }
        if streak >= self.failure_streak:
            return CertificationDecision(
                capability=capability, action=CertificationAction.REVOKE,
                reason=(f"{streak} consecutive failed verified actions "
                        f"(>= {self.failure_streak}) — certification revoked"),
                evidence=evidence, certified=False)
        if successes >= self.min_successes and streak == 0:
            return CertificationDecision(
                capability=capability, action=CertificationAction.CERTIFY,
                reason=(f"{successes} successful verified actions within the "
                        f"last {self.window} (>= {self.min_successes}) with no "
                        f"failure streak — certified"),
                evidence=evidence, certified=True)
        return CertificationDecision(
            capability=capability, action=CertificationAction.HOLD,
            reason=(f"insufficient evidence: {successes}/{self.min_successes} "
                    f"successes in the window (no evidence is not a pass)"),
            evidence=evidence, certified=False)

    def apply(self, registry: "CapabilityCertification",
              decision: CertificationDecision,
              *, cycle: Optional[int] = None) -> Optional[CertificationRecord]:
        """Apply a decision to a registry (explicit, HOLD changes nothing).

        Args:
            registry: the certification registry to mutate.
            decision: the workflow decision to apply.
            cycle: optional pipeline cycle stamped on a certification.

        Returns:
            The written CertificationRecord for CERTIFY/REVOKE, else None.
        """
        if decision.action == CertificationAction.CERTIFY:
            return self._write(registry, decision, cycle)
        if decision.action == CertificationAction.REVOKE:
            return registry.revoke(
                decision.capability, reason=decision.reason,
                certified_by="certification_workflow")
        return None

    @staticmethod
    def _write(registry: "CapabilityCertification",
               decision: CertificationDecision,
               cycle: Optional[int]) -> CertificationRecord:
        """Write a structured certification record (evidence_detail attached).

        Args:
            registry: the registry to mutate.
            decision: a CERTIFY decision.
            cycle: optional pipeline cycle.

        Returns:
            The written CertificationRecord.
        """
        rec = CertificationRecord(
            capability=decision.capability, certified=True,
            certified_by="certification_workflow",
            evidence=decision.reason,
            reason=str(decision.evidence),
            certified_cycle=cycle,
            evidence_detail=dict(decision.evidence),
        )
        registry._records[decision.capability] = rec
        return rec


__all__ = [
    "CertificationRecord", "CapabilityCertification", "DEFAULT_CERTIFICATION_PATH",
    "CertificationAction", "VerifiedOutcome", "CertificationDecision",
    "CertificationWorkflow",
]
