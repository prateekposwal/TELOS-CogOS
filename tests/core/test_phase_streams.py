"""
StreamPhase (core/phases/streams.py) — direct unit coverage.

This phase executes the cognitive streams, applies the attention auction, and
records StreamActivations. These tests drive it with a minimal fake pipeline so
the phase's own branching (skip threshold, None-intent, plan shortcut) is
covered directly rather than only through a full pipeline run.
"""
from types import SimpleNamespace

import numpy as np

from telos.core.attention.resource_budget import BudgetManager
from telos.core.phases.base import PhaseContext
from telos.core.phases.streams import StreamPhase
from telos.intent_ir import IntentIR


class _BaseStream:
    priority = 1.0
    estimated_cost_ms = 1.0

    def __init__(self, intent):
        self._intent = intent

    def process(self, world):
        return self._intent


class ReflexStream(_BaseStream):
    priority = 1.0


class PerceptionStream(_BaseStream):
    priority = 0.9


class PlanningStream(_BaseStream):
    priority = 0.5


class _Config(SimpleNamespace):
    stream_skip_threshold = 0.0
    parallel_streams = False
    memory_fast_path_enabled = False
    fidelity_fast_path_enabled = False
    state_dim = 2


class _Pipeline:
    def __init__(self, streams, config):
        self.streams = streams
        self.config = config
        self.budget_manager = BudgetManager(total_budget_ms=1000.0)
        self._trust_manager = SimpleNamespace(authorize_stream=lambda name: True)
        self.planning_horizon = SimpleNamespace(has_plan=False, get_next_step=lambda: None)
        self.readiness_engine = SimpleNamespace(emit_signal=lambda *a, **k: None)
        self.pattern_library = SimpleNamespace(record=lambda **k: None)
        self.ledger = SimpleNamespace(enrich=lambda world, *a, **k: world)
        self._infra_manager = None
        self._tripartite_u = None
        self._reality_gap_tracker = None


def _ctx():
    ctx = PhaseContext(cycle_count=1, state=np.zeros(2), user_name="t")
    ctx.world = SimpleNamespace(metadata={})
    ctx.effective_n_worlds = 8
    ctx.effective_horizon = 3
    return ctx


def _intent(kind="reflex_avoid", conf=0.8):
    return IntentIR(intent_type=kind, confidence=conf)


def test_execute_activates_streams_and_records_intents():
    streams = [ReflexStream(_intent()), PerceptionStream(_intent("perception_update"))]
    pipeline = _Pipeline(streams, _Config())
    ctx = _ctx()
    StreamPhase().execute(pipeline, ctx)

    activated = [a for a in ctx.stream_activations if a.activated]
    assert len(activated) == 2
    assert len(ctx.intents) == 2
    # weighted score = priority * confidence * influence
    types = {i.intent_type for i, _ in ctx.intents}
    assert types == {"reflex_avoid", "perception_update"}
    # PSDT partials were recorded for each activated stream.
    assert len(ctx.psdt.partials) == 2


def test_none_intent_stream_is_recorded_inactive():
    streams = [ReflexStream(None)]
    pipeline = _Pipeline(streams, _Config())
    ctx = _ctx()
    StreamPhase().execute(pipeline, ctx)
    assert len(ctx.stream_activations) == 1
    assert ctx.stream_activations[0].activated is False
    assert ctx.intents == []


def test_high_skip_threshold_skips_all_streams():
    cfg = _Config()
    cfg.stream_skip_threshold = 2.0  # influence (1.0) can never clear this
    pipeline = _Pipeline([ReflexStream(_intent())], cfg)
    ctx = _ctx()
    StreamPhase().execute(pipeline, ctx)
    assert all(not a.activated for a in ctx.stream_activations)
    assert ctx.intents == []


def test_plan_shortcut_injects_planned_intent_and_skips_planner():
    plan_intent = _intent("plan_trajectory", 0.7)
    pipeline = _Pipeline([PlanningStream(_intent("reflex_avoid"))], _Config())
    pipeline.planning_horizon = SimpleNamespace(
        has_plan=True, get_next_step=lambda: plan_intent)
    ctx = _ctx()
    StreamPhase().execute(pipeline, ctx)
    # The planned intent is injected with weight 1.0; the PlanningStream is skipped.
    assert (plan_intent, 1.0) in ctx.intents
    assert all(a.stream_name != "PlanningStream" or not a.activated
               for a in ctx.stream_activations)
