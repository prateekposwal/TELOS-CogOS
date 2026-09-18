"""
TELOS quickstart — install, run one governed cycle, and read the result.

Run it:

    pip install -e .
    python examples/quickstart.py

What you will see:
  - a real 9-phase pipeline cycle on the synthetic GridWorld domain;
  - the decision integrity (DI) and mission drift (MD) for the cycle;
  - whether governance blocked the action;
  - how many decision-memory records were consulted and stored.

Everything is local and deterministic (seed 42). No network, no keys.
"""

from __future__ import annotations

import os
import sys

# Allow running from a source checkout without installing.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from telos import __version__
from telos.cli import _build_gridworld_pipeline


def main() -> int:
    """Run a short governed session and print the measured outcome.

    Returns:
        Process exit code (0 on success).
    """
    print(f"TELOS CogOS {__version__} — quickstart")
    print("=" * 56)

    checkpoint_dir = os.path.join(os.path.dirname(__file__), ".quickstart_state")
    pipeline = _build_gridworld_pipeline(checkpoint_dir=checkpoint_dir)

    state = np.array([0.0, 0.0])
    for cycle in range(1, 6):
        result = pipeline.execute(state, user_name="quickstart")
        trace = getattr(pipeline, "_last_trace", None)
        selected = getattr(trace, "selected_action", None) if trace else None
        blocked = result.council_blocked or result.firewall_blocked
        print(
            f"  cycle {cycle}: DI={result.decision_integrity:.3f} "
            f"MD={result.mission_drift:.3f} "
            f"blocked={blocked}"
        )
        # Advance the agent with a legal cardinal move when one was selected.
        if selected is not None:
            try:
                nxt = pipeline.config.simulator.transition(state, selected)
                if 0.0 <= float(nxt[0]) <= 4.0 and 0.0 <= float(nxt[1]) <= 4.0:
                    state = nxt
            except Exception:
                pass

    mem = pipeline.memory_report()
    print("-" * 56)
    print(f"  memory recalled: {mem.get('memory_consumed', 0)}")
    print(f"  memory stored:   {mem.get('inserted', 0)}")
    print(f"  memory live:     {mem.get('total', 0)}")
    policy = getattr(pipeline.infra_manager, "policy", None)
    if policy is not None:
        current = getattr(policy, "current", policy)
        print(f"  risk tolerance:  {current.risk_tolerance:.2f}")
        print(f"  recovery mode:   {current.recovery_mode}")

    pipeline.shutdown()
    print("=" * 56)
    print("Done. Next: `telos status`, or read TELOS_V7.md for the architecture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
