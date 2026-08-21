"""
DualConfidence — Separate "I Know What to Do" from "I Understand Why."

Prateek's insight: "Explanation confidence vs decision confidence — separate
'I know what to do' from 'I understand why.' Different metrics."

Most systems have a single confidence score. But knowing WHAT to do and
understanding WHY are fundamentally different:

- Decision Confidence (DC): "I know what action to take."
  → Based on: predictive accuracy, past success rate, option quality
  → High DC = clear course of action, even if explanation is incomplete

- Explanation Confidence (EC): "I understand why this is the right action."
  → Based on: causal model coherence, evidence chain completeness, theory support
  → High EC = I can explain the reasoning chain end-to-end

These can diverge:
  - I know what to do but can't explain why (intuition, pattern matching)
  - I can explain why but don't know what to do (analysis paralysis)
  - I know AND I can explain (mature understanding)
  - I neither know nor can explain (novel situation)

Architecture:
  - DualConfidence tracks both metrics separately
  - Each is computed from different signals
  - The pipeline uses both: DC for action selection, EC for transparency reporting
  - A large gap between DC and EC signals incomplete understanding
  - Meta-cognition uses the gap to decide: explore more, or exploit?
"""

from __future__ import annotations

import logging
import math
import time
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger('telos_dual_confidence')


@dataclass
class DecisionConfidence:
    """Confidence in knowing WHAT action to take."""
    score: float                    # 0-1 overall decision confidence
    predictive_accuracy: float      # Past success rate for similar decisions
    option_clarity: float           # How clear the best option is (0=all equal, 1=clear winner)
    familiarity: float              # How familiar this situation is
    urgency: float                  # Time pressure (higher = more reliance on DC)
    sources: Dict[str, float] = field(default_factory=dict)

    @property
    def is_high(self) -> bool:
        return self.score >= 0.7

    @property
    def is_low(self) -> bool:
        return self.score < 0.4


@dataclass
class ExplanationConfidence:
    """Confidence in understanding WHY an action is right."""
    score: float                    # 0-1 overall explanation confidence
    causal_coherence: float         # How well the causal chain holds together
    evidence_completeness: float    # Are all links in the chain supported?
    theory_support: float           # Does this align with established theories?
    falsifiability: float           # Could we be wrong? (higher = more honest)
    sources: Dict[str, float] = field(default_factory=dict)

    @property
    def is_high(self) -> bool:
        return self.score >= 0.7

    @property
    def is_low(self) -> bool:
        return self.score < 0.4


@dataclass
class ConfidenceReport:
    """Complete dual confidence report for a decision."""
    decision_id: str
    decision_confidence: DecisionConfidence
    explanation_confidence: ExplanationConfidence
    gap: float                      # |DC - EC|, 0=aligned, 1=completely divergent
    gap_type: str                   # "aligned", "intuition", "analysis_paralysis", "confusion"
    timestamp: float = field(default_factory=time.time)


class DualConfidence:
    """Tracks decision confidence and explanation confidence separately.

    The dual confidence tracker:
    1. Maintains separate metrics for DC and EC
    2. Computes DC from: predictive accuracy, option clarity, familiarity
    3. Computes EC from: causal coherence, evidence completeness, theory support
    4. Tracks the gap between DC and EC over time
    5. Classifies the gap type for meta-cognitive use

    Gap types:
      - ALIGNED: DC ≈ EC — coherent understanding
      - INTUITION: DC > EC — knows what to do but can't fully explain
      - ANALYSIS_PARALYSIS: EC > DC — can explain but unsure what to do
      - CONFUSION: DC low, EC low — novel or ambiguous situation

    Integration:
      - Fed into meta-cognition module
      - Gap type influences exploration vs exploitation decisions
      - EC reported in transparency/audit logs
      - DC used in action selection with appropriate caution
    """

    def __init__(self, window_size: int = 20):
        self._window_size = window_size
        self._report_history: List[ConfidenceReport] = []
        self._max_history = 200
        self._total_reports: int = 0

        # Running averages
        self._avg_dc: float = 0.5
        self._avg_ec: float = 0.5
        self._avg_gap: float = 0.0

    def compute_decision_confidence(self,
                                     predictive_accuracy: float,
                                     option_scores: List[float],
                                     familiarity: float,
                                     urgency: float = 0.0) -> DecisionConfidence:
        """Compute decision confidence (what to do).

        Args:
            predictive_accuracy: How often similar decisions succeeded [0, 1]
            option_scores: Scores of all options under consideration
            familiarity: How familiar this situation is [0, 1]
            urgency: Time pressure [0, 1]

        Returns:
            DecisionConfidence with computed score and sources
        """
        # Option clarity: how distinct is the best option?
        if len(option_scores) >= 2:
            sorted_scores = sorted(option_scores, reverse=True)
            best = sorted_scores[0]
            second = sorted_scores[1]
            if best > 0:
                option_clarity = (best - second) / best
            else:
                option_clarity = 0.0
            option_clarity = min(1.0, max(0.0, option_clarity))
        elif len(option_scores) == 1:
            option_clarity = 1.0
        else:
            option_clarity = 0.0

        # Blend factors
        dc = (
            predictive_accuracy * 0.35 +
            option_clarity * 0.35 +
            familiarity * 0.20 +
            urgency * 0.10  # Urgency boosts DC (forced confidence)
        )
        dc = min(1.0, max(0.0, dc))

        return DecisionConfidence(
            score=dc,
            predictive_accuracy=predictive_accuracy,
            option_clarity=option_clarity,
            familiarity=familiarity,
            urgency=urgency,
            sources={
                "predictive_accuracy": predictive_accuracy,
                "option_clarity": option_clarity,
                "familiarity": familiarity,
                "urgency": urgency,
            },
        )

    def compute_explanation_confidence(self,
                                        causal_coherence: float,
                                        evidence_completeness: float,
                                        theory_support: float,
                                        falsifiability: float = 0.5) -> ExplanationConfidence:
        """Compute explanation confidence (why this action).

        Args:
            causal_coherence: How well the causal chain holds together [0, 1]
            evidence_completeness: Are all reasoning links supported? [0, 1]
            theory_support: Alignment with established theories [0, 1]
            falsifiability: Awareness of potential flaws [0, 1]

        Returns:
            ExplanationConfidence with computed score and sources
        """
        # High falsifiability actually LOWERS EC slightly (honest uncertainty)
        ec = (
            causal_coherence * 0.30 +
            evidence_completeness * 0.30 +
            theory_support * 0.25 +
            (1.0 - falsifiability) * 0.15  # Less falsifiable = more confident (less honest)
        )
        ec = min(1.0, max(0.0, ec))

        return ExplanationConfidence(
            score=ec,
            causal_coherence=causal_coherence,
            evidence_completeness=evidence_completeness,
            theory_support=theory_support,
            falsifiability=falsifiability,
            sources={
                "causal_coherence": causal_coherence,
                "evidence_completeness": evidence_completeness,
                "theory_support": theory_support,
                "falsifiability": falsifiability,
            },
        )

    def report(self, decision_id: str,
                dc: DecisionConfidence,
                ec: ExplanationConfidence) -> ConfidenceReport:
        """Generate a dual confidence report for a decision.

        Args:
            decision_id: Identifier for this decision
            dc: Decision confidence
            ec: Explanation confidence

        Returns:
            ConfidenceReport with gap analysis
        """
        gap = abs(dc.score - ec.score)

        # Classify gap type
        if gap < 0.15:
            gap_type = "aligned"
        elif dc.score > ec.score + 0.15:
            gap_type = "intuition"
        elif ec.score > dc.score + 0.15:
            gap_type = "analysis_paralysis"
        else:
            gap_type = "confusion"

        report = ConfidenceReport(
            decision_id=decision_id,
            decision_confidence=dc,
            explanation_confidence=ec,
            gap=gap,
            gap_type=gap_type,
        )

        self._report_history.append(report)
        if len(self._report_history) > self._max_history:
            self._report_history.pop(0)
        self._total_reports += 1

        # Update running averages
        n = len(self._report_history)
        self._avg_dc = (self._avg_dc * (n - 1) + dc.score) / n if n > 0 else dc.score
        self._avg_ec = (self._avg_ec * (n - 1) + ec.score) / n if n > 0 else ec.score
        self._avg_gap = (self._avg_gap * (n - 1) + gap) / n if n > 0 else gap

        if gap > 0.3:
            logger.info(
                f"DualConfidence: DC={dc.score:.2f} ≠ EC={ec.score:.2f} "
                f"(gap={gap:.2f}, type={gap_type}) — {decision_id[:30]}"
            )

        return report

    def get_recent_gap_trend(self, window: int = 10) -> str:
        """Describe how the DC-EC gap is trending.
            Args:
                window: the window argument for this call.
        """
        if len(self._report_history) < window:
            return "insufficient_data"
        recent = [r.gap for r in self._report_history[-window:]]
        if len(recent) < 2:
            return "stable"
        first = sum(recent[:window//2]) / (window//2)
        second = sum(recent[window//2:]) / (window - window//2)
        if second > first + 0.1:
            return "widening"
        elif second < first - 0.1:
            return "narrowing"
        return "stable"

    @property
    def average_decision_confidence(self) -> float:
        return self._avg_dc

    @property
    def average_explanation_confidence(self) -> float:
        return self._avg_ec

    @property
    def average_gap(self) -> float:
        return self._avg_gap

    @property
    def dominant_gap_type(self) -> str:
        """Most common gap type in recent history."""
        if not self._report_history:
            return "unknown"
        recent = self._report_history[-50:]
        types = {}
        for r in recent:
            types[r.gap_type] = types.get(r.gap_type, 0) + 1
        return max(types, key=types.get) if types else "unknown"

    def to_dict(self) -> Dict:
        return {
            "total_reports": self._total_reports,
            "average_decision_confidence": round(self._avg_dc, 3),
            "average_explanation_confidence": round(self._avg_ec, 3),
            "average_gap": round(self._avg_gap, 3),
            "dominant_gap_type": self.dominant_gap_type,
            "gap_trend": self.get_recent_gap_trend(),
            "recent_reports": [
                {
                    "decision_id": r.decision_id[:30],
                    "dc": round(r.decision_confidence.score, 3),
                    "ec": round(r.explanation_confidence.score, 3),
                    "gap": round(r.gap, 3),
                    "gap_type": r.gap_type,
                }
                for r in self._report_history[-10:]
            ],
        }
