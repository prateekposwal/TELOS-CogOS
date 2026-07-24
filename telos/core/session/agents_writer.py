"""
AgentsWriter — Auto-generates structured session summaries for AGENTS.md.

Automatically writes a "Session Handoff" block to AGENTS.md when context
pressure exceeds 80%, or on graceful shutdown. Enables lossless session
continuity across "starting fresh" context windows.

Integrates with:
    - ContextSummarizer (session essence extraction)
    - TokenBudgetManager (signal-weighted message retention)
    - CheckpointManager (checkpoint reference)
    - Pipeline (DI, MD, cycle metrics)

Axiom 4.7 (System Memory), Axiom 5.1 (Self-Preservation)
"""

from __future__ import annotations

import os
import logging
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from telos.core.runtime import TelosV14Pipeline

logger = logging.getLogger('telos_agents_writer')

DEFAULT_AGENTS_PATH = "AGENTS.md"
CONTEXT_PRESSURE_THRESHOLD = 0.8


@dataclass
class SessionSummary:
    """Structured summary of a session for lossless handoff.

    Fields:
        current_state: What was being worked on (from ContextSummarizer essence)
        decisions_made: Key decisions with reasoning
        open_issues: Todos, bugs, questions, or unresolved items
        metrics: DI, MD, cycle count, token budget usage, checkpoint ref
        checkpoint_ref: Path to latest checkpoint file
        timestamp: ISO-formatted timestamp of the handoff
    """
    current_state: List[str] = field(default_factory=list)
    decisions_made: List[str] = field(default_factory=list)
    open_issues: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    checkpoint_ref: str = ""
    timestamp: str = ""


class AgentsWriter:
    """Auto-generates structured session summaries and writes to AGENTS.md.

    Detects context pressure from cycle count, token budget usage, and
    chat history size. When pressure exceeds the threshold, generates a
    structured markdown handoff block and inserts it into AGENTS.md.

    Usage:
        writer = AgentsWriter("AGENTS.md")
        pressure = writer.detect_context_pressure(pipeline, cycle_count)
        if pressure > 0.8:
            writer.write_summary(pipeline, cycle_count, chat_history,
                                 session_essence=essence)
    """

    def __init__(self, agents_path: str = DEFAULT_AGENTS_PATH):
        self.agents_path = agents_path

    def detect_context_pressure(
        self,
        pipeline: Any,
        cycle_count: int = 0,
        chat_history: Optional[List[Dict]] = None,
    ) -> float:
        """Detect context pressure on a 0.0–1.0 scale.

        Factors (each capped at 1.0 before weighting):
          - Cycle count:  more cycles → higher pressure  (weight 0.4)
          - Token budget: higher usage → higher pressure  (weight 0.4)
          - History size: longer history → higher pressure (weight 0.2)

        Returns:
            Float in [0.0, 1.0].
        """
        # ── Cycle factor ──────────────────────────────────────────────
        cycle_factor = min(1.0, cycle_count / 50.0) * 0.4

        # ── Token budget factor ───────────────────────────────────────
        budget_factor = 0.0
        tb = getattr(pipeline, '_token_budget', None)
        bm = getattr(pipeline, 'budget_manager', None)
        if bm is not None and hasattr(bm, 'total_budget_ms') and bm.total_budget_ms > 0:
            usage = bm.consumed_ms / bm.total_budget_ms
            budget_factor = min(1.0, usage) * 0.4

        # ── History size factor ───────────────────────────────────────
        history_factor = 0.0
        if chat_history is not None:
            history_factor = min(1.0, len(chat_history) / 100.0) * 0.2

        pressure = min(1.0, cycle_factor + budget_factor + history_factor)
        return pressure

    # ── Private extractors ────────────────────────────────────────────

    @staticmethod
    def _extract_essence(session_essence: Optional[Dict]) -> tuple:
        """Return (current_state, decisions_made) from a session essence."""
        current_state: List[str] = []
        decisions_made: List[str] = []

        if session_essence is None:
            return current_state, decisions_made

        for d in session_essence.get('key_decisions', []):
            decisions_made.append(d)

        for intent in session_essence.get('recurring_intents', []):
            current_state.append(f"Working on: {intent}")

        for pref in session_essence.get('user_preferences', []):
            current_state.append(f"User preference: {pref}")

        blocks = session_essence.get('blockers_resolved', [])
        if blocks:
            current_state.append(f"Resolved blockers: {'; '.join(blocks[:3])}")

        mood = session_essence.get('mood_trajectory', '')
        if mood:
            current_state.append(f"Session mood: {mood}")

        return current_state, decisions_made

    @staticmethod
    def _extract_open_issues(pipeline: Any, cycle_count: int) -> List[str]:
        """Scan pipeline for open issues / unrecovered problems."""
        issues: List[str] = []

        # Recent blocking events via telemetry
        telemetry = getattr(pipeline, '_telemetry', None)
        if telemetry is not None:
            try:
                recent = telemetry.get_recent_cycles(10)
                blocks = [
                    c for c in recent
                    if c and (c.get('council_blocked') or c.get('firewall_blocked'))
                ]
                if blocks:
                    issues.append(
                        f"{len(blocks)} blocking event(s) in last 10 cycles"
                    )
            except Exception:
                pass

        # Failure ledger
        infra = getattr(pipeline, '_infra_manager', None)
        if infra is not None:
            failures = getattr(infra, 'failures', None)
            if failures is not None:
                try:
                    f_len = len(list(failures))
                    if f_len > 0:
                        issues.append(f"{f_len} failure(s) recorded in ledger")
                except Exception:
                    pass

        # Escalation pending
        if hasattr(pipeline, '_last_trace') and pipeline._last_trace is not None:
            if getattr(pipeline._last_trace, 'escalation_requested', False):
                issues.append("Escalation is pending resolution")

        return issues

    @staticmethod
    def _extract_metrics(pipeline: Any, cycle_count: int) -> Dict[str, Any]:
        """Extract key performance metrics from the pipeline."""
        metrics: Dict[str, Any] = {}
        metrics['cycle_count'] = cycle_count

        lt = getattr(pipeline, '_last_trace', None)
        if lt is not None:
            metrics['di'] = round(getattr(lt, 'decision_integrity', 1.0), 3)
            metrics['md'] = round(getattr(lt, 'mission_drift', 0.0), 3)
        else:
            metrics['di'] = 1.0
            metrics['md'] = 0.0

        bm = getattr(pipeline, 'budget_manager', None)
        if bm is not None and hasattr(bm, 'total_budget_ms') and bm.total_budget_ms > 0:
            pct = round(bm.consumed_ms / bm.total_budget_ms * 100, 1)
            metrics['token_budget_pct'] = pct
        else:
            metrics['token_budget_pct'] = 0.0

        cp = getattr(pipeline, '_checkpointer', None)
        if cp is not None:
            latest = cp.latest_path
            metrics['checkpoint_ref'] = str(latest) if latest is not None else "N/A"
        else:
            metrics['checkpoint_ref'] = "N/A"

        if telemetry := getattr(pipeline, '_telemetry', None):
            try:
                stats = telemetry.get_stats()
                metrics['total_cycles'] = stats.get('total_cycles', cycle_count)
            except Exception:
                metrics['total_cycles'] = cycle_count

        return metrics

    # ── Markdown generation ───────────────────────────────────────────

    def generate_markdown(self, summary: SessionSummary) -> str:
        """Produce a structured markdown block for the session handoff.

        The block uses a consistent heading hierarchy so it can be parsed
        or concatenated with other AGENTS.md content.
        """
        ts = summary.timestamp or datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        lines: List[str] = []
        lines.append(f"## Session Handoff — {ts}")
        lines.append("")

        # ── Current State ─────────────────────────────────────────────
        lines.append("### Current State")
        if summary.current_state:
            for item in summary.current_state:
                lines.append(f"- {item}")
        else:
            lines.append("- *(No current state captured)*")
        lines.append("")

        # ── Decisions Made ────────────────────────────────────────────
        lines.append("### Decisions Made")
        if summary.decisions_made:
            for d in summary.decisions_made:
                lines.append(f"- {d}")
        else:
            lines.append("- *(No decisions recorded)*")
        lines.append("")

        # ── Open Issues ───────────────────────────────────────────────
        lines.append("### Open Issues")
        if summary.open_issues:
            for issue in summary.open_issues:
                lines.append(f"- {issue}")
        else:
            lines.append("- *(No open issues)*")
        lines.append("")

        # ── Metrics ───────────────────────────────────────────────────
        lines.append("### Metrics")
        m = summary.metrics
        di = m.get('di', 1.0)
        md = m.get('md', 0.0)
        cycles = m.get('cycle_count', 0)
        budget = m.get('token_budget_pct', 0.0)
        lines.append(
            f"- DI: {di:.3f} | MD: {md:.3f} | Cycles: {cycles} | "
            f"Token budget: {budget}%"
        )
        lines.append("")

        # ── Checkpoint ────────────────────────────────────────────────
        lines.append("### Checkpoint")
        cp = summary.checkpoint_ref or m.get('checkpoint_ref', 'N/A')
        lines.append(f"- {cp}")
        lines.append("")

        return "\n".join(lines)

    # ── Public write API ──────────────────────────────────────────────

    def write_summary(
        self,
        pipeline: Any,
        cycle_count: int,
        chat_history: Optional[List[Dict]] = None,
        trace_history: Optional[Dict] = None,
        session_essence: Optional[Dict] = None,
    ) -> str:
        """Generate a session handoff and persist it to AGENTS.md.

        Args:
            pipeline: TelosV14Pipeline (or any object with compatible attrs).
            cycle_count: Current pipeline cycle number.
            chat_history: Full chat history (used for pressure detection).
            trace_history: Not consumed directly — signature preserved for
                           future use with TokenBudgetManager traces.
            session_essence: Optional dict from ContextSummarizer.

        Returns:
            The generated markdown string (also written to file).
        """
        current_state, decisions_made = self._extract_essence(session_essence)
        open_issues = self._extract_open_issues(pipeline, cycle_count)
        metrics = self._extract_metrics(pipeline, cycle_count)
        checkpoint_ref = metrics.get('checkpoint_ref', 'N/A')

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        summary = SessionSummary(
            current_state=current_state,
            decisions_made=decisions_made,
            open_issues=open_issues,
            metrics=metrics,
            checkpoint_ref=checkpoint_ref,
            timestamp=timestamp,
        )

        markdown = self.generate_markdown(summary)
        self._write_to_agents(markdown)

        logger.info(
            "AgentsWriter: Session handoff written to %s — "
            "%d state items, %d decisions, %d issues",
            self.agents_path,
            len(current_state),
            len(decisions_made),
            len(open_issues),
        )

        return markdown

    # ── File I/O ──────────────────────────────────────────────────────

    def _write_to_agents(self, markdown_block: str) -> None:
        """Insert the handoff block into AGENTS.md at the right location.

        Strategy:
            1. If the file does not exist, create it.
            2. If a "## TELOS — Future Work (Todo)" section exists, insert
               the block right before it.
            3. Otherwise, if a "## TELOS" heading exists, insert before it.
            4. Otherwise append to the end.
        """
        if not os.path.exists(self.agents_path):
            header = (
                "# Auto-Generated Session Handoffs\n\n"
                "This file is automatically managed by TELOS AgentsWriter.\n"
                "Session handoffs are inserted as context pressure increases.\n\n"
            )
            content = header + markdown_block + "\n"
            with open(self.agents_path, 'w') as f:
                f.write(content)
            logger.info("Created new %s", self.agents_path)
            return

        with open(self.agents_path, 'r') as f:
            content = f.read()

        # Determine insertion point
        future_work = "## TELOS — Future Work (Todo)"
        telos_heading = "## TELOS"

        if future_work in content:
            idx = content.index(future_work)
            content = content[:idx] + markdown_block + "\n\n" + content[idx:]
        elif telos_heading in content:
            idx = content.index(telos_heading)
            content = content[:idx] + markdown_block + "\n\n" + content[idx:]
        else:
            content = content.rstrip() + "\n\n" + markdown_block + "\n"

        with open(self.agents_path, 'w') as f:
            f.write(content)
