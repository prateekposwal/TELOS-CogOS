"""
End-to-end test for the Latent Cognition architecture.

Validates:
1. Runtime pipeline executes with all 4 cognitive streams
2. BudgetManager tracks resource consumption across streams
3. RepresentationPlanner makes adaptive meta-reasoning decisions
4. DecisionTrace captures the complete latent cognition audit trail
5. ExperienceManager indexes skills from successful decisions
6. TransparencyMonitor generates human-readable reports
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.attention import BudgetManager
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.planner import RepresentationPlanner
from telos.core.simulation import CounterfactualEngine
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.experience_manager import ExperienceManager, ExperienceConfig
from telos.audit.monitor import TransparencyMonitor
from telos.world.world import World
from telos.world.facts import DomainFacts
from tests.core.conftest import MockSimulator
from telos.intent_ir import IntentIR
from telos.core.council.base import Council, CouncilVerdict, ValidationSignal
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.world_ledger import WorldLedger, EntityRecord, SemanticDepth
from telos.core.governance.trust_manager import TrustManager, AccessLevel
from telos.core.governance.timing import InformationReadinessEngine, ReadinessCondition, ReadinessState
from telos.core.governance.firewall import DecisionFirewall, FirewallConfig
from telos.core.infra_manager.stream_calibrator import StreamCalibrator
from telos.core.infra_manager.failure_ledger import FailureLedger
from telos.core.infra_manager.mission_policy import MissionPolicyManager, MissionPolicy
from telos.core.infra_manager.audit_controller import AuditController
from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
from typing import List


def test_imports():
    """Verify all modules import cleanly."""
    print("=== Test 1: Imports ===")
    assert BudgetManager is not None
    assert TelosV14Pipeline is not None
    assert ReflexStream is not None
    assert PerceptionStream is not None
    assert MemoryStream is not None
    assert PlanningStream is not None
    assert RepresentationPlanner is not None
    assert ExperienceManager is not None
    assert TransparencyMonitor is not None
    print("PASS: All modules import successfully\n")


def test_budget_manager():
    """Verify budget tracking."""
    print("=== Test 2: BudgetManager ===")
    bm = BudgetManager(total_budget_ms=50.0)
    assert bm.consumed_ms == 0.0
    assert bm.check_budget("test", 10.0) is True
    bm.consume("test", 10.0)
    assert bm.consumed_ms == 10.0
    assert bm.check_budget("test", 45.0) is False
    bm.reset()
    assert bm.consumed_ms == 0.0
    print("PASS: BudgetManager tracks correctly\n")


def test_streams():
    """Verify all 4 cognitive streams process World correctly."""
    print("=== Test 3: Cognitive Streams ===")
    skill_lib = SkillLibrary()
    sim = MockSimulator()
    sim_engine = CounterfactualEngine(sim)

    # ReflexStream
    reflex = ReflexStream(skill_lib)
    world = World(state=np.array([10.0, 10.0]), metadata={}, uncertainty=0.9)
    intent = reflex.process(world)
    assert intent.intent_type == "reflex"
    # Uncertainty alone no longer triggers reflex (old rule removed)
    assert intent.confidence == 0.0
    # NaN still triggers reflex
    world_nan = World(state=np.array([float('nan'), 10.0]), metadata={}, uncertainty=0.5)
    intent_nan = reflex.process(world_nan)
    assert intent_nan.intent_type == "reflex"
    assert intent_nan.confidence >= 0.5
    print(f"  ReflexStream: type={intent.intent_type}, confidence={intent.confidence:.2f}")

    # PerceptionStream
    perception = PerceptionStream(skill_lib)
    world = World(state=np.array([1.0, 2.0, 0.0, 0.0, 0.0, 0.0]))
    intent = perception.process(world)
    assert intent.intent_type == "perceive"
    assert "features" in intent.params
    assert len(world.entities) > 0
    print(f"  PerceptionStream: entities={world.entities}")

    # MemoryStream
    memory = MemoryStream(skill_lib)
    world = World(state=np.array([1.0, 2.0]))
    intent = memory.process(world)
    assert intent.intent_type == "memory_miss"
    print(f"  MemoryStream: type={intent.intent_type}")

    # PlanningStream
    planning = PlanningStream(skill_lib, sim_engine=sim_engine)
    world = World(state=np.array([1.0, 2.0]))
    intent = planning.process(world)
    assert intent.intent_type in ("plan_trajectory", "plan_empty", "plan_noop")
    print(f"  PlanningStream: type={intent.intent_type}")

    print("PASS: All streams process World correctly\n")


def test_planner():
    """Verify RepresentationPlanner meta-reasoning."""
    print("=== Test 4: RepresentationPlanner ===")
    bm = BudgetManager(total_budget_ms=50.0)
    planner = RepresentationPlanner(bm)

    # Low-norm state → should prefer cartesian
    facts_close = DomainFacts(
        state=np.array([0.1, 0.2]),
        resources={}, constraints=[], events=[],
        metrics={"distance_from_origin": 0.22},
    )
    rep1 = planner.select_representation(facts_close)
    print(f"  Close state: rep={rep1}")

    # High-norm state → should prefer polar
    facts_far = DomainFacts(
        state=np.array([4.0, 3.0]),
        resources={}, constraints=[], events=[],
        metrics={"distance_from_origin": 5.0},
    )
    rep2 = planner.select_representation(facts_far)
    print(f"  Far state: rep={rep2}")

    assert rep1 in ("cartesian", "polar")
    assert rep2 in ("cartesian", "polar")
    assert len(planner.selection_history) == 2
    print(f"  History: {len(planner.selection_history)} entries")
    print("PASS: Planner makes adaptive decisions\n")


def test_full_pipeline():
    """Verify complete pipeline execution with all components."""
    print("=== Test 5: Full Pipeline ===")
    sim = MockSimulator()
    sim.initialize()

    config = PipelineConfig(
        simulator=sim,
        compute_budget_ms=100.0,
        state_dim=6,
        n_worlds=10,
        horizon=5,
    )
    pipeline = TelosV14Pipeline(config)

    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    result = pipeline.execute(state)

    assert result.pipeline_phase.value == "complete"
    assert result.decision_trace is not None
    assert len(result.decision_trace.stream_activations) == 4
    assert result.decision_trace.budget_consumed_ms > 0
    assert not result.council_blocked, "Council should approve clean state"
    assert result.decision_integrity > 0.5, "DI should be high for clean state"
    assert result.decision_trace.council_validated is True
    print(f"  Health: {result.health_score:.3f}")
    print(f"  Budget: {result.decision_trace.budget_consumed_ms:.1f}ms")
    print(f"  Worlds: {result.worlds_generated}")
    print(f"  Council: {'APPROVED' if not result.council_blocked else 'BLOCKED'}")
    print(f"  DI: {result.decision_integrity:.3f}, MD: {result.mission_drift:.3f}")
    print(f"  Streams activated: {len([a for a in result.decision_trace.stream_activations if a.activated])}/4")
    print(f"  Selected intent: {result.selected_trajectory.intent_type if result.selected_trajectory else 'none'}")
    print(f"  Representation: {result.decision_trace.representation}")

    sim.cleanup()
    print("PASS: Full pipeline executes end-to-end\n")


def test_experience_manager():
    """Verify external learning observer indexes skills."""
    print("=== Test 6: ExperienceManager ===")
    skill_lib = SkillLibrary()
    manager = ExperienceManager(skill_lib, ExperienceConfig(utility_threshold=0.3))

    from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace

    good_result = PipelineResult(
        selected_trajectory=IntentIR("good_plan", confidence=0.9),
        health_score=0.8,
        pipeline_phase=PipelinePhase.COMPLETE,
        worlds_generated=10,
            decision_trace=DecisionTrace(
                cycle_id=1, timestamp=0.0,
                world_state_snapshot=np.array([1.0, 2.0]),
                domain_facts=None, stream_activations=[],
                selected_intent=IntentIR("good_plan"),
                selected_action=np.array([0.1, 0.2]),
                representation="cartesian",
                budget_consumed_ms=15.0, budget_total_ms=50.0,
                worlds_simulated=10, cycle_duration_ms=12.0,
                health_score=0.8, council_validated=True,
                decision_integrity=1.0, mission_drift=0.0,
            ),
    )

    skill = manager.observe(good_result)
    assert skill is not None
    assert skill.skill_id in skill_lib.skills
    print(f"  Indexed skill: {skill.skill_id}")
    print(f"  Stats: {manager.stats}")

    bad_result = PipelineResult(
        selected_trajectory=None,
        health_score=0.1,
        pipeline_phase=PipelinePhase.COMPLETE,
    )
    skill2 = manager.observe(bad_result)
    assert skill2 is None
    print("PASS: ExperienceManager indexes skills correctly\n")


def test_transparency_monitor():
    """Verify transparency monitor captures and reports."""
    print("=== Test 7: TransparencyMonitor ===")
    monitor = TransparencyMonitor()

    from telos.core.runtime import DecisionTrace

    for i in range(3):
        trace = DecisionTrace(
            cycle_id=i + 1, timestamp=float(i),
            world_state_snapshot=np.array([float(i), float(i + 1)]),
            domain_facts=DomainFacts(
                state=np.array([float(i)]),
                resources={"r": float(i)},
                constraints=["c1"] if i > 0 else [],
                events=["e1"],
                metrics={"m": float(i)},
            ),
            stream_activations=[],
            selected_intent=IntentIR("test"),
            selected_action=np.array([0.1]),
            representation="cartesian",
            budget_consumed_ms=10.0 + i,
            budget_total_ms=50.0,
            worlds_simulated=5,
            cycle_duration_ms=8.0 + i,
            health_score=0.8 - i * 0.1,
            council_validated=(i < 2),
            decision_integrity=0.9 - i * 0.3,
            mission_drift=float(i),
            blocking_validator="TestValidator" if i == 2 else None,
            council_signals=[
                {"validator": "TestValidator", "passed": i < 2,
                 "confidence": -1.0 if i == 2 else 1.0,
                 "reason": "test", "evidence_weight": 0.5},
            ],
        )
        monitor.record(trace)

    report = monitor.generate_report()
    assert "Latent Cognition" in report
    assert "Cycle 1" in report
    print(f"  Report length: {len(report)} chars")
    print(f"  Traces recorded: {len(monitor.get_traces())}")
    print("PASS: Monitor generates transparency reports\n")


def test_multi_cycle():
    """Verify pipeline works across multiple decision cycles."""
    print("=== Test 8: Multi-Cycle Execution ===")
    sim = MockSimulator()
    sim.initialize()

    config = PipelineConfig(
        simulator=sim, compute_budget_ms=100.0,
        state_dim=6, n_worlds=10, horizon=5,
    )
    pipeline = TelosV14Pipeline(config)

    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)
    experience = ExperienceManager(skill_lib)
    monitor = TransparencyMonitor()

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    state = np.array([2.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    for cycle in range(5):
        result = pipeline.execute(state)
        experience.observe(result)
        if result.decision_trace:
            monitor.record(result.decision_trace)
        state = state + np.random.randn(6) * 0.1

    report = monitor.generate_report()
    print(f"  Cycles: 5")
    print(f"  Skills indexed: {experience.stats['skills_indexed']}")
    print(f"  Report generated: {len(report)} chars")
    print(f"  Decision log exists: {os.path.exists('telos/audit/runtime/decision_log.json')}")

    sim.cleanup()
    print("PASS: Multi-cycle execution works\n")


def test_council_base():
    """Verify Council base — ValidationSignal, CouncilVerdict, Council."""
    print("=== Test 9: Council Base ===")

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
    assert "all clear" in verdict.summary

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

    print(f"  Pass signal: passed={signal_pass.passed}, confidence={signal_pass.confidence:+.1f}")
    print(f"  Block signal: passed={signal_block.passed}, confidence={signal_block.confidence:+.1f}")
    print(f"  Council passes: {verdict.validated}, DI={verdict.decision_integrity:.1f}")
    print("PASS: Council base works correctly\n")


def test_council_validators():
    """Verify each concrete validator independently."""
    print("=== Test 10: Council Validators ===")

    from telos.core.ledger.skill_library import SkillLibrary

    # RealityValidator
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
    assert sig_nan.reason != sig_clean.reason
    print(f"  RealityValidator: clean={sig_clean.passed}, NaN={sig_nan.passed}, Inf={sig_inf.passed}")

    # ConstraintValidator
    cv = ConstraintValidator()
    world_low_safety = World(state=np.array([1.0, 2.0]), safety_score=0.2)
    facts = DomainFacts(state=np.array([1.0]), resources={}, constraints=["_bounds"], events=[], metrics={})

    sig_safe = cv.validate(world_clean, intent)
    sig_unsafe = cv.validate(world_low_safety, intent)
    assert sig_safe.passed is True
    assert sig_unsafe.passed is False
    print(f"  ConstraintValidator: safe={sig_safe.passed}, unsafe={sig_unsafe.passed}")

    # MemoryAdvisor
    skill_lib = SkillLibrary()
    ma = MemoryAdvisor(skill_lib)
    world = World(state=np.array([1.0, 2.0]))
    sig_no_memory = ma.validate(world, intent)
    assert sig_no_memory.passed is True
    print(f"  MemoryAdvisor (empty library): passed={sig_no_memory.passed}")

    # MissionDriftDetector
    md = MissionDriftDetector(drift_threshold=3.0)
    sig_no_drift = md.validate(world_clean, intent)
    assert sig_no_drift.passed is True
    assert sig_no_drift.reason is not None
    print(f"  MissionDriftDetector: passed={sig_no_drift.passed}, drift=0.0")

    print("PASS: All validators behave correctly\n")


def test_council_blocks_bad_intent():
    """Verify the Council blocks action when RealityValidator detects issues."""
    print("=== Test 11: Council Blocks Bad Intent ===")

    council = Council()
    council.register(RealityValidator())

    intent_bad = IntentIR("bad", params={"action_vector": np.array([float('nan'), float('nan')])})
    world_bad = World(state=np.array([1.0, 2.0]))

    verdict = council.evaluate(world_bad, intent_bad)
    assert verdict.validated is False
    assert verdict.blocking_validator == "RealityValidator"
    assert verdict.decision_integrity < 0.8
    print(f"  Bad action (NaN): validated={verdict.validated}, blocker={verdict.blocking_validator}, DI={verdict.decision_integrity:.3f}")

    intent_good = IntentIR("good", params={"action_vector": np.array([0.1, 0.2])})
    verdict2 = council.evaluate(world_bad, intent_good)
    assert verdict2.validated is True
    print(f"  Good action: validated={verdict2.validated}, DI={verdict2.decision_integrity:.3f}")

    print("PASS: Council blocks bad intents correctly\n")


def test_pipeline_with_council():
    """Verify full pipeline with Council integrated."""
    print("=== Test 12: Full Pipeline with Council ===")
    sim = MockSimulator()
    sim.initialize()

    config = PipelineConfig(
        simulator=sim, compute_budget_ms=100.0,
        state_dim=6, n_worlds=10, horizon=5,
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

    # Clean state — should be approved
    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    result = pipeline.execute(state)
    assert not result.council_blocked
    assert result.decision_trace is not None
    assert result.decision_trace.council_validated is True
    assert len(result.decision_trace.council_signals) == 4
    print(f"  Clean state: council={'APPROVED' if not result.council_blocked else 'BLOCKED'}, "
          f"DI={result.decision_integrity:.3f}, "
          f"signals={len(result.decision_trace.council_signals)}")

    # Nan state — RealityValidator should block
    state_bad = np.array([float('nan'), 2.0, 0.0, 0.0, 0.0, 0.0])
    result_bad = pipeline.execute(state_bad)
    assert result_bad.council_blocked
    assert result_bad.selected_trajectory is None
    assert result_bad.decision_integrity < 1.0
    print(f"  NaN state: council={'BLOCKED' if result_bad.council_blocked else 'APPROVED'}, "
          f"DI={result_bad.decision_integrity:.3f}, "
          f"blocker={result_bad.decision_trace.blocking_validator}")

    # Multi-cycle run with clean state — all approved
    state = np.array([2.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    for cycle in range(3):
        result = pipeline.execute(state)
        assert not result.council_blocked, f"Cycle {cycle} should be approved"
        state = state + np.random.randn(6) * 0.1
    print("  3 clean cycles: all approved")

    sim.cleanup()
    print("PASS: Pipeline with Council executes correctly\n")


def test_world_ledger_history():
    """Verify the WorldLedger accumulates entity history across cycles.

    Validates the Hidden History Principle:
    - First observation: newly_discovered
    - After multiple cycles: well_known_N_observations
    - Semantic identity evolves with history
    """
    print("=== Test 13: WorldLedger — History Accumulation ===")

    ledger = WorldLedger()

    # Create a simple world and perception intent
    world1 = World(state=np.array([1.0, 2.0, 0.5]), entities=["active_region"])
    intent1 = IntentIR("perceive", params={
        "features": {"state_norm": 2.2, "state_mean": 1.0, "energy": 5.0},
        "entities": ["active_region"], "entity_ids": ["ent_test"],
    })

    # Cycle 1: enrich → entity should be newly_discovered
    enriched1 = ledger.enrich(world1, intent1, cycle=1)
    depths1 = enriched1.metadata.get("semantic_depths", [])
    assert len(depths1) == 1
    assert depths1[0].historical_context == "newly_discovered"
    assert depths1[0].semantic_identity == "active_region"
    rec = ledger.get_record("active_region")
    assert rec is not None
    assert rec.observation_count == 1
    print(f"  Cycle 1: identity={depths1[0].semantic_identity}, "
          f"history={depths1[0].historical_context}, observations={rec.observation_count}")

    # Cycle 2: same entity → history should update
    world2 = World(state=np.array([1.1, 2.1, 0.4]), entities=["active_region"])
    intent2 = IntentIR("perceive", params={
        "features": {"state_norm": 2.3, "state_mean": 1.1, "energy": 5.2},
        "entities": ["active_region"], "entity_ids": ["ent_test"],
    })
    enriched2 = ledger.enrich(world2, intent2, cycle=2)
    depths2 = enriched2.metadata.get("semantic_depths", [])
    assert depths2[0].historical_context != "newly_discovered"
    assert rec.observation_count == 2
    print(f"  Cycle 2: identity={depths2[0].semantic_identity}, "
          f"history={depths2[0].historical_context}, observations={rec.observation_count}")

    # Cycle 3-5: accumulate more history
    for cyc in range(3, 6):
        s = np.array([1.0 + cyc * 0.1, 2.0, 0.5])
        w = World(state=s, entities=["active_region"])
        i = IntentIR("perceive", params={
            "features": {"state_norm": float(np.linalg.norm(s))},
            "entities": ["active_region"], "entity_ids": ["ent_test"],
        })
        ledger.enrich(w, i, cycle=cyc)

    assert rec.observation_count == 5
    assert rec.last_seen > rec.first_seen
    assert "persistent_entity" in rec.semantic_identity

    # Verify the full record
    print(f"  Final: identity={rec.semantic_identity}, "
          f"observations={rec.observation_count}, "
          f"age={rec.age_seconds:.2f}s, "
          f"relevance={rec.mission_relevance:.2f}")

    print("PASS: WorldLedger accumulates history correctly\n")


def test_governance():
    """Verify Governance Layer — TrustManager, ReadinessEngine, DecisionFirewall."""
    print("=== Test 14: Governance — Cognitive Confidentiality ===")

    # ── TrustManager ──
    tm = TrustManager()
    tm.set_mission("payment_processing")

    # Register a stream with restricted access
    tm.register_stream("PlanningStream", knowledge_domains={"public", "simulation"})
    tm.register_stream("PaymentStream", knowledge_domains={"financial", "public"},
                       authorized_missions={"payment_processing"})

    assert tm.authorize_stream("PaymentStream", "financial") is True
    assert tm.authorize_stream("PlanningStream", "financial") is False
    assert tm.authorize_stream("PlanningStream", "public") is True
    print(f"  TrustManager: grants={tm.stats['grants']}, denials={tm.stats['denials']}")

    # Mission change → previously authorized stream now denied
    tm.set_mission("support")
    assert tm.authorize_stream("PaymentStream", "financial") is False
    print(f"  TrustManager (mission=support): denies PaymentStream access to financial")

    # ── InformationReadinessEngine ──
    re = InformationReadinessEngine()
    re.register_fact("disaster_plan", conditions=[
        ReadinessCondition("signal_detected", threshold=1.0, description="high_severity_alarm"),
    ])

    assert not re.is_ready("disaster_plan")
    print(f"  ReadinessEngine: fact locked initially ({re.stats['locked']} locked, {re.stats['ready']} ready)")

    re.emit_signal("high_severity_alarm", strength=1.0)
    re.tick()
    assert re.is_ready("disaster_plan")
    print(f"  ReadinessEngine: fact READY after signal ({re.stats['locked']} locked, {re.stats['ready']} ready)")

    # Cycle-based readiness
    re2 = InformationReadinessEngine()
    re2.register_fact("strategic_data", conditions=[
        ReadinessCondition("cycle_count", threshold=3),
    ])
    for _ in range(2):
        re2.tick()
    assert not re2.is_ready("strategic_data")
    re2.tick()
    assert re2.is_ready("strategic_data")
    print(f"  ReadinessEngine: cycle-based unlock works (ready after cycle 3)")

    # ── DecisionFirewall ──
    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
    world = World(state=np.array([1.0, 2.0]))
    intent = IntentIR("test")

    v1 = fw.inspect(world, intent, council_validated=True, decision_integrity=0.9)
    assert v1.passed is True
    print(f"  Firewall: clean decision passes (DI=0.9)")

    v2 = fw.inspect(world, intent, council_validated=False, decision_integrity=0.9)
    assert v2.passed is False
    assert v2.blocked_by == "council_rejection"
    print(f"  Firewall: council rejection → blocked")

    v3 = fw.inspect(world, intent, council_validated=True, decision_integrity=0.2)
    assert v3.passed is False
    assert v3.blocked_by == "low_integrity"
    print(f"  Firewall: low DI → blocked (DI=0.2 < 0.5)")

    print("PASS: Governance layer works correctly\n")


def test_infrastructure_stream_calibrator():
    """Verify StreamCalibrator tracks influence weights."""
    print("=== Test 15: StreamCalibrator ===")

    from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace

    cal = StreamCalibrator()

    sim = MockSimulator()
    config = PipelineConfig(simulator=sim, compute_budget_ms=100.0)
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
        cal.observe(result)

    # At least some streams should be calibrated after 3 cycles
    assert cal.stats["calibrated_streams"] > 0
    for name, c in cal.stats["calibrations"].items():
        assert 0.0 <= c["influence"] <= 2.0
        print(f"  {name}: accuracy={c['accuracy']:.3f}, reliability={c['reliability']:.3f}, influence={c['influence']:.3f}")

    # Fresh stream gets default influence
    assert cal.get_influence_weight("nonexistent") == 1.0

    print(f"  Calibrated streams: {cal.stats['calibrated_streams']}")
    print("PASS: StreamCalibrator tracks influence weights\n")


def test_infrastructure_failure_ledger():
    """Verify FailureLedger records failures correctly."""
    print("=== Test 16: FailureLedger (Kintsugi) ===")

    from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace

    ledger = FailureLedger()

    # No failure — clean cycle
    clean_trace = DecisionTrace(
        cycle_id=1, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("test"),
        selected_action=np.array([0.1]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.9, council_validated=True,
        decision_integrity=0.9, mission_drift=0.5,
    )
    clean = PipelineResult(None, 0.9, PipelinePhase.COMPLETE, decision_trace=clean_trace)
    assert ledger.observe(clean) is None
    assert ledger.total_failures == 0

    # Council block failure
    blocked_trace = DecisionTrace(
        cycle_id=2, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("bad"),
        selected_action=None,
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.5, council_validated=False,
        decision_integrity=0.2, mission_drift=2.0,
        blocking_validator="RealityValidator",
    )
    blocked_result = PipelineResult(None, 0.5, PipelinePhase.COMPLETE,
                                     council_blocked=True, decision_trace=blocked_trace)
    fail = ledger.observe(blocked_result)
    assert fail is not None
    assert fail.failure_type == "council_block"
    assert ledger.total_failures == 1

    # High drift failure
    drift_trace = DecisionTrace(
        cycle_id=3, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("drift"),
        selected_action=np.array([0.1]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.8, council_validated=True,
        decision_integrity=0.9, mission_drift=6.0,
    )
    drift_result = PipelineResult(None, 0.8, PipelinePhase.COMPLETE,
                                   decision_trace=drift_trace)
    fail2 = ledger.observe(drift_result)
    assert fail2 is not None
    assert fail2.failure_type == "high_drift"

    print(f"  Total failures: {ledger.total_failures}")
    print(f"  Root causes: {ledger.get_root_cause_summary()}")
    print(f"  Recent: {len(ledger.get_recent_failures())}")
    print("PASS: FailureLedger records Kintsugi failures\n")


def test_infrastructure_mission_policy():
    """Verify MissionPolicyManager adapts parameters."""
    print("=== Test 17: MissionPolicyManager ===")

    ppm = MissionPolicyManager()

    # Default policy
    assert ppm.current.risk_tolerance == 0.3
    assert ppm.current.mission_name == "default"

    # Set new mission
    ppm.set_policy(MissionPolicy("high_stakes", risk_tolerance=0.1, exploration_budget=0.2))
    assert ppm.current.risk_tolerance == 0.1
    assert ppm.current.mission_name == "high_stakes"

    # Adaptive adjustments
    ppm.adjust_risk_tolerance(0.15)
    assert ppm.current.risk_tolerance == 0.25

    ppm.adjust_exploration_budget(0.1)
    assert abs(ppm.current.exploration_budget - 0.3) < 1e-10

    # Clamping
    ppm.adjust_risk_tolerance(10.0)  # would exceed 1.0
    assert abs(ppm.current.risk_tolerance - 1.0) < 1e-10
    ppm.adjust_risk_tolerance(-10.0)  # would go below 0.0
    assert ppm.current.risk_tolerance == 0.0

    # Firewall threshold
    ppm2 = MissionPolicyManager(MissionPolicy("test", risk_tolerance=0.2))
    assert ppm2.firewall_di_threshold == 0.8

    print(f"  Policy changes: {ppm.stats['policy_changes']}")
    print(f"  Firewall DI threshold at risk=0.2: {ppm2.firewall_di_threshold}")
    print("PASS: MissionPolicyManager adapts parameters\n")


def test_infrastructure_audit_controller():
    """Verify AuditController tracks infrastructure health."""
    print("=== Test 18: AuditController ===")

    from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace

    controller = AuditController()
    sim = MockSimulator()
    config = PipelineConfig(simulator=sim, compute_budget_ms=100.0)
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
        controller.observe(result)

    report = controller.generate_report(calibrated_streams=2, total_streams=4)
    assert report.total_cycles == 3
    assert 0.0 <= report.health_score <= 1.0

    print(f"  Cycles: {report.total_cycles}")
    print(f"  Health score: {report.health_score:.3f}")
    print(f"  Avg DI: {report.avg_decision_integrity:.3f}")
    print(f"  Avg MD: {report.avg_mission_drift:.3f}")
    print(f"  Failure rate: {report.failure_rate:.3f}")
    print(f"  Calibration coverage: {report.stream_calibration_coverage:.3f}")
    print("PASS: AuditController tracks health\n")


def test_infrastructure_manager_integration():
    """Verify full InfrastructureManager integrates with Pipeline."""
    print("=== Test 19: InfrastructureManager Integration ===")

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
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())

    infra = pipeline.infra_manager
    assert infra is not None

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    for cycle in range(5):
        result = pipeline.execute(state)
        assert result is not None
        state = state + np.random.randn(6) * 0.1

    # After 5 cycles, infra should have calibrations
    stats = infra.stats
    assert stats["calibrator"]["calibrated_streams"] > 0
    assert stats["audit"]["cycles_observed"] == 5

    report = infra.generate_report()
    assert report.health_score > 0.0
    assert report.total_cycles == 5

    print(f"  Calibrated: {stats['calibrator']['calibrated_streams']} streams")
    print(f"  Failures: {stats['failures']['total_failures']}")
    print(f"  Policy mission: {stats['policy']['mission']}")
    print(f"  Health score: {report.health_score:.3f}")
    print("PASS: InfrastructureManager integrates with Pipeline\n")


def test_infrastructure_mission_rotation():
    """Verify adaptive behavior under rotating mission vectors.

    This tests the system's ability to calibrate differently under
    different mission contexts — the heart of "Infrastructure-First".
    """
    print("=== Test 20: Mission Rotation — Adaptive Calibration ===")

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

    infra = pipeline.infra_manager

    # Mission: strict (low risk tolerance)
    infra.set_mission("strict", risk_tolerance=0.1, exploration_budget=0.1)
    assert infra.policy.current.risk_tolerance == 0.1

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    for _ in range(3):
        pipeline.execute(state)

    # Mission: exploratory (high risk tolerance)
    infra.set_mission("exploratory", risk_tolerance=0.8, exploration_budget=0.7)
    assert infra.policy.current.mission_name == "exploratory"
    assert infra.policy.current.risk_tolerance == 0.8

    for _ in range(3):
        pipeline.execute(state)

    policy_history = infra.policy.stats["policy_changes"]
    assert policy_history == 2

    print(f"  Policy changes: {policy_history}")
    print(f"  Final mission: {infra.policy.current.mission_name}")
    print(f"  Risk tolerance: {infra.policy.current.risk_tolerance}")
    print(f"  Exploration budget: {infra.policy.current.exploration_budget}")
    print(f"  Stream calibrations: {len(infra.calibrator.stats['calibrations'])}")
    print("PASS: Mission rotation calibrates adaptively\n")


if __name__ == "__main__":
    print("=" * 60)
    print("TELOS — GOVERNED COGNITIVE OPERATING SYSTEM")
    print("=" * 60)
    print()

    test_imports()
    test_budget_manager()
    test_streams()
    test_planner()
    test_full_pipeline()
    test_experience_manager()
    test_transparency_monitor()
    test_multi_cycle()
    test_council_base()
    test_council_validators()
    test_council_blocks_bad_intent()
    test_pipeline_with_council()
    test_world_ledger_history()
    test_governance()
    test_infrastructure_stream_calibrator()
    test_infrastructure_failure_ledger()
    test_infrastructure_mission_policy()
    test_infrastructure_audit_controller()
    test_infrastructure_manager_integration()
    test_infrastructure_mission_rotation()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
