"""
Representation Memory — the system's memory of *how* it chose to think.

Each entry records:
  - Problem fingerprint (compressed state signature)
  - Which transform chain was selected
  - What alternatives were considered
  - The cost, information loss, and outcome quality
  - A learning signal for future planning

Over time the memory converges on the most useful coordinate system
for each class of problem, making TELOS better at choosing how to
think, not just what to act.
"""

import time
import hashlib
import uuid
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from collections import deque, OrderedDict


def compute_fingerprint(state: np.ndarray,
                        coupling_index: float = 0.0,
                        domain: str = "continuous") -> str:
    """Deterministic hash capturing essential problem characteristics."""
    data = np.ascontiguousarray(state).tobytes()
    data += str(round(coupling_index, 3)).encode()
    data += domain.encode()
    return hashlib.sha256(data).hexdigest()[:16]


@dataclass
class RepresentationMemoryEntry:
    """A single record of how a problem was represented and solved."""
    entry_id: str
    timestamp: float
    step_count: int
    problem_fingerprint: str
    selected_transform_chain: List[str]
    alternatives_considered: List[Tuple[str, float]]
    representation_cost_ms: float
    information_loss: float
    outcome_quality: float
    health_score: float
    mission_drift: float
    learning_signal: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "step_count": self.step_count,
            "problem_fingerprint": self.problem_fingerprint,
            "selected_transform_chain": list(self.selected_transform_chain),
            "alternatives_considered": [
                (name, round(score, 3)) for name, score in self.alternatives_considered
            ],
            "representation_cost_ms": round(self.representation_cost_ms, 3),
            "information_loss": round(self.information_loss, 3),
            "outcome_quality": round(self.outcome_quality, 3),
            "health_score": round(self.health_score, 3),
            "mission_drift": round(self.mission_drift, 3),
            "learning_signal": self.learning_signal,
        }


class RepresentationMemory:
    """Storage, retrieval, and learning over representation choices.

    Two-tier structure:
      - Ring buffer of recent entries (for query / analysis).
      - Per-transform performance tracker (for learning priors).
    """

    def __init__(self, max_entries: int = 2000,
                 learning_rate: float = 0.1):
        self._entries: deque = deque(maxlen=max_entries)
        self._by_fingerprint: Dict[str, List[str]] = OrderedDict()
        self._learning_rate = learning_rate

        # transform_name → deque of (outcome_quality, count)
        self._transform_outcomes: Dict[str, deque] = {}
        self._total_recorded = 0

    # ── Recording ─────────────────────────────────────────────────

    def record(self, entry: RepresentationMemoryEntry) -> None:
        self._entries.append(entry)
        self._total_recorded += 1

        fp = entry.problem_fingerprint
        if fp not in self._by_fingerprint:
            self._by_fingerprint[fp] = []
        self._by_fingerprint[fp].append(entry.entry_id)
        if len(self._by_fingerprint) > 5000:
            self._by_fingerprint.popitem(last=False)

        for t_name in entry.selected_transform_chain:
            if t_name not in self._transform_outcomes:
                self._transform_outcomes[t_name] = deque(maxlen=100)
            self._transform_outcomes[t_name].append(entry.outcome_quality)

    # ── Query ─────────────────────────────────────────────────────

    def query_by_fingerprint(self, fingerprint: str,
                             k: int = 5) -> List[RepresentationMemoryEntry]:
        ids = self._by_fingerprint.get(fingerprint, [])
        matches = [e for e in self._entries if e.entry_id in ids]
        return matches[-k:]

    def query_similar(self, state: np.ndarray,
                      coupling_index: float = 0.0,
                      domain: str = "continuous",
                      k: int = 5) -> List[RepresentationMemoryEntry]:
        fp = compute_fingerprint(state, coupling_index, domain)
        return self.query_by_fingerprint(fp, k)

    def get_recent(self, n: int = 10) -> List[RepresentationMemoryEntry]:
        return list(self._entries)[-n:]

    # ── Learning ──────────────────────────────────────────────────

    def get_transform_prior(self, transform_name: str) -> float:
        """Learned boost / penalty in [−0.3, 0.3] for a transform name.

        Positive means past use of this transform correlated with good
        outcomes; the planner can add this to the raw ``applicable()`` score.
        """
        outcomes = self._transform_outcomes.get(transform_name)
        if not outcomes or len(outcomes) < 3:
            return 0.0
        avg = float(np.mean(outcomes))
        return float(np.clip((avg - 0.5) * self._learning_rate * 2,
                             -0.3, 0.3))

    def get_best_chain_for_fingerprint(self, fingerprint: str
                                       ) -> Optional[List[str]]:
        """Return the transform chain that produced the best outcome
        for a known fingerprint."""
        matches = self.query_by_fingerprint(fingerprint, k=20)
        if not matches:
            return None
        best = max(matches, key=lambda e: e.outcome_quality)
        return best.selected_transform_chain

    def get_transform_summary(self) -> Dict[str, Dict]:
        """Per-transform performance statistics."""
        summary = {}
        for name, outcomes in self._transform_outcomes.items():
            arr = list(outcomes)
            summary[name] = {
                "n_uses": len(arr),
                "avg_outcome": float(np.mean(arr)),
                "std_outcome": float(np.std(arr)) if len(arr) > 1 else 0.0,
                "prior": self.get_transform_prior(name),
            }
        return summary

    # ── Statistics ────────────────────────────────────────────────

    def get_statistics(self) -> Dict:
        return {
            "total_recorded": self._total_recorded,
            "current_entries": len(self._entries),
            "unique_fingerprints": len(self._by_fingerprint),
            "tracked_transforms": len(self._transform_outcomes),
            "transform_summary": self.get_transform_summary(),
        }

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return (f"RepresentationMemory("
                f"entries={len(self._entries)}, "
                f"transforms={len(self._transform_outcomes)})")
