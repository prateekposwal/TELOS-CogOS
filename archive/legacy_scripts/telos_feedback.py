"""
TELOS v14: Epistemic Feedback Loop

Records trajectory outcomes, updates simulation priors, and archives
knowledge so the simulator improves over time.

Key insight: the simulation engine should learn from executed trajectories
which action patterns lead to mission-aligned outcomes and which lead to
corruption or drift.

Feedback cycle:
  Execute → Observe → Record → Extract Knowledge → Update Priors → Simulate

Priors influence:
  - Which strategies the simulation engine favors
  - Which action patterns are seeded more frequently
  - Which historical evidence is surfaced during trajectory generation
"""

import time
import hashlib
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque, OrderedDict


@dataclass
class OutcomeRecord:
    """A recorded outcome from an executed trajectory."""
    trajectory_id: str
    health: float
    mission_drift: float
    corruption: float
    success: bool
    steps_completed: int
    action_signature: Optional[np.ndarray] = None
    state_signature: Optional[np.ndarray] = None
    active_role_ids: List[str] = field(default_factory=list)
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeEntry:
    """Archived knowledge from trajectory outcomes."""
    pattern_hash: str
    success_rate: float
    avg_health: float
    avg_drift: float
    n_samples: int
    last_updated: float
    action_pattern: Optional[np.ndarray] = None


@dataclass
class FeedbackReport:
    """Summary of feedback loop state."""
    total_outcomes: int
    success_rate: float
    avg_health: float
    avg_drift: float
    n_knowledge_entries: int
    n_priors: int
    top_patterns: List[Dict[str, Any]]


class EpistemicFeedbackLoop:
    """
    Records trajectory outcomes and updates simulation priors.

    Over time, the feedback loop builds a model of which action patterns
    lead to good outcomes (high health, low drift) and biases future
    simulation toward those patterns.

    Components:
      - outcome_history: recent trajectory outcomes
      - knowledge_archive: extracted knowledge from outcomes
      - simulation_priors: bias parameters for the simulation engine
    """

    def __init__(self, learning_rate: float = 0.1,
                 memory_size: int = 200,
                 knowledge_size: int = 500,
                 max_priors: int = 500,
                 decay_factor: float = 0.99):
        self.learning_rate = learning_rate
        self.memory_size = memory_size
        self.knowledge_size = knowledge_size
        self.max_priors = max_priors
        self.decay_factor = decay_factor
        self._outcome_history: deque = deque(maxlen=memory_size)
        self._knowledge_archive: deque = deque(maxlen=knowledge_size)
        self._simulation_priors: Dict[str, Dict[str, float]] = {}
        self._priors_access_order: OrderedDict = OrderedDict()
        self._total_outcomes = 0
        self._success_count = 0

    def record_outcome(self, trajectory_steps, health: float,
                       mission_drift: float, corruption: float,
                       success: bool,
                       trajectory_id: str = "",
                       active_role_ids: Optional[List[str]] = None,
                       metadata: Optional[Dict] = None) -> OutcomeRecord:
        self._total_outcomes += 1
        if success:
            self._success_count += 1

        action_sig = None
        state_sig = None
        n_steps = 0
        if trajectory_steps:
            actions = [s.action for s in trajectory_steps if hasattr(s, 'action')]
            states = [s.state for s in trajectory_steps if hasattr(s, 'state')]
            if actions:
                action_sig = np.mean(actions, axis=0)
            if states:
                state_sig = states[-1].copy() if states else None
            n_steps = len(trajectory_steps)

        record = OutcomeRecord(
            trajectory_id=trajectory_id,
            health=health,
            mission_drift=mission_drift,
            corruption=corruption,
            success=success,
            steps_completed=n_steps,
            action_signature=action_sig,
            state_signature=state_sig,
            active_role_ids=active_role_ids or [],
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._outcome_history.append(record)

        if action_sig is not None:
            self._extract_and_store_knowledge(record, action_sig)

        self._update_priors(record)

        return record

    def _extract_and_store_knowledge(self, record: OutcomeRecord,
                                     action_pattern: np.ndarray) -> None:
        pattern_hash = self._hash_pattern(action_pattern)

        existing = None
        for entry in self._knowledge_archive:
            if entry.pattern_hash == pattern_hash:
                existing = entry
                break

        alpha = self.learning_rate
        if existing:
            existing.n_samples += 1
            existing.success_rate = (1 - alpha) * existing.success_rate + alpha * float(record.success)
            existing.avg_health = (1 - alpha) * existing.avg_health + alpha * record.health
            existing.avg_drift = (1 - alpha) * existing.avg_drift + alpha * record.mission_drift
            existing.last_updated = time.time()
        else:
            entry = KnowledgeEntry(
                pattern_hash=pattern_hash,
                success_rate=float(record.success),
                avg_health=record.health,
                avg_drift=record.mission_drift,
                n_samples=1,
                last_updated=time.time(),
                action_pattern=action_pattern.copy(),
            )
            self._knowledge_archive.append(entry)

    def _update_priors(self, record: OutcomeRecord) -> None:
        if record.action_signature is None:
            return

        key = self._state_action_key(record)
        if key in self._simulation_priors:
            self._priors_access_order.move_to_end(key)
        else:
            if len(self._simulation_priors) >= self.max_priors:
                oldest, _ = self._priors_access_order.popitem(last=False)
                del self._simulation_priors[oldest]
            self._simulation_priors[key] = {
                'success_rate': 0.5,
                'avg_health': 0.5,
                'avg_drift': 0.5,
                'n_samples': 0,
                'exploration_bonus': 1.0,
            }
            self._priors_access_order[key] = None

        prior = self._simulation_priors[key]
        prior['n_samples'] += 1
        alpha = self.learning_rate

        prior['success_rate'] = (1 - alpha) * prior['success_rate'] + alpha * float(record.success)
        prior['avg_health'] = (1 - alpha) * prior['avg_health'] + alpha * record.health
        prior['avg_drift'] = (1 - alpha) * prior['avg_drift'] + alpha * record.mission_drift
        prior['exploration_bonus'] *= self.decay_factor

    def _state_action_key(self, record: OutcomeRecord) -> str:
        if record.action_signature is not None:
            quantized = np.round(record.action_signature, 1)
            return hashlib.md5(quantized.tobytes()).hexdigest()[:12]
        return "default"

    def _hash_pattern(self, pattern: np.ndarray) -> str:
        quantized = np.round(pattern, 2)
        return hashlib.md5(quantized.tobytes()).hexdigest()[:12]

    def get_enhanced_priors(self) -> Dict[str, float]:
        if not self._simulation_priors:
            return {'success_bias': 0.5, 'health_bias': 0.5, 'drift_penalty': 0.5}

        success_rates = [p['success_rate'] for p in self._simulation_priors.values()]
        health_rates = [p['avg_health'] for p in self._simulation_priors.values()]
        drift_rates = [p['avg_drift'] for p in self._simulation_priors.values()]

        return {
            'success_bias': float(np.mean(success_rates)),
            'health_bias': float(np.mean(health_rates)),
            'drift_penalty': float(np.mean(drift_rates)),
            'n_prior_entries': len(self._simulation_priors),
        }

    def get_top_knowledge(self, k: int = 5) -> List[KnowledgeEntry]:
        sorted_entries = sorted(
            self._knowledge_archive,
            key=lambda e: e.success_rate * e.avg_health,
            reverse=True,
        )
        return sorted_entries[:k]

    def get_report(self) -> FeedbackReport:
        overall_success = (
            self._success_count / self._total_outcomes
            if self._total_outcomes > 0 else 0.0
        )

        healths = [r.health for r in self._outcome_history]
        drifts = [r.mission_drift for r in self._outcome_history]

        top = self.get_top_knowledge(3)
        top_patterns = [
            {
                'hash': e.pattern_hash,
                'success_rate': round(e.success_rate, 3),
                'avg_health': round(e.avg_health, 3),
                'n_samples': e.n_samples,
            }
            for e in top
        ]

        return FeedbackReport(
            total_outcomes=self._total_outcomes,
            success_rate=overall_success,
            avg_health=float(np.mean(healths)) if healths else 0.0,
            avg_drift=float(np.mean(drifts)) if drifts else 0.0,
            n_knowledge_entries=len(self._knowledge_archive),
            n_priors=len(self._simulation_priors),
            top_patterns=top_patterns,
        )

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_outcomes': self._total_outcomes,
            'success_count': self._success_count,
            'success_rate': self._success_count / self._total_outcomes if self._total_outcomes > 0 else 0.0,
            'knowledge_entries': len(self._knowledge_archive),
            'prior_entries': len(self._simulation_priors),
            'history_size': len(self._outcome_history),
        }
