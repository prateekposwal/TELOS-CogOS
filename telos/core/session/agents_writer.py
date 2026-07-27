"""agents_writer — cross-session learning persistence.

At session end, queries pipeline state and populates AGENTS.md
with structured data so the system remembers what it learned.
Also provides backward-compatible AgentsWriter class.
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger('telos_agents_writer')

AGENTS_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS.md')


class SessionSummary:
    """Structured session handoff data (backward-compatible)."""
    def __init__(self, current_state=None, decisions_made=None,
                 open_issues=None, metrics=None, checkpoint_ref="",
                 timestamp="", di=1.0, md=0.0, cycles=0, mood="neutral"):
        self.current_state = current_state or []
        self.decisions_made = decisions_made or []
        self.open_issues = open_issues or []
        self.metrics = metrics or {}
        self.checkpoint_ref = checkpoint_ref
        self.timestamp = timestamp
        self.di = di
        self.md = md
        self.cycles = cycles
        self.mood = mood


class AgentsWriter:
    """Backward-compatible session handoff writer."""
    def __init__(self, path: Optional[str] = None):
        self._path = path or AGENTS_PATH

    def generate_markdown(self, summary: SessionSummary) -> str:
        return build_handoff(None, {
            "di": getattr(summary, 'di', summary.metrics.get('di', 1.0)),
            "md": getattr(summary, 'md', summary.metrics.get('md', 0.0)),
            "cycles": getattr(summary, 'cycles', summary.metrics.get('cycle_count', 0)),
            "mood": getattr(summary, 'mood', 'neutral'),
        })

    def write_summary(self, summary: SessionSummary,
                      path: Optional[str] = None) -> None:
        markdown = self.generate_markdown(summary)
        target = path or self._path
        with open(target, 'a') as f:
            f.write("\n" + markdown + "\n")

    def detect_context_pressure(self) -> float:
        return 0.0


def build_handoff(pipeline, metrics: Dict) -> str:
    """Build a session handoff block from pipeline state."""
    learnings = []
    if pipeline is not None:
        em = getattr(pipeline, '_experience_manager', None)
        if em and hasattr(em, 'skill_library'):
            sl = em.skill_library
            if hasattr(sl, '_skills') and sl._skills:
                top = sorted(sl._skills.values(),
                            key=lambda s: getattr(s, 'utility_score', 0), reverse=True)[:3]
                for s in top:
                    learnings.append(f"- Learned skill '{getattr(s, 'skill_id', 'unknown')}' "
                                   f"(utility={getattr(s, 'utility_score', 0):.2f})")

    lines = [
        f"## Session Handoff — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "### Current State",
        f"- Session mood: {metrics.get('mood', 'neutral')}",
        "",
        "### Decisions Made",
    ]
    if learnings:
        lines.extend(learnings)
    else:
        lines.extend(["- *(No decisions recorded)*"])

    lines.extend(["", "### Open Issues"])
    lines.extend(["- *(No open issues)*"])

    lines.extend([
        "",
        "### Metrics",
        f"- DI: {metrics.get('di', 1.0):.3f} | MD: {metrics.get('md', 0.0):.3f} | "
        f"Cycles: {metrics.get('cycles', 0)}",
        "",
    ])
    return "\n".join(lines)


def write_handoff(pipeline, metrics: Dict) -> bool:
    """Append session handoff to AGENTS.md."""
    try:
        handoff = build_handoff(pipeline, metrics)
        with open(AGENTS_PATH, 'a') as f:
            f.write("\n" + handoff + "\n")
        logger.info(f"AgentsWriter: handoff written to {AGENTS_PATH}")
        return True
    except Exception as e:
        logger.warning(f"AgentsWriter: failed to write handoff: {e}")
        return False
