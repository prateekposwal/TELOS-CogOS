"""
Council of Cognitive Advisors — Epistemic Integrity Layer

The Council is NOT multi-agent architecture. Advisors are not
sovereign agents with independent goals. They are Validators:
specialized cognitive processes that perform mandatory sanity
checks on the World model and the Planned Trajectory before
the Decision Integrator is allowed to act.

Key properties:
  1. Shared State: All Advisors read from the same World object
  2. No Autonomy: They cannot act — they only output ValidationSignals
  3. Mandatory Integration: The Decision Integrator REFUSES to act
     if the Council returns Non-Validated status

This prevents the "sycophant problem" — a system that learns to tell
the user what they want to hear rather than what is true.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Literal
import numpy as np
import logging

from telos.world.world import World
from telos.intent_ir import IntentIR

logger = logging.getLogger('telos_council')


@dataclass
class ValidationSignal:
    """The atomic unit of internal dissent.

    Each validator outputs one ValidationSignal per decision cycle.
    The signal records whether the validator approved or objected,
    with what confidence, and (crucially) the evidence_weight.

    Verdict modes:
      PASS     — all good, proceed
      BLOCK    — this must not proceed
      ESCALATE — uncertain; suggest human guidance (0.3 ≤ confidence ≤ 0.7)
    """
    validator_name: str
    passed: bool
    confidence: float
    reason: str
    evidence_weight: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    verdict: Literal["PASS", "BLOCK", "ESCALATE"] = "PASS"


@dataclass
class CouncilVerdict:
    """The aggregated output of the Council for one decision cycle.

    Decision Integrity (DI):
        1 - sum(IgnoredEvidence * BeliefConfidence) / TotalAvailableEvidence
        DI = 1.0 means fully evidence-led; DI drops when evidence is ignored.

    Mission Drift (MD):
        ||PredictedState - ObservedState||
        MD increases when the system's model of reality diverges from actual outcomes.

    Escalation:
        When a validator's verdict is ESCALATE (not BLOCK, not PASS),
        the Council flags escalation_requested and stores the reason.
        The pipeline may proceed but should log the uncertainty for human review.
    """
    validated: bool
    signals: List[ValidationSignal] = field(default_factory=list)
    decision_integrity: float = 1.0
    mission_drift: float = 0.0
    blocking_validator: Optional[str] = None
    escalation_requested: bool = False
    escalation_reason: Optional[str] = None
    escalation_signals: List[ValidationSignal] = field(default_factory=list)

    @property
    def summary(self) -> str:
        passed = sum(1 for s in self.signals if s.passed)
        total = len(self.signals)
        blockers = [s.validator_name for s in self.signals if not s.passed]
        escalations = [s.validator_name for s in self.escalation_signals]
        blk = f"BLOCKED by: {', '.join(blockers)}" if blockers else "all clear"
        esc = f" | ESCALATED by: {', '.join(escalations)}" if escalations else ""
        return f"Council: {passed}/{total} passed, DI={self.decision_integrity:.3f}, MD={self.mission_drift:.3f}, {blk}{esc}"


class Validator(ABC):
    """Abstract interface for all Council Advisors.

    Each validator implements validate() which receives the current
    World state, the candidate IntentIR, and optional DomainFacts.
    It returns a ValidationSignal indicating approval or objection.

    The confidence field of ValidationSignal represents:
      1.0 = "I am certain this is correct"
      0.0 = "I have no opinion / abstain"
      -1.0 = "I am certain this is WRONG" (most dissent signals are negative)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None) -> ValidationSignal:
        ...


class Council:
    """Orchestrates validators and produces a binding verdict.

    The Council is the Integrity Stack. It routes the selected intent
    through all registered validators in priority order. If any
    validator returns a blocking signal (passed=False), the Council
    returns validated=False and the Decision Integrator MUST refuse to act.

    The Council also computes:
      - Decision Integrity (DI): evidence-truthfulness metric
      - Mission Drift (MD): reality-divergence metric
    """

    DISSENT_FLOOR: float = 0.3

    def __init__(self):
        self._validators: List[Validator] = []

    def register(self, validator: Validator) -> None:
        self._validators.append(validator)

    def evaluate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 predicted_state: Optional[np.ndarray] = None,
                 observed_state: Optional[np.ndarray] = None,
                 evidence_influence_weights: Optional[Dict[str, float]] = None) -> CouncilVerdict:
        """Run all validators and produce a binding verdict.

        Args:
            evidence_influence_weights: Optional dict mapping validator_name →
                evidence multiplier for DI computation.
        """
        signals: List[ValidationSignal] = []

        for validator in self._validators:
            try:
                signal = validator.validate(world, intent, domain_facts)
            except Exception as e:
                logger.error(f"Council: validator {validator.name} raised {e}")
                signal = ValidationSignal(
                    validator_name=validator.name,
                    passed=False,
                    confidence=0.0,
                    reason=f"validator error: {e}",
                    evidence_weight=0.5,
                )
            # Auto-ESCALATE if validator confidence is in the uncertain range
            # and evidence_weight is non-trivial
            if signal.passed and 0.3 < signal.confidence < 0.7 and signal.evidence_weight > 0.3:
                signal.verdict = "ESCALATE"
            elif not signal.passed:
                signal.verdict = "BLOCK"
            else:
                signal.verdict = "PASS"
            signals.append(signal)

        # Compute Decision Integrity (DI)
        di = self._compute_decision_integrity(signals, evidence_influence_weights)

        # Compute Mission Drift (MD)
        md = self._compute_mission_drift(predicted_state, observed_state)

        # Find blocking validators
        blockers = [s.validator_name for s in signals if not s.passed]
        validated = len(blockers) == 0
        blocking_name = blockers[0] if blockers else None

        # Find escalation signals
        escalations = [s for s in signals if s.verdict == "ESCALATE"]
        escalation_requested = len(escalations) > 0
        escalation_reason = (
            "; ".join(f"{s.validator_name}: {s.reason}" for s in escalations)
            if escalations else None
        )

        verdict = CouncilVerdict(
            validated=validated,
            signals=signals,
            decision_integrity=di,
            mission_drift=md,
            blocking_validator=blocking_name,
            escalation_requested=escalation_requested,
            escalation_reason=escalation_reason,
            escalation_signals=escalations,
        )

        logger.info(verdict.summary)
        return verdict

    def _compute_decision_integrity(self, signals: List[ValidationSignal],
                                     evidence_weights: Optional[Dict[str, float]] = None) -> float:
        """DI = 1 - sum(IgnoredEvidence * BeliefConfidence) / TotalAvailableEvidence

        When evidence_weights are provided (from StreamCalibrator), each
        validator's evidence_weight is modulated by the corresponding stream's
        evidence score, so low-evidence streams carry less weight.
        
        DissentFloor: When any BLOCK exists, DI cannot exceed DISSENT_FLOOR
        (default 0.3) regardless of numerical computation. Prevents evidence-weight
        manipulation from silencing legitimate dissent.
        """
        total_evidence = 0.0
        ignored = 0.0
        has_block = False
        for s in signals:
            ew = s.evidence_weight
            if evidence_weights and s.validator_name in evidence_weights:
                ew *= evidence_weights[s.validator_name]
            total_evidence += ew
            if not s.passed:
                has_block = True
                ignored += ew * abs(s.confidence)
        total_evidence = total_evidence or 1e-9
        di = float(np.clip(1.0 - ignored / total_evidence, 0.0, 1.0))

        # DissentFloor: cap DI when any BLOCK exists
        if has_block:
            di = min(di, self.DISSENT_FLOOR)

        return di

    def _compute_mission_drift(self, predicted: Optional[np.ndarray],
                                observed: Optional[np.ndarray]) -> float:
        """MD = ||PredictedState - ObservedState||"""
        if predicted is None or observed is None:
            return 0.0
        return float(np.linalg.norm(predicted - observed))

    @property
    def validator_count(self) -> int:
        return len(self._validators)
