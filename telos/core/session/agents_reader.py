"""agents_reader — cross-session learning context loading.

At session start, reads AGENTS.md handoff blocks and extracts
learnings, open issues, and metrics into the pipeline context.
"""

import os
import re
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger('telos_agents_reader')

AGENTS_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS.md')


@dataclass
class SessionLearnings:
    learnings: List[str]
    open_issues: List[str]
    metrics: Dict[str, float]
    timestamp: str = ""


def read_latest_handoff() -> Optional[SessionLearnings]:
    """Read the most recent session handoff from AGENTS.md."""
    if not os.path.exists(AGENTS_PATH):
        return None
    with open(AGENTS_PATH) as f:
        content = f.read()

    blocks = content.split("## Session Handoff")
    if len(blocks) < 2:
        return None

    latest = "## Session Handoff" + blocks[-1]
    learnings = []
    open_issues = []
    metrics = {}

    in_decisions = False
    in_issues = False
    in_metrics = False

    for line in latest.split("\n"):
        if "### Decisions Made" in line:
            in_decisions = True
            in_issues = False
            in_metrics = False
            continue
        if "### Open Issues" in line:
            in_decisions = False
            in_issues = True
            in_metrics = False
            continue
        if "### Metrics" in line:
            in_decisions = False
            in_issues = False
            in_metrics = True
            continue

        if in_decisions and line.strip().startswith("- "):
            learnings.append(line.strip()[2:])
        if in_issues and line.strip().startswith("- "):
            open_issues.append(line.strip()[2:])
        if in_metrics:
            for key in ["DI", "MD", "Cycles"]:
                pattern = rf"{key}:\s*([\d.]+)"
                m = re.search(pattern, line)
                if m:
                    metrics[key.lower()] = float(m.group(1))

    if not learnings and not open_issues:
        return None

    return SessionLearnings(
        learnings=learnings,
        open_issues=open_issues,
        metrics=metrics,
        timestamp=latest.split("\n")[0].replace("## Session Handoff", "").strip(),
    )


def inject_into_context(pipeline) -> None:
    """Inject previous session learnings into pipeline context at init."""
    handoff = read_latest_handoff()
    if handoff is None:
        logger.info("AgentsReader: no previous handoff found — starting fresh")
        return

    try:
        ctx = getattr(pipeline, '_context', None)
        if ctx is None:
            return

        ctx.previous_learnings = handoff.learnings
        ctx.previous_open_issues = handoff.open_issues
        ctx.previous_metrics = handoff.metrics
        logger.info(f"AgentsReader: loaded {len(handoff.learnings)} learnings, "
                    f"{len(handoff.open_issues)} open issues from {handoff.timestamp}")
    except Exception as e:
        logger.warning(f"AgentsReader: injection failed: {e}")
