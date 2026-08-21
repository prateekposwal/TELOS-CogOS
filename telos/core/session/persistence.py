"""Cross-session learning persistence — saves/loads learnings across sessions.

ExperienceManager.observe() runs every cycle but learnings are ephemeral.
This module persists key learnings to disk and reloads them on restart.
"""

from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

logger = logging.getLogger('telos_persistence')

PERSISTENCE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'learnings.json')


@dataclass
class SessionLearnings:
    session_id: str
    cycle_count: int
    top_skills: List[Dict] = field(default_factory=list)
    top_theories: List[Dict] = field(default_factory=list)
    persistent_questions: List[str] = field(default_factory=list)
    failure_patterns: List[Dict] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> 'SessionLearnings':
        return cls(**d)


def save_learnings(pipeline, metrics: Dict) -> bool:
    """Extract learnings from pipeline state and persist to disk.
        Args:
            metrics: metrics to fold into the result
    """
    try:
        em = getattr(pipeline, '_experience_manager', None)
        tb = getattr(pipeline, '_theory_builder', None)
        uud = getattr(pipeline, '_unknown_unknown_detector', None)
        fl = getattr(pipeline, '_infra_manager', None)

        top_skills = []
        if em and hasattr(em, 'skill_library') and hasattr(em.skill_library, '_skills'):
            skills = list(em.skill_library._skills.values())
            skills.sort(key=lambda s: getattr(s, 'utility_score', 0), reverse=True)
            for s in skills[:5]:
                top_skills.append({
                    "id": getattr(s, 'skill_id', ''),
                    "utility": getattr(s, 'utility_score', 0),
                })

        top_theories = []
        if tb:
            for t in (tb.get_active_theories() or []):
                top_theories.append({
                    "name": getattr(t, 'name', ''),
                    "confidence": getattr(t, 'confidence', 0),
                })

        questions = []
        if uud:
            for q in (uud.get_unanswered_questions() or []):
                questions.append(getattr(q, 'question_text', ''))

        learnings = SessionLearnings(
            session_id=metrics.get('session_id', 'unknown'),
            cycle_count=metrics.get('cycles', 0),
            top_skills=top_skills,
            top_theories=top_theories,
            persistent_questions=questions,
            metrics=metrics,
        )

        with open(PERSISTENCE_PATH, 'w') as f:
            json.dump(learnings.to_dict(), f, indent=2, default=str)
        logger.info(f"Cross-session learnings saved to {PERSISTENCE_PATH}")
        return True
    except Exception as e:
        logger.warning(f"Cross-session save failed: {e}")
        return False


def load_learnings() -> Optional[SessionLearnings]:
    """Load learnings from previous session."""
    if not os.path.exists(PERSISTENCE_PATH):
        return None
    try:
        with open(PERSISTENCE_PATH) as f:
            data = json.load(f)
        return SessionLearnings.from_dict(data)
    except Exception as e:
        logger.warning(f"Cross-session load failed: {e}")
        return None
