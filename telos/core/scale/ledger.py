"""
RecursionLedger — the self-similarity ledger for deliberate recursion.

Every recursive invocation of the deliberation law (supervisor → sub-
pipeline, spawn or execute) is recorded here so that recursion is
*observable* rather than accidental. The ledger is the bookkeeping half of
the ScaleInvariancePrinciple: it records each invocation's phase signature
and verified axiom set, and can report how self-similar the recursion has
been (the fraction of invocations whose structure matches the canonical
law).
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from telos.core.scale.principle import ScaleInvariancePrinciple


@dataclass
class RecursionEntry:
    """A single recorded recursive invocation of the deliberation law."""

    entry_id: str
    parent_scope: str          # who spawned/ran the invocation (e.g. "supervisor:orchestrate")
    scope: str                 # the recursive scope (e.g. "sub:scout")
    scale: str                 # granularity label: macro | meso | micro
    kind: str                  # "spawn" | "execute"
    phase_signature: Tuple[str, ...]
    axiom_ids: Tuple[str, ...] = ()
    success: Optional[bool] = None
    decision_integrity: Optional[float] = None
    mission_drift: Optional[float] = None
    duration_ms: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "parent_scope": self.parent_scope,
            "scope": self.scope,
            "scale": self.scale,
            "kind": self.kind,
            "phase_signature": list(self.phase_signature),
            "axiom_ids": list(self.axiom_ids),
            "success": self.success,
            "decision_integrity": self.decision_integrity,
            "mission_drift": self.mission_drift,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


class RecursionLedger:
    """Records and audits recursive invocations of the deliberation law."""

    def __init__(self,
                 owner: str = "telos",
                 principle: Optional[ScaleInvariancePrinciple] = None):
        self._owner = owner
        self._principle = principle or ScaleInvariancePrinciple()
        self._entries: List[RecursionEntry] = []

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def principle(self) -> ScaleInvariancePrinciple:
        return self._principle

    @property
    def entries(self) -> List[RecursionEntry]:
        return list(self._entries)

    def record(self,
               parent_scope: str,
               scope: str,
               scale: str,
               kind: str = "execute",
               phase_signature: Tuple[str, ...] = (),
               axiom_ids: Tuple[str, ...] = (),
               success: Optional[bool] = None,
               decision_integrity: Optional[float] = None,
               mission_drift: Optional[float] = None,
               duration_ms: Optional[float] = None) -> RecursionEntry:
        """Record a recursive invocation. Returns the created entry.

        Args:
            parent_scope: the scope that spawned this invocation.
            scope: the name of the recursive scope being recorded.
            scale: the scale label (e.g. macro / meso / micro).
            kind: invocation kind ("spawn" or "execute").
            phase_signature: the tuple of phase names executed.
            axiom_ids: the tuple of axiom ids verified during the invocation.
            success: whether the invocation completed successfully.
            decision_integrity: DI score for the invocation.
            mission_drift: MD score for the invocation.
            duration_ms: wall-clock duration of the invocation.
        """
        entry = RecursionEntry(
            entry_id=f"{scope}:{uuid.uuid4().hex[:8]}",
            parent_scope=parent_scope,
            scope=scope,
            scale=scale,
            kind=kind,
            phase_signature=tuple(phase_signature),
            axiom_ids=tuple(sorted(axiom_ids)),
            success=success,
            decision_integrity=decision_integrity,
            mission_drift=mission_drift,
            duration_ms=duration_ms,
        )
        self._entries.append(entry)
        return entry

    def summary(self) -> Dict:
        """Aggregate statistics over all recorded invocations."""
        n = len(self._entries)
        by_kind: Dict[str, int] = {}
        by_scale: Dict[str, int] = {}
        for e in self._entries:
            by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
            by_scale[e.scale] = by_scale.get(e.scale, 0) + 1
        return {
            "entries": n,
            "by_kind": by_kind,
            "by_scale": by_scale,
            "self_similarity": self.self_similarity(),
            "invariant_holds": self.invariant_holds(),
            "scales_seen": sorted(by_scale.keys()),
        }

    def self_similarity(self) -> float:
        """Fraction of recorded invocations whose phase signature matches the
        canonical deliberation law. 1.0 = perfectly scale-invariant so far."""
        if not self._entries:
            return 0.0
        matching = sum(
            1 for e in self._entries
            if self._principle.matches_phases(e.phase_signature)
        )
        return matching / len(self._entries)

    def axiom_sets_by_scale(self) -> Dict[str, Tuple[str, ...]]:
        """Verified axiom id sets per scale (from execute entries only)."""
        sets: Dict[str, Tuple[str, ...]] = {}
        for e in self._entries:
            if e.kind == "execute" and e.axiom_ids:
                sets[e.scale] = tuple(e.axiom_ids)
        return sets

    def invariant_holds(self) -> bool:
        """True if every recorded invocation matches the canonical law.

        A ledger with no entries is vacuously invariant (nothing violated).
        """
        return all(
            self._principle.matches_phases(e.phase_signature)
            for e in self._entries
        )

    def to_dict(self) -> dict:
        return {
            "owner": self._owner,
            "principle": self._principle.to_dict(),
            "summary": self.summary(),
            "entries": [e.to_dict() for e in self._entries],
        }


__all__ = ["RecursionLedger", "RecursionEntry"]
