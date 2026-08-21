"""
Information Readiness Engine — Governs when facts become visible.

This engine addresses the principle that some knowledge is true, but
"not ready." Facts in the World model are tagged with ReadinessConditions.
The engine holds them in a "Locked" state until conditions are met, then
releases them to the cognitive streams.

Engineering Value:
  Prevents the system from cluttering working memory with
  "in-case-of-emergency" data during normal operation.
"""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from telos.core.governance.base import ReadinessState, ReadinessCondition

logger = logging.getLogger('telos_governance')


@dataclass
class LockedFact:
    """A fact that exists in the knowledge base but is not yet releasable."""
    fact_name: str
    state: ReadinessState = ReadinessState.LOCKED
    conditions: List[ReadinessCondition] = field(default_factory=list)
    cycle_locked: int = 0
    payload: Any = None


class InformationReadinessEngine:
    """Governs when facts become visible to cognitive streams.

    Facts live in the engine with a lifecycle:
      LOCKED → (conditions met) → READY → (consumed) → EXPIRED

    The engine exposes only READY facts to the World. Streams never
    see LOCKED or EXPIRED facts — they literally do not exist in
    the filtered World.
    """

    def __init__(self, signal_ttl: int = 3):
        self._facts: Dict[str, LockedFact] = {}
        self._cycle_count: int = 0
        self._signals: Dict[str, float] = {}
        self._signal_ttl: int = signal_ttl
        self._signal_expiry: Dict[str, int] = {}

    def register_fact(self, fact_name: str,
                       conditions: Optional[List[ReadinessCondition]] = None,
                       payload: Any = None) -> None:
        """Register a fact in the knowledge base (initially LOCKED).
        fact_name: the fact name for this operation
        conditions: the conditions for this operation
        payload: the payload for this operation
"""
        self._facts[fact_name] = LockedFact(
            fact_name=fact_name,
            state=ReadinessState.LOCKED,
            conditions=conditions or [],
            cycle_locked=self._cycle_count,
            payload=payload,
        )
        logger.debug(f"ReadinessEngine: registered fact '{fact_name}' ({len(conditions or [])} conditions)")

    def emit_signal(self, signal_name: str, strength: float = 1.0) -> None:
        """Emit a signal that may satisfy readiness conditions.

        Signals are the mechanism by which conditions are met.
        Example: a SensorStream emits signal "high_severity_alarm"
        which satisfies the condition for unlocking the DisasterPlan.
        
        signal_name: the signal name for this operation
        strength: the strength for this operation
"""
        self._signals[signal_name] = strength
        self._signal_expiry[signal_name] = self._cycle_count + self._signal_ttl
        logger.debug(f"ReadinessEngine: signal '{signal_name}' (strength={strength:.2f})")

    def tick(self) -> None:
        """Advance one cycle — evaluate all locked facts."""
        self._cycle_count += 1

        # Clean expired signals before evaluating conditions
        expired = [name for name, exp in self._signal_expiry.items()
                   if exp <= self._cycle_count]
        for name in expired:
            self._signals.pop(name, None)
            self._signal_expiry.pop(name, None)
        if expired:
            logger.debug(f"ReadinessEngine: cleaned {len(expired)} expired signal(s)")

        for fact_name, fact in list(self._facts.items()):
            if fact.state == ReadinessState.EXPIRED:
                continue

            if fact.state == ReadinessState.LOCKED:
                self._evaluate_conditions(fact)

            elif fact.state == ReadinessState.READY:
                # Facts stay ready for a configurable duration
                if self._cycle_count - fact.cycle_locked > 10:
                    fact.state = ReadinessState.EXPIRED
                    logger.debug(f"ReadinessEngine: fact '{fact_name}' expired")

    def _evaluate_conditions(self, fact: LockedFact) -> None:
        """Evaluate all conditions for a locked fact."""
        if not fact.conditions:
            # No conditions → immediately ready
            fact.state = ReadinessState.READY
            return

        all_met = True
        for cond in fact.conditions:
            if cond.condition_type == "cycle_count":
                met = self._cycle_count >= cond.threshold
            elif cond.condition_type == "signal_detected":
                met = cond.description in self._signals
            else:
                met = False
            if not met:
                all_met = False

        if all_met:
            fact.state = ReadinessState.READY
            fact.cycle_locked = self._cycle_count
            logger.info(f"ReadinessEngine: fact '{fact.fact_name}' is now READY")

    def is_ready(self, fact_name: str) -> bool:
        """Check if a specific fact is ready for consumption.
        fact_name: the fact name for this operation
"""
        fact = self._facts.get(fact_name)
        return fact is not None and fact.state == ReadinessState.READY

    def release_manually(self, fact_name: str) -> bool:
        """Force-release a locked fact (emergency override).
        fact_name: the fact name for this operation
"""
        fact = self._facts.get(fact_name)
        if fact is None:
            return False
        fact.state = ReadinessState.READY
        fact.cycle_locked = self._cycle_count
        logger.warning(f"ReadinessEngine: MANUAL RELEASE of '{fact_name}'")
        return True

    @property
    def stats(self) -> Dict:
        states = {s: 0 for s in ReadinessState}
        for f in self._facts.values():
            states[f.state] = states.get(f.state, 0) + 1
        return {
            "total_facts": len(self._facts),
            "locked": states.get(ReadinessState.LOCKED, 0),
            "ready": states.get(ReadinessState.READY, 0),
            "expired": states.get(ReadinessState.EXPIRED, 0),
            "cycle": self._cycle_count,
        }
