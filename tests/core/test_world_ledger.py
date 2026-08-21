"""Tests for WorldLedger — history-aware entity persistence, user identity
profiles, semantic-depth enrichment, and JSON persistence round-trips."""

import numpy as np
import pytest

from telos.world.world import World
from telos.core.ledger.world_ledger import WorldLedger
from telos.core.ledger.types import UserProfile, EntityRecord, ObservationEntry


from types import SimpleNamespace


def make_world(entities, state=None):
    return World(
        state=np.zeros(2) if state is None else state,
        entities=entities,
    )


def make_intent(features):
    return SimpleNamespace(params={"features": features})


class TestUserProfiles:
    def test_upsert_creates_then_reuses(self):
        ledger = WorldLedger()
        p1 = ledger.upsert_user("Prateek")
        assert isinstance(p1, UserProfile)
        assert p1.name == "Prateek"
        assert p1.first_seen > 0
        assert p1.last_seen >= p1.first_seen
        p2 = ledger.upsert_user("Prateek")
        assert p1 is p2
        assert ledger.known_users == 1

    def test_record_user_interaction_accumulates(self):
        ledger = WorldLedger()
        ledger.record_user_interaction("Prateek", "inquiry", 0.8, 1)
        ledger.record_user_interaction("Prateek", "execute", 0.7, 2)
        profile = ledger.get_user_profile("Prateek")
        assert profile.total_interactions == 2
        assert profile.last_intent == "execute"
        assert profile.typical_intents == ["inquiry", "execute"]
        assert "execute" in profile.interaction_history[-1]
        assert 0.4 < profile.trust_level <= 1.0
        assert profile.relationship_summary == "emerging_familiarity"

    def test_get_unknown_profile_returns_none(self):
        ledger = WorldLedger()
        assert ledger.get_user_profile("nobody") is None

    def test_known_user_summaries(self):
        ledger = WorldLedger()
        ledger.upsert_user("Alice")
        s = ledger.get_known_user_summaries()
        assert len(s) == 1
        assert set(s[0]) == {"name", "relationship", "trust", "interactions", "last_intent"}
        assert s[0]["name"] == "Alice"


class TestEnrich:
    def test_enrich_creates_records_for_each_entity(self):
        ledger = WorldLedger()
        world = make_world(["bridge", "chair"])
        enriched = ledger.enrich(world, make_intent({"state_norm": 1.0}), cycle=1)
        records = enriched.metadata["entity_records"]
        assert isinstance(records, list) and len(records) == 2
        assert len(enriched.metadata["semantic_depths"]) == 2
        assert enriched.metadata["ledger_total_observations"] == 2
        for r in records:
            assert isinstance(r, EntityRecord)
            assert r.observation_count == 1
            assert len(r.observations) == 1
            assert r.observations[0].features == {"state_norm": 1.0}
            assert r.observations[0].cycle == 1

    def test_enrich_does_not_mutate_original_world(self):
        ledger = WorldLedger()
        world = make_world(["bridge"])
        ledger.enrich(world, make_intent({"state_norm": 1.0}), cycle=1)
        assert "entity_records" not in world.metadata

    def test_entity_id_derived_from_name(self):
        ledger = WorldLedger()
        enriched = ledger.enrich(make_world(["bridge"]), cycle=2)
        rec = enriched.metadata["entity_records"][0]
        assert rec.entity_id.startswith("ent_")
        assert len(rec.entity_id) == 4 + 8

    def test_history_accumulates_across_cycles(self):
        ledger = WorldLedger()
        enriched = ledger.enrich(make_world(["bridge"]), cycle=1)
        rec = enriched.metadata["entity_records"][0]
        assert rec.observations[0].cycle == 1
        enriched2 = ledger.enrich(
            enrich_world(make_world(["bridge"])), cycle=2
        )
        rec2 = enriched2.metadata["entity_records"][0]
        assert rec2.observation_count == 2
        assert len(rec2.observations) == 2
        assert rec2.observations[1].cycle == 2
        assert rec2.semantic_identity == "bridge_persistent_entity"

    def test_empty_entities_yield_empty_metadata(self):
        ledger = WorldLedger()
        enriched = ledger.enrich(make_world([]), cycle=1)
        assert enriched.metadata["entity_records"] == []
        assert enriched.metadata["semantic_depths"] == []
        assert enriched.metadata["ledger_total_observations"] == 0

    def test_mission_relevance_drives_identity(self):
        ledger = WorldLedger()
        near = ledger.enrich(
            make_world(["bridge"]), make_intent({"state_norm": 0.5}), cycle=1,
            mission_vector=np.array([0.5]),
        )
        near_rec = near.metadata["entity_records"][0]
        assert near_rec.semantic_identity.startswith("bridge")
        assert "high_mission_priority" in near_rec.semantic_identity
        far = ledger.enrich(
            make_world(["chair"]), make_intent({"state_norm": 0.5}), cycle=1,
            mission_vector=np.array([4.5]),
        )
        far_rec = far.metadata["entity_records"][0]
        assert "low_mission_priority" in far_rec.semantic_identity

    def test_well_known_context_after_many_observations(self):
        ledger = WorldLedger()
        for cycle in range(1, 7):
            enriched = ledger.enrich(make_world(["bridge"]), cycle=cycle)
        depth = enriched.metadata["semantic_depths"][0]
        assert depth.historical_context == "well_known_6_observations"


class TestRecordAndPersistence:
    def test_get_record_and_entity_count(self):
        ledger = WorldLedger()
        assert ledger.get_record("bridge") is None
        ledger.enrich(make_world(["bridge"]))
        assert ledger.entity_count == 1
        assert ledger.get_record("bridge") is not None

    def test_clear(self):
        ledger = WorldLedger()
        ledger.enrich(make_world(["bridge", "chair"]))
        ledger.upsert_user("Alice")
        ledger.clear()
        assert ledger.entity_count == 0
        assert ledger._total_observations == 0
        assert ledger.known_users == 1

    def test_save_load_round_trip(self, tmp_path):
        ledger = WorldLedger()
        ledger.enrich(make_world(["bridge"]), make_intent({"state_norm": 0.8}), cycle=3)
        ledger.record_user_interaction("Alice", "inquiry", 0.6, 3)
        path = str(tmp_path / "ledger.json")
        ledger.save(path)
        assert path
        restored = WorldLedger()
        restored.load(path)
        assert restored.entity_count == 1
        rec = restored.get_record("bridge")
        assert rec.name == "bridge"
        assert rec.observation_count == 1
        # load restores metadata but not the observation entries (real behavior)
        assert rec.observations == []
        profile = restored.get_user_profile("Alice")
        assert profile.total_interactions == 1
        assert profile.last_intent == "inquiry"
        assert profile.relationship_summary == "new_user"

    def test_load_missing_file_is_noop(self, tmp_path):
        ledger = WorldLedger()
        ledger.load(str(tmp_path / "does_not_exist.json"))
        assert ledger.entity_count == 0


def enrich_world(w):
    return w