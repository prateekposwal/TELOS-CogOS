"""TELOS debug-loop guard — structural patterns that keep the human-facing
agent/skill layer from stuttering (the patterns the GridWorld pipeline already
embodies, now made load-bearing for the debugger/agent layer)."""
from telos.core.debug.guard import (
    DebugLoopGuard,
    GuardStatus,
    PatentLoops,
    NO_ACTION_REPEAT_THRESHOLD,
    UNSUPPORTED_FALSIFIED_AFTER,
)

__all__ = [
    "DebugLoopGuard", "GuardStatus", "PatentLoops",
    "NO_ACTION_REPEAT_THRESHOLD", "UNSUPPORTED_FALSIFIED_AFTER",
]
