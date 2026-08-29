"""
SkillLibrary — Persistent ledger of successful trajectories with Option Decay (Axiom 3.3).

Skills that are not matched within `prune_age_cycles` cycles are archived
to prevent identity bloat and preserve computational entropy.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import numpy as np
import time
import logging
from telos.world.world import World

logger = logging.getLogger("telos_skill_library")


@dataclass
class Skill:
    skill_id: str
    fingerprint: str
    trajectory: Any
    utility_score: float
    domain_config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_matched_cycle: int = 0


class SkillLibrary:
    def __init__(self, max_skills: int = 100, prune_age_cycles: int = 50,
                 max_archived: int = 100):
        self.max_skills = max_skills
        self.prune_age_cycles = prune_age_cycles
        self.max_archived = max_archived
        self.skills: Dict[str, Skill] = {}
        self._archived: List[Skill] = []
        self._cycle: int = 0

    def index_skill(self, skill: Skill) -> None:
        """Index a skill with input validation.

        - skill_id must be a non-empty string
        - fingerprint must be a non-empty string
        - utility_score is clamped to [0.0, 1.0] if out of range
        """
        # Validate skill_id: must be a non-empty string
        if not isinstance(skill.skill_id, str) or len(skill.skill_id) == 0:
            raise ValueError(
                f"skill_id must be a non-empty string, got {skill.skill_id!r}"
            )

        # Validate fingerprint: must be a non-empty string
        if not isinstance(skill.fingerprint, str) or len(skill.fingerprint) == 0:
            raise ValueError(
                f"fingerprint must be a non-empty string, got {skill.fingerprint!r}"
            )

        # Validate utility_score: must be a number; clamp to [0.0, 1.0]
        if not isinstance(skill.utility_score, (int, float)):
            raise ValueError(
                f"utility_score must be a number, got {type(skill.utility_score).__name__}"
            )
        if skill.utility_score < 0.0 or skill.utility_score > 1.0:
            logger.warning(
                "Clamping utility_score from %.4f to [0.0, 1.0] for skill %s",
                skill.utility_score, skill.skill_id,
            )
            skill.utility_score = max(0.0, min(1.0, skill.utility_score))

        if len(self.skills) >= self.max_skills:
            oldest = min(self.skills, key=lambda k: self.skills[k].utility_score)
            self._archive(self.skills[oldest])
            del self.skills[oldest]
        self.skills[skill.skill_id] = skill

    def _archive(self, skill: Skill) -> None:
        """Move a skill to the bounded archived list (oldest-first eviction)."""
        self._archived.append(skill)
        if len(self._archived) > self.max_archived:
            self._archived.sort(key=lambda s: s.last_matched_cycle)
            self._archived = self._archived[-self.max_archived:]

    def find_relevant_skills(self, state: np.ndarray, threshold: float = 0.8) -> List[Skill]:
        self._cycle += 1
        import hashlib
        state_bytes = state.tobytes()
        state_fingerprint = hashlib.md5(state_bytes).hexdigest()[:12]
        relevant = [
            s for s in self.skills.values()
            if s.fingerprint == state_fingerprint or s.utility_score > threshold
        ]
        for s in relevant:
            s.last_matched_cycle = self._cycle
        self.prune()
        return relevant

    def prune(self) -> int:
        """Remove skills not matched in prune_age_cycles. Returns count pruned."""
        cutoff = self._cycle - self.prune_age_cycles
        to_prune = [
            sid for sid, s in self.skills.items()
            if s.last_matched_cycle > 0 and s.last_matched_cycle < cutoff
        ]
        for sid in to_prune:
            self._archive(self.skills[sid])
            del self.skills[sid]

        # Utility-floor eviction: if active skills still exceed 80% capacity,
        # evict low-utility skills while keeping at least top 10.
        if len(self.skills) > self.max_skills * 0.8:
            # Keep at least the top 10 highest-utility skills regardless of score
            sorted_skills = sorted(self.skills.items(), key=lambda x: -x[1].utility_score)
            protected = set(sid for sid, _ in sorted_skills[:10])
            utility_evicted = []
            for sid, s in list(self.skills.items()):
                if sid in protected:
                    continue
                if s.utility_score < 0.3:
                    self._archive(s)
                    del self.skills[sid]
                    utility_evicted.append(sid)
            if utility_evicted:
                logger.info(
                    "Utility-floor eviction: removed %d skills with utility_score < 0.3 "
                    "(kept top 10 protected)",
                    len(utility_evicted),
                )

        return len(to_prune)

    @property
    def skill_count(self) -> int:
        return len(self.skills)

    @property
    def archived_count(self) -> int:
        return len(self._archived)

    def reset_cycle(self) -> None:
        self._cycle = 0
        for s in self.skills.values():
            s.last_matched_cycle = 0
        # P2.4: Instead of moving ALL archived back, only restore top-N by utility_score
        if self._archived:
            self._archived.sort(key=lambda s: s.utility_score, reverse=True)
            top_n = min(len(self._archived), max(10, self.max_skills // 2))
            for s in self._archived[:top_n]:
                s.last_matched_cycle = 0
                self.skills[s.skill_id] = s
            self._archived = self._archived[top_n:]

    @property
    def stats(self) -> Dict:
        return {
            "active_skills": self.skill_count,
            "archived_skills": self.archived_count,
            "max_skills": self.max_skills,
            "max_archived": self.max_archived,
            "prune_age_cycles": self.prune_age_cycles,
            "current_cycle": self._cycle,
        }
