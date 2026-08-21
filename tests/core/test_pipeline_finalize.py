"""Tests for pipeline_finalize — post-cycle hooks: axiom verification,
v2 module wiring, and resource accounting."""

import logging
from types import SimpleNamespace

from telos.core.phases.base import PhaseContext
from telos.core.phases.base import StreamActivation
from telos.core.pipeline_finalize import (
    run_axiom_prover,
    run_v2_module_hooks,
    record_resource_accounting,
)
from telos.core.introspection.scheduler import IntrospectionTier


def make_ctx(cycle=3, verdict=None):
    ctx = PhaseContext(cycle_count=cycle, state=None, user_name=None)
    if verdict is not None:
        ctx.verdict = verdict
    return ctx


class FakeVerifier:
    def __init__(self, results=None, raise_on_verify=False):
        self.results = results if results is not None else {}
        self.raise_on_verify = raise_on_verify
        self.verify_kwargs = None

    def verify(self, trace, ctx, **kwargs):
        self.verify_kwargs = kwargs
        if self.raise_on_verify:
            raise RuntimeError("boom")
        return self.results


class _Recorder:
    def __init__(self):
        self.calls = []

    def record(self, *a, **kw):
        self.calls.append((a, kw))


class FakeIntrospection(_Recorder):
    def __init__(self, due=None):
        super().__init__()
        self.due = due if due is not None else []

    def get_due_tiers(self, cycle):
        self.record("get_due_tiers", cycle)
        return self.due

    def introspect(self, cycle):
        self.record("introspect", cycle)
        return []


class FakeTheoryBuilder:
    total_experiences = 3
    _theories = {"t1": object()}

    def __init__(self):
        self.calls = []

    def cluster(self):
        self.calls.append("cluster")

    def hypothesize(self):
        self.calls.append("hypothesize")

    def promote(self):
        self.calls.append("promote")


class FakeUUD(_Recorder):
    def record_observation(self, cycle, predictions, observations):
        self.calls.append(("record_observation", cycle, predictions, observations))

    def promote_to_questions(self, cycle):
        self.calls.append(("promote_to_questions", cycle))
        return []


class FakeEffects:
    exploration_modifier = 1.5


class FakeCognitiveEnergy(_Recorder):
    energy_ratio = 0.7

    def compute_difficulty(self, **kwargs):
        self.record("compute_difficulty", kwargs)
        return 0.9

    def consume(self, difficulty):
        self.record("consume", difficulty)
        return FakeEffects()


class FakeVerdict:
    def __init__(self, signals=None, validated=True):
        self.signals = signals if signals is not None else []
        self.validated = validated


class _FlatRecorder(_Recorder):
    def auto_examine(self, cycle):
        self.record("auto_examine", cycle)

    def record(self, name, value=None):
        self.calls.append(name)


class FakeCuriosityDrive(_Recorder):
    def set_compression(self, rate):
        self.calls.append(("set_compression", rate))


class FakeCognitiveMomentum(_Recorder):
    momentum = 0.4

    def recommend_unstick(self):
        self.calls.append(("recommend_unstick",))
        return {"action": "goal_seek_recovery"}


class FakeResearchSeasons(_Recorder):
    def get_phase(self, cycle):
        self.record("get_phase", cycle)
        return SimpleNamespace(value="growth")

    def exploration_bonus(self, cycle):
        self.record("exploration_bonus", cycle)
        return 0.25


class FakeDiscoveryRate(_Recorder):
    marginal_rate = 0.33

    def record(self, cycle, new_insights=0):
        self.calls.append(("record", cycle, new_insights))


class FakeEcosystem(_Recorder):
    def update_discovery_rate(self, *a):
        self.calls.append(("update_discovery_rate", a))

    def get_bridge_candidates(self):
        return []

    def cycle(self):
        self.calls.append(("cycle",))


class FakeModelCompetition(_Recorder):
    dominant_model = SimpleNamespace(name="m1")
    dominant_model_id = "m1"

    def record_prediction(self, model_id, correct):
        self.calls.append(("record_prediction", model_id, correct))


class FakeDiscoveryOrchestrator(_Recorder):
    def cycle(self, cycle, **kwargs):
        self.calls.append(("cycle", cycle, kwargs))
        return {"step": 1}


class FakeIdentityUtility(_Recorder):
    active_profile = SimpleNamespace(identity_markers=["truth", "safety"])

    def compute_utility(self, dimension_scores, identity_markers=None):
        self.calls.append(("compute_utility", dimension_scores, identity_markers))


class FakeInterpretation(_Recorder):
    def record_outcome(self, conflict_id="auto", outcome_quality=0.0):
        self.calls.append(("record_outcome", conflict_id, outcome_quality))


class FakeBenchmarkCollector(_Recorder):
    def collect(self, pipeline, trace, ctx):
        self.calls.append(("collect",))


class FakeBudgetManager:
    consumed_ms = 12.0
    total_budget_ms = 50.0


class FakeResourceAccounting(_Recorder):
    def set_cycle(self, cycle):
        self.calls.append(("set_cycle", cycle))

    def record_action(self, name, cost, metadata=None):
        self.calls.append(("record_action", name, cost, metadata))

    def record_stream_activation(self, stream_name, compute_ms):
        self.calls.append(("record_stream_activation", stream_name, compute_ms))

    def cycle_summary(self):
        return {"compute": 12.0}

    def check_budget(self, **kwargs):
        return {"within_budget": True, "exceeded_dimensions": []}


class FakePipeline:
    """Minimal pipeline exposing every attribute run_v2_module_hooks touches."""

    def __init__(self, introspection=None):
        self._introspection_scheduler = introspection or FakeIntrospection()
        self._theory_builder = FakeTheoryBuilder()
        self._unknown_unknown_detector = FakeUUD()
        self._cognitive_energy = FakeCognitiveEnergy()
        self._dual_confidence = _FlatRecorder()
        self._active_forgetting = _FlatRecorder()
        self._cognitive_momentum = FakeCognitiveMomentum()
        self._curiosity_drive = FakeCuriosityDrive()
        self._identity_compression = SimpleNamespace(overall_compression_rate=0.5)
        self._research_seasons = FakeResearchSeasons()
        self._discovery_rate = FakeDiscoveryRate()
        self._ecosystem = FakeEcosystem()
        self._model_competition = FakeModelCompetition()
        self._discovery_orchestrator = FakeDiscoveryOrchestrator()
        self._identity_utility = FakeIdentityUtility()
        self._axiom_evolution = None
        self._human_gateway = None
        self._interpretation_engine = FakeInterpretation()
        self._benchmark_collector = FakeBenchmarkCollector()
        self._creator_present = False
        self.budget_manager = FakeBudgetManager()
        self._resource_accounting = FakeResourceAccounting()

        from telos.core.axioms.evolution import AxiomEvolutionEngine
        self._axiom_evolution = AxiomEvolutionEngine()


def _trace(di=0.9, md=0.1):
    t = SimpleNamespace(decision_integrity=di, mission_drift=md)
    t.axiom_results = None  # pre-declared so hasattr() is True (real contract)
    return t


class TestRunAxiomProver:
    def test_sets_trace_axiom_results(self):
        prover = FakeVerifier({"a1": {"passed": True}, "a2": {"passed": False}})
        pipeline = FakePipeline()
        pipeline._axiom_prover = prover
        trace = _trace()
        ctx = make_ctx()
        run_axiom_prover(pipeline, trace, ctx)
        assert trace.axiom_results == {"a1": {"passed": True}, "a2": {"passed": False}}
        assert prover.verify_kwargs["stream_results"] == []
        assert prover.verify_kwargs["pipeline"] is pipeline

    def test_skips_when_verify_raises(self):
        prover = FakeVerifier(raise_on_verify=True)
        pipeline = FakePipeline()
        pipeline._axiom_prover = prover
        trace = _trace()
        run_axiom_prover(pipeline, trace, ctx := make_ctx())
        assert trace.axiom_results is None


class TestRunV2ModuleHooks:
    def test_runs_with_minimal_ctx_without_error(self):
        pipeline = FakePipeline()
        run_v2_module_hooks(pipeline, make_ctx(), _trace())

    def test_introspection_calls_and_strategic_promotion(self):
        p = FakePipeline(
            introspection=FakeIntrospection(
                due=[IntrospectionTier.STRATEGIC, IntrospectionTier.REFLECT]
            )
        )
        run_v2_module_hooks(p, make_ctx(cycle=5), _trace())
        calls = p._introspection_scheduler.calls
        assert calls[0] == (("get_due_tiers", 5), {})
        assert calls[1] == (("introspect", 5), {})
        assert p._theory_builder.calls == ["cluster", "hypothesize", "promote"]

    def test_performance_baseline_collection(self):
        p = FakePipeline()
        ctx = make_ctx()
        ctx._phase_timings = {"simulate": 10.0}
        run_v2_module_hooks(p, ctx, _trace())
        assert ctx._phase_durations["simulate"] == [10.0]

    def test_unknown_unknown_detector_wired(self):
        p = FakePipeline()
        ctx = make_ctx()
        ctx.state = __import__("numpy").array([1.0, 2.0])
        run_v2_module_hooks(p, ctx, _trace())
        calls = p._unknown_unknown_detector.calls
        assert calls[0][0] == "record_observation"
        assert calls[0][1] == 3
        assert calls[0][2]["state_norm"] == calls[0][3]["state_norm"] > 0

    def test_cognitive_energy_fatigue(self):
        p = FakePipeline()
        ctx = make_ctx()
        run_v2_module_hooks(p, ctx, _trace())
        assert ctx.cognitive_fatigue == 1.0 - 0.7
        assert ctx.exploration_modifier == 1.5

    def test_dual_confidence_and_forgetting_called(self):
        p = FakePipeline()
        run_v2_module_hooks(p, make_ctx(), _trace())
        assert "auto_examine" in "".join(str(c) for c in p._active_forgetting.calls)

    def test_curiosity_gets_compression(self):
        p = FakePipeline()
        run_v2_module_hooks(p, make_ctx(), _trace())
        assert ("set_compression", 0.5) in p._curiosity_drive.calls

    def test_research_season_and_discovery_rate(self):
        p = FakePipeline()
        ctx = make_ctx()
        run_v2_module_hooks(p, ctx, _trace())
        assert ctx.research_season == "growth"
        assert ctx.research_bonus == 0.25
        assert ctx.discovery_rate == 0.33
        assert ctx.discovery_step == {"step": 1}

    def test_identity_utility_computed(self):
        p = FakePipeline()
        run_v2_module_hooks(p, make_ctx(), _trace())
        compute_call = [c for c in p._identity_utility.calls
                        if c[0] == "compute_utility"]
        assert compute_call
        assert compute_call[0][1]["coherence"] == 0.5  # _creator_present False
        assert compute_call[0][2] == ["truth", "safety"]

    def test_axiom_evolution_observed(self):
        p = FakePipeline()
        run_v2_module_hooks(p, make_ctx(), _trace())
        assert p._axiom_evolution._total_proposals >= 0
        assert len(p._axiom_evolution._observation_history) == 1
        assert p._axiom_evolution._observation_history[0]["di"] == 0.9
        assert p._axiom_evolution._observation_history[0]["md"] == 0.1

    def test_interpretation_engine_wired_on_valid_verdict(self):
        p = FakePipeline()
        ctx = make_ctx(verdict=FakeVerdict(validated=True))
        run_v2_module_hooks(p, ctx, _trace(di=0.7))
        assert p._interpretation_engine.calls
        assert p._interpretation_engine.calls[0][0] == "record_outcome"

    def test_benchmark_collector_wired(self):
        p = FakePipeline()
        run_v2_module_hooks(p, make_ctx(), _trace())
        assert p._benchmark_collector.calls == [("collect",)]

    def test_ecology_cycle_called(self):
        p = FakePipeline()
        run_v2_module_hooks(p, make_ctx(), _trace())
        assert ("cycle",) in p._ecosystem.calls

    def test_cognitive_momentum_recommendation(self):
        p = FakePipeline()
        run_v2_module_hooks(p, make_ctx(), _trace())
        assert ("recommend_unstick",) in p._cognitive_momentum.calls


class TestRecordResourceAccounting:
    def test_records_intent_action(self):
        p = FakePipeline()
        ctx = make_ctx()
        from telos.intent_ir import IntentIR
        ctx.selected_intent = IntentIR(intent_type="explore")
        ctx.state = __import__("numpy").array([1.0, 2.0, 3.0])
        record_resource_accounting(p, ctx)
        ra = p._resource_accounting
        assert ("set_cycle", 3) in ra.calls
        action_call = [c for c in ra.calls if c[0] == "record_action"]
        assert action_call
        assert action_call[0][1] == "intent:explore"
        assert action_call[0][3] == {"governance": "APPROVED"}
        assert ctx.resource_accounting_summary == {"compute": 12.0}
        assert ctx.resource_accounting_budget_ok is True

    def test_records_stream_activations(self):
        p = FakePipeline()
        ctx = make_ctx()
        ctx.stream_activations = [
            StreamActivation(stream_name="reflex", priority=0.8, intent=None,
                             cost_ms=2.0, budget_remaining_ms=30.0, activated=True),
            StreamActivation(stream_name="off", priority=0.5, intent=None,
                             cost_ms=9.0, budget_remaining_ms=20.0, activated=False),
        ]
        record_resource_accounting(p, ctx)
        stream_calls = [c for c in p._resource_accounting.calls
                        if c[0] == "record_stream_activation"]
        assert ("record_stream_activation", "reflex", 2.0) in stream_calls
        # inactive streams are skipped
        assert all(s[1] != "off" for s in stream_calls)