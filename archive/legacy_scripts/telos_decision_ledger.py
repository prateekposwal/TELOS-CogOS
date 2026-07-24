"""
TELOS Decision Ledger

Captures not just what was decided, but WHY: assumptions, evidence,
dependencies, and expected outcomes. When drift occurs, the system
looks up the exact chain of logic leading to the current state,
enabling targeted assumption invalidation rather than blind rollbacks.

Integrates:
1. Decision Ledger with structured metadata
2. Assumption-Triggered Re-Evaluation (ATRE)
3. Epistemic Confidence Decay
4. Merkle-Anchored Decision Trails
5. Genesis Recovery integration
"""

import time
import uuid
import hashlib
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque, OrderedDict
from enum import Enum


class DecisionStatus(Enum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    REVIEWED = "REVIEWED"
    RECOVERED = "RECOVERED"


@dataclass
class DecisionLedgerEntry:
    """Single audited decision node with explicit assumptions and dependencies."""
    decision_id: str
    timestamp: float
    mission_id: str
    action_summary: str
    assumptions: List[str]
    evidence: Dict[str, Any]
    dependencies: List[str]
    confidence: float
    expected_outcome: Dict[str, Any]
    status: str = "ACTIVE"
    parent_decision_id: Optional[str] = None
    confidence_decay_rate: float = 0.01
    merkle_hash: str = ""
    recovery_tier: int = 0
    invalidated_at: Optional[float] = None
    invalidation_reason: Optional[str] = None

    def compute_hash(self) -> str:
        data = f"{self.decision_id}:{self.mission_id}:{self.action_summary}:{self.confidence}:{self.status}"
        return hashlib.sha256(data.encode()).hexdigest()

    def get_decayed_confidence(self, current_time: Optional[float] = None) -> float:
        t = current_time or time.time()
        elapsed = t - self.timestamp
        hours = elapsed / 3600.0
        return self.confidence * np.exp(-self.confidence_decay_rate * hours)

    def to_dict(self) -> Dict:
        return {
            'decision_id': self.decision_id,
            'timestamp': self.timestamp,
            'mission_id': self.mission_id,
            'action_summary': self.action_summary,
            'assumptions': self.assumptions,
            'evidence': self.evidence,
            'dependencies': self.dependencies,
            'confidence': self.confidence,
            'expected_outcome': self.expected_outcome,
            'status': self.status,
            'parent_decision_id': self.parent_decision_id,
            'merkle_hash': self.merkle_hash,
            'recovery_tier': self.recovery_tier,
            'invalidated_at': self.invalidated_at,
            'invalidation_reason': self.invalidation_reason,
        }


@dataclass
class AssumptionViolation:
    decision_id: str
    assumption: str
    telemetry_key: str
    expected: Any
    actual: Any
    severity: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class RecoveryTrigger:
    decision_id: str
    tier: int
    reason: str
    violated_assumptions: List[str]
    confidence_delta: float
    timestamp: float = field(default_factory=time.time)


class ATREEngine:
    """Assumption-Triggered Re-Evaluation engine.

    When a dependent variable changes state in the Context Mesh,
    ATRE automatically queues affected decisions for verification.
    """

    def __init__(self, severity_threshold: float = 0.5):
        self.severity_threshold = severity_threshold
        self._assumption_registry: Dict[str, List[str]] = {}
        self._telemetry_keys: Dict[str, str] = {}
        self._revaluation_queue: deque = deque(maxlen=1000)
        self._total_checks = 0
        self._total_violations = 0

    def register_assumption(self, decision_id: str, assumption: str,
                           telemetry_key: str):
        if decision_id not in self._assumption_registry:
            self._assumption_registry[decision_id] = []
        self._assumption_registry[decision_id].append(assumption)
        self._telemetry_keys[f"{decision_id}:{assumption}"] = telemetry_key

    def check_assumptions(self, decision_id: str,
                         assumptions: List[str],
                         current_telemetry: Dict[str, Any]) -> List[AssumptionViolation]:
        violations = []
        self._total_checks += len(assumptions)

        for assumption in assumptions:
            key = f"{decision_id}:{assumption}"
            telemetry_key = self._telemetry_keys.get(key, assumption)

            if telemetry_key in current_telemetry:
                expected = current_telemetry.get(f"{telemetry_key}_expected",
                                                 current_telemetry.get(telemetry_key))
                actual = current_telemetry[telemetry_key]

                if isinstance(expected, bool) and not actual:
                    severity = 1.0
                elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                    diff = abs(expected - actual)
                    severity = min(1.0, diff / (abs(expected) + 1e-8))
                else:
                    severity = 0.0 if expected == actual else 0.8

                if severity > 0:
                    self._total_violations += 1
                    violations.append(AssumptionViolation(
                        decision_id=decision_id,
                        assumption=assumption,
                        telemetry_key=telemetry_key,
                        expected=expected,
                        actual=actual,
                        severity=severity,
                    ))

        return violations

    def queue_revaluation(self, decision_id: str, reason: str):
        self._revaluation_queue.append({
            'decision_id': decision_id,
            'reason': reason,
            'timestamp': time.time(),
        })

    def get_revaluation_queue(self) -> List[Dict]:
        return list(self._revaluation_queue)

    def get_statistics(self) -> Dict:
        return {
            'total_checks': self._total_checks,
            'total_violations': self._total_violations,
            'violation_rate': self._total_violations / self._total_checks if self._total_checks else 0.0,
            'queued_revaluations': len(self._revaluation_queue),
            'registered_decisions': len(self._assumption_registry),
        }


class DecisionLedger:
    """Manages lifecycle, tracking, and retroactive auditing of decisions."""

    def __init__(self, max_entries: int = 10000, decay_rate: float = 0.01):
        self._entries: OrderedDict[str, DecisionLedgerEntry] = OrderedDict()
        self._mission_index: Dict[str, List[str]] = {}
        self._atre = ATREEngine()
        self._decay_rate = decay_rate
        self._max_entries = max_entries
        self._merkle_chain: List[str] = []
        self._total_recorded = 0
        self._total_invalidated = 0

    def record_decision(self, mission_id: str, action_summary: str,
                       assumptions: List[str], evidence: Dict[str, Any],
                       dependencies: List[str], confidence: float,
                       expected_outcome: Dict[str, Any],
                       parent_decision_id: Optional[str] = None) -> str:
        entry_id = f"dec-{uuid.uuid4().hex[:8]}"
        entry = DecisionLedgerEntry(
            decision_id=entry_id,
            timestamp=time.time(),
            mission_id=mission_id,
            action_summary=action_summary,
            assumptions=assumptions,
            evidence=evidence,
            dependencies=dependencies,
            confidence=confidence,
            expected_outcome=expected_outcome,
            parent_decision_id=parent_decision_id,
            confidence_decay_rate=self._decay_rate,
        )

        entry.merkle_hash = entry.compute_hash()
        self._entries[entry_id] = entry

        if mission_id not in self._mission_index:
            self._mission_index[mission_id] = []
        self._mission_index[mission_id].append(entry_id)

        for assumption in assumptions:
            self._atre.register_assumption(entry_id, assumption, assumption)

        self._merkle_chain.append(entry.merkle_hash)
        self._total_recorded += 1

        if len(self._entries) > self._max_entries:
            self._evict_oldest()

        return entry_id

    def get_decision(self, decision_id: str) -> Optional[DecisionLedgerEntry]:
        return self._entries.get(decision_id)

    def get_decisions_for_mission(self, mission_id: str) -> List[DecisionLedgerEntry]:
        ids = self._mission_index.get(mission_id, [])
        return [self._entries[i] for i in ids if i in self._entries]

    def get_active_decisions(self) -> List[DecisionLedgerEntry]:
        return [e for e in self._entries.values() if e.status == "ACTIVE"]

    def audit_assumptions(self, current_telemetry: Dict[str, Any]) -> List[str]:
        invalidated = []
        for dec_id, entry in list(self._entries.items()):
            if entry.status != "ACTIVE":
                continue

            violations = self._atre.check_assumptions(
                dec_id, entry.assumptions, current_telemetry
            )

            severe_violations = [v for v in violations if v.severity >= self._atre.severity_threshold]
            if severe_violations:
                entry.status = "INVALIDATED"
                entry.invalidated_at = time.time()
                entry.invalidation_reason = f"Assumption violations: {[v.assumption for v in severe_violations]}"
                self._total_invalidated += 1
                invalidated.append(dec_id)

        return invalidated

    def decay_confidences(self, current_time: Optional[float] = None):
        t = current_time or time.time()
        for entry in self._entries.values():
            if entry.status == "ACTIVE":
                _ = entry.get_decayed_confidence(t)

    def get_decision_chain(self, decision_id: str) -> List[DecisionLedgerEntry]:
        chain = []
        current = self._entries.get(decision_id)
        while current:
            chain.append(current)
            current = self._entries.get(current.parent_decision_id) if current.parent_decision_id else None
        return list(reversed(chain))

    def verify_merkle_chain(self) -> bool:
        for entry in self._entries.values():
            if entry.merkle_hash != entry.compute_hash():
                return False
        return True

    def get_merkle_root(self) -> Optional[str]:
        if not self._merkle_chain:
            return None
        combined = ":".join(self._merkle_chain)
        return hashlib.sha256(combined.encode()).hexdigest()

    def trigger_recovery(self, decision_id: str, anomaly_severity: float) -> Optional[RecoveryTrigger]:
        entry = self._entries.get(decision_id)
        if not entry or entry.status != "ACTIVE":
            return None

        if anomaly_severity < 0.4:
            tier = 0
        elif anomaly_severity < 0.7:
            tier = 1
        elif anomaly_severity < 0.85:
            tier = 2
        else:
            tier = 3

        entry.recovery_tier = tier
        entry.status = "RECOVERED"

        return RecoveryTrigger(
            decision_id=decision_id,
            tier=tier,
            reason=f"Anomaly severity {anomaly_severity:.3f} triggered tier-{tier} recovery",
            violated_assumptions=entry.assumptions,
            confidence_delta=entry.confidence - entry.get_decayed_confidence(),
        )

    def get_lineage(self, decision_id: str) -> Dict:
        chain = self.get_decision_chain(decision_id)
        return {
            'root_decision': chain[0].to_dict() if chain else None,
            'chain_length': len(chain),
            'total_confidence': sum(d.confidence for d in chain) / len(chain) if chain else 0,
            'assumptions_union': list(set(a for d in chain for a in d.assumptions)),
        }

    def _evict_oldest(self):
        if not self._entries:
            return
        self._entries.popitem(last=False)

    def get_statistics(self) -> Dict:
        active = sum(1 for e in self._entries.values() if e.status == "ACTIVE")
        invalidated = sum(1 for e in self._entries.values() if e.status == "INVALIDATED")
        recovered = sum(1 for e in self._entries.values() if e.status == "RECOVERED")

        return {
            'total_entries': len(self._entries),
            'total_recorded': self._total_recorded,
            'active': active,
            'invalidated': invalidated,
            'recovered': recovered,
            'invalidation_rate': self._total_invalidated / self._total_recorded if self._total_recorded else 0.0,
            'merkle_chain_valid': self.verify_merkle_chain(),
            'merkle_root': self.get_merkle_root(),
            'atre': self._atre.get_statistics(),
        }
