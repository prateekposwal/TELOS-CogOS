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
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("telos_capability_certification")

# The canonical certification record: a repo-relative JSON file under the audit
# tree. It is a REVIEWED artifact (an operator commits it), not a runtime write.
DEFAULT_CERTIFICATION_PATH = str(
    Path(__file__).resolve().parents[3] / "telos" / "audit" / "capability_certification.json"
)

#: The SEPARATE sandbox-evidence artifact: the durable record of the earned
#: SANDBOX-CERTIFIED state. It is deliberately NOT the canonical LIVE registry
#: (``capability_certification.json``) — sandbox evidence is preserved and
#: cited, never promoted. A sandbox record in the canonical file is ignored by
#: the loader (fail-closed); it only counts at the SANDBOX tier for the bounded
#: live-producer canary.
DEFAULT_SANDBOX_EVIDENCE_PATH = str(
    Path(__file__).resolve().parents[3] / "telos" / "audit" / "sandbox_certification.json"
)


class CertificationTier(str, Enum):
    """The evidence tier a certification record rests on.

    The two-tier distinction is fail-closed by construction:

      * ``SANDBOX`` — the earned sandbox evidence (variance battery + loop
        invariants I1-I8) is preserved and cited, but it is NOT LIVE
        certification. A sandbox record never authorizes production LIVE and is
        ignored by the canonical LIVE registry loader. It authorizes exactly
        one thing: the bounded, disposable-target live-producer canary.
      * ``LIVE`` — live evidence satisfied the same certification invariants.
        Only a LIVE-tier record may be persisted to the canonical registry and
        counted as certified-to-leave-dry-run.
    """

    SANDBOX = "SANDBOX"
    LIVE = "LIVE"


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
        tier: the evidence tier this record rests on (``CertificationTier``
            value; default LIVE for explicitly-constructed records). A
            ``SANDBOX`` record is preserved evidence but is NEVER counted as
            LIVE certification.
    """

    capability: str
    certified: bool = False
    certified_by: str = ""
    evidence: str = ""
    reason: str = ""
    certified_cycle: Optional[int] = None
    evidence_detail: Optional[Dict[str, Any]] = None
    tier: str = CertificationTier.LIVE.value

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
            "tier": self.tier,
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
                           path: Optional[str] = None,
                           tier: str = CertificationTier.LIVE.value
                           ) -> "CapabilityCertification":
        """Build a registry certifying exactly the named capabilities.

        Args:
            capabilities: iterable of capability names to certify.
            certified_by: identity recorded on each record.
            evidence: evidence recorded on each record.
            reason: rationale recorded on each record.
            path: optional path recorded on the registry (not written).
            tier: the evidence tier for the records (default LIVE; a SANDBOX
                registry is only ever used for the bounded live canary).

        Returns:
            A CapabilityCertification certifying only the supplied names.
        """
        records = {
            name: CertificationRecord(
                capability=name, certified=True, certified_by=certified_by,
                evidence=evidence, reason=reason, tier=tier,
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
            raw_tier = entry.get("tier", CertificationTier.LIVE.value)
            tier = str(raw_tier).strip().upper()
            declared_certified = bool(entry.get("certified", False))
            if tier not in (CertificationTier.SANDBOX.value,
                            CertificationTier.LIVE.value):
                # An unknown tier is malformed evidence -> fail closed.
                logger.warning(
                    "certification record %r has unknown tier %r; failing "
                    "closed (not certified)", name, raw_tier)
                declared_certified = False
                tier = CertificationTier.LIVE.value
            elif tier == CertificationTier.SANDBOX.value:
                # FAIL-CLOSED: the canonical (LIVE) registry NEVER counts
                # sandbox evidence as certification-to-leave-dry-run. The
                # record is preserved as evidence but not certified here.
                if declared_certified:
                    logger.warning(
                        "certification record %r declares SANDBOX tier in the "
                        "canonical LIVE registry; preserved as evidence but "
                        "NOT certified (fail-closed)", name)
                declared_certified = False
            reason = str(entry.get("reason", ""))
            if tier == CertificationTier.SANDBOX.value:
                reason = (reason + " [sandbox-tier evidence: not promoted to "
                          "the canonical LIVE registry]").strip()
            records[name] = CertificationRecord(
                capability=name,
                certified=declared_certified,
                certified_by=str(entry.get("certified_by", "")),
                evidence=str(entry.get("evidence", "")),
                reason=reason,
                certified_cycle=entry.get("certified_cycle"),
                evidence_detail=(entry.get("evidence_detail")
                                 if isinstance(entry.get("evidence_detail"), dict)
                                 else None),
                tier=tier,
            )
        # A bare `certified` name-list is also honoured (operator shorthand).
        # The shorthand means the canonical LIVE tier (the registry it appears
        # in is the LIVE registry); it is never sandbox evidence.
        for name in data.get("certified", []) or []:
            if isinstance(name, str) and name.strip() and name not in records:
                records[name] = CertificationRecord(
                    capability=name, certified=True,
                    certified_by=str(data.get("certified_by", "")),
                    evidence=str(data.get("evidence", "")),
                    reason=str(data.get("reason", "listed as certified")),
                    tier=CertificationTier.LIVE.value,
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

    def is_certified_at(self, capability: str, tier: str) -> bool:
        """Whether a capability is certified at a specific evidence tier.

        Args:
            capability: the capability name to query.
            tier: the ``CertificationTier`` value to require.

        Returns:
            True only for a certified record whose tier matches exactly.
        """
        rec = self._records.get(capability)
        want = (tier.value if isinstance(tier, CertificationTier)
                else str(tier).strip().upper())
        return bool(rec is not None and rec.certified
                    and str(rec.tier).strip().upper() == want)

    def is_live_certified(self, capability: str) -> bool:
        """Whether a capability holds a LIVE-tier certification.

        This is the explicit two-tier predicate: sandbox evidence never
        satisfies it (fail-closed).

        Args:
            capability: the capability name to query.

        Returns:
            True only for a certified LIVE-tier record.
        """
        return self.is_certified_at(capability, CertificationTier.LIVE.value)

    def live_certified_names(self) -> List[str]:
        """The sorted capability names holding a LIVE-tier certification.

        Returns:
            Sorted list of LIVE-certified capability names.
        """
        return sorted(n for n, r in self._records.items()
                      if r.certified and str(r.tier).strip().upper()
                      == CertificationTier.LIVE.value)

    def record_for(self, capability: str) -> Optional[CertificationRecord]:
        """Return the record for a capability, or None when none exists.

        Args:
            capability: the capability name to query.

        Returns:
            The CertificationRecord, or None.
        """
        return self._records.get(capability)

    def store(self, record: CertificationRecord) -> CertificationRecord:
        """Store a fully-formed record (an explicit, reviewed write).

        Used by the live canary to persist a LIVE-tier record with its
        structured evidence detail. It does NOT authorize anything by itself;
        the runner still requires the per-action approval and gates.

        Args:
            record: the record to store (keyed by its capability).

        Returns:
            The stored record.
        """
        self._records[record.capability] = record
        return record

    def certified_names(self) -> List[str]:
        """The sorted capability names currently certified.

        Returns:
            Sorted list of certified capability names.
        """
        return sorted(n for n, r in self._records.items() if r.certified)

    def certify(self, capability: str, *, certified_by: str, evidence: str,
                reason: str, cycle: Optional[int] = None,
                tier: str = CertificationTier.LIVE.value) -> CertificationRecord:
        """Explicitly certify one capability (an operator decision).

        Args:
            capability: the capability name to certify.
            certified_by: who is certifying it.
            evidence: the evidence reference backing the decision.
            reason: the recorded rationale.
            cycle: optional pipeline cycle of certification.
            tier: the evidence tier (default LIVE).

        Returns:
            The written CertificationRecord.
        """
        rec = CertificationRecord(
            capability=capability, certified=True, certified_by=certified_by,
            evidence=evidence, reason=reason, certified_cycle=cycle,
            tier=tier,
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
            "live_certified": self.live_certified_names(),
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
        directory = os.path.dirname(dest) or "."
        os.makedirs(directory, exist_ok=True)
        # Atomic temp+fsync+rename (Λ6.7 durability contract): a crash or a
        # concurrent reader never observes a half-written certification /
        # revocation record. The on-disk FORMAT is unchanged.
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".cert_reg_",
                                   suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
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


#: The loop invariants certification is gated on (I1-I8). Each measures a
#: distinct property of the prediction -> observation -> gap -> authority loop;
#: a pass count cannot substitute for any of them.
CERTIFICATION_INVARIANTS = ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8")


@dataclass(frozen=True)
class VarianceEvidence:
    """Structured evidence that the loop behaved correctly UNDER VARIANCE.

    Pass counts alone cannot certify: a capability could record three matching
    actions and still be BLIND to divergence (always predicting whatever it
    observed). This record carries the measured facts a certification must
    cite — which variance families were exercised, whether the loop invariants
    held, whether the gap DISCRIMINATED (bounded on normal cases, non-zero and
    correctly ordered on divergent cases), whether any mismatch was wrongly
    admitted, whether any case failed open, and whether a failure streak
    actually revoked. Absence of this record is not a pass (fail-closed).

    Attributes:
        capability: the capability the evidence covers.
        families: case count per variance family (normal / near_match /
            adversarial / refusal).
        invariants: invariant name (I1..I8) -> whether it held.
        measured_gaps: every gap measured in the battery (each bounded [0,1]).
        normal_gap_max: the largest gap over exact/normal cases, or None.
        adversarial_gap_min: the smallest NON-ZERO gap over divergent cases
            (near-match/adversarial), or None. Must exceed ``normal_gap_max``
            or the loop is blind (it cannot tell a match from a divergence).
        adversarial_gap_max: the largest gap over divergent cases, or None.
            Must exceed ``min_large_gap`` so the loop is proven to detect a
            LARGE divergence, not merely any non-zero wobble.
        false_admits: admissions on a mismatch (must be 0).
        fail_open_count: cases that admitted/certified without evidence (must
            be 0; the loop must be fail-closed).
        revocation_demonstrated: a failure streak actually revoked.
        min_normal_cases: required exact/normal cases.
        min_adversarial_cases: required divergent cases.
        min_refusal_cases: required error/refusal cases.
        source: provenance of the evidence (e.g. the campaign artifact path).
        detail: optional free-form context.
    """

    capability: str
    families: Dict[str, int] = field(default_factory=dict)
    invariants: Dict[str, bool] = field(default_factory=dict)
    measured_gaps: List[float] = field(default_factory=list)
    normal_gap_max: Optional[float] = None
    adversarial_gap_min: Optional[float] = None
    adversarial_gap_max: Optional[float] = None
    false_admits: int = 0
    fail_open_count: int = 0
    revocation_demonstrated: bool = False
    min_normal_cases: int = 1
    min_adversarial_cases: int = 3
    min_refusal_cases: int = 1
    min_large_gap: float = 0.5
    source: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializable variance-evidence record.

        Returns:
            Dict of the evidence fields.
        """
        return {
            "capability": self.capability,
            "families": dict(self.families),
            "invariants": dict(self.invariants),
            "measured_gaps": [float(g) for g in self.measured_gaps],
            "normal_gap_max": self.normal_gap_max,
            "adversarial_gap_min": self.adversarial_gap_min,
            "adversarial_gap_max": self.adversarial_gap_max,
            "false_admits": self.false_admits,
            "fail_open_count": self.fail_open_count,
            "revocation_demonstrated": self.revocation_demonstrated,
            "min_normal_cases": self.min_normal_cases,
            "min_adversarial_cases": self.min_adversarial_cases,
            "min_refusal_cases": self.min_refusal_cases,
            "source": self.source,
            "detail": dict(self.detail),
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

    STRENGTHENED BAR (loop-correctness under variance, not pass count): a
    capability is CERTIFIED only when BOTH of these hold:

      1. LOOP-CORRECTNESS UNDER VARIANCE — a :class:`VarianceEvidence` record
         shows the variance battery was exercised across normal AND divergent
         families, the loop invariants I1-I8 all held, the Reality Gap
         DISCRIMINATED (bounded on normal cases AND a correctly-ordered
         non-zero gap on divergent cases — the loop is not blind), no mismatch
         was admitted, no case failed open, and a failure streak actually
         revoked.
      2. VERIFIED OUTCOMES — a bounded window of the capability's MOST RECENT
         verified LIVE outcomes contains at least ``min_successes`` successes
         (a success = ``matched`` AND ``gap <= max_gap``) with NO active
         failure streak.

    Requirement (2) alone is the OLD, pass-count criterion and is explicitly
    insufficient: three matching actions prove the loop can match, never that
    it can DETECT a divergence, recalibrate authority, block on reduced
    authority, refuse to admit on a mismatch, or revoke. Requirement (1) is
    what certification rests on.

    A trailing failure streak of ``failure_streak`` or more REVOKES an existing
    certification (revocation is still demonstrated to be reachable). Anything
    else HOLDs (fail-closed: no evidence is never a pass). When
    ``require_variance`` is set, a missing variance record HOLDs rather than
    silently falling back to the pass-count gate.

    The workflow is a PURE evaluator: it never mutates a registry on its own.
    ``apply`` performs the explicit mutation, and only for a CERTIFY/REVOKE
    decision — a HOLD changes nothing.
    """

    def __init__(self, *, min_successes: int = 3, max_gap: float = 0.2,
                 window: int = 5, failure_streak: int = 2,
                 require_variance: bool = False):
        """Configure the certification criteria.

        Args:
            min_successes: successful outcomes required within the window.
            max_gap: the largest gap that still counts as a success.
            window: how many most-recent outcomes are considered.
            failure_streak: trailing failures that force revocation.
            require_variance: when True, a missing :class:`VarianceEvidence`
                record forces a HOLD (the pass-count window cannot certify on
                its own). Default False preserves the legacy evaluator for
                callers that supply no variance record, but certification in
                production MUST be taken with a variance record.
        """
        self.min_successes = max(1, int(min_successes))
        self.max_gap = float(max_gap)
        self.window = max(self.min_successes, int(window))
        self.failure_streak = max(1, int(failure_streak))
        self.require_variance = bool(require_variance)

    def _variance_gate(self, variance: VarianceEvidence) -> tuple:
        """Evaluate the strengthened, loop-correctness variance gates.

        Args:
            variance: the structured variance evidence to judge.

        Returns:
            (ok, failures, detail) — ok is True only when EVERY gate holds;
            failures lists the failing gate names; detail is a serializable
            record of each gate's measured value.
        """
        failures: List[str] = []
        detail: Dict[str, Any] = {}
        fam = dict(variance.families or {})
        detail["families"] = fam
        if int(fam.get("normal", 0)) < int(variance.min_normal_cases):
            failures.append("battery_normal_cases")
        if int(fam.get("adversarial", 0)) < int(variance.min_adversarial_cases):
            failures.append("battery_adversarial_cases")
        if int(fam.get("refusal", 0)) < int(variance.min_refusal_cases):
            failures.append("battery_refusal_cases")
        inv = dict(variance.invariants or {})
        detail["invariants"] = inv
        for name in CERTIFICATION_INVARIANTS:
            if inv.get(name) is not True:
                failures.append(f"invariant_{name}")
        gaps = [float(g) for g in (variance.measured_gaps or [])]
        bounded = bool(gaps) and all(0.0 <= g <= 1.0 for g in gaps)
        detail["gaps_bounded"] = bounded
        if not bounded:
            failures.append("gaps_unbounded")
        nmax = variance.normal_gap_max
        amin = variance.adversarial_gap_min
        detail["normal_gap_max"] = nmax
        detail["adversarial_gap_min"] = amin
        amax = variance.adversarial_gap_max
        detail["adversarial_gap_max"] = amax
        detects_large = amax is not None and float(amax) > float(
            variance.min_large_gap)
        detail["detects_large_divergence"] = detects_large
        discriminates = (
            nmax is not None and amin is not None
            and float(nmax) <= self.max_gap and float(amin) > float(nmax)
            and detects_large)
        detail["discriminates"] = discriminates
        if not discriminates:
            failures.append("gap_not_discriminating")
        detail["false_admits"] = int(variance.false_admits)
        if int(variance.false_admits) != 0:
            failures.append("false_admits")
        detail["fail_open_count"] = int(variance.fail_open_count)
        if int(variance.fail_open_count) != 0:
            failures.append("fail_open")
        detail["revocation_demonstrated"] = bool(
            variance.revocation_demonstrated)
        if not variance.revocation_demonstrated:
            failures.append("revocation_not_demonstrated")
        return (not failures), failures, detail

    def evaluate(self, capability: str,
                 outcomes: Iterable[VerifiedOutcome], *,
                 variance: Optional[VarianceEvidence] = None
                 ) -> CertificationDecision:
        """Evaluate recent outcomes (+ variance evidence) into a decision.

        Args:
            capability: the capability being evaluated.
            outcomes: the recorded outcomes (chronological; only the tail
                ``window`` outcomes are considered).
            variance: the loop-correctness evidence. When supplied it is
                REQUIRED to hold; when None and ``require_variance`` is set,
                the decision is a fail-closed HOLD.

        Returns:
            A CertificationDecision citing the exact counts + variance gates
            that justified it.
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
                "require_variance": self.require_variance,
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
        variance_ok: Optional[bool] = None
        if variance is not None:
            variance_ok, v_failures, v_detail = self._variance_gate(variance)
            evidence["variance"] = {
                "required": True,
                "satisfied": variance_ok,
                "failures": v_failures,
                "source": variance.source,
                "gates": v_detail,
            }
        elif self.require_variance:
            variance_ok = False
            evidence["variance"] = {
                "required": True,
                "satisfied": False,
                "failures": ["variance_evidence_missing"],
                "source": "",
            }
        if streak >= self.failure_streak:
            return CertificationDecision(
                capability=capability, action=CertificationAction.REVOKE,
                reason=(f"{streak} consecutive failed verified actions "
                        f"(>= {self.failure_streak}) — certification revoked"),
                evidence=evidence, certified=False)
        window_ok = successes >= self.min_successes and streak == 0
        if variance_ok is False:
            failed = ", ".join(evidence["variance"]["failures"])
            return CertificationDecision(
                capability=capability, action=CertificationAction.HOLD,
                reason=("loop-correctness under variance not established "
                        f"(failing gates: {failed}); pass count alone is not "
                        "a certification"),
                evidence=evidence, certified=False)
        if variance_ok is True:
            if window_ok:
                return CertificationDecision(
                    capability=capability, action=CertificationAction.CERTIFY,
                    reason=(f"loop-correctness under variance satisfied "
                            f"(I1-I8 held, gap discriminated normal<="
                            f"{self.max_gap} < divergent, zero false admits, "
                            f"fail-closed, revocation shown) AND {successes} "
                            f"successful verified actions within the last "
                            f"{self.window} (>= {self.min_successes}) with no "
                            f"failure streak — certified"),
                    evidence=evidence, certified=True)
            return CertificationDecision(
                capability=capability, action=CertificationAction.HOLD,
                reason=(f"loop-correctness under variance satisfied but only "
                        f"{successes}/{self.min_successes} successes in the "
                        f"window (verified outcomes still required)"),
                evidence=evidence, certified=False)
        # variance_ok is None: no variance record supplied and not required.
        if window_ok:
            return CertificationDecision(
                capability=capability, action=CertificationAction.CERTIFY,
                reason=(f"LEGACY pass-count criterion: {successes} successful "
                        f"verified actions within the last {self.window} "
                        f"(>= {self.min_successes}) with no failure streak — "
                        "certified WITHOUT variance evidence (insufficient on "
                        "its own; certification must cite variance)"),
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

def load_sandbox_evidence(
        path: Optional[str] = None) -> CapabilityCertification:
    """Load the SANDBOX-CERTIFIED evidence artifact as a scoped registry.

    This is the ONLY reader that treats a sandbox-tier record as ``certified``
    — and it exists solely so the bounded live-producer canary can be
    authorized to exercise a DISPOSABLE target. It deliberately bypasses the
    canonical loader's sandbox downgrade because the canary's authority is the
    preserved sandbox evidence, not production LIVE certification. The canonical
    ``capability_certification.json`` loader still ignores sandbox records
    (fail-closed); nothing else in the system calls this.

    Fails CLOSED: a missing, unreadable, or malformed artifact yields an empty
    registry (nothing certified), never a permissive default.

    Args:
        path: the sandbox evidence path (defaults to the canonical artifact).

    Returns:
        A CapabilityCertification whose records are sandbox-tier.
    """
    src = path or DEFAULT_SANDBOX_EVIDENCE_PATH
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info("sandbox evidence %r absent; canary stays uncertified", src)
        return CapabilityCertification(records={}, path=src)
    except Exception as e:
        logger.warning("sandbox evidence %r unreadable (%s); failing closed",
                       src, e)
        return CapabilityCertification(records={}, path=src)
    if not isinstance(data, dict):
        return CapabilityCertification(records={}, path=src)
    records: Dict[str, CertificationRecord] = {}
    for entry in data.get("records", []) or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("capability")
        if not isinstance(name, str) or not name.strip():
            continue
        tier = str(entry.get("tier",
                             CertificationTier.SANDBOX.value)).strip().upper()
        if tier != CertificationTier.SANDBOX.value:
            # This artifact carries sandbox evidence only; refuse anything else.
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
            tier=CertificationTier.SANDBOX.value,
        )
    logger.info("sandbox evidence loaded: %d sandbox-tier record(s) from %s",
                len(records), src)
    return CapabilityCertification(records=records, path=src)


__all__ = [
    "CertificationRecord", "CapabilityCertification", "DEFAULT_CERTIFICATION_PATH",
    "DEFAULT_SANDBOX_EVIDENCE_PATH", "CertificationTier", "load_sandbox_evidence",
    "CertificationAction", "VerifiedOutcome", "CertificationDecision",
    "CertificationWorkflow", "VarianceEvidence", "CERTIFICATION_INVARIANTS",
]
