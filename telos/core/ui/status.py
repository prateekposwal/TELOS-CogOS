"""
ThinkingDisplay — Live pipeline status indicator for TELOS.

Shows which phase is active, which streams are contributing, and live DI/MD
as the pipeline executes. Updates in place using \r carriage return.

Usage:
    display = ThinkingDisplay()
    pipeline._display = display
    result = pipeline.execute(state)
    display.freeze()
"""

import sys
from typing import List, Tuple, Optional


class ThinkingDisplay:
    """Live-updating, terminal-friendly thinking indicator."""

    PHASE_EMOJI = {
        "perceive": "🔍", "streams": "🧵", "simulate": "🎲",
        "evaluate": "⚖️", "synthesis": "📋", "select": "✅",
        "council": "🛡️", "act": "⚡", "reflect": "🔁",
    }
    PHASE_LABELS = [
        "perceive", "streams", "simulate", "evaluate",
        "synthesis", "select", "council", "act", "reflect",
    ]

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._active_phase: str = ""
        self._cycle: int = 0
        self._streams: List[Tuple[str, float]] = []
        self._di: float = 0.0
        self._md: float = 0.0
        self._status: str = ""
        self._worlds: int = 0
        self._best_score: float = 0.0
        self._frozen: bool = False

    def on_cycle_start(self, cycle: int):
        self._cycle = cycle
        self._streams = []
        self._di = 0.0
        self._md = 0.0
        self._status = ""
        self._render()

    def on_phase_start(self, phase_name: str):
        self._active_phase = phase_name
        self._render()

    def on_stream_result(self, stream_name: str, confidence: float):
        self._streams.append((stream_name, confidence))
        self._streams.sort(key=lambda x: -x[1])
        self._render()

    def on_simulation(self, worlds: int, best_score: float):
        self._worlds = worlds
        self._best_score = best_score
        self._status = f"Simulating {worlds} futures... best: {best_score:.2f}"
        self._render()

    def on_council_signal(self, di: float, md: float, summary: str = ""):
        self._di = di
        self._md = md
        if summary:
            self._status = summary
        else:
            self._status = f"Council evaluating — DI: {di:.2f}, MD: {md:.2f}"
        self._render()

    def set_status(self, text: str):
        self._status = text
        self._render()

    def freeze(self):
        self._frozen = True
        sys.stdout.write("\n\n")
        sys.stdout.flush()

    def _render(self):
        if not self.enabled or self._frozen:
            return

        # Line 1: Phase progress bar
        parts = [f"🧠 Cycle {self._cycle} —"]
        for name in self.PHASE_LABELS:
            emoji = self.PHASE_EMOJI.get(name, "·")
            if name == self._active_phase:
                parts.append(f"{emoji} {name.upper()}")
            else:
                parts.append(f"·{emoji} {name}")
        bar = " → ".join(parts)

        # Line 2: Stream leaderboard (if any)
        stream_line = ""
        if self._streams:
            tops = self._streams[:2]
            entries = [f"{s} ({c:.2f})" for s, c in tops]
            stream_line = f"{' ' * 4}↗ {' · '.join(entries)}"

        # Line 3: DI/MD + status
        council = f"[DI: {self._di:.2f} · MD: {self._md:.2f}]"
        status_text = self._status or "Thinking..."
        status_line = f"{council} {status_text}"

        # Write all 3 lines, move cursor up to overwrite next time
        sys.stdout.write(f"\r{bar}\n\r{stream_line}\n\r{status_line}")
        sys.stdout.write("\033[3A")
        sys.stdout.flush()
