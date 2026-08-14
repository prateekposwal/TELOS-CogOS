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
        self.agents_path = self._path

    def generate_markdown(self, summary: SessionSummary) -> str:
        ts = (summary.timestamp or datetime.now().strftime('%Y-%m-%d %H:%M:%S'))[:19]
        lines = [
            f"## Session Handoff — {ts}",
            "",
            "### Current State",
        ]
        if getattr(summary, 'current_state', None):
            lines.extend(f"- {s}" for s in summary.current_state)
        else:
            lines.append("*(No current state captured)*")

        lines.extend(["", "### Decisions Made"])
        if getattr(summary, 'decisions_made', None):
            lines.extend(f"- {d}" for d in summary.decisions_made)
        else:
            lines.append("*(No decisions recorded)*")

        lines.extend(["", "### Open Issues"])
        if getattr(summary, 'open_issues', None):
            lines.extend(f"- {o}" for o in summary.open_issues)
        else:
            lines.append("*(No open issues)*")

        m = getattr(summary, 'metrics', {}) or {}
        cp = getattr(summary, 'checkpoint_ref', None) or m.get('checkpoint_ref', "N/A")
        tb = m.get('token_budget_pct', 0)
        lines.extend([
            "",
            "### Metrics",
            f"- DI: {m.get('di', 1.0):.3f} | MD: {m.get('md', 0.0):.3f} | "
            f"Cycles: {m.get('cycle_count', 0)} | Token budget: {tb:.1f}%",
            "",
            "### Checkpoint",
            f"- {cp}",
            "",
        ])
        return "\n".join(lines)

    def write_summary(self, summary_or_pipeline: Any = None,
                      path: Optional[str] = None,
                      pipeline: Any = None,
                      cycle_count: int = 0,
                      chat_history: Any = None,
                      session_essence: Any = None) -> str:
        if summary_or_pipeline is not None and not isinstance(summary_or_pipeline, SessionSummary):
            if pipeline is None:
                pipeline = summary_or_pipeline
            summary_or_pipeline = SessionSummary(
                metrics={"di": 1.0, "md": 0.0, "cycle_count": cycle_count},
            )
        if summary_or_pipeline is None:
            summary_or_pipeline = SessionSummary(
                metrics={"di": 1.0, "md": 0.0, "cycle_count": cycle_count},
            )
        # Extract checkpoint from pipeline if available
        if pipeline is not None:
            chk = getattr(pipeline, '_checkpointer', None)
            if chk is not None and hasattr(chk, 'latest_path') and chk.latest_path:
                summary_or_pipeline.checkpoint_ref = chk.latest_path
        # Incorporate session_essence into the summary
        if session_essence and isinstance(session_essence, dict):
            decisions = session_essence.get('key_decisions', [])
            if decisions and not getattr(summary_or_pipeline, 'decisions_made', None):
                summary_or_pipeline.decisions_made = decisions
        markdown = self.generate_markdown(summary_or_pipeline)
        target = path or self._path
        if target:
            os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
            with open(target, 'a') as f:
                f.write("\n" + markdown + "\n")
        return markdown

    def detect_context_pressure(self, pipeline: Any = None,
                                 cycle_count: int = 0,
                                 budget_consumed: float = 0.0,
                                 budget_total: float = 1.0,
                                 chat_history: Any = None,
                                 timestamp: str = "") -> float:
        util = budget_consumed / max(budget_total, 1)
        return min(1.0, 0.1 + util * 0.5 + cycle_count * 0.01)


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
    """Append session handoff to AGENTS.md from the given pipeline + metrics.

    Skips the write when the session has nothing to record (no learnings
    AND zero cycles) — e.g. test-harness pipelines. Empty duplicate
    handoffs are the documented AGENTS.md bloat source; they must not
    regenerate.
    """
    try:
        handoff = build_handoff(pipeline, metrics)
        if "(No decisions recorded)" in handoff and metrics.get('cycles', 0) == 0:
            logger.debug("AgentsWriter: skipping empty handoff (no decisions, 0 cycles)")
            return False
        with open(AGENTS_PATH, 'a') as f:
            f.write("\n" + handoff + "\n")
        logger.info(f"AgentsWriter: handoff written to {AGENTS_PATH}")
        return True
    except Exception as e:
        logger.warning(f"AgentsWriter: failed to write handoff: {e}")
        return False
