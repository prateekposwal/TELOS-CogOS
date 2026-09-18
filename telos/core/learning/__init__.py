"""
TELOS learning layer (Phase 3).

Verified skill acquisition (Λ2.3 applied to learning) + a deterministic,
novelty-ordered curriculum (Voyager's self-verifying curriculum). Learning is
measured against a frozen control by telos/tools/learning_curve.py.
"""

from telos.core.learning.acquisition import (
    SkillAcquisition, SkillCandidate,
    DEFAULT_MIN_OUTCOME, DEFAULT_CANDIDATE_TTL_CYCLES, DEFAULT_MAX_CANDIDATES,
)
from telos.core.learning.curriculum import (
    Curriculum, CurriculumTask, ZPD_LOW, ZPD_HIGH,
)

__all__ = [
    "SkillAcquisition", "SkillCandidate", "Curriculum", "CurriculumTask",
    "DEFAULT_MIN_OUTCOME", "DEFAULT_CANDIDATE_TTL_CYCLES", "DEFAULT_MAX_CANDIDATES",
    "ZPD_LOW", "ZPD_HIGH",
]
