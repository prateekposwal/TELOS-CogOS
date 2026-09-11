"""RNG isolation for GridSim.maybe_shift_terrain (audit Item #3).

GridSim is a PRODUCTION hot path: the dashboard producer calls
maybe_shift_terrain every cycle (producer.py:_run_cycle). It used the global
`random` module — shared mutable state whose sequence depends on whatever
imported it first (the exact flake class that collapsed GridWorld
discrimination before private RandomState isolation). Mirrors the existing
regression pattern (tests/core/test_strategic_options.py::
test_rng_isolation_immune_to_global_np_random_pollution): same seed ->
identical sequences, global poisoning does not perturb a sim, and the sim's
RNG is a private instance, never the global module.
"""

import random

import pytest

from telos_task import TERRAIN, DEFAULT_BLOCKED, DEFAULT_REWARDS, GridSim


def _baseline_terrain():
    return dict(TERRAIN)


def _run_shifts(seed, cycles):
    """Run `cycles` maybe_shift_terrain calls on a fresh seeded sim and
    return the (x, y, old -> new) change sequence. TERRAIN is module-level
    shared state that the sim mutates; snapshot/restore so each run starts
    from the same baseline and the test process never leaks terrain edits.
    """
    saved = _baseline_terrain()
    try:
        sim = GridSim(
            blocked=set(DEFAULT_BLOCKED),
            rewards=dict(DEFAULT_REWARDS),
            random_seed=seed,
        )
        out = []
        for _ in range(cycles):
            for change in sim.maybe_shift_terrain():
                out.append((change["x"], change["y"], change["old"], change["new"]))
        assert sim._rng is not random, "sim must own a private Random instance"
        return out
    finally:
        TERRAIN.clear()
        TERRAIN.update(saved)


def test_same_seed_identical_terrain_shift_sequences():
    """Two sims with the same seed must produce byte-identical terrain-shift
    sequences (determinism contract for the other engines' pattern)."""
    cycles = 24   # 8 terrain-shift events (every 3rd cycle) per sim
    a = _run_shifts(seed=42, cycles=cycles)
    b = _run_shifts(seed=42, cycles=cycles)
    assert a == b, "same-seed sims must agree on terrain shifts"
    assert a, "seeded sim must actually shift terrain within 24 cycles"


def test_global_random_poisoning_does_not_perturb_sim():
    """Poisoning the GLOBAL random module must not perturb a seeded sim's
    terrain sequence — its private Random is structurally isolated."""
    clean = _run_shifts(seed=7, cycles=24)
    # Poison + heavily consume the global stream (mirror of the np.random
    # poison fixture in the GridWorld regression).
    random.seed(12345)
    for _ in range(200):
        random.random()
    poisoned = _run_shifts(seed=7, cycles=24)
    assert poisoned == clean, "global random poison leaked into the sim"


def test_unseeded_sim_still_owns_private_rng():
    """An unseeded GridSim must still be isolated: a private OS-entropy
    Random instance, never the global module (the structural rule: each
    engine/sim owns a private stream; global = forbidden)."""
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    assert sim._rng is not None
    assert sim._rng is not random, "unseeded sim must not alias the global module"
    # A real private random.Random instance (the structural rule: the sim
    # owns a stream; the global module is shared mutable state it must
    # never read or write).
    assert type(sim._rng) is random.Random
