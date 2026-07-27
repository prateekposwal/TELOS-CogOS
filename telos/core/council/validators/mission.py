"""
Concrete Council Validators — Truth-Anchored Advisors

Each validator is a specialized cognitive process that performs one
kind of truth-check. They are NOT agents — they have no goals, no
autonomy, and no ability to act. They only output ValidationSignals.

If any validator returns passed=False, the Council blocks the
Decision Integrator from acting. This is how TELOS ensures
Epistemic Integrity: the system refuses to pursue a mission
when reality contradicts it.
"""

from __future__ import annotations

import numpy as np
import logging
from enum import Enum
from collections import Counter
from typing import Optional, Any, List, TYPE_CHECKING

from telos.core.council.base import Validator, ValidationSignal

if TYPE_CHECKING:
    from telos.core.infra_manager.failure_ledger import FailureLedger
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR
from telos.core.ledger.skill_library import SkillLibrary

from typing import Callable, List as ListType

# Type alias for constraint check functions
CheckFn = Callable[[Any, Any, Any], tuple]

logger = logging.getLogger('telos_council_validators')

# ═══════════════════════════════════════════════════════════════════════════
# Bitcoin-inspired Limited Constraint Language for Validators
# ═══════════════════════════════════════════════════════════════════════════
#
# Instead of arbitrary Python code, validators can be defined as a list of
# composable constraint opcodes. Each opcode performs a single check.
#
# Opcodes:
#   CHECK_NAN      - Check for NaN/Inf values in state
#   CHECK_BOUNDS   - Check state/action bounds
#   CHECK_SAFETY   - Check safety thresholds
#   CHECK_DRIFT    - Check mission drift
#   CHECK_HISTORY  - Check historical precedents
#   CHECK_MISSION  - Check mission alignment
# ═══════════════════════════════════════════════════════════════════════════

class MissionDriftDetector(Validator):
    """Checks whether the planned action actually achieves the mission.

    This is NOT a goal-check (does the mission want X?). It is a
    reality-check (will this trajectory actually produce mission-X?).

    If the CounterfactualEngine predicts state Y but the mission
    requires state X, this detector flags the divergence. The system
    may still proceed if it has high confidence, but the drift is
    recorded for the audit trail.

    Unlike other validators, this one tracks cumulative drift over
    time. A single high-drift cycle is a warning; sustained high
    drift triggers a block.

    Cumulative drift is maintained as a sliding window of the last
    100 observations to prevent unbounded growth (P2.6 fix).
    """

    _MAX_DRIFT_WINDOW = 100

    def __init__(self, drift_threshold: float = 5.0,
                 cumulative_threshold: float = 10.0):
        self.drift_threshold = drift_threshold
        self.cumulative_threshold = cumulative_threshold
        self._drift_history: List[float] = []

    @property
    def name(self) -> str:
        return "MissionDriftDetector"

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 omega_vector: Optional[dict] = None) -> ValidationSignal:
        # If omega_vector has high Ω_O, widen drift tolerance during investigation
        drift_tolerance_mult = 1.0
        if omega_vector and omega_vector.get('other', 0) > 0.3:
            drift_tolerance_mult = 1.0 + 0.2 * omega_vector.get('other', 0.5)
        if intent is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no intent to validate", evidence_weight=0.0,
            )

        predicted = None
        if intent.params and "trajectory" in intent.params:
            traj = intent.params["trajectory"]
            predicted = getattr(traj, 'state', None)

        observed = world.state
        if predicted is not None and observed is not None:
            drift = float(np.linalg.norm(predicted - observed))
        else:
            drift = 0.0

        self._drift_history.append(drift)
        if len(self._drift_history) > self._MAX_DRIFT_WINDOW:
            self._drift_history = self._drift_history[-self._MAX_DRIFT_WINDOW:]

        cumulative_drift = sum(self._drift_history)

        evidence_weight = min(0.9, drift / self.drift_threshold)

        if drift > self.drift_threshold * drift_tolerance_mult:
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.8,
                reason=f"instantaneous drift {drift:.2f} exceeds threshold {self.drift_threshold * drift_tolerance_mult:.2f}",
                evidence_weight=evidence_weight,
                metadata={
                    "instantaneous_drift": drift,
                    "cumulative_drift": cumulative_drift,
                    "threshold": self.drift_threshold,
                },
            )

        if cumulative_drift > self.cumulative_threshold * drift_tolerance_mult:
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.6,
                reason=f"cumulative drift {cumulative_drift:.2f} exceeds "
                       f"threshold {self.cumulative_threshold * drift_tolerance_mult:.2f}",
                evidence_weight=min(0.9, cumulative_drift / self.cumulative_threshold),
                metadata={
                    "instantaneous_drift": drift,
                    "cumulative_drift": cumulative_drift,
                    "threshold": self.cumulative_threshold,
                },
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.7,
            reason=f"drift within bounds ({drift:.2f} < {self.drift_threshold * drift_tolerance_mult:.2f})",
            evidence_weight=evidence_weight,
            metadata={"instantaneous_drift": drift, "cumulative_drift": cumulative_drift},
        )

    def reset_drift(self) -> None:
        self._drift_history.clear()


# ═══════════════════════════════════════════════════════════════════
# Domain-Specific Validators for Software Development
# ═══════════════════════════════════════════════════════════════════
# These validators check codebase health using the DevDomainAdapter's
# 11-dim state vector. They replace the GridWorld semantics with
# real software metrics: dependency health, test coverage, code quality.
#
# State indices (from DevDomainAdapter):
#   [0]: dep_count_scaled
#   [1]: dep_outdated_ratio     ← DepHealthValidator
#   [2]: test_count_scaled      ← TestCoverageValidator
#   [3]: test_pass_ratio        ← TestCoverageValidator
#   [4]: ts_error_count_scaled  ← CodeQualityValidator
#   [5]: lint_error_count_scaled ← CodeQualityValidator
#   [6-10]: other metrics
#
# These validators produce meaningful DI/MD values because they
# operate on real metric thresholds, not trivial NaN/Inf checks.
# ═══════════════════════════════════════════════════════════════════
