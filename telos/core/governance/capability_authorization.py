"""
TELOS v6 — Phase 7: CapabilityAuthorization — non-tradeable hard gates.

This is the governance-layer gate that answers: "is ACT structurally
authorized by the system's current capability evidence?"

It is deliberately DISTINCT from the perception-layer `CapabilityRegistry`
(telos/core/perception/capabilities.py), which models *detection envelopes*
(e.g. the minimum object size a CV pipeline can resolve). That registry tells
you *what the perception stack can detect*; this authorization tells you
*whether the system is entitled to ACT at all* based on hard, conjunctive
capability gates.

Design principle (mirroring the Council's conjunctive veto — see
telos/core/council/base.py `validated = len(blockers) == 0`):

    A capability gap is NOT a probability or a scalar readiness score.
    Each MANDATORY dimension is a VETO. If any mandatory dimension is FAIL,
    ACT is structurally unavailable — REGARDLESS of how good the other
    dimensions are (high DI, high utility, high confidence, high fidelity).

    authorized() == all(mandatory gates == PASS)

This is what makes TELOS structurally incapable of claiming more authority
than its evidence supports: high *optimization* scores cannot trade away a
*failed* capability gate.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class CapabilityStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    LIMITED = "LIMITED"
    UNKNOWN = "UNKNOWN"

    @property
    def is_ok(self) -> bool:
        """A gate is 'ok' (does not veto) iff it is PASS or LIMITED.

        FAIL always vetoes (hard gate). UNKNOWN is treated as NOT-ok for
        authorization purposes (can't claim competence without evidence),
        but is distinguished from FAIL so the reason can say *why*.
        """
        return self in (CapabilityStatus.PASS, CapabilityStatus.LIMITED)


@dataclass
class CapabilityDimension:
    """One mandatory capability dimension and its current status.

    A dimension is a VETO when its status is FAIL (hard). UNKNOWN is not a
    veto in the sense of a hard boundary, but it does not grant authorization
    either (authorization requires PASS or LIMITED).
    """
    name: str
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    detail: str = ""
    mandatory: bool = True

    @property
    def passed(self) -> bool:
        return self.status.is_ok


class CapabilityAuthorization:
    """Conjunctive hard-gate authorization for ACT.

    The seven mandatory dimensions modeled by TELOS v6:

        observability      — can we observe the state we must act upon?
        model_fidelity     — is our world model validated against reality?
        action_validity    — is the proposed action within the action space?
        risk_coverage      — are the risks of acting covered/acceptable?
        causal_confidence  — do we have causal grounds, not just correlation?
        recovery           — can we recover if the action diverges from plan?
        authority          — are we authorized (domain/world) to act?

    ACT is authorized ONLY if every mandatory gate PASSES (or is LIMITED).
    A single FAIL makes ACT structurally impossible — no scalar aggregate can
    undo it.
    """

    def __init__(
        self,
        observability: CapabilityStatus = CapabilityStatus.PASS,
        model_fidelity: CapabilityStatus = CapabilityStatus.PASS,
        action_validity: CapabilityStatus = CapabilityStatus.PASS,
        risk_coverage: CapabilityStatus = CapabilityStatus.PASS,
        causal_confidence: CapabilityStatus = CapabilityStatus.PASS,
        recovery: CapabilityStatus = CapabilityStatus.PASS,
        authority: CapabilityStatus = CapabilityStatus.PASS,
        details: Optional[Dict[str, str]] = None,
    ):
        details = details or {}
        self._dimensions: List[CapabilityDimension] = [
            CapabilityDimension("observability", observability, details.get("observability", "")),
            CapabilityDimension("model_fidelity", model_fidelity, details.get("model_fidelity", "")),
            CapabilityDimension("action_validity", action_validity, details.get("action_validity", "")),
            CapabilityDimension("risk_coverage", risk_coverage, details.get("risk_coverage", "")),
            CapabilityDimension("causal_confidence", causal_confidence, details.get("causal_confidence", "")),
            CapabilityDimension("recovery", recovery, details.get("recovery", "")),
            CapabilityDimension("authority", authority, details.get("authority", "")),
        ]

    def __repr__(self) -> str:
        return f"CapabilityAuthorization(authorized={self.authorized()})"

    def authorized(self) -> bool:
        """True iff all mandatory gates PASS (or LIMITED).

        This is CONJUNCTIVE — one FAIL vetoes regardless of the others.
        """
        return all(d.status.is_ok for d in self._dimensions)

    def failed_gates(self) -> List[str]:
        """Names of mandatory gates currently FAIL."""
        return [d.name for d in self._dimensions if d.status == CapabilityStatus.FAIL]

    def gate(self, name: str) -> Optional[CapabilityDimension]:
        for d in self._dimensions:
            if d.name == name:
                return d
        return None

    @property
    def dimensions(self) -> List[CapabilityDimension]:
        return list(self._dimensions)

    def to_dict(self) -> Dict:
        """Capability profile vector + which gates failed."""
        return {
            "authorized": self.authorized(),
            "failed_gates": self.failed_gates(),
            "profile": {
                d.name: d.status.value for d in self._dimensions
            },
            "details": {
                d.name: d.detail for d in self._dimensions if d.detail
            },
        }


# ─── Convenience constructors ──────────────────────────────────────────────────

def all_pass() -> CapabilityAuthorization:
    """A fully-authorized capability profile (every mandatory gate PASS)."""
    return CapabilityAuthorization()


def from_dimensions(dimensions: Dict[str, CapabilityStatus],
                    details: Optional[Dict[str, str]] = None,
                    default: CapabilityStatus = CapabilityStatus.PASS) -> CapabilityAuthorization:
    """Build from a partial mapping of dimension name -> status.

    Any dimension not supplied defaults to `default`. Missing dimensions do
    NOT silently grant authorization if `default` is not PASS — for an
    untested/unknown system you'd pass default=UNKNOWN so a gap cannot be
    waved through by omission.

    Args:
        dimensions: partial mapping of dimension name -> CapabilityStatus.
        details: optional human/free-form detail map to attach.
        default: fallback status for any dimension not present in `dimensions`.
    """
    kwargs = {d.name: dimensions.get(d.name, default) for d in CapabilityAuthorization().dimensions}
    return CapabilityAuthorization(**kwargs, details=details)
