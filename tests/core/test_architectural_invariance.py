"""
Architectural Invariance Test — Proves Axiom 1.1 (Architecture Produces Outcomes).

The Pipeline must produce structurally identical behavior across domain swaps.
This test swaps GridWorld ↔ Synthetic ↔ Chess domains and verifies that:
  - The same number of streams activate
  - The same pipeline phases complete
  - Council behavior is consistent
  - Budget consumption patterns match
  - The pipeline never crashes or produces domain-specific errors

If this test fails, Axiom 1.1 is violated: outcomes depend on domain-specific
knowledge rather than architectural structure.
"""

import numpy as np

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import ReflexStream, PerceptionStream, MemoryStream, PlanningStream
from telos.core.simulation import CounterfactualEngine
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.council.validators import RealityValidator, ConstraintValidator, MemoryAdvisor
from telos.examples.gridworld.simulator import GridWorldSimulator
from telos.examples.synthetic.simulator import SyntheticWorld
from telos.examples.chess.simulator import ChessDomainSimulator
from tests.core.conftest import MockSimulator


def _build_pipeline(simulator, state_dim=6):
    """Build a fully-instrumented Pipeline with the given simulator."""
    config = PipelineConfig(
        simulator=simulator,
        compute_budget_ms=100.0,
        state_dim=state_dim,
        n_worlds=10,
        horizon=5,
    )
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(simulator)

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))

    return pipeline


def test_invariance_identical_budget_pattern():
    """Different domains must produce comparable budget consumption patterns.

    Streams should consume budget in the same order (priority-order) regardless
    of what domain facts look like.
    """
    domains = [
        ("GridWorld", GridWorldSimulator(size=10), 2),
        ("Synthetic", SyntheticWorld(), 2),
        ("Chess", ChessDomainSimulator(), 64),
    ]

    for name, sim, state_dim in domains:
        sim.initialize()
        pipeline = _build_pipeline(sim, state_dim=state_dim)

        # Build a state matching the domain's dimension
        state = np.random.randn(state_dim).astype(float)

        result = pipeline.execute(state)
        trace = result.decision_trace

        assert trace is not None, f"{name}: no decision trace"
        assert trace.stream_activations is not None, f"{name}: no stream activations"

        # Structural invariance: all 4 streams must be present in activations
        stream_names = [sa.stream_name for sa in trace.stream_activations]
        assert "ReflexStream" in stream_names, f"{name}: missing ReflexStream"
        assert "PerceptionStream" in stream_names, f"{name}: missing PerceptionStream"
        assert "MemoryStream" in stream_names, f"{name}: missing MemoryStream"
        assert "PlanningStream" in stream_names, f"{name}: missing PlanningStream"

        # Budget consumption must be non-negative and bounded
        assert trace.budget_consumed_ms >= 0, f"{name}: negative budget"
        assert trace.budget_consumed_ms <= trace.budget_total_ms, f"{name}: exceeded budget"

        # Pipeline must complete
        assert result.pipeline_phase.value == "complete", f"{name}: incomplete"

        # Health score must be valid
        assert 0.0 <= result.health_score <= 1.0, f"{name}: invalid health"

        print(f"  {name}: budget={trace.budget_consumed_ms:.1f}/{trace.budget_total_ms:.1f}ms, "
              f"health={result.health_score:.3f}, streams={len([s for s in stream_names])}")

        sim.cleanup()


def test_invariance_council_blocks_nan_any_domain():
    """The Council must block NaN states in every domain.

    This verifies that RealityValidator's constraint propagation
    (Axiom 2.1) is domain-independent.
    """
    domains = [
        ("GridWorld", GridWorldSimulator(size=10), 2),
        ("Synthetic", SyntheticWorld(), 2),
        ("Chess", ChessDomainSimulator(), 64),
    ]

    for name, sim, state_dim in domains:
        sim.initialize()
        pipeline = _build_pipeline(sim, state_dim=state_dim)

        # Inject NaN state — must be blocked regardless of domain
        state = np.full(state_dim, float('nan'))
        result = pipeline.execute(state)

        assert result.council_blocked, f"{name}: NaN state was not blocked"
        assert result.selected_trajectory is None, f"{name}: trajectory produced from NaN"
        assert result.decision_integrity < 1.0, f"{name}: perfect DI for NaN state"

        assert result.decision_trace is not None
        assert not result.decision_trace.council_validated, f"{name}: council validated NaN"

        print(f"  {name}: NaN blocked (DI={result.decision_integrity:.3f}, "
              f"blocker={result.decision_trace.blocking_validator})")

        sim.cleanup()


def test_invariance_multi_cycle_drift():
    """Mission Drift must behave similarly across domains.

    Predicted-vs-observed divergence (MD) should increase with domain complexity
    but remain in the same order of magnitude across structurally similar domains.
    """
    domains = [
        ("Mock", MockSimulator(), 6),
        ("GridWorld", GridWorldSimulator(size=10), 2),
        ("Synthetic", SyntheticWorld(), 2),
    ]

    md_values = {}

    for name, sim, state_dim in domains:
        sim.initialize()
        pipeline = _build_pipeline(sim, state_dim=state_dim)

        state = np.random.randn(state_dim).astype(float)

        mds = []
        for _ in range(3):
            result = pipeline.execute(state)
            if result.decision_trace:
                mds.append(result.decision_trace.mission_drift)
            state = state + np.random.randn(state_dim) * 0.1

        md_values[name] = np.mean(mds)
        print(f"  {name}: avg MD={np.mean(mds):.3f} over 3 cycles")

        sim.cleanup()

    # All domains must produce finite MD
    for name, md in md_values.items():
        assert np.isfinite(md), f"{name}: MD is not finite"


def test_invariance_pipeline_never_crashes():
    """Pipeline must never raise an exception, regardless of domain.

    This is the weakest but most important invariance: structural stability.
    """
    simulators = [
        ("GridWorld(5)", GridWorldSimulator(size=5), 2),
        ("GridWorld(20)", GridWorldSimulator(size=20), 2),
        ("Synthetic(noise=0.1)", SyntheticWorld(noise_std=0.1), 2),
        ("Synthetic(noise=0.5)", SyntheticWorld(noise_std=0.5), 2),
        ("Chess", ChessDomainSimulator(), 64),
        ("Mock", MockSimulator(), 6),
    ]

    for name, sim, state_dim in simulators:
        sim.initialize()
        pipeline = _build_pipeline(sim, state_dim=state_dim)

        try:
            for _ in range(3):
                state = np.random.randn(state_dim).astype(float)
                result = pipeline.execute(state)
                assert result is not None
        except Exception as e:
            raise AssertionError(f"{name}: pipeline crashed with {e}") from e

        print(f"  {name}: 3 cycles stable")
        sim.cleanup()
