"""
Skill seed scaffold tests — Capital Guardian + Strategy Lab knowledge seeds.

Validates the 4 seed scaffolds against the real SkillLibrary schema:
schema completeness, indexing, fingerprint matching via canonical_state,
Option Decay interaction (Axiom 3.3), and ingestion-hook coverage.
"""

import numpy as np
import pytest

from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.skill_seeds import (
    SEED_MANIFEST,
    SEED_SKILL_IDS,
    build_capital_guardian_seed,
    build_microstructure_seed,
    build_crypto_framing_seed,
    build_position_sizing_seed,
    seed_by_id,
    seed_skill_library,
    validate_seed,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def all_seeds():
    return [seed_by_id(sid) for sid in SEED_SKILL_IDS]


def test_seed_registry_has_four_skills():
    """The manifest matches the agreed 4-book priority list."""
    assert set(SEED_SKILL_IDS) == {
        "capital_guardian",
        "microstructure",
        "crypto_framing",
        "position_sizing",
    }
    assert len(SEED_MANIFEST) == 4


def test_all_seeds_pass_schema_validation(all_seeds):
    """Every seed is a complete, valid Skill per the real schema."""
    for seed in all_seeds:
        violations = validate_seed(seed)
        assert violations == [], f"{seed.skill_id}: {violations}"


def test_seeds_index_into_skill_library(all_seeds):
    """Indexing respects SkillLibrary.index_skill validation (clamps, no errors)."""
    lib = SkillLibrary(max_skills=100)
    for seed in all_seeds:
        lib.index_skill(seed)
    assert lib.skill_count == 4


def test_seed_skill_library_helper():
    """seed_skill_library() registers all 4 and is additive."""
    lib = seed_skill_library()
    assert lib.skill_count == 4
    for sid in SEED_SKILL_IDS:
        assert sid in lib.skills

    # additive: seeding an existing library does not evict prior skills
    lib2 = SkillLibrary(max_skills=100)
    from telos.core.ledger.skill_library import Skill
    pre = Skill("pre_existing", "fp_x", np.array([0.5]), 0.9)
    lib2.index_skill(pre)
    seed_skill_library(lib2)
    assert lib2.skill_count == 5
    assert "pre_existing" in lib2.skills


def test_fingerprint_matching_via_canonical_state(all_seeds):
    """Seeds are matchable by find_relevant_skills via their canonical_state.

    This is the real Option Decay path: find_relevant_skills hashes the
    incoming state and matches against skill fingerprints.
    """
    lib = seed_skill_library()
    for seed in all_seeds:
        canonical = seed.domain_config["canonical_state"]
        matches = lib.find_relevant_skills(canonical, threshold=1.1)
        assert any(s.skill_id == seed.skill_id for s in matches), (
            f"seed {seed.skill_id} not matched via canonical_state"
        )


def test_seed_utility_above_eviction_floor(all_seeds):
    """Seeds sit above the 0.3 utility-floor eviction threshold (Axiom 3.3)."""
    for seed in all_seeds:
        assert 0.3 <= seed.utility_score <= 1.0, seed.skill_id


def test_seeds_survive_prune_with_recent_match(all_seeds):
    """Recently-matched seeds are not archived by prune()."""
    lib = seed_skill_library()
    # Match all seeds in current cycle so they are fresh
    for seed in all_seeds:
        lib.find_relevant_skills(seed.domain_config["canonical_state"], threshold=1.1)
    pruned = lib.prune()
    assert pruned == 0
    assert lib.skill_count == 4


def test_seed_option_decay_restore_on_reset(all_seeds):
    """Seeds restore from archive on reset_cycle like runtime skills."""
    lib = SkillLibrary(prune_age_cycles=10)
    for seed in all_seeds:
        lib.index_skill(seed)
        lib.skills[seed.skill_id].last_matched_cycle = 1
    lib._cycle = 100
    lib.prune()
    assert lib.skill_count == 0
    lib.reset_cycle()
    assert lib.skill_count == 4


def test_every_seed_has_toc_concept_map_and_ingestion_hooks(all_seeds):
    """TOC-derived concept maps + chapter ingestion hooks are mandatory."""
    for seed in all_seeds:
        assert seed.metadata["concept_map"], seed.skill_id
        assert seed.metadata["ingestion_hooks"], seed.skill_id
        for hook in seed.metadata["ingestion_hooks"]:
            assert hook["chapter"]
            assert hook["fills"]
            assert hook["verified"] is False  # honest until books land
        assert seed.metadata["required_after_reading"], seed.skill_id
        assert seed.metadata["toc_verified"] is False


def test_seed_source_books_match_acquisition_manifest(all_seeds):
    """Provenance is traceable to knowledge_library/books/README.md rows."""
    expected_primary = {
        "capital_guardian": "grant_trading_risk",
        "microstructure": "harris_trading_exchanges",
        "crypto_framing": "burniske_cryptoassets",
        "position_sizing": "vince_math_money_management",
    }
    for seed in all_seeds:
        assert seed.metadata["primary_source"] == expected_primary[seed.skill_id]
        assert seed.metadata["source_books"], seed.skill_id


def test_individual_builders():
    """Each builder returns a valid skill with the right id."""
    builders = [
        build_capital_guardian_seed,
        build_microstructure_seed,
        build_crypto_framing_seed,
        build_position_sizing_seed,
    ]
    expected_ids = [
        "capital_guardian",
        "microstructure",
        "crypto_framing",
        "position_sizing",
    ]
    for builder, sid in zip(builders, expected_ids):
        skill = builder()
        assert skill.skill_id == sid
        assert skill.trajectory["intent_type"]
        assert skill.trajectory["procedure"]


def test_unknown_seed_id_raises():
    with pytest.raises(KeyError):
        seed_by_id("does_not_exist")
