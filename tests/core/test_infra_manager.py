"""
Infrastructure Manager tests — calibrator, failure ledger, mission policy,
audit controller, full integration, and mission rotation.
"""

import numpy as np

from telos.core.runtime import TelosV14Pipeline, PipelineConfig, PipelineResult, PipelinePhase, DecisionTrace
from telos.core.simulation import CounterfactualEngine
from telos.core.streams.implementations import ReflexStream, PerceptionStream, MemoryStream, PlanningStream
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.council.validators import RealityValidator, ConstraintValidator
from telos.core.infra_manager.stream_calibrator import StreamCalibrator
from telos.core.infra_manager.failure_ledger import FailureLedger
from telos.core.infra_manager.mission_policy import MissionPolicyManager, MissionPolicy
from telos.core.infra_manager.audit_controller import AuditController
from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
from telos.intent_ir import IntentIR
from tests.core.conftest import MockSimulator


def test_infrastructure_stream_calibrator():
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

    assert cal.stats["calibrated_streams"] > 0
    for name, c in cal.stats["calibrations"].items():
        assert 0.0 <= c["influence"] <= 2.0

    assert cal.get_influence_weight("nonexistent") == 1.0


def test_infrastructure_failure_ledger():
    ledger = FailureLedger()

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


def test_infrastructure_mission_policy():
    ppm = MissionPolicyManager()

    assert ppm.current.risk_tolerance == 0.3
    assert ppm.current.mission_name == "default"

    ppm.set_policy(MissionPolicy("high_stakes", risk_tolerance=0.1, exploration_budget=0.2))
    assert ppm.current.risk_tolerance == 0.1
    assert ppm.current.mission_name == "high_stakes"

    ppm.adjust_risk_tolerance(0.15)
    assert abs(ppm.current.risk_tolerance - 0.25) < 1e-10

    ppm.adjust_exploration_budget(0.1)
    assert abs(ppm.current.exploration_budget - 0.3) < 1e-10

    ppm.adjust_risk_tolerance(10.0)
    assert abs(ppm.current.risk_tolerance - 1.0) < 1e-10
    ppm.adjust_risk_tolerance(-10.0)
    assert abs(ppm.current.risk_tolerance - 0.0) < 1e-10

    ppm2 = MissionPolicyManager(MissionPolicy("test", risk_tolerance=0.2))
    assert ppm2.firewall_di_threshold == 0.8


def test_infrastructure_audit_controller():
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


def test_infrastructure_manager_integration():
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

    stats = infra.stats
    assert stats["calibrator"]["calibrated_streams"] > 0
    assert stats["audit"]["cycles_observed"] == 5

    report = infra.generate_report()
    assert report.health_score > 0.0
    assert report.total_cycles == 5


def test_infrastructure_mission_rotation():
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

    infra.set_mission("strict", risk_tolerance=0.1, exploration_budget=0.1)
    assert infra.policy.current.risk_tolerance == 0.1

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    for _ in range(3):
        pipeline.execute(state)

    infra.set_mission("exploratory", risk_tolerance=0.8, exploration_budget=0.7)
    assert infra.policy.current.mission_name == "exploratory"
    assert infra.policy.current.risk_tolerance == 0.8

    for _ in range(3):
        pipeline.execute(state)

    assert infra.policy.stats["policy_changes"] == 2


def test_recovery_mode_enters_on_failure_cluster():
    """InfraManager enters recovery mode when failure rate exceeds threshold."""
    infra = InfrastructureManager()
    from telos.core.runtime import DecisionTrace, PipelineResult, PipelinePhase

    for _ in range(10):
        blocked_trace = DecisionTrace(
            cycle_id=1, timestamp=0.0,
            world_state_snapshot=np.array([1.0, 2.0]),
            domain_facts=None, stream_activations=[],
            selected_intent=IntentIR("bad"),
            selected_action=None,
            representation="cartesian",
            budget_consumed_ms=10.0, budget_total_ms=50.0,
            worlds_simulated=5, cycle_duration_ms=8.0,
            health_score=0.3, council_validated=False,
            decision_integrity=0.2, mission_drift=5.0,
            blocking_validator="RealityValidator",
        )
        result = PipelineResult(None, 0.3, PipelinePhase.COMPLETE,
                                 council_blocked=True, decision_trace=blocked_trace)
        infra.observe(result)

    assert infra.policy.current.recovery_mode is True
    assert infra.policy.current.risk_tolerance < 0.3
    assert infra.policy.current.exploration_budget < 0.3


def test_recovery_mode_exits_after_clean_cycles():
    """InfraManager exits recovery mode after sustained clean cycles."""
    infra = InfrastructureManager()
    from telos.core.runtime import DecisionTrace, PipelineResult, PipelinePhase

    for _ in range(10):
        blocked_trace = DecisionTrace(
            cycle_id=1, timestamp=0.0,
            world_state_snapshot=np.array([1.0, 2.0]),
            domain_facts=None, stream_activations=[],
            selected_intent=IntentIR("bad"),
            selected_action=None,
            representation="cartesian",
            budget_consumed_ms=10.0, budget_total_ms=50.0,
            worlds_simulated=5, cycle_duration_ms=8.0,
            health_score=0.3, council_validated=False,
            decision_integrity=0.2, mission_drift=5.0,
            blocking_validator="RealityValidator",
        )
        result = PipelineResult(None, 0.3, PipelinePhase.COMPLETE,
                                 council_blocked=True, decision_trace=blocked_trace)
        infra.observe(result)

    assert infra.policy.current.recovery_mode is True

    for _ in range(10):
        clean_trace = DecisionTrace(
            cycle_id=1, timestamp=0.0,
            world_state_snapshot=np.array([1.0, 2.0]),
            domain_facts=None, stream_activations=[],
            selected_intent=IntentIR("good"),
            selected_action=np.array([0.1]),
            representation="cartesian",
            budget_consumed_ms=10.0, budget_total_ms=50.0,
            worlds_simulated=5, cycle_duration_ms=8.0,
            health_score=0.9, council_validated=True,
            decision_integrity=0.9, mission_drift=0.5,
        )
        result = PipelineResult(None, 0.9, PipelinePhase.COMPLETE,
                                 decision_trace=clean_trace)
        infra.observe(result)

    assert infra.policy.current.recovery_mode is False


def test_recovery_mode_tightens_pipeline():
    """Pipeline with recovery mode produces stricter governance."""
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

    state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
    for _ in range(3):
        pipeline.execute(state)

    infra.enter_recovery()
    assert infra.policy.current.recovery_mode is True

    result = pipeline.execute(state)
    assert result is not None

    infra.exit_recovery()
    assert infra.policy.current.recovery_mode is False
