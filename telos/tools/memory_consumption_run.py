#!/usr/bin/env python3
"""
Memory consumption — measure SUSTAINED decision-memory use on a real pipeline.

PATTERN (evidence must span the behaviour it claims): the capability scorecard's
final memory point previously rested on a 4-cycle artifact produced incidentally
by a test. That proves the path RUNS once, not that memory works over time. This
tool drives a REAL pipeline through many cycles and writes the artifact with its
own provenance and observed span, so the scorecard can require a real duration.

Unlike a test, this is a measurement run: it reports the recalled/stored counts,
the tier distribution, storage growth vs evictions (the bounded-growth check),
and the rejected-suppression count.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/memory_consumption_run.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/memory_consumption_run.py --cycles 200 --ci
"""

import argparse
import json
import os
import sys
from typing import Any, Dict

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.cli import _build_gridworld_pipeline  # noqa: E402
from telos.core.runtime import MEMORY_CONSUMPTION_MIN_CYCLES  # noqa: E402

ARTIFACT = os.path.join(PROJECT, "telos", "audit", "memory_consumption.json")


def run(cycles: int = 120, checkpoint_dir: str = "/tmp/telos_mem_run") -> Dict[str, Any]:
    """Run a real pipeline for N cycles and measure memory consumption.

    Args:
        cycles: number of pipeline cycles to execute.
        checkpoint_dir: isolated state dir for the run.

    Returns:
        The consumption artifact payload that was written.
    """
    import numpy as np

    os.makedirs(checkpoint_dir, exist_ok=True)
    # Opt in to writing the runtime's own artifact (normally gated so tests and
    # short CLI runs cannot clobber the measured evidence).
    os.environ["TELOS_WRITE_MEMORY_ARTIFACT"] = "1"
    pipeline = _build_gridworld_pipeline(checkpoint_dir=checkpoint_dir)
    state = np.array([0.0, 0.0])
    for _ in range(cycles):
        result = pipeline.execute(state, user_name="memory_run")
        trace = getattr(pipeline, "_last_trace", None)
        selected = getattr(trace, "selected_action", None) if trace else None
        if selected is not None:
            try:
                nxt = pipeline.config.simulator.transition(state, selected)
                if 0.0 <= float(nxt[0]) <= 4.0 and 0.0 <= float(nxt[1]) <= 4.0:
                    state = nxt
            except Exception:
                pass

    report = pipeline.memory_report()
    payload = {
        "source": "memory_consumption_run",
        "cycles": cycles,
        "cycles_observed": cycles,
        "memory_consumed": report.get("memory_consumed", 0),
        "inserted": report.get("inserted", 0),
        "rejected_governance_suppression": report.get(
            "rejected_governance_suppression", 0),
        "tiered": {
            key: report.get(key, 0)
            for key in ("hot", "warm", "cold", "total", "evicted", "summarized")
        },
        "consumed_in_real_cycles": bool(
            report.get("memory_consumed", 0) > 0
            and report.get("inserted", 0) > 0
            and cycles >= MEMORY_CONSUMPTION_MIN_CYCLES
        ),
        "min_cycles_required": MEMORY_CONSUMPTION_MIN_CYCLES,
    }
    # The pipeline's own shutdown artifact is written separately; this run's
    # measurement is the authoritative sustained observation.
    pipeline.shutdown()
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    with open(ARTIFACT, "w") as f:
        json.dump(payload, f, indent=2)
    return payload


def print_report(payload: Dict[str, Any]) -> bool:
    """Print the sustained-consumption measurement.

    Args:
        payload: the artifact payload.

    Returns:
        True when consumption is sustained and growth is bounded.
    """
    tiered = payload["tiered"]
    total = tiered.get("total", 0)
    print(f"\n{'TELOS Sustained Memory Consumption':^72}")
    print("=" * 72)
    print(f"  source:           {payload['source']}")
    print(f"  cycles observed:  {payload['cycles_observed']} "
          f"(min {payload['min_cycles_required']})")
    print(f"  recalled:         {payload['memory_consumed']}")
    print(f"  stored:           {payload['inserted']}")
    print(f"  rejected (gov):   {payload['rejected_governance_suppression']}")
    print(f"  tiers:            hot={tiered.get('hot')} warm={tiered.get('warm')} "
          f"cold={tiered.get('cold')} total={total}")
    print(f"  evicted:          {tiered.get('evicted')} "
          f"summarized={tiered.get('summarized')}")
    print("=" * 72)
    span_ok = payload["cycles_observed"] >= payload["min_cycles_required"]
    recalled_ok = payload["memory_consumed"] > 0
    stored_ok = payload["inserted"] > 0
    bounded = total <= 320  # hot 16 + warm 48 + cold 256
    ok = span_ok and recalled_ok and stored_ok and bounded \
        and payload["consumed_in_real_cycles"]
    print(f"  span>={payload['min_cycles_required']}: {span_ok} | "
          f"recalled>0: {recalled_ok} | stored>0: {stored_ok} | "
          f"bounded(<=320): {bounded}")
    print("MEMORY CONSUMPTION:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=120,
                    help="pipeline cycles to run (default 120)")
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless consumption is sustained and bounded")
    args = ap.parse_args()
    result = run(cycles=max(1, args.cycles))
    ok = print_report(result)
    if args.ci:
        sys.exit(0 if ok else 1)
