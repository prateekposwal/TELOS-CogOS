"""
Benchmark loop — drive a pipeline the way the LIVE producer does.

The producer signals episode resets: when the simulator reaches a terminal
state it sets `episode_reset_pending`, and the NEXT `execute(...)` call passes
`episode_reset=True`. Benchmark harnesses that reset the state to the origin
WITHOUT that signal poison the model's reality gap (the model predicted a
landing near the goal, then observes the origin -> a huge spurious gap ->
fidelity collapses -> the act `model_fidelity` gate DEFERs). This helper is the
one correct driver, so every tool measures the real system.
"""

from __future__ import annotations

from typing import Any, Dict, Generator, Optional

import numpy as np


def drive(pipeline: Any, cycles: int,
          user_name: str = "benchmark") -> Generator[Dict[str, Any], None, None]:
    """Drive a pipeline through `cycles`, honoring the episode-reset protocol.

    Args:
        pipeline: a built TelosV14Pipeline (needs config.simulator + terminal()).
        cycles: number of cycles.
        user_name: creator-name binding passed to execute().

    Yields:
        dict with keys: cycle, result, trace, state_before, state_after,
        terminal.
    """
    sim = pipeline.config.simulator
    state = np.array([0.0, 0.0])
    reset_pending = False
    for i in range(cycles):
        res = pipeline.execute(np.array(state, dtype=float), user_name=user_name,
                               episode_reset=reset_pending)
        reset_pending = False
        trace = res.decision_trace
        state_before = state
        action = trace.selected_action if trace is not None else None
        if action is not None and not res.firewall_blocked:
            state = sim.transition(state, action)
        terminal = bool(sim.terminal(state)) if sim is not None else False
        if terminal:
            # Signal the NEXT cycle that it observes a fresh episode — the one
            # thing a naive harness omits (and that corrupts fidelity).
            reset_pending = True
            state = np.array([0.0, 0.0])
        yield {
            "cycle": i,
            "result": res,
            "trace": trace,
            "state_before": state_before,
            "state_after": state,
            "terminal": terminal,
        }


__all__ = ["drive"]
