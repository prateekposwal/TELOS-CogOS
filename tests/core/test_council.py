"""
Council of Cognitive Advisors tests — base, validators, blocking, pipeline integration.
"""

import numpy as np

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.simulation import CounterfactualEngine
from telos.core.streams.implementations import ReflexStream, PerceptionStream, MemoryStream, PlanningStream
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.council.base import Council, CouncilVerdict, ValidationSignal
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR
from tests.core.conftest import MockSimulator


def test_council_base():
    signal_pass = ValidationSignal(
        validator_name="TestValidator", passed=True,
        confidence=0.9, reason="all good", evidence_weight=0.3,
    )
    signal_block = ValidationSignal(
        validator_name="BlockingValidator", passed=False,
        confidence=-0.8, reason="reality mismatch", evidence_weight=0.7,
    )

    assert signal_pass.passed is True
    assert signal_block.passed is False
    assert signal_block.confidence == -0.8

    verdict = CouncilVerdict(validated=True, signals=[signal_pass], decision_integrity=1.0)
    assert verdict.validated is True
    assert verdict.blocking_validator is None

    verdict_blocked = CouncilVerdict(
        validated=False, signals=[signal_block],
        decision_integrity=0.3, blocking_validator="BlockingValidator",
    )
    assert verdict_blocked.validated is False
    assert "BLOCKED" in verdict_blocked.summary

    council = Council()
    assert council.validator_count == 0

    class MockPassValidator:
        name = "MockPass"
        def validate(self, world, intent, facts=None):
            return ValidationSignal("MockPass", True, 1.0, "mock pass", 0.1)

    council.register(MockPassValidator())
    assert council.validator_count == 1

    world = World(state=np.array([1.0, 2.0]))
    intent = IntentIR("test")
    verdict = council.evaluate(world, intent)
    assert verdict.validated is True
    assert verdict.decision_integrity == 1.0


def test_council_validators():
    from telos.core.ledger.skill_library import SkillLibrary

    rv = RealityValidator()
    world_clean = World(state=np.array([1.0, 2.0]))
    world_nan = World(state=np.array([float('nan'), 2.0]))
    world_inf = World(state=np.array([float('inf'), 2.0]))
    intent = IntentIR("test", params={"action_vector": np.array([0.1, 0.2])})

    sig_clean = rv.validate(world_clean, intent)
    sig_nan = rv.validate(world_nan, intent)
    sig_inf = rv.validate(world_inf, intent)

    assert sig_clean.passed is True
    assert sig_nan.passed is False
    assert sig_inf.passed is False

    cv = ConstraintValidator()
    world_low_safety = World(state=np.array([1.0, 2.0]), safety_score=0.2)
    facts = DomainFacts(state=np.array([1.0]), resources={}, constraints=["_bounds"], events=[], metrics={})

    sig_safe = cv.validate(world_clean, intent)
    sig_unsafe = cv.validate(world_low_safety, intent)
    assert sig_safe.passed is True
    assert sig_unsafe.passed is False

    skill_lib = SkillLibrary()
    ma = MemoryAdvisor(skill_lib)
    world = World(state=np.array([1.0, 2.0]))
    sig_no_memory = ma.validate(world, intent)
    assert sig_no_memory.passed is True

    md = MissionDriftDetector(drift_threshold=3.0)
    sig_no_drift = md.validate(world_clean, intent)
    assert sig_no_drift.passed is True
    assert sig_no_drift.reason is not None


def test_council_blocks_bad_intent():
    council = Council()
    council.register(RealityValidator())

    intent_bad = IntentIR("bad", params={"action_vector": np.array([float('nan'), float('nan')])})
    world_bad = World(state=np.array([1.0, 2.0]))

    verdict = council.evaluate(world_bad, intent_bad)
    assert verdict.validated is False
    assert verdict.blocking_validator == "RealityValidator"
    assert verdict.decision_integrity < 0.8

    intent_good = IntentIR("good", params={"action_vector": np.array([0.1, 0.2])})
    verdict2 = council.evaluate(world_bad, intent_good)
    assert verdict2.validated is True


def test_pipeline_with_council():
    sim = MockSimulator()
    sim.initialize()

    config = PipelineConfig(
        simulator=sim, compute_budget_ms=100.0, state_dim=6, n_worlds=10, horizon=5,
    )
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))

    assert pipeline.council.validator_count == 4

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    result = pipeline.execute(state)
    assert not result.council_blocked
    assert result.decision_trace is not None
    assert result.decision_trace.council_validated is True
    assert len(result.decision_trace.council_signals) == 4

    state_bad = np.array([float('nan'), 2.0, 0.0, 0.0, 0.0, 0.0])
    result_bad = pipeline.execute(state_bad)
    assert result_bad.council_blocked
    assert result_bad.selected_trajectory is None
    assert result_bad.decision_integrity < 1.0

    state = np.array([2.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    for cycle in range(3):
        result = pipeline.execute(state)
        assert not result.council_blocked
        state = state + np.random.randn(6) * 0.1

    sim.cleanup()


def test_kintsugi_memory_advisor_blocks_on_failure_match():
    """MemoryAdvisor with FailureLedger blocks when root cause matches current intent."""
    from telos.core.infra_manager.failure_ledger import FailureLedger

    skill_lib = SkillLibrary()
    ledger = FailureLedger()
    ma = MemoryAdvisor(skill_lib, failure_ledger=ledger)

    intent = IntentIR("plan", params={"action_vector": np.array([0.5])})
    world = World(state=np.array([1.0, 2.0]))

    sig = ma.validate(world, intent)
    assert sig.passed is True

    from telos.core.runtime import DecisionTrace, PipelinePhase, PipelineResult
    fail_trace = DecisionTrace(
        cycle_id=1, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("plan"),
        selected_action=None,
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.3, council_validated=False,
        decision_integrity=0.2, mission_drift=5.0,
        blocking_validator="plan",
    )
    fail_result = PipelineResult(
        selected_trajectory=None, health_score=0.3,
        pipeline_phase=PipelinePhase.COMPLETE,
        council_blocked=True, decision_trace=fail_trace,
    )
    ledger.observe(fail_result)

    # exact match uses block name + intent type
    sig2 = ma.validate(world, intent)
    assert sig2.passed is False
    assert "Kintsugi" in sig2.reason
    assert sig2.confidence <= -0.2  # recency-scaled: -0.2 - 0.8*recency
    assert "kintsugi_match_count" in sig2.metadata
    assert sig2.metadata["kintsugi_match_count"] >= 1
    assert "recency" in sig2.metadata
    assert "kintsugi_confidence" in sig2.metadata


def test_kintsugi_memory_advisor_ignores_governance_failures():
    """MemoryAdvisor skips governance_intervention and simulation_divergence root causes."""
    from telos.core.infra_manager.failure_ledger import FailureLedger
    from telos.core.runtime import DecisionTrace, PipelinePhase, PipelineResult

    ledger = FailureLedger()
    ma = MemoryAdvisor(SkillLibrary(), failure_ledger=ledger)

    # Firewall block → root_cause = "governance_intervention"
    fb_trace = DecisionTrace(
        cycle_id=1, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("plan"),
        selected_action=None,
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.4, council_validated=True,
        decision_integrity=0.4, mission_drift=4.0,
        firewall_blocked=True, firewall_blocked_by="TrustManager",
    )
    fb_result = PipelineResult(
        selected_trajectory=None, health_score=0.4,
        pipeline_phase=PipelinePhase.COMPLETE,
        firewall_blocked=True, governance_blocked_by="TrustManager",
        decision_trace=fb_trace,
    )
    ledger.observe(fb_result)

    # High drift → root_cause = "simulation_divergence"
    drift_trace = DecisionTrace(
        cycle_id=2, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("plan"),
        selected_action=np.array([0.5]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.5, council_validated=True,
        decision_integrity=0.5, mission_drift=6.0,
    )
    drift_result = PipelineResult(
        selected_trajectory=IntentIR("plan"), health_score=0.5,
        pipeline_phase=PipelinePhase.COMPLETE,
        decision_trace=drift_trace,
    )
    ledger.observe(drift_result)

    intent = IntentIR("plan", params={"action_vector": np.array([0.5])})
    world = World(state=np.array([1.0, 2.0]))

    sig = ma.validate(world, intent)
    assert sig.passed is True
    assert "Kintsugi" not in sig.reason


def test_kintsugi_memory_advisor_without_ledger_noop():
    """MemoryAdvisor without FailureLedger behaves as before (no Kintsugi)."""
    ma = MemoryAdvisor(SkillLibrary())

    intent = IntentIR("plan", params={"action_vector": np.array([0.5])})
    world = World(state=np.array([1.0, 2.0]))

    sig = ma.validate(world, intent)
    assert sig.passed is True
    assert "Kintsugi" not in sig.reason

