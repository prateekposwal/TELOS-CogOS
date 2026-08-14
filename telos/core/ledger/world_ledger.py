"""
WorldLedger — History-Aware Entity Persistence

The WorldLedger is the mechanism that transforms the World from a
flat snapshot into a Temporal Volume. Every entity the system
perceives carries its full history across decision cycles.

This implements the Semantic Depth Ladder:
  1. Observable State:   Raw data from current perception
  2. Historical Context:  Accumulated record from prior cycles
  3. Mission Context:     Relevance to the current objective
  4. Semantic Identity:   Synthesized meaning (the bridge is not just
                         a bridge — it's a critical infrastructure node
                         with earthquake survival history)
"""

import time
import hashlib
import numpy as np
import logging
from typing import Dict, List, Optional, Any, Set

from telos.world.world import World
from telos.core.ledger.types import (
    ObservationEntry, InteractionRecord, EntityRecord,
    SemanticDepth, UserProfile,
)

logger = logging.getLogger('telos_ledger')


class WorldLedger:
    """Persistent store of entity histories across decision cycles.

    The ledger bridges snapshots: it allows the system to see not
    just "a bridge" but "a bridge + stress history + earthquake
    survival + maintenance needs."

    Usage:
        ledger = WorldLedger()
        # After PerceptionStream detects entities:
        enriched_world = ledger.enrich(world, perception_intent)
        # The World now carries EntityRecords for each entity
    """

    def __init__(self):
        self._records: Dict[str, EntityRecord] = {}
        self._total_observations: int = 0
        self._user_profiles: Dict[str, UserProfile] = {}

    def upsert_user(self, name: str) -> UserProfile:
        """Create or retrieve a user identity profile.
        
        This is how TELOS remembers who you are across cycles.
        Call this during PERCEIVE to load known user context.
        """
        if name in self._user_profiles:
            self._user_profiles[name].last_seen = time.time()
            return self._user_profiles[name]
        now = time.time()
        profile = UserProfile(
            name=name,
            first_seen=now,
            last_seen=now,
        )
        self._user_profiles[name] = profile
        return profile

    def record_user_interaction(self, user_name: str, intent_type: str,
                                 confidence: float, cycle: int) -> None:
        """Record a user interaction cycle — builds identity memory.

        The profile is upserted on first interaction so the interaction
        is never silently dropped (Kintsugi Λ2.3: no silent swallows).
        """
        profile = self.upsert_user(user_name)
        profile.update_from_interaction(intent_type, confidence, cycle)

    def get_user_profile(self, user_name: str) -> Optional[UserProfile]:
        """Retrieve a user's identity profile, or None if unknown."""
        return self._user_profiles.get(user_name)

    def get_known_user_summaries(self) -> List[Dict]:
        """Return summaries of all known users."""
        return [
            {
                "name": p.name,
                "relationship": p.relationship_summary,
                "trust": round(p.trust_level, 3),
                "interactions": p.total_interactions,
                "last_intent": p.last_intent,
            }
            for p in self._user_profiles.values()
        ]

    @property
    def known_users(self) -> int:
        return len(self._user_profiles)

    def enrich(self, world: World, perception_intent: Optional[Any] = None,
               cycle: int = 0, mission_vector: Optional[np.ndarray] = None) -> World:
        """Attach EntityRecords to each entity in the World.

        For each entity name in world.entities:
        1. Look up existing EntityRecord by name
        2. If found, append current observation and return history
        3. If not found, create new EntityRecord
        4. Compute SemanticDepth for each entity

        The enriched World carries entity_records and semantic_depths
        as metadata.

        Returns:
            World with entity_records metadata populated.
        """
        from copy import deepcopy
        enriched_world = deepcopy(world)

        features = {}
        if perception_intent is not None and hasattr(perception_intent, 'params'):
            features = perception_intent.params.get("features", {})

        entity_records: List[EntityRecord] = []
        semantic_depths: List[SemanticDepth] = []

        for entity_name in world.entities:
            record = self._get_or_create(entity_name)
            self._record_observation(record, features, cycle)

            depth = self._compute_semantic_depth(record, mission_vector)
            semantic_depths.append(depth)

            entity_records.append(record)
            self._total_observations += 1

        enriched_world.metadata["entity_records"] = entity_records
        enriched_world.metadata["semantic_depths"] = semantic_depths
        enriched_world.metadata["ledger_total_observations"] = self._total_observations

        logger.debug(
            f"Ledger: enriched {len(entity_records)} entities "
            f"(total observations: {self._total_observations})"
        )
        return enriched_world

    def _get_or_create(self, entity_name: str) -> EntityRecord:
        """Look up existing record or create a new one."""
        if entity_name in self._records:
            return self._records[entity_name]
        now = time.time()
        record = EntityRecord(
            entity_id=f"ent_{hashlib.md5(entity_name.encode()).hexdigest()[:8]}",
            name=entity_name,
            first_seen=now,
            last_seen=now,
            observation_count=0,
        )
        self._records[entity_name] = record
        return record

    def _record_observation(self, record: EntityRecord, features: Dict[str, float],
                             cycle: int) -> None:
        """Append an observation entry to an entity's history."""
        record.last_seen = time.time()
        record.observation_count += 1

        entry = ObservationEntry(
            cycle=cycle,
            timestamp=record.last_seen,
            features=features.copy(),
            affordances=list(record.affordances),
        )
        record.observations.append(entry)

    def _compute_semantic_depth(self, record: EntityRecord,
                                 mission_vector: Optional[np.ndarray] = None) -> SemanticDepth:
        """Compute the four layers of meaning for an entity.

        Layer 1 — Observable State: Current features
        Layer 2 — Historical Context: How long observed, how many interactions
        Layer 3 — Mission Context: Relevance to current mission
        Layer 4 — Semantic Identity: Synthesized meaning
        """
        current_features = record.observed_features

        # Layer 2: Historical Context
        if record.observation_count <= 1:
            historical = "newly_discovered"
        elif record.observation_count <= 5:
            historical = f"observed_{record.observation_count}_times"
        else:
            historical = f"well_known_{record.observation_count}_observations"

        # Layer 3: Mission Context
        if mission_vector is not None and current_features:
            state_norm = current_features.get("state_norm", 1.0)
            relevance = float(np.clip(1.0 / (1.0 + abs(state_norm - np.linalg.norm(mission_vector))),
                                       0.0, 1.0))
        else:
            relevance = record.mission_relevance

        # Layer 4: Synthesized Identity
        identity = self._synthesize_identity(record, relevance)

        record.mission_relevance = relevance
        record.semantic_identity = identity

        return SemanticDepth(
            entity_id=record.entity_id,
            observable_state=current_features,
            historical_context=historical,
            mission_context=f"relevance_{relevance:.2f}",
            semantic_identity=identity,
        )

    def _synthesize_identity(self, record: EntityRecord,
                              mission_relevance: float) -> str:
        """Synthesize the semantic identity from history + mission context.

        This is the key function that gives TELOS Cognitive Understanding.
        A "chair" is not just a chair — it's:
        - A "fuel source" to a fire-seeking system
        - A "tool" to a height-seeking system
        - A "obstacle" to a movement-seeking system
        """
        identity_parts = [record.name]

        if record.observation_count > 1:
            identity_parts.append("persistent_entity")

        if mission_relevance > 0.7:
            identity_parts.append("high_mission_priority")
        elif mission_relevance < 0.3:
            identity_parts.append("low_mission_priority")

        if record.interactions:
            identity_parts.append("interacted")
            outcomes = [i.outcome for i in record.interactions[-3:]]
            if "failure" in outcomes:
                identity_parts.append("historically_hazardous")

        return "_".join(identity_parts)

    def record_interaction(self, entity_name: str, action_type: str,
                           outcome: str, confidence: float, cycle: int) -> None:
        """Record a system interaction with an entity."""
        record = self._records.get(entity_name)
        if record is None:
            return
        record.interactions.append(InteractionRecord(
            cycle=cycle, action_type=action_type,
            outcome=outcome, confidence=confidence,
        ))

    def get_record(self, entity_name: str) -> Optional[EntityRecord]:
        return self._records.get(entity_name)

    @property
    def entity_count(self) -> int:
        return len(self._records)

    @property
    def all_records(self) -> List[EntityRecord]:
        return list(self._records.values())

    def clear(self) -> None:
        self._records.clear()
        self._total_observations = 0

    def save(self, path: str) -> None:
        """Persist ledger state (entity records + user profiles) to JSON."""
        import json
        data = {
            "total_observations": self._total_observations,
            "records": {
                eid: {
                    "entity_id": r.entity_id,
                    "name": r.name,
                    "first_seen": r.first_seen,
                    "last_seen": r.last_seen,
                    "observation_count": r.observation_count,
                    "affordances": sorted(r.affordances),
                    "semantic_identity": r.semantic_identity,
                    "mission_relevance": r.mission_relevance,
                    "is_active": r.is_active,
                    "observations": [
                        {"features": o.features, "timestamp": o.timestamp}
                        for o in r.observations[-50:]
                    ],
                    "interactions": [
                        {"cycle": i.cycle, "action_type": i.action_type,
                         "outcome": i.outcome, "confidence": i.confidence}
                        for i in r.interactions[-50:]
                    ],
                }
                for eid, r in self._records.items()
            },
            "user_profiles": [
                {
                    "name": p.name,
                    "first_seen": p.first_seen,
                    "last_seen": p.last_seen,
                    "total_interactions": p.total_interactions,
                    "trust_level": p.trust_level,
                    "typical_intents": p.typical_intents,
                    "preferences": p.preferences,
                    "last_intent": p.last_intent,
                    "relationship_summary": p.relationship_summary,
                    "interaction_history": p.interaction_history[-50:],
                }
                for p in self._user_profiles.values()
            ],
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        """Restore ledger state from a JSON file."""
        import json
        try:
            with open(path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return
        self._total_observations = data.get("total_observations", 0)
        for eid, rd in data.get("records", {}).items():
            self._records[eid] = EntityRecord(
                entity_id=rd["entity_id"],
                name=rd["name"],
                first_seen=rd["first_seen"],
                last_seen=rd["last_seen"],
                observation_count=rd["observation_count"],
                affordances=set(rd.get("affordances", [])),
                semantic_identity=rd.get("semantic_identity", "unknown"),
                mission_relevance=rd.get("mission_relevance", 0.5),
                is_active=rd.get("is_active", True),
            )
        for up in data.get("user_profiles", []):
            profile = UserProfile(
                name=up["name"],
                first_seen=up.get("first_seen", 0.0),
                last_seen=up.get("last_seen", 0.0),
                total_interactions=up.get("total_interactions", 0),
                trust_level=up.get("trust_level", 0.5),
                typical_intents=up.get("typical_intents", []),
                preferences=up.get("preferences", {}),
                last_intent=up.get("last_intent", ""),
                relationship_summary=up.get("relationship_summary", "new_user"),
                interaction_history=up.get("interaction_history", [])[-50:],
            )
            self._user_profiles[profile.name] = profile
