"""
CouncilReflector — Meta-Learning for the Council of Cognitive Advisors.

Prateek's insight #1: "Council must update itself — not just block/pass
but ask 'was that right?' afterwards. Meta-learning."

The Council currently blocks or passes but never evaluates its own accuracy.
CouncilReflector adds a hindsight loop: after action, compare prediction to
outcome and update validator confidence weights accordingly.

Architecture:
  - Each validator's confidence is treated as a Bayesian prior
  - After the outcome is known, the reflector computes posterior confidence
  - Validators that were right get boosted; those that were wrong get dampened
  - Historical accuracy is tracked per validator for meta-attribution

Integrates with:
  - Council.evaluate() — called after each decision cycle with outcome data
  - ErrorAttributionEngine — reports which validator caused the error
  - DecisionTrace — stores reflection results
"""

from __future__ import annotations

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger('telos_council_reflector')


@dataclass
class ReflectionRecord:
    """A single reflection: what was predicted, what happened, who was right."""
    cycle: int
    selected_intent: str
    predicted_di: float
    actual_di: float
    predicted_md: float
    actual_md: float
    was_blocked: bool
    should_have_been_blocked: bool
    validator_accuracy: Dict[str, bool]  # validator_name -> was_correct
    outcome_quality: float  # 0.0 (bad) to 1.0 (good)


@dataclass
class ValidatorTrackRecord:
    """Longitudinal accuracy tracking for a single validator."""
    validator_name: str
    total_decisions: int = 0
    correct_decisions: int = 0
    false_positives: int = 0  # blocked when shouldn't have
    false_negatives: int = 0  # passed when shouldn't have
    confidence_history: List[float] = field(default_factory=list)
    accuracy_window: List[bool] = field(default_factory=list)
    max_window: int = 100

    @property
    def accuracy(self) -> float:
        if self.total_decisions == 0:
            return 0.5  # no evidence yet
        return self.correct_decisions / max(self.total_decisions, 1)

    @property
    def precision(self) -> float:
        denom = self.correct_decisions + self.false_positives
        return self.correct_decisions / max(denom, 1) if denom > 0 else 0.5

    @property
    def recall(self) -> float:
        denom = self.correct_decisions + self.false_negatives
        return self.correct_decisions / max(denom, 1) if denom > 0 else 0.5

    def record_decision(self, was_correct: bool, predicted_block: bool,
                         should_have_blocked: bool) -> None:
        self.total_decisions += 1
        self.accuracy_window.append(was_correct)
        if len(self.accuracy_window) > self.max_window:
            self.accuracy_window.pop(0)
        if was_correct:
            self.correct_decisions += 1
        elif predicted_block and not should_have_blocked:
            self.false_positives += 1
        elif not predicted_block and should_have_blocked:
            self.false_negatives += 1


class CouncilReflector:
    """Post-hoc evaluator of council decisions.

    After each decision cycle, the reflector determines:
    1. Was the council's decision correct? (should it have blocked?)
    2. Which validators were right/wrong?
    3. What should change about validator confidence weights?

    The reflector does NOT modify validators directly. It produces
    a reflection report that the pipeline can use to adjust trust
    weights for the next cycle.
    """

    def __init__(self, window_size: int = 50):
        self._track_records: Dict[str, ValidatorTrackRecord] = {}
        self._reflection_history: List[ReflectionRecord] = []
        self._max_history = 200
        self._window_size = window_size
        self._total_reflections: int = 0
        self._consecutive_incorrect: int = 0

    def _get_track(self, name: str) -> ValidatorTrackRecord:
        if name not in self._track_records:
            self._track_records[name] = ValidatorTrackRecord(validator_name=name)
        return self._track_records[name]

    def reflect(self, cycle: int, selected_intent: str,
                validator_signals: List[Dict],
                predicted_di: float, actual_di: float,
                predicted_md: float, actual_md: float,
                was_blocked: bool,
                outcome_success: bool) -> ReflectionRecord:
        """Reflect on a completed decision cycle.

        Args:
            cycle: Current pipeline cycle
            selected_intent: The intent that was selected
            validator_signals: List of dicts with 'validator_name', 'passed', 'confidence'
            predicted_di: DI that was predicted before action
            actual_di: DI that resulted after action
            predicted_md: MD that was predicted
            actual_md: MD that resulted
            was_blocked: Whether the council blocked action
            outcome_success: Whether the outcome was actually good (from hindsight)

        Returns:
            ReflectionRecord with accuracy data
        """
        # Determine if blocking was correct in hindsight
        # A block is correct if the outcome would have been bad
        # A pass is correct if the outcome was good
        should_have_been_blocked = not outcome_success
        council_was_correct = (
            (was_blocked and should_have_been_blocked) or
            (not was_blocked and outcome_success)
        )

        # Evaluate each validator's decision
        validator_accuracy: Dict[str, bool] = {}
        for signal in validator_signals:
            name = signal.get('validator_name', 'unknown')
            predicted_block = not signal.get('passed', True)
            was_correct = (
                (predicted_block and should_have_been_blocked) or
                (not predicted_block and outcome_success)
            )
            validator_accuracy[name] = was_correct

            track = self._get_track(name)
            track.record_decision(
                was_correct=was_correct,
                predicted_block=predicted_block,
                should_have_blocked=should_have_been_blocked,
            )

        # Track consecutive incorrect council decisions
        if council_was_correct:
            self._consecutive_incorrect = 0
        else:
            self._consecutive_incorrect += 1

        # Compute outcome quality
        di_quality = 1.0 - min(1.0, abs(predicted_di - actual_di))
        md_quality = 1.0 - min(1.0, abs(predicted_md - actual_md) / 5.0)
        outcome_quality = (di_quality + md_quality) / 2.0

        record = ReflectionRecord(
            cycle=cycle,
            selected_intent=selected_intent,
            predicted_di=predicted_di,
            actual_di=actual_di,
            predicted_md=predicted_md,
            actual_md=actual_md,
            was_blocked=was_blocked,
            should_have_been_blocked=should_have_been_blocked,
            validator_accuracy=validator_accuracy,
            outcome_quality=outcome_quality,
        )

        self._reflection_history.append(record)
        if len(self._reflection_history) > self._max_history:
            self._reflection_history.pop(0)
        self._total_reflections += 1

        logger.info(
            f"CouncilReflector: council_was_correct={council_was_correct}, "
            f"outcome_quality={outcome_quality:.3f}, "
            f"consecutive_incorrect={self._consecutive_incorrect}"
        )

        return record

    def get_validator_confidence_adjustments(self) -> Dict[str, float]:
        """Compute confidence adjustments for each validator.

        Returns a dict mapping validator_name -> adjustment factor.
        > 1.0 means boost confidence; < 1.0 means reduce.
        Based on recent accuracy in the sliding window.
        """
        adjustments: Dict[str, float] = {}
        for name, track in self._track_records.items():
            if track.total_decisions < 5:
                adjustments[name] = 1.0  # not enough data
                continue

            recent_window = track.accuracy_window[-self._window_size:]
            if not recent_window:
                adjustments[name] = 1.0
                continue

            recent_accuracy = sum(recent_window) / len(recent_window)
            # Map accuracy to adjustment: 0.5 -> 1.0, 1.0 -> 1.2, 0.0 -> 0.5
            adjustment = 0.5 + recent_accuracy * 0.7
            adjustments[name] = round(adjustment, 3)

        return adjustments

    def get_validator_trust_scores(self) -> Dict[str, float]:
        """Return trust scores [0, 1] for each validator based on track record."""
        scores: Dict[str, float] = {}
        for name, track in self._track_records.items():
            # Blend accuracy and precision with Bayesian prior
            accuracy = track.accuracy
            precision = track.precision
            scores[name] = round((accuracy * 0.6 + precision * 0.4), 3)
        return scores

    def get_worst_performers(self, top_n: int = 3) -> List[Tuple[str, float]]:
        """Return the N validators with lowest recent accuracy."""
        recent_accuracies = []
        for name, track in self._track_records.items():
            if len(track.accuracy_window) >= 5:
                recent = sum(track.accuracy_window[-10:]) / max(len(track.accuracy_window[-10:]), 1)
                recent_accuracies.append((name, recent))
        recent_accuracies.sort(key=lambda x: x[1])
        return recent_accuracies[:top_n]

    @property
    def reflection_count(self) -> int:
        return self._total_reflections

    @property
    def council_accuracy(self) -> float:
        """Overall council accuracy over history."""
        if not self._reflection_history:
            return 0.5
        correct = sum(
            1 for r in self._reflection_history
            if r.was_blocked == r.should_have_been_blocked
        )
        return correct / len(self._reflection_history)

    def to_dict(self) -> Dict:
        return {
            "total_reflections": self._total_reflections,
            "council_accuracy": round(self.council_accuracy, 3),
            "consecutive_incorrect": self._consecutive_incorrect,
            "validator_tracks": {
                name: {
                    "accuracy": track.accuracy,
                    "precision": track.precision,
                    "recall": track.recall,
                    "total_decisions": track.total_decisions,
                }
                for name, track in self._track_records.items()
            },
        }
