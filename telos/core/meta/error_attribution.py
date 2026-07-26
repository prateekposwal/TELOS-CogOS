"""
MetaErrorAttribution — Which Subsystem Caused This?

Prateek's insight #2: "Meta-Error Attribution — not 'I made a mistake'
but 'which subsystem caused it?' Update the right component."

The current system has Kintsugi (failure recording) but no mechanism
for attributing errors to specific subsystems: streams, validators,
simulation, perception, or governance.

Architecture:
  - Each error is traced back to the subsystem that most likely caused it
  - Attribution uses a combination of signal analysis and counterfactual
    comparison: "would alternative B have avoided this error?"
  - Error types are categorized and tracked per-subsystem
  - The pipeline uses attribution results to target repairs

Subsystems tracked:
  - PERCEPTION: Failed to observe relevant state
  - STREAM: Generated incorrect intent
  - SIMULATION: Predicted wrong future
  - COUNCIL: Wrongly blocked or passed
  - GOVERNANCE: Policy error
  - EXECUTION: Action failed to produce expected state
"""

from __future__ import annotations

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger('telos_error_attribution')


class Subsystem(Enum):
    PERCEPTION = "perception"
    STREAM = "stream"
    SIMULATION = "simulation"
    COUNCIL = "council"
    GOVERNANCE = "governance"
    EXECUTION = "execution"
    IDENTITY = "identity"
    UNKNOWN = "unknown"


class ErrorClass(Enum):
    FALSE_POSITIVE = "false_positive"      # acted when shouldn't have
    FALSE_NEGATIVE = "false_negative"      # didn't act when should have
    MISPLANNING = "misplanning"            # plan was wrong
    MISPERCEPTION = "misperception"        # saw wrong thing
    MISATTRIBUTION = "misattribution"      # blamed wrong cause
    RESOURCE_ERROR = "resource_error"      # ran out of resources
    TIMING_ERROR = "timing_error"          # acted too early/late
    CONSTRAINT_VIOLATION = "constraint_violation"  # broke a rule


@dataclass
class ErrorAttribution:
    """The result of attributing an error to one or more subsystems."""
    cycle: int
    primary_subsystem: Subsystem
    contributing_subsystems: List[Subsystem]
    error_class: ErrorClass
    confidence: float  # 0.0-1.0 how confident we are in this attribution
    evidence: Dict[str, Any]  # supporting evidence
    description: str


@dataclass
class SubsystemErrorRecord:
    """Longitudinal error record for one subsystem."""
    subsystem: Subsystem
    total_errors: int = 0
    error_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    recent_attributions: List[ErrorAttribution] = field(default_factory=list)
    max_history: int = 50
    fixable: bool = True  # whether this subsystem can be automatically updated

    def record(self, attribution: ErrorAttribution) -> None:
        self.total_errors += 1
        self.error_counts[attribution.error_class.value] += 1
        self.recent_attributions.append(attribution)
        if len(self.recent_attributions) > self.max_history:
            self.recent_attributions.pop(0)

    @property
    def primary_error_class(self) -> Optional[str]:
        if not self.error_counts:
            return None
        return max(self.error_counts, key=self.error_counts.get)

    @property
    def error_rate(self) -> float:
        return self.total_errors / max(len(self.recent_attributions), 1)


class ErrorAttributionEngine:
    """Attributes errors to subsystems based on signal analysis.

    The engine operates in two phases:
    1. Signal Collection: Gather signals from each subsystem
    2. Attribution: Determine which subsystem caused the error

    Attribution logic:
      - If council blocked but outcome would have been good -> COUNCIL (false positive)
      - If council passed but outcome was bad -> COUNCIL (false negative)
      - If simulation predicted wrong -> SIMULATION
      - If perception reported wrong state -> PERCEPTION
      - If action failed -> EXECUTION
      - If policy blocked unnecessarily -> GOVERNANCE
    """

    def __init__(self):
        self._subsystem_records: Dict[Subsystem, SubsystemErrorRecord] = {
            s: SubsystemErrorRecord(subsystem=s)
            for s in Subsystem
        }
        self._attribution_history: List[ErrorAttribution] = []
        self._max_history = 200
        self._total_attributions = 0
        # Fixable subsystems (can be automatically updated)
        for s in [Subsystem.COUNCIL, Subsystem.STREAM, Subsystem.IDENTITY]:
            self._subsystem_records[s].fixable = True
        for s in [Subsystem.PERCEPTION, Subsystem.SIMULATION, Subsystem.GOVERNANCE]:
            self._subsystem_records[s].fixable = True
        self._subsystem_records[Subsystem.EXECUTION].fixable = False
        self._subsystem_records[Subsystem.UNKNOWN].fixable = False

    def attribute(self, cycle: int,
                  predicted_state: Any, actual_state: Any,
                  was_blocked: bool, should_have_blocked: bool,
                  council_signals: List[Dict],
                  simulation_error: float,
                  perception_quality: float,
                  action_error: float,
                  intent_type: str) -> ErrorAttribution:
        """Attribute an error to the most likely subsystem.

        Args:
            cycle: Pipeline cycle number
            predicted_state: State predicted by simulation
            actual_state: Actual resulting state
            was_blocked: Whether council blocked action
            should_have_blocked: Whether action should have been blocked (hindsight)
            council_signals: List of validator signal dicts
            simulation_error: ||predicted - actual|| divergence
            perception_quality: Perception quality score (0-1)
            action_error: How much actual action differed from planned (0-1)
            intent_type: The type of intent that was selected

        Returns:
            ErrorAttribution with primary subsystem and evidence
        """
        evidence: Dict[str, Any] = {}
        primary = Subsystem.UNKNOWN
        error_class = ErrorClass.MISATTRIBUTION
        confidence = 0.5
        description = ""

        # ── Rule 1: Council classification error ──
        if was_blocked != should_have_blocked:
            if was_blocked and not should_have_blocked:
                # Council blocked when it shouldn't have
                primary = Subsystem.COUNCIL
                error_class = ErrorClass.FALSE_POSITIVE
                confidence = 0.8
                description = "Council blocked a valid action (false positive)"
                evidence = {
                    "blocking_validators": [
                        s.get('validator_name') for s in council_signals
                        if not s.get('passed', True)
                    ],
                    "verdict": "blocked_incorrectly",
                }
            else:
                # Council passed when it shouldn't have
                primary = Subsystem.COUNCIL
                error_class = ErrorClass.FALSE_NEGATIVE
                confidence = 0.8
                description = "Council passed an invalid action (false negative)"
                evidence = {
                    "passing_validators": [
                        s.get('validator_name') for s in council_signals
                        if s.get('passed', True)
                    ],
                    "verdict": "passed_incorrectly",
                }

        # ── Rule 2: Simulation error ──
        elif simulation_error > 5.0:
            primary = Subsystem.SIMULATION
            error_class = ErrorClass.MISPLANNING
            confidence = min(0.9, simulation_error / 10.0)
            description = f"Simulation predicted wrong state (error={simulation_error:.2f})"
            evidence = {"prediction_error": simulation_error}

        # ── Rule 3: Perception error ──
        elif perception_quality < 0.3:
            primary = Subsystem.PERCEPTION
            error_class = ErrorClass.MISPERCEPTION
            confidence = 0.7
            description = f"Perception quality too low ({perception_quality:.2f})"
            evidence = {"perception_quality": perception_quality}

        # ── Rule 4: Execution error ──
        elif action_error > 0.5:
            primary = Subsystem.EXECUTION
            error_class = ErrorClass.RESOURCE_ERROR
            confidence = 0.6
            description = f"Action execution failed (error={action_error:.2f})"
            evidence = {"action_error": action_error}

        # ── Rule 5: No clear attribution ──
        else:
            primary = Subsystem.UNKNOWN
            error_class = ErrorClass.MISATTRIBUTION
            confidence = 0.3
            description = "No clear subsystem attribution available"
            evidence = {"ambiguous": True}

        attribution = ErrorAttribution(
            cycle=cycle,
            primary_subsystem=primary,
            contributing_subsystems=self._find_contributors(
                primary, simulation_error, perception_quality, was_blocked
            ),
            error_class=error_class,
            confidence=confidence,
            evidence=evidence,
            description=description,
        )

        # Record in subsystem tracking
        self._subsystem_records[primary].record(attribution)
        for contributor in attribution.contributing_subsystems:
            if contributor != primary:
                self._subsystem_records[contributor].record(attribution)

        self._attribution_history.append(attribution)
        if len(self._attribution_history) > self._max_history:
            self._attribution_history.pop(0)
        self._total_attributions += 1

        logger.info(
            f"ErrorAttribution: cycle={cycle}, primary={primary.value}, "
            f"class={error_class.value}, confidence={confidence:.2f}, "
            f"desc={description[:60]}"
        )

        return attribution

    def _find_contributors(self, primary: Subsystem,
                           sim_error: float, perception_quality: float,
                           was_blocked: bool) -> List[Subsystem]:
        """Find subsystems that contributed to the error."""
        contributors: List[Subsystem] = []
        if sim_error > 2.0 and primary != Subsystem.SIMULATION:
            contributors.append(Subsystem.SIMULATION)
        if perception_quality < 0.5 and primary != Subsystem.PERCEPTION:
            contributors.append(Subsystem.PERCEPTION)
        if was_blocked and primary != Subsystem.COUNCIL:
            contributors.append(Subsystem.COUNCIL)
        return contributors

    def get_subsystem_health(self) -> Dict[str, Dict]:
        """Return health metrics for each subsystem."""
        health: Dict[str, Dict] = {}
        for subsystem, record in self._subsystem_records.items():
            health[subsystem.value] = {
                "total_errors": record.total_errors,
                "error_rate": record.error_rate,
                "primary_error_class": record.primary_error_class,
                "fixable": record.fixable,
                "error_breakdown": dict(record.error_counts),
            }
        return health

    def get_most_erratic_subsystem(self) -> Optional[Tuple[Subsystem, float]]:
        """Return the subsystem with the highest error rate."""
        best = None
        best_rate = 0.0
        for subsystem, record in self._subsystem_records.items():
            if record.error_rate > best_rate:
                best_rate = record.error_rate
                best = subsystem
        return (best, best_rate) if best else None

    @property
    def total_attributions(self) -> int:
        return self._total_attributions

    def to_dict(self) -> Dict:
        return {
            "total_attributions": self._total_attributions,
            "subsystem_health": self.get_subsystem_health(),
            "worst_subsystem": (
                self.get_most_erratic_subsystem()[0].value
                if self.get_most_erratic_subsystem() else None
            ),
        }
