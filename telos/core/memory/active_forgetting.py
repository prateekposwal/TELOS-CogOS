"""
ActiveForgetting — Deliberately Forget Obsolete Beliefs.

Prateek's insight: "Active forgetting — deliberately forget obsolete beliefs.
Not just pruning unused skills — asking 'what belief should I question today?'"

Most systems accumulate beliefs forever. Beliefs become entrenched and never
re-examined. Active Forgetting is the deliberate, periodic examination of held
beliefs to determine which are obsolete, incorrect, or no longer useful.

This is NOT forgetting due to capacity limits (passive forgetting). It is
ACTIVE forgetting: the system asks "what should I stop believing?"

Architecture:
  - Belief Registry: all active beliefs with confidence, evidence, last_used
  - Forgetting Curator: periodically selects a belief to examine
  - Examination: "Is this belief still supported by evidence?"
  - Forgetting Decision: retain, weaken, archive, or delete
  - Belief Lifecycle: formation → strengthening → weakening → archival/deletion

Belief types:
  - FACTUAL: "The world is like X"
  - SELF: "I am capable of Y"
  - PROCEDURAL: "Approach Z works"
  - TEMPORAL: "Transitions happen at rate R"
  - SOCIAL: "User prefers X"

Key insight: Forgetting is not failure. It is cognitive hygiene.
An unexamined belief is not worth holding.
"""

from __future__ import annotations

import logging
import time
import math
import hashlib
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger('telos_active_forgetting')


class BeliefType(Enum):
    FACTUAL = "factual"
    SELF = "self"
    PROCEDURAL = "procedural"
    TEMPORAL = "temporal"
    SOCIAL = "social"
    EPISTEMIC = "epistemic"


class ForgettingAction(Enum):
    RETAIN = "retain"           # Keep as-is
    WEAKEN = "weaken"           # Reduce confidence but keep
    ARCHIVE = "archive"         # Store but remove from active beliefs
    DELETE = "delete"           # Remove entirely


@dataclass
class Belief:
    """A single belief held by the system."""
    id: str
    description: str
    type: BeliefType
    confidence: float           # 0.0-1.0 how strongly held
    evidence_for: int = 0       # Count of supporting evidence
    evidence_against: int = 0   # Count of contradicting evidence
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    last_examined: float = field(default_factory=time.time)
    last_used_cycle: int = 0
    staleness_cycles: int = 0
    times_examined: int = 0
    examination_history: List[bool] = field(default_factory=list)  # survived?
    active: bool = True
    archived: bool = False
    source: str = "experience"

    @property
    def staleness(self) -> float:
        """Seconds since last used."""
        return time.time() - self.last_used

    @property
    def evidential_balance(self) -> float:
        """Overall evidence balance [-1, 1]."""
        total = self.evidence_for + self.evidence_against
        if total == 0:
            return 0.0
        return (self.evidence_for - self.evidence_against) / total

    @property
    def survival_rate(self) -> float:
        """How often this belief has survived examination."""
        if not self.examination_history:
            return 1.0
        return sum(self.examination_history) / len(self.examination_history)

    @property
    def worth_holding(self) -> float:
        """Composite score: should we keep this belief?"""
        if self.archived or not self.active:
            return 0.0
        # Blend: confidence + recent use + evidential balance
        recency = math.exp(-self.staleness / 86400.0)  # 1 day decay
        return (self.confidence * 0.4 + recency * 0.3 +
                (self.evidential_balance + 1) / 2 * 0.3)


@dataclass
class ForgettingRecord:
    """Record of a single forgetting decision."""
    belief_id: str
    belief_description: str
    belief_type: str
    confidence_before: float
    confidence_after: float
    action: str  # retain, weaken, archive, delete
    reason: str
    cycle: int
    timestamp: float = field(default_factory=time.time)


class ActiveForgetting:
    """Deliberate examination and forgetting of obsolete beliefs.

    The forgetting mechanism:
    1. Maintains a registry of active beliefs
    2. Periodically selects a belief for examination (via curator)
    3. Examines the belief: is it still supported by evidence?
    4. Decides: retain, weaken, archive, or delete
    5. Records all forgetting decisions for audit

    Selection strategies:
      - Least recently examined (lazy beliefs)
      - Lowest evidential balance (weak beliefs)
      - Highest confidence + oldest (overconfident beliefs — most to lose)
      - Random sampling (for stochastic coverage)

    The curator does NOT delete rarely-used skills. That's SkillLibrary's job.
    The curator asks: "What belief should I question TODAY?"
    """

    def __init__(self, examination_interval: int = 5):
        self._beliefs: Dict[str, Belief] = {}
        self._records: List[ForgettingRecord] = []
        self._max_records = 200
        self._last_examination_cycle: int = 0
        self._examination_interval = examination_interval
        self._total_examinations: int = 0
        self._total_forgotten: int = 0  # beliefs archived or deleted

        # Register some starting beliefs
        self._register_core_beliefs()

    def _register_core_beliefs(self) -> None:
        """Register foundational beliefs the system starts with."""
        core_beliefs = [
            ("World is predictable", BeliefType.FACTUAL, 0.7),
            ("My actions affect state", BeliefType.SELF, 0.8),
            ("Council is trustworthy", BeliefType.EPISTEMIC, 0.6),
            ("Simulations predict reality", BeliefType.EPISTEMIC, 0.6),
            ("Exploration improves outcomes", BeliefType.PROCEDURAL, 0.65),
            ("User feedback is valuable", BeliefType.SOCIAL, 0.8),
            ("Identity is stable over time", BeliefType.SELF, 0.5),
        ]
        for desc, btype, conf in core_beliefs:
            bid = self._make_id(desc)
            self._beliefs[bid] = Belief(
                id=bid,
                description=desc,
                type=btype,
                confidence=conf,
                source="genesis",
            )

    def _make_id(self, description: str) -> str:
        raw = f"blf_{description}_{time.time()}"
        return f"blf_{hashlib.md5(raw.encode()).hexdigest()[:8]}"

    def register_belief(self, description: str, type: BeliefType,
                         confidence: float = 0.5,
                         source: str = "experience") -> str:
        """Register a new belief."""
        bid = self._make_id(description)
        if bid not in self._beliefs:
            self._beliefs[bid] = Belief(
                id=bid,
                description=description,
                type=type,
                confidence=confidence,
                source=source,
            )
        return bid

    def strengthen(self, belief_id: str, amount: float = 0.05) -> bool:
        """Increase confidence in a belief."""
        belief = self._beliefs.get(belief_id)
        if not belief or not belief.active:
            return False
        belief.confidence = min(1.0, belief.confidence + amount)
        belief.evidence_for += 1
        belief.last_used = time.time()
        return True

    def weaken(self, belief_id: str, amount: float = 0.1) -> bool:
        """Decrease confidence in a belief."""
        belief = self._beliefs.get(belief_id)
        if not belief or not belief.active:
            return False
        belief.confidence = max(0.0, belief.confidence - amount)
        belief.evidence_against += 1
        belief.last_used = time.time()
        return True

    def use_belief(self, belief_id: str, cycle: int = 0) -> None:
        """Mark a belief as having been used."""
        belief = self._beliefs.get(belief_id)
        if belief:
            belief.last_used = time.time()
            belief.last_used_cycle = cycle
            belief.staleness_cycles = 0

    def select_belief_to_examine(self, strategy: str = "least_used") -> Optional[Belief]:
        """Select a belief for examination using the given strategy.

        Strategies:
          - least_used: examine beliefs not used recently
          - weakest: examine beliefs with lowest evidential balance
          - overconfident: examine high-confidence old beliefs
          - random: random selection
        """
        active = [b for b in self._beliefs.values() if b.active and not b.archived]
        if not active:
            return None

        if strategy == "least_used":
            active.sort(key=lambda b: b.last_used)
            return active[0]
        elif strategy == "weakest":
            active.sort(key=lambda b: b.evidential_balance)
            return active[0]
        elif strategy == "overconfident":
            # High confidence + not recently examined
            active.sort(key=lambda b: -(b.confidence * 0.7 + (1 - min(1.0, b.staleness / 604800)) * 0.3))
            return active[0]
        else:  # random
            import random
            return random.choice(active)

    def examine(self, belief_id: str, cycle: int,
                 counter_evidence: Optional[str] = None,
                 force_action: Optional[ForgettingAction] = None) -> Optional[ForgettingRecord]:
        """Examine a belief and decide whether to keep, weaken, archive, or delete.

        Args:
            belief_id: The belief to examine
            cycle: Current pipeline cycle
            counter_evidence: Optional evidence that contradicts this belief
            force_action: Override the automatic decision

        Returns:
            ForgettingRecord or None if belief not found
        """
        belief = self._beliefs.get(belief_id)
        if not belief:
            return None

        confidence_before = belief.confidence
        belief.last_examined = time.time()
        belief.times_examined += 1

        if force_action:
            action = force_action
            reason = f"forced: {force_action.value}"
        else:
            action, reason = self._decide_action(belief, counter_evidence)

        # Apply the action
        confidence_after = confidence_before
        if action == ForgettingAction.RETAIN:
            belief.confidence = min(1.0, belief.confidence + 0.02)  # strengthen
            belief.examination_history.append(True)
            confidence_after = belief.confidence
        elif action == ForgettingAction.WEAKEN:
            belief.confidence = max(0.0, belief.confidence - 0.15)
            belief.examination_history.append(False)
            confidence_after = belief.confidence
        elif action == ForgettingAction.ARCHIVE:
            belief.active = False
            belief.archived = True
            belief.examination_history.append(False)
            confidence_after = 0.0
            self._total_forgotten += 1
        elif action == ForgettingAction.DELETE:
            belief.active = False
            # Remove from registry entirely (but keep the record)
            confidence_after = 0.0
            self._total_forgotten += 1

        record = ForgettingRecord(
            belief_id=belief_id,
            belief_description=belief.description,
            belief_type=belief.type.value,
            confidence_before=confidence_before,
            confidence_after=confidence_after,
            action=action.value,
            reason=reason,
            cycle=cycle,
        )

        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records.pop(0)
        self._total_examinations += 1

        # Delete if action was DELETE
        if action == ForgettingAction.DELETE:
            del self._beliefs[belief_id]

        log_action = action.value.upper()
        logger.info(
            f"ActiveForgetting: {log_action} '{belief.description[:30]}...' "
            f"(conf {confidence_before:.2f}→{confidence_after:.2f}, reason: {reason})"
        )

        return record

    def _decide_action(self, belief: Belief,
                        counter_evidence: Optional[str] = None) -> Tuple[ForgettingAction, str]:
        """Determine what action to take on a belief.

        Decision logic:
        - If conf < 0.2 and evidence_against > evidence_for → DELETE
        - If conf < 0.4 and evidence_against > evidence_for → ARCHIVE
        - If conf < 0.5 and not used in 7 days → WEAKEN
        - If staleness > 30 days and repeated examination → ARCHIVE
        - If counter_evidence provided and conf > 0.8 → WEAKEN (overconfident)
        - Otherwise → RETAIN
        """
        staleness_days = belief.staleness / 86400.0

        if counter_evidence and belief.confidence > 0.8:
            return (ForgettingAction.WEAKEN,
                    "overconfident belief with counter-evidence")

        if belief.confidence < 0.2 and belief.evidence_against > belief.evidence_for:
            return (ForgettingAction.DELETE,
                    f"confidence too low ({belief.confidence:.2f}) with negative evidence")

        if belief.confidence < 0.4 and belief.evidence_against > belief.evidence_for:
            return (ForgettingAction.ARCHIVE,
                    f"low confidence ({belief.confidence:.2f}) with contradicting evidence")

        if belief.confidence < 0.5 and staleness_days > 7:
            return (ForgettingAction.WEAKEN,
                    f"unused for {staleness_days:.0f} days with low confidence")

        if staleness_days > 30 and belief.times_examined > 3:
            return (ForgettingAction.ARCHIVE,
                    f"unused for {staleness_days:.0f} days, examined {belief.times_examined}x")

        if belief.survival_rate < 0.3 and belief.times_examined > 2:
            return (ForgettingAction.ARCHIVE,
                    f"fails examination regularly (survival: {belief.survival_rate:.2f})")

        return (ForgettingAction.RETAIN, "belief is active and supported")

    def auto_examine(self, cycle: int,
                      strategy: str = "least_used") -> Optional[ForgettingRecord]:
        """Automatically select and examine a belief.

        Called periodically by the pipeline.
        """
        if cycle - self._last_examination_cycle < self._examination_interval:
            return None

        belief = self.select_belief_to_examine(strategy)
        if not belief:
            return None

        self._last_examination_cycle = cycle
        return self.examine(belief.id, cycle)

    def get_obsolete_beliefs(self, threshold_days: float = 30) -> List[Belief]:
        """Get beliefs that haven't been used in threshold_days."""
        cutoff = time.time() - threshold_days * 86400
        return [
            b for b in self._beliefs.values()
            if b.active and not b.archived and b.last_used < cutoff
        ]

    def get_overconfident_beliefs(self, threshold: float = 0.9) -> List[Belief]:
        """Get beliefs with very high confidence that haven't been examined recently."""
        return [
            b for b in self._beliefs.values()
            if b.active and b.confidence >= threshold and
            b.staleness > 86400 * 7  # not examined in 7 days
        ]

    @property
    def total_beliefs(self) -> int:
        return len([b for b in self._beliefs.values() if b.active and not b.archived])

    @property
    def archived_beliefs(self) -> int:
        return len([b for b in self._beliefs.values() if b.archived])

    def to_dict(self) -> Dict:
        return {
            "total_examinations": self._total_examinations,
            "total_forgotten": self._total_forgotten,
            "active_beliefs": self.total_beliefs,
            "archived_beliefs": self.archived_beliefs,
            "examination_interval": self._examination_interval,
            "beliefs": {
                bid: {
                    "description": b.description[:50],
                    "type": b.type.value,
                    "confidence": round(b.confidence, 3),
                    "evidential_balance": round(b.evidential_balance, 3),
                    "staleness_hours": round(b.staleness / 3600, 1),
                    "times_examined": b.times_examined,
                    "survival_rate": round(b.survival_rate, 3),
                    "active": b.active,
                }
                for bid, b in sorted(
                    self._beliefs.items(),
                    key=lambda x: -x[1].confidence,
                )[:30]
            },
            "recent_examinations": [
                {
                    "belief": r.belief_description[:40],
                    "action": r.action,
                    "confidence": f"{r.confidence_before:.2f}→{r.confidence_after:.2f}",
                    "reason": r.reason[:50],
                    "cycle": r.cycle,
                }
                for r in self._records[-10:]
            ],
        }
