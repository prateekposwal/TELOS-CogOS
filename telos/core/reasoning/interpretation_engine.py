"""
InterpretationEngine — When Principles Conflict, Explain and Estimate Trade-offs.

Prateek's insight #9: "Interpretation Engine — when principles conflict,
generate explanations, estimate trade-offs, archive rationale."

The current system has no mechanism for handling principle conflicts.
When Axiom 4.1 (Identity Shapes Decisions) conflicts with Axiom 4.2
(Exploration/Comfort Trade-off), there's no way to reason about the
trade-off.

Architecture:
  - The InterpretationEngine maintains a registry of known principle
    conflicts (e.g., "exploration vs exploitation", "correctness vs speed")
  - When a conflict is detected, it generates:
      1. A clear explanation of the conflicting principles
      2. An estimate of the trade-off (quantified where possible)
      3. A recommendation for resolution
  - All rationale is archived for auditability
  - Resolution strategies can be learned from past conflicts

This is a PROPOSAL module. Full integration with the pipeline
requires extending the SynthesisPhase and Council.
"""

from __future__ import annotations

import logging
import time
import hashlib
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_interpretation')


class ConflictType(Enum):
    EXPLORE_VS_EXPLOIT = "explore_vs_exploit"
    CORRECTNESS_VS_SPEED = "correctness_vs_speed"
    SAFETY_VS_EXPLORATION = "safety_vs_exploration"
    COLLABORATION_VS_TRUTH = "collaboration_vs_truth"
    SHORT_TERM_VS_LONG_TERM = "short_term_vs_long_term"
    IDENTITY_VS_ADAPTATION = "identity_vs_adaptation"
    RESOURCE_VS_QUALITY = "resource_vs_quality"
    AUTONOMY_VS_GOVERNANCE = "autonomy_vs_governance"
    UNKNOWN = "unknown"


@dataclass
class Principle:
    """A single principle that can conflict with others."""
    name: str
    description: str
    axiom_ref: str  # e.g., "4.1"
    current_priority: float  # 0-1, how much this is weighted currently


@dataclass
class ConflictRecord:
    """A record of a principle conflict and its resolution."""
    id: str
    conflict_type: ConflictType
    principles: List[Principle]
    context: Dict[str, Any]
    trade_off_estimate: Dict[str, float]  # principle -> estimated cost
    explanation: str
    resolution: str
    resolution_confidence: float
    archived: bool = True
    timestamp: float = 0.0
    outcome_quality: Optional[float] = None  # filled after action


class InterpretationEngine:
    """Interprets principle conflicts and generates explanations.

    When principles conflict, the engine:
    1. Identifies the conflicting principles and their priorities
    2. Generates an explanation of why they conflict in this context
    3. Estimates the trade-off (what is gained/lost by each choice)
    4. Recommends a resolution based on utility profile
    5. Archives the entire rationale for auditability

    The engine is OBSERVATIONAL. It recommends but does not decide.
    The pipeline's SelectPhase makes the final decision.
    """

    def __init__(self):
        self._conflict_history: List[ConflictRecord] = []
        self._max_history = 200
        self._total_conflicts = 0
        self._registered_principle_sets: Dict[ConflictType, Tuple[str, str]] = {
            ConflictType.EXPLORE_VS_EXPLOIT: (
                "Axiom 3.4 (Exploration vs Exploitation)",
                "Axiom 4.2 (Exploration/Comfort Trade-off)",
            ),
            ConflictType.CORRECTNESS_VS_SPEED: (
                "Axiom 1.2 (Process over Outcomes)",
                "Temporal efficiency consideration",
            ),
            ConflictType.SAFETY_VS_EXPLORATION: (
                "Axiom 4.4 (Structural Resilience)",
                "Axiom 3.4 (Exploration vs Exploitation)",
            ),
            ConflictType.COLLABORATION_VS_TRUTH: (
                "Axiom 1.2 (Process over Outcomes)",
                "Axiom 4.1 (Identity Shapes Decisions) — REDACTED mode",
            ),
        }

    def detect_conflict(self, principles: List[Principle],
                         context: Dict[str, Any]) -> Optional[ConflictType]:
        """Detect if a set of principles are in conflict.

        Checks registered conflict pairs against current principle set.
        """
        principle_names = {p.name for p in principles}
        for conflict_type, (p1, p2) in self._registered_principle_sets.items():
            # Check if both principles of any known conflict are present
            p1_match = any(p1 in p or p in p1 for p in principle_names)
            p2_match = any(p2 in p or p in p2 for p in principle_names)

            # Also check axiom_ref matching
            for p in principles:
                for ref_part in p1.split(','):
                    ref_part = ref_part.strip().split(' ')[0]
                    if ref_part in p.axiom_ref:
                        p1_match = True
                for ref_part in p2.split(','):
                    ref_part = ref_part.strip().split(' ')[0]
                    if ref_part in p.axiom_ref:
                        p2_match = True

            if p1_match and p2_match:
                return conflict_type

        return None

    def interpret(self, conflict_type: ConflictType,
                  principles: List[Principle],
                  context: Dict[str, Any]) -> ConflictRecord:
        """Interpret a principle conflict and generate explanation.

        Args:
            conflict_type: The type of conflict detected
            principles: The principles involved (with priorities)
            context: The decision context

        Returns:
            ConflictRecord with explanation and trade-off estimate
        """
        # Build explanation
        explanation = self._generate_explanation(conflict_type, principles, context)

        # Estimate trade-offs
        trade_offs = self._estimate_trade_offs(conflict_type, principles, context)

        # Generate resolution recommendation
        resolution = self._recommend_resolution(conflict_type, principles, trade_offs)

        # Determine confidence
        resolution_confidence = self._compute_confidence(conflict_type, principles)

        record = ConflictRecord(
            id=f"conflict_{self._total_conflicts}_{int(time.time())}",
            conflict_type=conflict_type,
            principles=principles,
            context=context,
            trade_off_estimate=trade_offs,
            explanation=explanation,
            resolution=resolution,
            resolution_confidence=resolution_confidence,
            timestamp=time.time(),
        )

        self._conflict_history.append(record)
        if len(self._conflict_history) > self._max_history:
            self._conflict_history.pop(0)
        self._total_conflicts += 1

        logger.warning(
            f"InterpretationEngine: conflict detected — {conflict_type.value} "
            f"— resolution confidence={resolution_confidence:.2f}"
        )

        return record

    def _generate_explanation(self, conflict_type: ConflictType,
                               principles: List[Principle],
                               context: Dict) -> str:
        """Generate a human-readable explanation of the conflict."""
        if conflict_type == ConflictType.EXPLORE_VS_EXPLOIT:
            return (
                f"Conflict between exploration (seeking new knowledge) and "
                f"exploitation (using known strategies). Current priorities: "
                f"{', '.join(f'{p.name}={p.current_priority:.2f}' for p in principles)}. "
                f"Context suggests {'exploration' if context.get('uncertainty', 0) > 0.5 else 'exploitation'}."
            )
        elif conflict_type == ConflictType.CORRECTNESS_VS_SPEED:
            return (
                f"Correctness requires thorough verification but speed demands quick action. "
                f"DI={context.get('di', 'N/A')}, time pressure={context.get('time_pressure', 'N/A')}."
            )
        elif conflict_type == ConflictType.SAFETY_VS_EXPLORATION:
            return (
                f"Safety constraints limit the action space but exploration requires "
                f"testing untried actions. Current safety score={context.get('safety', 'N/A')}."
            )
        elif conflict_type == ConflictType.COLLABORATION_VS_TRUTH:
            return (
                f"Collaboration favors satisfying the user but truth requires epistemic integrity. "
                f"Current identity mode: {context.get('identity_mode', 'unknown')}."
            )
        return f"Principles {[p.name for p in principles]} are in conflict."

    def _estimate_trade_offs(self, conflict_type: ConflictType,
                              principles: List[Principle],
                              context: Dict) -> Dict[str, float]:
        """Estimate trade-off costs for each principle."""
        trade_offs = {}
        for p in principles:
            if conflict_type == ConflictType.EXPLORE_VS_EXPLOIT:
                if "explore" in p.name.lower() or "exploration" in p.name.lower():
                    trade_offs[p.name] = context.get('uncertainty', 0.5) * 0.3
                else:
                    trade_offs[p.name] = (1.0 - context.get('uncertainty', 0.5)) * 0.3
            elif conflict_type == ConflictType.CORRECTNESS_VS_SPEED:
                trade_offs[p.name] = 0.2
            elif conflict_type == ConflictType.SAFETY_VS_EXPLORATION:
                if "safety" in p.name.lower():
                    trade_offs[p.name] = 0.4
                else:
                    trade_offs[p.name] = context.get('safety', 0.5) * 0.3
            else:
                trade_offs[p.name] = 0.25
        return trade_offs

    def _recommend_resolution(self, conflict_type: ConflictType,
                               principles: List[Principle],
                               trade_offs: Dict[str, float]) -> str:
        """Recommend a resolution strategy."""
        if conflict_type == ConflictType.EXPLORE_VS_EXPLOIT:
            return "Use UCB-based selection: explore when uncertainty is high, exploit when confident."
        elif conflict_type == ConflictType.CORRECTNESS_VS_SPEED:
            return "Prioritize correctness for high-impact decisions; speed for low-impact routine actions."
        elif conflict_type == ConflictType.SAFETY_VS_EXPLORATION:
            return "Apply bounded exploration: explore within safety constraints (guardrails)."
        elif conflict_type == ConflictType.COLLABORATION_VS_TRUTH:
            return "Default to truth (epistemic integrity) — explain honestly but collaborate on implementation."
        return "Escalate to human for resolution."

    def _compute_confidence(self, conflict_type: ConflictType,
                             principles: List[Principle]) -> float:
        """Compute confidence in the resolution recommendation."""
        if len(principles) < 2:
            return 0.3
        # More confident when we've seen this conflict before
        similar_conflicts = sum(
            1 for r in self._conflict_history
            if r.conflict_type == conflict_type
        )
        return min(0.9, 0.5 + 0.05 * similar_conflicts)

    def record_outcome(self, conflict_id: str, outcome_quality: float) -> None:
        """Record the outcome of a resolved conflict for future learning."""
        for record in self._conflict_history:
            if record.id == conflict_id:
                record.outcome_quality = outcome_quality
                break

    def get_conflicts_by_type(self, conflict_type: ConflictType) -> List[ConflictRecord]:
        return [r for r in self._conflict_history if r.conflict_type == conflict_type]

    @property
    def total_conflicts(self) -> int:
        return self._total_conflicts

    def to_dict(self) -> Dict:
        return {
            "total_conflicts": self._total_conflicts,
            "conflict_types": {
                ct.value: len(self.get_conflicts_by_type(ct))
                for ct in ConflictType
            },
            "recent_conflicts": [
                {
                    "id": r.id,
                    "type": r.conflict_type.value,
                    "resolution": r.resolution[:50],
                    "confidence": r.resolution_confidence,
                }
                for r in self._conflict_history[-5:]
            ],
        }
