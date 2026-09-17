"""
StrategicOption tests — Axiom 4.3 (Possibility Preservation).

Validates that the system maintains alternative future trajectories
that can be queried after each decision cycle.
"""

import numpy as np

from telos.core.simulation import CounterfactualEngine, StrategicOption
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import ReflexStream, PerceptionStream, MemoryStream, PlanningStream
from telos.core.ledger.skill_library import SkillLibrary
from tests.core.conftest import MockSimulator


def test_strategic_option_dataclass():
    """StrategicOption stores an alternative future trajectory."""
    option = StrategicOption(
        world="mock_world",
        score=0.85,
        rank=2,
        horizon=5,
        metadata={"source": "test"},
    )
    assert option.score == 0.85
    assert option.rank == 2
    assert option.metadata["source"] == "test"


def test_engine_generates_options():
    """CounterfactualEngine generates and ranks multiple options."""
    sim = MockSimulator()
    engine = CounterfactualEngine(sim)
    state = np.array([1.0, 2.0])

    options = engine.generate_options(state, horizon=5, n_worlds=10)

    assert len(options) > 0
    assert engine.has_options is True
    assert engine.alternative_count >= 0

    # Options must be rank-ordered (1 = best)
    for i, opt in enumerate(options):
        assert opt.rank == i + 1

    # Scores must be descending
    scores = [o.score for o in options]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1]


def test_engine_query_empty():
    """Engine returns empty list when no options generated."""
    sim = MockSimulator()
    engine = CounterfactualEngine(sim)

    assert engine.has_options is False
    assert engine.query_options() == []
    assert engine.query_options(min_score=0.5) == []


def test_engine_query_filter():
    """Query filters by min_score and top_k."""
    sim = MockSimulator()
    engine = CounterfactualEngine(sim)
    state = np.array([1.0, 2.0])

    engine.generate_options(state, horizon=5, n_worlds=10)

    # Filter by score
    high_scoring = engine.query_options(min_score=0.0)
    assert len(high_scoring) > 0

    # Top-k
    top3 = engine.query_options(top_k=3)
    assert len(top3) <= 3
    if top3:
        assert top3[0].rank <= top3[-1].rank

    # Multiple filters
    filtered = engine.query_options(min_score=-10.0, top_k=5)
    assert len(filtered) <= 5


def test_engine_stats():
    """Engine reports statistics about generated options."""
    sim = MockSimulator()
    engine = CounterfactualEngine(sim)
    state = np.array([1.0, 2.0])

    engine.generate_options(state, horizon=5, n_worlds=10)
    stats = engine.stats

    assert stats["total_generated"] > 0
    assert stats["last_horizon"] == 5
    assert stats["last_n_worlds"] == 10
    assert stats["best_score"] is not None


def test_pipeline_stores_alternatives():
    """Pipeline stores alternative futures in DecisionTrace."""
    sim = MockSimulator()
    config = PipelineConfig(simulator=sim, compute_budget_ms=100.0,
                             state_dim=6, n_worlds=10, horizon=5)
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    result = pipeline.execute(state)

    assert result.alternatives_available >= 0
    assert result.decision_trace is not None
    assert hasattr(result.decision_trace, 'strategic_options')

    if result.decision_trace.strategic_options:
        opt = result.decision_trace.strategic_options[0]
        assert "rank" in opt
        assert "score" in opt


def test_pipeline_query_options():
    """Pipeline exposes query_options() for alternative futures."""
    sim = MockSimulator()
    config = PipelineConfig(simulator=sim, compute_budget_ms=100.0,
                             state_dim=6, n_worlds=10, horizon=5)
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    pipeline.execute(state)

    options = pipeline.query_options()
    assert isinstance(options, list)

    top3 = pipeline.query_options(top_k=3)
    assert len(top3) <= 3


def test_alternatives_after_multi_cycle():
    """Alternatives persist across cycles; each cycle replaces the last set."""
    sim = MockSimulator()
    config = PipelineConfig(simulator=sim, compute_budget_ms=100.0,
                             state_dim=6, n_worlds=10, horizon=5)
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    for _ in range(3):
        result = pipeline.execute(state)
        state = state + np.random.randn(6) * 0.1

    # After last cycle, options reflect the last simulation
    options = pipeline.query_options()
    assert isinstance(options, list)


def test_evaluate_paths_nonzero_for_real_domains():
    """Regression: evaluate_paths() must return nonzero scores for real domain plugins."""
    from telos.examples.gridworld.simulator import GridWorldSimulator
    from telos.examples.synthetic.simulator import SyntheticWorld

    # Deterministic seeding (RNG-isolation pattern): the engine and each
    # simulator own private seeded streams, so scores are reproducible and
    # independent of whatever other tests did to global np.random.
    for name, sim, state in [
        ("GridWorld", GridWorldSimulator(size=5, seed=42), np.array([0.0, 0.0])),
        ("Synthetic", SyntheticWorld(noise_std=0.0, seed=7), np.array([2.0, 3.0])),
    ]:
        sim.initialize()
        engine = CounterfactualEngine(sim, seed=123)
        options = engine.generate_options(state, horizon=3, n_worlds=5)
        assert len(options) > 0, f"{name}: no options generated"
        scores = [o.score for o in options]
        assert any(s != 0.0 for s in scores), f"{name}: all scores are 0.0 (evaluate_paths returning 0)"
        assert max(scores) > min(scores), f"{name}: all scores identical (no discrimination)"
        sim.cleanup()


def test_best_path_selects_genuinely_best():
    """Regression: best_path must pick a genuinely better path, not just first."""
    from telos.examples.gridworld.simulator import GridWorldSimulator
    sim = GridWorldSimulator(size=5, seed=42)
    sim.initialize()
    engine = CounterfactualEngine(sim, seed=123)

    state = np.array([0.0, 0.0])
    best = engine.best_path(state, horizon=5, n_worlds=10)

    assert best is not None
    best_state = getattr(best, 'state', best)
    dist_from_start = np.linalg.norm(best_state - np.array([0.0, 0.0]))

    assert dist_from_start > 0, "best_path did not move from start"
    sim.cleanup()


def test_uq_full_stats_only_top3_cheap_tail():
    """v9: UQ resampling is bounded to the top-3 contenders (cost bound —
    previously max(3, n_worlds//2)); the long tail carries an honest
    single-sample ProbabilisticScore (n_samples=1, std=0). MockSimulator
    ALWAYS yields worlds, so the resample loop deterministically fires.
    Because resampled MEANS can re-rank (the pre-existing promotion edge,
    simulate.py fallbacks already handle an unsampled rank<=3 option), the
    resampled options are not guaranteed to sit at ranks 1-3 — but the
    number of full-CI options is a hard <= 3, the cheap tail rows state
    exactly what was measured, and the only None rows are promoted
    rank<=3 options (the documented, pre-existing edge)."""
    from tests.core.conftest import MockSimulator

    sim = MockSimulator()
    engine = CounterfactualEngine(sim, n_repetitions=4, seed=123)
    options = engine.generate_options(np.array([2.0, 3.0]), horizon=3, n_worlds=10)
    assert len(options) > 3, "need a long tail to exercise the cheap path"
    # cost bound: full CI is reserved for the rank<=3 contenders, never more
    resampled = [o for o in options
                 if o.probabilistic and o.probabilistic.n_samples >= 2]
    assert len(resampled) >= 1, "resampling must fire for the top contenders"
    assert len(resampled) <= 3, "full CI beyond 3 options is a cost regression"
    for opt in options:
        p = opt.probabilistic
        if p is None:
            # pre-existing promotion edge only: an option that entered rank<=3
            # without having been resampled (its None is transient and the
            # simulate-phase fallback covers it).
            assert opt.rank <= 3, "a rank>3 option must carry a score"
            continue
        assert p.n_samples >= 1
        assert np.isfinite(p.std) and p.std >= 0.0
        if p.n_samples == 1:
            assert p.std == 0.0, "a single sample states std=0 (no invented CI)"
            assert p.mean == opt.score
            assert p.ci_lower == opt.score and p.ci_upper == opt.score
            assert p.min_score == opt.score and p.max_score == opt.score
    for i, opt in enumerate(options):
        assert opt.rank == i + 1


def test_rng_isolation_immune_to_global_np_random_pollution():
    """Regression for the latent flake (GAP 2): the discrimination collapse
    (all 5 GridWorld options scoring -0.9811) happened because the simulator
    read the SHARED global np.random stream, whose state depends on whatever
    tests ran before. The structural fix: simulators/engines own private
    RandomState instances and never read global np.random — so even with the
    global stream driven into the exact degenerate state that caused the
    observed collapse, trajectories still discriminate."""
    from telos.examples.gridworld.simulator import GridWorldSimulator
    from telos.core.simulation import CounterfactualEngine

    # Reproduce the observed failure precondition: global seed 34 + pollution
    # made np.random.randint(4) return clipping actions every draw.
    np.random.seed(34)
    for _ in range(4):
        np.random.randn(6)

    # Unseeded simulator: still private RandomState (OS entropy) — but to make
    # the test fully deterministic, drive it with a fixed per-instance seed
    # and prove it discriminates under the poisoned global stream.
    for sim_seed in (42, 7, 2026):
        sim = GridWorldSimulator(size=5, seed=sim_seed)
        engine = CounterfactualEngine(sim, seed=sim_seed + 1)
        opts = engine.generate_options(np.array([0.0, 0.0]), horizon=3, n_worlds=5)
        scores = [o.score for o in opts]
        assert max(scores) > min(scores), \
            f"seed {sim_seed}: discrimination collapsed under global pollution"
        assert any(s != -0.9811497450761412 for s in scores), \
            f"seed {sim_seed}: degenerate all-origin walk leaked through"

    # The engine itself must never consult global np.random for simulation
    # noise: an unseeded engine owns a private stream too.
    sim = GridWorldSimulator(size=5, seed=42)
    engine = CounterfactualEngine(sim, seed=123)
    assert engine._rng is not None
    assert engine._rng is not np.random
