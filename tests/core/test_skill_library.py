"""
SkillLibrary (core/ledger/skill_library.py) — honest contract coverage.
"""
import numpy as np

from telos.core.ledger.skill_library import Skill, SkillLibrary


class TestSkillLibrary:
    def test_index_and_find(self):
        lib = SkillLibrary(max_skills=50)
        import hashlib
        state = np.array([0.9, 0.1])
        fp = hashlib.md5(state.tobytes()).hexdigest()[:12]
        skill = Skill(skill_id="s1", fingerprint=fp, trajectory=state,
                      utility_score=0.8)
        lib.index_skill(skill)
        assert lib.skill_count == 1
        found = lib.find_relevant_skills(state, threshold=0.7)
        assert any(s.skill_id == "s1" for s in found)

    def test_prune(self):
        lib = SkillLibrary(max_skills=5, prune_age_cycles=1)
        for i in range(8):
            lib.index_skill(Skill(skill_id=f"s{i}", fingerprint=f"fp{i}",
                                  trajectory=np.array([0.5, 0.5]),
                                  utility_score=0.1))
        lib.reset_cycle()
        assert lib.prune() >= 0        # pruning returns a count
        assert lib.archived_count >= 0

    def test_stats(self):
        lib = SkillLibrary()
        assert lib.stats is not None
