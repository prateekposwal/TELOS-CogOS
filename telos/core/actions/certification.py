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
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """

    capability: str
    certified: bool = False
    certified_by: str = ""
    evidence: str = ""
    reason: str = ""
    certified_cycle: Optional[int] = None

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


__all__ = [
    "CertificationRecord", "CapabilityCertification", "DEFAULT_CERTIFICATION_PATH",
]
