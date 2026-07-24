"""
Ledger tests — WorldLedger history accumulation, ExperienceManager skill indexing.
"""

import numpy as np

from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace
from telos.core.ledger.world_ledger import WorldLedger
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.experience_manager import ExperienceManager, ExperienceConfig
from telos.world.world import World
from telos.intent_ir import IntentIR


def test_world_ledger_history():
    ledger = WorldLedger()

    world1 = World(state=np.array([1.0, 2.0, 0.5]), entities=["active_region"])
    intent1 = IntentIR("perceive", params={
        "features": {"state_norm": 2.2, "state_mean": 1.0, "energy": 5.0},
        "entities": ["active_region"], "entity_ids": ["ent_test"],
    })

    enriched1 = ledger.enrich(world1, intent1, cycle=1)
    depths1 = enriched1.metadata.get("semantic_depths", [])
    assert len(depths1) == 1
    assert depths1[0].historical_context == "newly_discovered"
    assert depths1[0].semantic_identity == "active_region"
    rec = ledger.get_record("active_region")
    assert rec is not None
    assert rec.observation_count == 1

    world2 = World(state=np.array([1.1, 2.1, 0.4]), entities=["active_region"])
    intent2 = IntentIR("perceive", params={
        "features": {"state_norm": 2.3, "state_mean": 1.1, "energy": 5.2},
        "entities": ["active_region"], "entity_ids": ["ent_test"],
    })
    enriched2 = ledger.enrich(world2, intent2, cycle=2)
    depths2 = enriched2.metadata.get("semantic_depths", [])
    assert depths2[0].historical_context != "newly_discovered"
    assert rec.observation_count == 2

    for cyc in range(3, 6):
        s = np.array([1.0 + cyc * 0.1, 2.0, 0.5])
        w = World(state=s, entities=["active_region"])
        i = IntentIR("perceive", params={
            "features": {"state_norm": float(np.linalg.norm(s))},
            "entities": ["active_region"], "entity_ids": ["ent_test"],
        })
        ledger.enrich(w, i, cycle=cyc)

    assert rec.observation_count == 5
    assert rec.last_seen > rec.first_seen
    assert "persistent_entity" in rec.semantic_identity


def test_experience_manager():
    skill_lib = SkillLibrary()
    manager = ExperienceManager(skill_lib, ExperienceConfig(utility_threshold=0.3))

    good_result = PipelineResult(
        selected_trajectory=IntentIR("good_plan", confidence=0.9),
        health_score=0.8,
        pipeline_phase=PipelinePhase.COMPLETE,
        worlds_generated=10,
        decision_trace=DecisionTrace(
            cycle_id=1, timestamp=0.0,
            world_state_snapshot=np.array([1.0, 2.0]),
            domain_facts=None, stream_activations=[],
            selected_intent=IntentIR("good_plan"),
            selected_action=np.array([0.1, 0.2]),
            representation="cartesian",
            budget_consumed_ms=15.0, budget_total_ms=50.0,
            worlds_simulated=10, cycle_duration_ms=12.0,
            health_score=0.8, council_validated=True,
            decision_integrity=1.0, mission_drift=0.0,
        ),
    )

    skill = manager.observe(good_result)
    assert skill is not None
    assert skill.skill_id in skill_lib.skills

    bad_result = PipelineResult(
        selected_trajectory=None,
        health_score=0.1,
        pipeline_phase=PipelinePhase.COMPLETE,
    )
    skill2 = manager.observe(bad_result)
    assert skill2 is None


def test_user_identity_memory():
    """Identity memory persists across cycles (Axiom 4.1)."""
    ledger = WorldLedger()

    profile = ledger.upsert_user("Prateek")
    assert profile.name == "Prateek"
    assert profile.relationship_summary == "new_user"
    assert profile.trust_level == 0.5

    ledger.record_user_interaction("Prateek", "navigate", 0.9, cycle=1)
    p = ledger.get_user_profile("Prateek")
    assert p.total_interactions == 1
    assert p.last_intent == "navigate"
    assert p.relationship_summary == "new_user"

    ledger.record_user_interaction("Prateek", "perceive", 0.8, cycle=2)
    p = ledger.get_user_profile("Prateek")
    assert p.total_interactions == 2
    assert p.relationship_summary == "emerging_familiarity"
    assert p.trust_level >= 0.5
    assert "navigate" in p.typical_intents

    for i in range(3, 12):
        ledger.record_user_interaction("Prateek", "explore", 0.85, cycle=i)
    p = ledger.get_user_profile("Prateek")
    assert p.total_interactions == 11
    assert p.relationship_summary == "deep_relationship"

    summaries = ledger.get_known_user_summaries()
    assert len(summaries) == 1
    assert summaries[0]["name"] == "Prateek"
    assert summaries[0]["relationship"] == "deep_relationship"

    unknown = ledger.get_user_profile("Unknown")
    assert unknown is None


def test_option_decay_prune():
    """Skills not matched for prune_age_cycles are archived (Axiom 3.3)."""
    from telos.core.ledger.skill_library import Skill

    lib = SkillLibrary(prune_age_cycles=50)

    s1 = Skill("s1", "fp1", np.array([0.1]), 0.9)
    s2 = Skill("s2", "fp2", np.array([0.2]), 0.8)
    s3 = Skill("s3", "fp3", np.array([0.3]), 0.95)

    lib.index_skill(s1)
    lib.index_skill(s2)
    lib.index_skill(s3)

    lib.skills["s1"].last_matched_cycle = 1
    lib.skills["s2"].last_matched_cycle = 99
    lib.skills["s3"].last_matched_cycle = 50

    lib._cycle = 100
    pruned = lib.prune()
    assert pruned == 1
    assert "s1" not in lib.skills
    assert "s2" in lib.skills
    assert "s3" in lib.skills
    assert len(lib._archived) == 1
    assert lib._archived[0].skill_id == "s1"


def test_option_decay_prune_auto_cycle_increment():
    """Skills have their last_matched_cycle updated by find_relevant_skills."""
    from telos.core.ledger.skill_library import Skill
    import numpy as np

    lib = SkillLibrary()
    s1 = Skill("s1", "fp1", np.array([0.1]), 0.9)
    lib.index_skill(s1)
    lib.skills["s1"].last_matched_cycle = 0

    lib.find_relevant_skills(np.array([0.1, 0.2]), threshold=0.0)
    assert lib.skills["s1"].last_matched_cycle == 1


def test_option_decay_restore_on_reset():
    """Pruned skills are restored by reset_cycle()."""
    from telos.core.ledger.skill_library import Skill
    import numpy as np

    lib = SkillLibrary(prune_age_cycles=10)
    s1 = Skill("s1", "fp1", np.array([0.1]), 0.9)
    lib.index_skill(s1)
    lib.skills["s1"].last_matched_cycle = 1
    lib._cycle = 100
    lib.prune()

    assert "s1" not in lib.skills
    assert len(lib._archived) == 1

    lib.reset_cycle()
    assert "s1" in lib.skills
    assert len(lib._archived) == 0
