"""CLI command to verify counterfactual determinism.

Run via: python3 -m telos.determinism_check
"""
from __future__ import annotations

import argparse
import json
import numpy as np
import sys
import os

# Add repo root to path so we can import telos packages
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telos.core.simulation.engine import CounterfactualEngine, DeterministicCounterfactualEngine
from telos.core.simulation.engine import DomainSimulator
from telos_task import GridSim


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify counterfactual determinism")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    parser.add_argument("--horizon", type=int, default=5, help="Simulation horizon")
    args = parser.parse_args()

    # Build a small GridSim
    sim = GridSim(blocked=set(), rewards={})
    engine = CounterfactualEngine(simulator=sim, n_repetitions=1, seed=args.seed)

    det = DeterministicCounterfactualEngine(engine)

    # Create a simple initial state (2D position on grid)
    initial_state = np.array([0.0, 0.0], dtype=float)  # (x, y) position

    result = det.run_two_from_same_seed(initial_state, horizon=args.horizon, rng_seed=args.seed)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
