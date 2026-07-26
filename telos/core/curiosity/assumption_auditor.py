"""
AssumptionAuditor — Curiosity That Questions Assumptions.

Prateek's insight #3: "Curiosity should question assumptions —
not 'what's out there?' but 'what assumptions have I stopped questioning?'"

The current CuriosityDrive explores physical space (counterfactual worlds)
but never questions its own assumptions. The AssumptionAuditor tracks
the system's active assumptions and periodically audits them.

Architecture:
  - Maintains a registry of active assumptions (beliefs the system holds)
  - Each assumption has a confidence level and a last-questioned timestamp
  - When curiosity is high, the auditor selects an assumption to challenge
  - Challenging means: "what would happen if this assumption were false?"
  - Assumptions that survive challenges get reinforced
  - Assumptions that fail challenges get revised

Assumption types:
  - DOMAIN: "This environment behaves like X"
  - SELF: "My capabilities include Y"
  - STRATEGIC: "Approach Z works in situation W"
  - TEMPORAL: "State transitions happen at rate R"
"""

from __future__ import annotations

import logging
import time
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_assumption_auditor')


class AssumptionType(Enum):
    DOMAIN = "domain"
    SELF = "self"
    STRATEGIC = "strategic"
    TEMPORAL = "temporal"
    CAUSAL = "causal"
    SOCIAL = "social"
    EPISTEMIC = "epistemic"


@dataclass
class Assumption:
    """A single assumption the system holds."""
    id: str
    description: str
    type: AssumptionType
    confidence: float  # 0.0-1.0
    last_questioned: float  # timestamp
    times_questioned: int = 0
    times_survived: int = 0  # survived challenge
    times_failed: int = 0  # failed challenge
    evidence_for: List[str] = field(default_factory=list)
    evidence_against: List[str] = field(default_factory=list)
    source: str = "initialization"
    active: bool = True

    @property
    def survival_rate(self) -> float:
        total = self.times_survived + self.times_failed
        if total == 0:
            return 1.0
        return self.times_survived / total

    @property
    def staleness(self) -> float:
        """How long since this assumption was last questioned (seconds)."""
        return time.time() - self.last_questioned

    def question(self) -> None:
        self.times_questioned += 1
        self.last_questioned = time.time()

    def survive(self, evidence: str) -> None:
        self.times_survived += 1
        self.confidence = min(1.0, self.confidence + 0.05)
        self.evidence_for.append(evidence)

    def fail(self, evidence: str) -> None:
        self.times_failed += 1
        self.confidence = max(0.0, self.confidence - 0.15)
        self.evidence_against.append(evidence)


@dataclass
class AuditReport:
    """Result of an assumption audit cycle."""
    assumption_audited: Optional[str]
    assumption_type: Optional[str]
    survived: bool
    confidence_before: float
    confidence_after: float
    new_confidence: float
    evidence: str
    triggered_by_curiosity: bool


class AssumptionAuditor:
    """Audits system assumptions when curiosity is high.

    The auditor maintains a registry of assumptions and selects one
    to challenge when curiosity exceeds a threshold or when an assumption
    hasn't been questioned recently.

    Integration:
      - Called by the CuriosityDrive when curiosity > threshold
      - Also triggered periodically (every N cycles)
      - Results feed into the TheoryBuilder
      - Failed assumptions trigger meta-cognitive state changes
    """

    def __init__(self):
        self._assumptions: Dict[str, Assumption] = {}
        self._audit_history: List[AuditReport] = []
        self._max_history = 100
        self._total_audits = 0
        self._last_audit_cycle: int = 0
        self._audit_interval: int = 10  # cycles between automatic audits
        self._curiosity_threshold: float = 0.6  # minimum curiosity for triggered audit

        # Register core assumptions
        self._register_core_assumptions()

    def _register_core_assumptions(self) -> None:
        """Register assumptions the system starts with."""
        core_assumptions = [
            Assumption(
                id="world_stable",
                description="The environment state changes predictably",
                type=AssumptionType.DOMAIN,
                confidence=0.8,
                last_questioned=time.time(),
                source="genesis",
            ),
            Assumption(
                id="action_effective",
                description="My actions produce expected state changes",
                type=AssumptionType.SELF,
                confidence=0.7,
                last_questioned=time.time(),
                source="genesis",
            ),
            Assumption(
                id="council_reliable",
                description="The Council's validators are making correct assessments",
                type=AssumptionType.EPISTEMIC,
                confidence=0.75,
                last_questioned=time.time(),
                source="genesis",
            ),
            Assumption(
                id="simulation_accurate",
                description="Counterfactual simulations predict realistic futures",
                type=AssumptionType.CAUSAL,
                confidence=0.7,
                last_questioned=time.time(),
                source="genesis",
            ),
            Assumption(
                id="identity_coherent",
                description="My identity (SystemSelf) is a useful self-model",
                type=AssumptionType.SELF,
                confidence=0.65,
                last_questioned=time.time(),
                source="genesis",
            ),
            Assumption(
                id="curiosity_useful",
                description="Exploration driven by curiosity improves outcomes",
                type=AssumptionType.STRATEGIC,
                confidence=0.8,
                last_questioned=time.time(),
                source="genesis",
            ),
        ]
        for a in core_assumptions:
            self._assumptions[a.id] = a

    def register_assumption(self, description: str, type: AssumptionType,
                            confidence: float = 0.5,
                            source: str = "experience") -> str:
        """Register a new assumption for tracking."""
        import hashlib
        aid = f"asm_{hashlib.md5(description.encode()).hexdigest()[:8]}"
        assumption = Assumption(
            id=aid,
            description=description,
            type=type,
            confidence=confidence,
            last_questioned=time.time(),
            source=source,
        )
        self._assumptions[aid] = assumption
        logger.debug(f"AssumptionAuditor: registered '{description[:40]}...' as {aid}")
        return aid

    def should_audit(self, cycle: int, curiosity_level: float) -> bool:
        """Determine whether to run an assumption audit.

        Triggers:
          1. Curiosity above threshold
          2. Periodic interval reached
          3. An assumption is very stale (never questioned)
        """
        # Curiosity trigger
        if curiosity_level >= self._curiosity_threshold:
            return True

        # Periodic trigger
        if cycle - self._last_audit_cycle >= self._audit_interval:
            return True

        # Staleness trigger
        stale_exists = any(
            a.staleness > 3600 and a.active  # not questioned in 1 hour
            for a in self._assumptions.values()
        )
        if stale_exists:
            return True

        return False

    def select_assumption_to_audit(self, cycle: int) -> Optional[Assumption]:
        """Select the best assumption to audit.

        Selection priority:
          1. High confidence + long unqueried (overconfident assumptions)
          2. Low confidence (fragile assumptions)
          3. Never questioned
        """
        candidates = [a for a in self._assumptions.values() if a.active]
        if not candidates:
            return None

        # Score each candidate
        def score(a: Assumption) -> float:
            staleness_factor = min(1.0, a.staleness / 3600.0)  # cap at 1 hour
            overconfidence = a.confidence * 0.5  # higher confidence -> more worth questioning
            fragility = (1.0 - a.confidence) * 0.3  # low confidence also worth checking
            never_questioned = 0.5 if a.times_questioned == 0 else 0.0
            return staleness_factor + overconfidence + fragility + never_questioned

        candidates.sort(key=score, reverse=True)
        return candidates[0]

    def audit(self, cycle: int, assumption_id: str,
              outcome_evidence: str, survived: bool,
              triggered_by_curiosity: bool = False) -> Optional[AuditReport]:
        """Audit a specific assumption and record the result.

        Args:
            cycle: Current pipeline cycle
            assumption_id: ID of the assumption to audit
            outcome_evidence: Evidence string describing what happened
            survived: Whether the assumption survived the challenge
            triggered_by_curiosity: Whether this was triggered by curiosity

        Returns:
            AuditReport or None if assumption not found
        """
        assumption = self._assumptions.get(assumption_id)
        if assumption is None:
            logger.warning(f"AssumptionAuditor: unknown assumption '{assumption_id}'")
            return None

        confidence_before = assumption.confidence
        assumption.question()

        if survived:
            assumption.survive(outcome_evidence)
        else:
            assumption.fail(outcome_evidence)

        report = AuditReport(
            assumption_audited=assumption_id,
            assumption_type=assumption.type.value,
            survived=survived,
            confidence_before=confidence_before,
            confidence_after=assumption.confidence,
            new_confidence=assumption.confidence,
            evidence=outcome_evidence,
            triggered_by_curiosity=triggered_by_curiosity,
        )

        self._audit_history.append(report)
        if len(self._audit_history) > self._max_history:
            self._audit_history.pop(0)
        self._total_audits += 1
        self._last_audit_cycle = cycle

        logger.info(
            f"AssumptionAuditor: audited '{assumption.description[:30]}' "
            f"({assumption.type.value}), survived={survived}, "
            f"confidence {confidence_before:.2f}→{assumption.confidence:.2f}"
        )

        return report

    def auto_audit(self, cycle: int, curiosity_level: float) -> Optional[AuditReport]:
        """Automatically select and audit an assumption.

        Called by the pipeline when curiosity is high or periodically.
        """
        if not self.should_audit(cycle, curiosity_level):
            return None

        assumption = self.select_assumption_to_audit(cycle)
        if assumption is None:
            return None

        triggered = curiosity_level >= self._curiosity_threshold
        return self.audit(
            cycle=cycle,
            assumption_id=assumption.id,
            outcome_evidence=f"auto-audit triggered (curiosity={curiosity_level:.2f})",
            survived=True,  # default: assumption survives auto-audit
            triggered_by_curiosity=triggered,
        )

    def get_overconfident_assumptions(self, threshold: float = 0.9) -> List[Assumption]:
        """Get assumptions with high confidence that haven't been questioned recently."""
        return [
            a for a in self._assumptions.values()
            if a.confidence >= threshold and a.staleness > 600 and a.active
        ]

    def get_fragile_assumptions(self, threshold: float = 0.3) -> List[Assumption]:
        """Get assumptions with low confidence."""
        return [
            a for a in self._assumptions.values()
            if a.confidence <= threshold and a.active
        ]

    @property
    def total_audits(self) -> int:
        return self._total_audits

    @property
    def active_assumptions(self) -> List[Assumption]:
        return [a for a in self._assumptions.values() if a.active]

    def to_dict(self) -> Dict:
        return {
            "total_audits": self._total_audits,
            "active_assumptions": len(self.active_assumptions),
            "assumptions": {
                aid: {
                    "description": a.description,
                    "type": a.type.value,
                    "confidence": a.confidence,
                    "times_questioned": a.times_questioned,
                    "survival_rate": a.survival_rate,
                    "staleness_seconds": a.staleness,
                    "active": a.active,
                }
                for aid, a in self._assumptions.items()
            },
        }
