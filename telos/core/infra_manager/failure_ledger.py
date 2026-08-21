"""
Failure Ledger — Kintsugi: Failure as a Structural Asset

Failures are not errors to be discarded. They are structural insights
to be integrated into the system's Cognitive Identity. When a decision
leads to a Council block, Firewall block, high MissionDrift, or low
DecisionIntegrity, the FailureLedger:

  1. Records the failure with full context (cycle, phase, reason)
  2. Tags the root cause (e.g., "representation_mismatch", "simulation_divergence")
  3. Updates the Cognitive Identity of affected entities
  4. Makes the failure available for MemoryAdvisor queries

The system becomes "fractally stronger" with every error — each failure
is a kintsugi repair that makes the whole structure more resilient.
"""

from __future__ import annotations

import time
import logging
import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Set, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from telos.core.runtime import PipelineResult

logger = logging.getLogger('telos_infra')


@dataclass
class FailureRecord:
    """A single failure event with root cause analysis."""
    failure_id: str
    cycle: int
    timestamp: float
    failure_type: str  # "council_block", "firewall_block", "high_drift", "low_integrity"
    severity: float    # 0.0 (minor) to 1.0 (critical)
    root_cause: str
    blocked_by: Optional[str] = None
    decision_integrity: float = 1.0
    mission_drift: float = 0.0
    affected_entities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    repair_outcome: Optional[str] = None  # Kintsugi: what structural repair was made
    repair_effective: Optional[bool] = None  # Kintsugi: did the repair work?
    identity_markers_added: List[str] = field(default_factory=list)  # Kintsugi: markers added to SystemSelf


class FailureLedger:
    """Persistent ledger of system failures — the Kintsugi integration point.

    Every failure is recorded with root cause analysis and made available
    for future reasoning. The ledger does not "delete" failures — it
    integrates them as structural knowledge.
    """

    ROOT_CAUSE_PATTERNS = {
        "council_rejection": "governance_intervention",
        "low_integrity": "epistemic_compromise",
        "reality_mismatch": "sensor_divergence",
        "constraint_violation": "policy_boundary",
        "pattern_lock": "opponent_adaptation",
        "escalation": "unresolved_uncertainty",
    }

    def __init__(self, max_failures: int = 10000):
        self._failures: List[FailureRecord] = []
        self._max_failures = max_failures
        self._eviction_count: int = 0
        self._type_index: Dict[str, List[int]] = defaultdict(list)
        self._root_cause_counts: Dict[str, int] = {}

    def observe(self, result: Any) -> Optional[FailureRecord]:
        """Record a failure if the cycle had issues.

        Returns the FailureRecord if one was created, else None.
        Args:
            result: the observation result
        """
        trace = result.decision_trace
        if trace is None:
            return None

        failure = None

        if result.council_blocked:
            failure = self._record(
                failure_type="council_block",
                severity=0.8,
                result=result,
                root_cause=self.ROOT_CAUSE_PATTERNS.get(
                    trace.blocking_validator or "", "council_rejection"
                ),
                blocked_by=trace.blocking_validator,
            )
        elif result.firewall_blocked:
            failure = self._record(
                failure_type="firewall_block",
                severity=0.7,
                result=result,
                root_cause="governance_intervention",
                blocked_by=result.governance_blocked_by,
            )
        elif trace.mission_drift > 5.0:
            failure = self._record(
                failure_type="high_drift",
                severity=min(0.6, trace.mission_drift / 10.0),
                result=result,
                root_cause="simulation_divergence",
            )
        elif trace.decision_integrity < 0.3:
            failure = self._record(
                failure_type="low_integrity",
                severity=0.5,
                result=result,
                root_cause="epistemic_compromise",
            )

        return failure

    def _append(self, record: FailureRecord) -> FailureRecord:
        """Append a record with cap enforcement and type indexing."""
        if len(self._failures) >= self._max_failures:
            self._failures.pop(0)
            self._eviction_count += 1
        idx = len(self._failures)
        self._failures.append(record)
        self._type_index[record.failure_type].append(idx)
        self._root_cause_counts[record.root_cause] = \
            self._root_cause_counts.get(record.root_cause, 0) + 1
        return record

    def _record(self, failure_type: str, severity: float,
                 result: PipelineResult, root_cause: str,
                 blocked_by: Optional[str] = None) -> FailureRecord:
        trace = result.decision_trace
        record = FailureRecord(
            failure_id=f"fail_{uuid.uuid4().hex[:8]}",
            cycle=trace.cycle_id if trace else 0,
            timestamp=time.time(),
            failure_type=failure_type,
            severity=severity,
            root_cause=root_cause,
            blocked_by=blocked_by,
            decision_integrity=trace.decision_integrity if trace else 1.0,
            mission_drift=trace.mission_drift if trace else 0.0,
            affected_entities=list(trace.semantic_depths) if trace and trace.semantic_depths else [],
            metadata={
                "council_validated": trace.council_validated if trace else True,
                "firewall_blocked": trace.firewall_blocked if hasattr(trace, 'firewall_blocked') else False,
            },
        )
        self._append(record)
        logger.info(f"Kintsugi: recorded {failure_type} (severity={severity:.2f}, cause={root_cause})")
        return record


    def record_direct(self, record: FailureRecord) -> FailureRecord:
        """Record a pre-built FailureRecord directly, bypassing observe().

        Used by InfraManager for synthetic failures (budget_starvation,
        simulation_timeout, escalation, predictive_degradation) that
        need to be recorded without going through the normal observe()
        pipeline.
        """
        self._append(record)
        logger.info(
            f"Kintsugi: recorded {record.failure_type} via record_direct "
            f"(severity={record.severity:.2f}, cause={record.root_cause})"
        )
        return record

    def integrate_into_identity(self, failure: FailureRecord) -> Set[str]:
        """Kintsugi: Update identity markers based on failure patterns.

        Maps failure types to identity markers so the system knows
        what it is recovering from. Returns the set of markers added.
        """
        marker_map = {
            "council_block": "learning_governance",
            "firewall_block": "testing_boundaries",
            "high_drift": "calibrating_prediction",
            "low_integrity": "repairing_epistemics",
            "pattern_exploit": "breaking_patterns",
            "budget_starvation": "conserving_resources",
            "simulation_timeout": "improving_simulation",
            "escalation": "seeking_clarity",
        }
        marker = marker_map.get(failure.failure_type, "recovering_from_" + failure.root_cause)
        failure.identity_markers_added.append(marker)
        failure.repair_outcome = "identity_update"
        logger.info(
            f"Kintsugi: integrated {failure.failure_id} ({failure.failure_type}) "
            f"→ identity marker '{marker}'"
        )
        return {marker}

    def get_recent_failures(self, n: int = 10) -> List[FailureRecord]:
        return self._failures[-n:]

    def get_failures_by_type(self, failure_type: str) -> List[FailureRecord]:
        indices = self._type_index.get(failure_type, [])
        return [self._failures[i] for i in indices if i < len(self._failures)]

    def get_root_cause_summary(self) -> Dict[str, int]:
        return dict(self._root_cause_counts)

    @property
    def total_failures(self) -> int:
        return len(self._failures)

    @property
    def stats(self) -> Dict:
        return {
            "total_failures": self.total_failures,
            "max_failures": self._max_failures,
            "eviction_count": self._eviction_count,
            "root_causes": self.get_root_cause_summary(),
            "by_type": {
                t: len(self.get_failures_by_type(t))
                for t in ["council_block", "firewall_block", "high_drift", "low_integrity", "pattern_exploit", "escalation", "simulation_timeout", "perception_degraded", "budget_starvation", "knowledge_conflict"]
            },
        }
