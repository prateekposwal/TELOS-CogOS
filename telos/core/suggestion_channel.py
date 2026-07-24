"""
SuggestionChannel — Surface TELOS findings to the user without waiting for a query.

Collects pipeline output (findings, recommendations, warnings) and presents them
in a readable format. Integrates with the ProactiveScheduler to push findings.

Usage:
    channel = SuggestionChannel()
    channel.push("📦", "Outdated dependencies", "3 packages have newer versions")
    channel.display()
"""

import time
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger('telos_suggest')


@dataclass
class Suggestion:
    """A single suggestion from TELOS."""
    category: str       # emoji category: 🔧, 🧪, 📦, ⚠️, ✅
    title: str
    message: str
    timestamp: float = field(default_factory=time.time)
    severity: int = 1   # 1=info, 2=warning, 3=critical
    domain: str = "codebase"
    dismissed: bool = False


class SuggestionChannel:
    """Collects and displays TELOS suggestions.

    Suggestions are stored in memory and can be:
      - Pushed from the ProactiveScheduler
      - Queried via get_pending()
      - Displayed via display() or summary()
    """

    def __init__(self, max_history: int = 50):
        self._suggestions: List[Suggestion] = []
        self._max_history = max_history

    def push(self, category: str, title: str, message: str,
             severity: int = 1, domain: str = "codebase"):
        """Add a new suggestion."""
        self._suggestions.append(Suggestion(
            category=category, title=title, message=message,
            severity=severity, domain=domain,
        ))
        # Trim to max history
        if len(self._suggestions) > self._max_history:
            self._suggestions = self._suggestions[-self._max_history:]

    def push_findings(self, findings: List[str]):
        """Push multiple findings from the DevDomainAdapter."""
        for f in findings:
            severity = 2 if any(w in f for w in ['❌', 'Missing', 'error']) else 1
            cat = '✅' if '✅' in f else '⚠️' if '⚠️' in f else '📋'
            title = f.split(':')[0] if ':' in f else "Finding"
            message = f
            self.push(cat, title, message, severity)

    def get_pending(self, min_severity: int = 1) -> List[Suggestion]:
        """Get all non-dismissed suggestions above a severity threshold."""
        return [s for s in self._suggestions
                if not s.dismissed and s.severity >= min_severity]

    def dismiss(self, title: str):
        """Dismiss a suggestion by title."""
        for s in self._suggestions:
            if s.title == title:
                s.dismissed = True

    def display(self, min_severity: int = 1) -> str:
        """Format all pending suggestions as a human-readable block."""
        pending = self.get_pending(min_severity)
        if not pending:
            return "✅ No active suggestions."

        lines = ["📋  TELOS SUGGESTIONS\n"]
        by_severity = {1: [], 2: [], 3: []}
        for s in pending:
            by_severity[s.severity].append(s)

        for sev in [3, 2, 1]:
            items = by_severity[sev]
            if not items:
                continue
            label = {3: "🔴 CRITICAL", 2: "🟡 WARNINGS", 1: "🔵 INFO"}[sev]
            lines.append(f"  {label}")
            lines.append(f"  {'=' * 30}")
            for s in items:
                time_str = datetime.fromtimestamp(s.timestamp).strftime('%H:%M')
                lines.append(f"  {s.category} {s.title}")
                lines.append(f"     {s.message}")
                lines.append(f"     [{time_str} | {s.domain}]")
            lines.append("")

        return "\n".join(lines)

    def summary(self) -> str:
        """Brief one-line summary of suggestion counts."""
        pending = self.get_pending()
        critical = sum(1 for s in pending if s.severity == 3)
        warnings = sum(1 for s in pending if s.severity == 2)
        info = sum(1 for s in pending if s.severity == 1)
        parts = []
        if critical:
            parts.append(f"🔴{critical}")
        if warnings:
            parts.append(f"🟡{warnings}")
        if info:
            parts.append(f"🔵{info}")
        return f"📋 {' · '.join(parts)} suggestions" if parts else "✅ All clear"

    def clear(self):
        """Clear all suggestions."""
        self._suggestions.clear()
