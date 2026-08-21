"""
Ledger data types — extracted from world_ledger.py to reduce file complexity.

Contains: ObservationEntry, InteractionRecord, EntityRecord, SemanticDepth, UserProfile.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
import numpy as np


@dataclass
class ObservationEntry:
    """A single observation of an entity at one point in time."""
    cycle: int
    timestamp: float
    features: Dict[str, float]
    affordances: List[str]
    state_snapshot: Optional[np.ndarray] = None


@dataclass
class InteractionRecord:
    """Record of how the system interacted with this entity."""
    cycle: int
    action_type: str
    outcome: str
    confidence: float


@dataclass
class EntityRecord:
    """The complete history of a single perceived entity."""
    entity_id: str
    name: str
    first_seen: float
    last_seen: float
    observation_count: int
    observations: List[ObservationEntry] = field(default_factory=list)
    affordances: Set[str] = field(default_factory=set)
    interactions: List[InteractionRecord] = field(default_factory=list)
    semantic_identity: str = "unknown"
    mission_relevance: float = 0.5
    is_active: bool = True

    @property
    def age_seconds(self) -> float:
        return self.last_seen - self.first_seen

    @property
    def observed_features(self) -> Dict[str, float]:
        if not self.observations:
            return {}
        return self.observations[-1].features.copy()


@dataclass
class SemanticDepth:
    """The four layers of meaning for a single entity."""
    entity_id: str
    observable_state: Dict[str, float] = field(default_factory=dict)
    historical_context: str = "new_entity"
    mission_context: str = "unassessed"
    semantic_identity: str = "unknown"


@dataclass
class UserProfile:
    """Structured identity memory for a known user across cycles."""
    name: str
    first_seen: float = 0.0
    last_seen: float = 0.0
    total_interactions: int = 0
    trust_level: float = 0.5
    typical_intents: List[str] = field(default_factory=list)
    preferences: Dict[str, float] = field(default_factory=dict)
    last_intent: str = ""
    relationship_summary: str = "new_user"
    interaction_history: List[str] = field(default_factory=list)

    def update_from_interaction(self, intent_type: str, confidence: float,
                                 cycle: int) -> None:
        self.total_interactions += 1
        self.last_seen = time.time()
        self.last_intent = intent_type

        if intent_type not in self.typical_intents:
            self.typical_intents.append(intent_type)

        self.interaction_history.append(
            f"[cyc:{cycle}] {intent_type} (conf={confidence:.2f})"
        )
        if len(self.interaction_history) > 50:
            self.interaction_history = self.interaction_history[-50:]

        self.trust_level = min(1.0, 0.3 + 0.7 * (
            1.0 - 1.0 / (1.0 + self.total_interactions * 0.2)
        ))

        if self.total_interactions <= 1:
            self.relationship_summary = "new_user"
        elif self.total_interactions <= 3:
            self.relationship_summary = "emerging_familiarity"
        elif self.total_interactions <= 10:
            self.relationship_summary = "established_relationship"
        else:
            self.relationship_summary = "deep_relationship"

