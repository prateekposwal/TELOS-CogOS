"""
Verified skill acquisition (Phase 3, Λ2.3 Kintsugi applied to learning).

PATTERN (one acquisition discipline): the write-side fix loop already refuses
to call a patch "done" until an allowlisted test rerun proves it green. Learning
had no equivalent — ExperienceManager indexed a skill whenever `health_score`
cleared a threshold, which is a self-reported utility, not a verified one.

SkillAcquisition generalizes the fix-loop rule: a skill is admitted to the
library ONLY after a verification signal for that specific skill is observed.
A candidate that never verifies is retained as a *candidate* and eventually
retired — never silently promoted. This is what separates "we did something"
from "we can do it again".

Verification is explicit and pluggable: an `outcome >= min_outcome` on a later
matching cycle, or an operator-supplied verifier. Unverified candidates do not
enter the library and do not raise the acquisition count.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from telos.core.ledger.skill_library import Skill, SkillLibrary

DEFAULT_MIN_OUTCOME = 0.6
DEFAULT_CANDIDATE_TTL_CYCLES = 50
DEFAULT_MAX_CANDIDATES = 200


@dataclass
class SkillCandidate:
    """A proposed skill awaiting verification.

    Attributes:
        candidate_id: unique id.
        fingerprint: the situation fingerprint it should match.
        trajectory: the action/trajectory payload.
        proposed_cycle: cycle the candidate was proposed.
        context: free-form proposal context.
        attempts: how many times it has been (re)proposed/observed.
        verified: True once a verification signal confirmed it.
        source: who proposed it (runtime/fix_loop/seed/operator).
    """

    candidate_id: str
    fingerprint: str
    trajectory: Any
    proposed_cycle: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    verified: bool = False
    source: str = "runtime"

    def to_dict(self) -> Dict[str, Any]:
        """Serializable form."""
        return {
            "candidate_id": self.candidate_id,
            "fingerprint": self.fingerprint,
            "trajectory": self.trajectory,
            "proposed_cycle": self.proposed_cycle,
            "context": dict(self.context),
            "attempts": self.attempts,
            "verified": self.verified,
            "source": self.source,
        }


class SkillAcquisition:
    """Admits skills into the library only after verified outcomes."""

    def __init__(self, skill_library: SkillLibrary,
                 min_outcome: float = DEFAULT_MIN_OUTCOME,
                 candidate_ttl_cycles: int = DEFAULT_CANDIDATE_TTL_CYCLES,
                 max_candidates: int = DEFAULT_MAX_CANDIDATES,
                 verifier: Optional[Callable[[SkillCandidate, float], bool]] = None):
        """Construct an acquisition controller over a skill library.

        Args:
            skill_library: the library verified skills are indexed into.
            min_outcome: outcome floor for a verification signal to count.
            candidate_ttl_cycles: retire unverified candidates after this age.
            max_candidates: bound on retained unverified candidates.
            verifier: optional custom verifier(candidate, outcome) -> bool;
                defaults to ``outcome >= min_outcome``.
        """
        self._library = skill_library
        self.min_outcome = float(min_outcome)
        self.candidate_ttl_cycles = max(1, int(candidate_ttl_cycles))
        self.max_candidates = max(1, int(max_candidates))
        self._verifier = verifier
        self._candidates: Dict[str, SkillCandidate] = {}
        self._order: List[str] = []
        self.acquired = 0
        self.proposed = 0
        self.retired = 0

    def propose(self, fingerprint: str, trajectory: Any, cycle: int = 0,
                context: Optional[Dict[str, Any]] = None,
                source: str = "runtime") -> SkillCandidate:
        """Register a skill candidate (unverified).

        Args:
            fingerprint: the situation fingerprint the skill matches.
            trajectory: the action/trajectory payload.
            cycle: the proposing cycle.
            context: optional proposal context.
            source: who proposed it.

        Returns:
            The created SkillCandidate.
        """
        candidate = SkillCandidate(
            candidate_id=f"cand_{uuid.uuid4().hex[:10]}",
            fingerprint=fingerprint,
            trajectory=trajectory,
            proposed_cycle=cycle,
            context=dict(context or {}),
            attempts=1,
            source=source,
        )
        self._candidates[candidate.candidate_id] = candidate
        self._order.append(candidate.candidate_id)
        self.proposed += 1
        self.retire(cycle)
        return candidate

    def _default_verifier(self, candidate: SkillCandidate, outcome: float) -> bool:
        """Default verification: outcome clears the floor.

        Args:
            candidate: the candidate being verified.
            outcome: the observed outcome.

        Returns:
            True when the outcome is at or above the verification floor.
        """
        return outcome >= self.min_outcome

    def verify(self, candidate_id: str, outcome: float, cycle: int = 0) -> bool:
        """Verify a candidate; on success, admit it to the library.

        Args:
            candidate_id: the candidate to verify.
            outcome: the observed outcome for its situation.
            cycle: the verifying cycle.

        Returns:
            True when the candidate was verified and acquired.
        """
        candidate = self._candidates.get(candidate_id)
        if candidate is None or candidate.verified:
            return False
        check = self._verifier or self._default_verifier
        if not check(candidate, outcome):
            candidate.attempts += 1
            return False
        candidate.verified = True
        skill = Skill(
            skill_id=f"skill_{uuid.uuid4().hex[:8]}",
            fingerprint=candidate.fingerprint,
            trajectory=candidate.trajectory,
            utility_score=max(0.0, min(1.0, float(outcome))),
            metadata={
                "source": "verified_acquisition",
                "candidate_id": candidate.candidate_id,
                "proposed_cycle": candidate.proposed_cycle,
                "verified_cycle": cycle,
                "verified_at": time.time(),
            },
        )
        self._library.index_skill(skill)
        self.acquired += 1
        self._candidates.pop(candidate_id, None)
        if candidate_id in self._order:
            self._order.remove(candidate_id)
        return True

    def verify_matching(self, fingerprint_prefix: str, outcome: float,
                        cycle: int = 0) -> int:
        """Verify every candidate whose fingerprint matches a prefix.

        Args:
            fingerprint_prefix: fingerprint prefix to match.
            outcome: the observed outcome for the matched situation.
            cycle: the verifying cycle.

        Returns:
            Number of candidates verified and acquired.
        """
        matched = [
            c.candidate_id for c in self._candidates.values()
            if c.fingerprint.startswith(fingerprint_prefix)
        ]
        return sum(1 for cid in matched if self.verify(cid, outcome, cycle=cycle))

    def retire(self, cycle: int) -> int:
        """Retire unverified candidates past their TTL or over the bound.

        Args:
            cycle: the current cycle (TTL is measured against it).

        Returns:
            Number of candidates retired.
        """
        expired = [
            cid for cid in self._order
            if cycle - self._candidates[cid].proposed_cycle > self.candidate_ttl_cycles
        ]
        for cid in expired:
            self._candidates.pop(cid, None)
            self._order.remove(cid)
            self.retired += 1
        # Bound the retained candidate set (oldest-first).
        while len(self._order) > self.max_candidates:
            cid = self._order.pop(0)
            self._candidates.pop(cid, None)
            self.retired += 1
        return len(expired)

    def stats(self) -> Dict[str, int]:
        """Return proposal/acquisition counters and candidate depth.

        Returns:
            Dict with proposed/acquired/retired/candidates counts.
        """
        return {
            "proposed": self.proposed,
            "acquired": self.acquired,
            "retired": self.retired,
            "candidates": len(self._candidates),
        }


__all__ = [
    "SkillAcquisition", "SkillCandidate",
    "DEFAULT_MIN_OUTCOME", "DEFAULT_CANDIDATE_TTL_CYCLES", "DEFAULT_MAX_CANDIDATES",
]
