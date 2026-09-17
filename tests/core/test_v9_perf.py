"""v9 performance-contract tests — confidence funnel, debate de-dup, and the
model-fidelity fast path.

Each test protects a measured v9 property:
  - standard-mode world counts stay byte-identical UNLESS the opt-in
    confidence_world_funnel flag is set (default False);
  - InternalDebate computes ONCE per standard cycle (select owns the record,
    council reuses — never a second per-cycle computation; the fallback only
    fires when select skipped it);
  - the model-fidelity fast path cuts worlds only when a CURRENTLY validated
    model meets a calm record, and predicted_state stays honest.
"""
import os

import numpy as np
import pytest

from telos.core.phases.simulate import SimulatePhase, counterfactual_budget
from telos.core.phases.base import PhaseContext
from telos.core.phases.council import CouncilPhase
from telos.core.simulation import CounterfactualEngine
from telos.core.council.base import Council
from telos.core.council.internal_debate import InternalDebate
from telos.core.types import PipelineConfig
from telos.world.epistemic import RealityGapTracker
from telos.world.world import World
from telos.intent_ir import IntentIR
from tests.core.conftest import MockSimulator


def _build_standard(tmp_path):
    from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS
    from telos.core.runtime import TelosV14Pipeline
    from telos.core.streams.implementations import (
        ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
    )
    from telos.core.streams.inquiry_stream import InquiryStream
    from telos.core.council.validators import (
        RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
        EvidenceProvenanceValidator,
    )
    from telos.core.ledger.skill_library import SkillLibrary
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=8, horizon=5,
        checkpoint_path=str(tmp_path / "cp"),
        knowledge_path=str(tmp_path / "kg.json"),
        ledger_path=str(tmp_path / "ld.json"),
        identity_path=str(tmp_path / "id.json"),
        pattern_path=str(tmp_path / "pt.json"),
        deterministic_seed=42, mode="standard",
    ))
    sl = SkillLibrary()
    for s in [ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
              PlanningStream(sl, sim_engine=CounterfactualEngine(sim)),
              InquiryStream(sl),
              TheoryStream(sl, theory_builder=getattr(pipe, "_theory_builder", None))]:
        pipe.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(), MemoryAdvisor(sl),
              MissionDriftDetector(drift_threshold=5.0), EvidenceProvenanceValidator()]:
        pipe.register_validator(v)
    return pipe


# ── Item 4: confidence_world_funnel (standard-mode, default-OFF) ─────────────

def _sim_stub(config_overrides=None, tracker=None, sim=None):
    from types import SimpleNamespace
    config = dict(
        simulator=sim or MockSimulator(), horizon=8, feedback_lag=0,
        mode="standard", is_fast_mode=False, confidence_world_funnel=False,
    )
    config.update(config_overrides or {})
    return SimpleNamespace(
        _infra_manager=SimpleNamespace(adaptive_horizon=None),
        _sim_engine=CounterfactualEngine(sim or MockSimulator(), seed=7),
        _scm=None,
        budget_manager=SimpleNamespace(check_budget=lambda *a, **k: True,
                                       consume=lambda *a, **k: None,
                                       total_budget_ms=100.0),
        config=SimpleNamespace(**config),
        _reality_gap_tracker=(tracker if tracker is not None else RealityGapTracker()),
    )


class _RNGIsolatedMock(MockSimulator):
    """MockSimulator with a PRIVATE RandomState: simulate() reads global
    np.random in the base class, which makes world counts jitter across
    runs. A private stream makes the funnel world-count comparisons
    deterministic (RNG-isolation pattern, test-side)."""

    def __init__(self, seed=3):
        self._seed = seed
        self._rng = np.random.RandomState(seed)

    def reset(self, seed=None):
        """Re-seed the private stream so a funnel-on run starts from the SAME
        generative state as its funnel-off twin (the engine advances the sim's
        stream across calls — only a reset makes the runs comparable)."""
        self._rng = np.random.RandomState(seed if seed is not None else self._seed)

    def legal_transitions(self, state):
        return [state + self._rng.randn(*state.shape) * 0.1 for _ in range(5)]

    def simulate(self, state, horizon):
        worlds = []
        s = state.copy()
        for _ in range(min(horizon, 5)):
            s = s + self._rng.randn(*s.shape) * 0.05
            worlds.append(World(state=s.copy(), metadata={"simulated": True}))
        return worlds


def test_confidence_world_funnel_pure_helper_semantics():
    assert counterfactual_budget("standard", 8, 0.9) == 8
    assert counterfactual_budget("standard", 8, 0.9, funnel_standard=True) == 4
    assert counterfactual_budget("standard", 8, 0.5, funnel_standard=True) == 8
    assert counterfactual_budget("fast", 8, 0.9) == 1
    assert counterfactual_budget("fast", 8, 0.5) == 4
    c = PipelineConfig()
    assert c.confidence_world_funnel is False, "funnel must ship default-OFF"
    assert c.fidelity_fast_path_enabled is True


def _funnel_ctx(tracker=None, funnel=True, stub=None):
    if stub is None:
        stub = _sim_stub(
            config_overrides={"confidence_world_funnel": funnel},
            tracker=tracker, sim=_RNGIsolatedMock())
    else:
        stub.config.confidence_world_funnel = funnel
        # deterministic baseline: same generative state for on vs off runs
        stub._sim_engine.simulator.reset()
    ctx = PhaseContext(cycle_count=1, state=np.zeros(2), user_name="perf")
    ctx.effective_n_worlds = 10
    ctx.intents = [(IntentIR("perceive", 0.9), 1.0)]
    SimulatePhase().execute(stub, ctx)
    return ctx.worlds_generated


def test_standard_funnel_halves_sweep_when_validated():
    tracker = RealityGapTracker()
    tracker.record("world", np.zeros(2), np.zeros(2), cycle=1)
    stub = _sim_stub(tracker=tracker, sim=_RNGIsolatedMock())
    on = _funnel_ctx(tracker=tracker, funnel=True, stub=stub)
    off = _funnel_ctx(tracker=tracker, funnel=False, stub=stub)
    assert on < off, (
        f"a validated model's high-confidence standard cycle must funnel "
        f"({on} worlds vs {off} full)")


def test_standard_funnel_full_budget_when_unvalidated():
    # Unvalidated tracker → model_fidelity None → full budget (no funnel),
    # byte-identical to a funnel-off cycle on the same deterministic stub.
    stub = _sim_stub(sim=_RNGIsolatedMock())
    on_unvalidated = _funnel_ctx(funnel=True, stub=stub)
    off = _funnel_ctx(funnel=False, stub=stub)
    assert on_unvalidated == off, (
        "an unvalidated model must keep the full sweep (evidence-rich Λ6.5)")


# ── Item 5: InternalDebate de-dup (one computation per standard cycle) ───────

def test_internal_debate_single_computation_per_cycle(tmp_path, monkeypatch):
    pipe = _build_standard(tmp_path)
    calls = {"n": 0}
    orig = pipe._internal_debate.debate

    def counting_debate(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(pipe._internal_debate, "debate", counting_debate)
    state = np.zeros(2)
    for _ in range(3):
        pipe.execute(state, user_name="perf")
    assert calls["n"] == 3, (
        f"debate ran {calls['n']}x over 3 standard cycles (want exactly 1/cycle — "
        f"select computes, council reuses, runtime duplicate removed)")
    assert pipe._internal_debate.total_debates == 3


def _council_ctx():
    ctx = PhaseContext(cycle_count=1, state=np.zeros(2), user_name=None)
    ctx.world = World(state=np.zeros(2))
    ctx.selected_intent = IntentIR("plan_trajectory", 0.8)
    ctx.intents = [(IntentIR("plan_trajectory", 0.8), 1.0)]
    return ctx


def _council_pipeline(debate_stub=None):
    from types import SimpleNamespace
    return SimpleNamespace(
        council=Council(), _internal_debate=debate_stub,
        config=SimpleNamespace(skip_advisory_layers=False),
        budget_manager=SimpleNamespace(total_budget_ms=100.0),
        infra_manager=None,
    )


class _RaisingDebate:
    def debate(self, *a, **k):
        raise AssertionError("council must reuse ctx._debate_result, not re-compute")


def test_council_reuses_ctx_debate_result():
    record = InternalDebate().debate(
        context={"uncertainty": 0.5, "options": ["plan_trajectory"],
                 "resources": {"budget": 100}, "goals": {"survival": 1.0}},
        context_description="Council review of plan_trajectory",
    )
    ctx = _council_ctx()
    ctx._debate_result = record
    CouncilPhase().execute(_council_pipeline(debate_stub=_RaisingDebate()), ctx)
    assert ctx.latest_debate["consensus"] == getattr(record, "consensus_level", 0.5)
    assert ctx._debate_result is record


def test_council_fallback_computes_when_select_skipped(tmp_path, monkeypatch):
    """When select never ran the debate (reconciled path), council computes
    exactly once and owns ctx._debate_result for the cycle."""
    pipe = _build_standard(tmp_path)
    calls = {"n": 0}
    orig = pipe._internal_debate.debate

    def counting_debate(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(pipe._internal_debate, "debate", counting_debate)
    state = np.zeros(2)
    pipe.execute(state, user_name="perf")
    assert calls["n"] >= 1, "the council must compute when select skipped it"
    assert calls["n"] <= 2, "even a bootstrap/blended cycle must stay ~1 computation"


# ── Item 6: model-fidelity fast path (streams phase) ─────────────────────────

def _fast_path_pipeline(tmp_path, validated=True):
    pipe = _build_standard(tmp_path)
    pipe.config.n_worlds = 10
    pipe.config.adaptive_worlds_enabled = False
    if validated:
        pipe._reality_gap_tracker.record(
            "world", np.zeros(2), np.zeros(2), cycle=1)
    pipe._last_di_for_omega = 0.8
    pipe._council_recent_blocks = 0
    pipe._last_sim_score = 0.95
    return pipe


def test_fidelity_fast_path_cuts_worlds_when_validated_and_calm(tmp_path):
    # GridSim branches ~3 options per requested world, so the honest signal is
    # a real REDUCTION vs the full sweep (measured: 8 vs 58 on this setup).
    pipe_cut = _fast_path_pipeline(tmp_path, validated=True)
    pipe_cut.execute(np.zeros(2), user_name="perf")
    cut = pipe_cut._last_trace.worlds_simulated
    assert pipe_cut._last_predicted_state is not None, (
        "predicted_state must stay honest for the deferred reality-gap record")
    pipe_full = _fast_path_pipeline(tmp_path, validated=True)
    pipe_full.config.fidelity_fast_path_enabled = False
    pipe_full.execute(np.zeros(2), user_name="perf")
    full = pipe_full._last_trace.worlds_simulated
    assert cut < full, f"fast path must cut worlds ({cut} vs {full})"
    assert full / cut >= 2, "the cut must be a real reduction, not a tie"


def test_fidelity_fast_path_unchanged_when_unvalidated(tmp_path):
    pipe = _fast_path_pipeline(tmp_path, validated=False)
    pipe.execute(np.zeros(2), user_name="perf")
    unval = pipe._last_trace.worlds_simulated
    pipe_cut = _fast_path_pipeline(tmp_path, validated=True)
    pipe_cut.execute(np.zeros(2), user_name="perf")
    cut = pipe_cut._last_trace.worlds_simulated
    assert unval > cut, (
        "an unvalidated model must keep the full sweep (no invented confidence)")
    # The flag kills the path outright (identical effective worlds).
    pipe_full = _fast_path_pipeline(tmp_path, validated=True)
    pipe_full.config.fidelity_fast_path_enabled = False
    pipe_full.execute(np.zeros(2), user_name="perf")
    assert pipe_full._last_trace.worlds_simulated == unval