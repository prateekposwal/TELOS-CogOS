"""
ToolRateLimiter — per-tool sliding-window + per-session execution budget.

An unenforced rate limit is not a limit. The registry declares
``ToolSpec.rate_limit_per_min`` for every tool; this module is the ONE
enforcement implementation, and ActionExecutor is the ONE call site every real
tool execution passes through (Λ6.7: one canonical registry, one enforcement
boundary).

Two independent bounds protect the governed channel from an autonomous loop:
  * per-tool sliding window  — at most ``rate_limit_per_min`` invocations of
    one tool in the trailing ``WINDOW_SECONDS`` (default 60s);
  * per-session budget       — at most ``max_total`` tool executions for the
    lifetime of the executor, even across different tools, so an autonomous
    loop cannot hammer tools by rotating among them.

DETERMINISM: the limiter NEVER reads the wall clock itself. The executor
injects a ``clock`` callable (default ``time.monotonic``); tests inject a fake
clock. Only a per-minute window needs a clock at all, and the injection keeps
that dependency explicit and isolated. The governed channel is opt-in and OFF
by default (no executor => no limiter, nothing to rate-limit), so the
deterministic core and the endurance/determinism gates never exercise this
clock.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Optional

# Sliding window for the per-tool ``rate_limit_per_min`` ceiling.
WINDOW_SECONDS = 60.0
# Default per-session (per-executor) global tool-execution budget. Sane cap for
# a run: generous for legitimate multi-step work, far below what a runaway loop
# would need. ``None`` disables the global budget (configurable).
DEFAULT_MAX_TOOL_EXECUTIONS = 200


@dataclass
class RateLimitDecision:
    """The outcome of one rate-limit check (allowed or a recorded block).

    Attributes:
        allowed: True when the request may proceed (and was recorded).
        reason: the recorded block reason when denied, else "".
        tool_name: the tool that was checked.
        tool_count: in-window invocations of the tool at decision time.
        tool_limit: the tool's per-minute ceiling (None = unlimited).
        total_count: the per-session execution count at decision time.
        total_budget: the per-session budget (None = unlimited).
    """

    allowed: bool
    reason: str = ""
    tool_name: str = ""
    tool_count: int = 0
    tool_limit: Optional[int] = None
    total_count: int = 0
    total_budget: Optional[int] = None


class ToolRateLimiter:
    """Deterministic sliding-window + global-budget limiter for tool runs.

    The limiter is self-contained: no I/O, no shared global state. One instance
    belongs to one ActionExecutor (one session/run). ``check`` records a
    permitted request and returns the decision; a denied request is NOT
    recorded (a block does not consume budget).
    """

    def __init__(self,
                 limits: Optional[Dict[str, Optional[int]]] = None,
                 max_total: Optional[int] = DEFAULT_MAX_TOOL_EXECUTIONS,
                 window_seconds: float = WINDOW_SECONDS,
                 clock: Optional[Callable[[], float]] = None):
        """Build a limiter.

        Args:
            limits: tool name -> per-minute ceiling (None = no per-tool limit).
            max_total: per-session tool-execution budget (None = unlimited).
            window_seconds: sliding-window length for per-tool limits.
            clock: monotonic seconds source (default ``time.monotonic``);
                injected so tests are deterministic and the wall clock is
                isolated to this opt-in, default-OFF channel.
        """
        self._limits: Dict[str, Optional[int]] = dict(limits or {})
        self._max_total = None if max_total is None else int(max_total)
        self._window = float(window_seconds)
        self._clock = clock or time.monotonic
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._total = 0

    def check(self, tool_name: str) -> RateLimitDecision:
        """Check + record one tool-execution request.

        On an allowed request the invocation is counted (per-tool window event
        and global budget). On a breach nothing is counted and a block reason
        is returned.

        Args:
            tool_name: the tool being requested.

        Returns:
            A RateLimitDecision — ``allowed=False`` carries the recorded
            reason for the block record.
        """
        now = self._clock()
        dq = self._events[tool_name]
        cutoff = now - self._window
        while dq and dq[0] <= cutoff:
            dq.popleft()
        tool_count = len(dq)
        limit = self._limits.get(tool_name)

        # Global budget first: it can never be satisfied by waiting.
        if self._max_total is not None and self._total >= self._max_total:
            return RateLimitDecision(
                allowed=False,
                reason=(f"global tool budget exhausted "
                        f"({self._total}/{self._max_total} executions)"),
                tool_name=tool_name,
                tool_count=tool_count,
                tool_limit=limit,
                total_count=self._total,
                total_budget=self._max_total,
            )
        if limit is not None and tool_count >= limit:
            return RateLimitDecision(
                allowed=False,
                reason=(f"rate limit exceeded for {tool_name!r}: "
                        f"{tool_count}/{limit} per {int(self._window)}s"),
                tool_name=tool_name,
                tool_count=tool_count,
                tool_limit=limit,
                total_count=self._total,
                total_budget=self._max_total,
            )

        dq.append(now)
        self._total += 1
        return RateLimitDecision(
            allowed=True,
            tool_name=tool_name,
            tool_count=len(dq),
            tool_limit=limit,
            total_count=self._total,
            total_budget=self._max_total,
        )

    def snapshot(self) -> Dict[str, object]:
        """Return the current counter state (audit/debugging).

        Returns:
            Dict with ``total`` executions and per-tool in-window counts.
        """
        now = self._clock()
        cutoff = now - self._window
        counts = {}
        for name, dq in self._events.items():
            live = [t for t in dq if t > cutoff]
            if live:
                counts[name] = len(live)
        return {
            "total": self._total,
            "max_total": self._max_total,
            "window_seconds": self._window,
            "per_tool": counts,
        }


__all__ = [
    "ToolRateLimiter", "RateLimitDecision",
    "WINDOW_SECONDS", "DEFAULT_MAX_TOOL_EXECUTIONS",
]
