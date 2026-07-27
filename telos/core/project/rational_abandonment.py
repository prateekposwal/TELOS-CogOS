"""Rational Abandonment Gate — distinguishes persistence from obsession.

Four-input decision function:

Abandon(Commitment, Evidence, Alternatives, Expected Value)
  -> {Continue, Pause, Archive, Terminate}

Persistence: Commitment up while Evidence >= threshold.
Obsession:   Commitment up while Evidence down and Alternatives up.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger('telos_abandonment')


class AbandonmentDecision(str, Enum):
    CONTINUE = "continue"
    PAUSE = "pause"
    ARCHIVE = "archive"
    TERMINATE = "terminate"


class Trend(str, Enum):
    RISING = "rising"
    STABLE = "stable"
    DECLINING = "declining"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass
class AbandonmentConfig:
    min_cycles_before_evaluation: int = 10
    evidence_decline_threshold: float = 0.3
    alternative_value_gap: float = 0.2
    min_cycles_method: int = 5
    min_cycles_project: int = 50
    min_cycles_mission: int = 500


@dataclass
class AbandonmentVerdict:
    decision: AbandonmentDecision
    reason: str
    confidence: float


class AbandonmentGate:
    """Four-input abandonment evaluator: Commitment, Evidence, Alternatives, EV."""

    def __init__(self, config: Optional[AbandonmentConfig] = None):
        self._config = config or AbandonmentConfig()

    def evaluate(self, commitment_trend: Trend, evidence_trend: Trend,
                 alternative_value: float, project_ev: float,
                 time_invested: int, level: str = "method") -> AbandonmentVerdict:
        cfg = self._config
        min_cycles = {"method": cfg.min_cycles_method,
                      "project": cfg.min_cycles_project,
                      "mission": cfg.min_cycles_mission}.get(level, 10)

        if time_invested < min_cycles:
            return AbandonmentVerdict(
                decision=AbandonmentDecision.CONTINUE,
                reason=f"too early ({time_invested} < {min_cycles} for {level})",
                confidence=1.0,
            )

        if level == "mission":
            return AbandonmentVerdict(
                decision=AbandonmentDecision.CONTINUE,
                reason="missions almost never terminate",
                confidence=0.95,
            )

        evidence_declining = evidence_trend == Trend.DECLINING
        commitment_rising = commitment_trend == Trend.RISING
        alternatives_better = alternative_value > project_ev + cfg.alternative_value_gap

        if commitment_rising and evidence_declining and alternatives_better:
            return AbandonmentVerdict(
                decision=AbandonmentDecision.PAUSE if level == "project" else AbandonmentDecision.ARCHIVE,
                reason=f"obsession pattern: commitment rising, evidence declining, alternatives better",
                confidence=0.7,
            )

        if evidence_declining and alternatives_better:
            return AbandonmentVerdict(
                decision=AbandonmentDecision.ARCHIVE if level == "method" else AbandonmentDecision.PAUSE,
                reason=f"evidence declining and alternatives better",
                confidence=0.6,
            )

        if commitment_rising and evidence_declining:
            return AbandonmentVerdict(
                decision=AbandonmentDecision.PAUSE,
                reason=f"commitment rising despite declining evidence",
                confidence=0.5,
            )

        return AbandonmentVerdict(
            decision=AbandonmentDecision.CONTINUE,
            reason=f"no abandonment signal",
            confidence=0.8,
        )
