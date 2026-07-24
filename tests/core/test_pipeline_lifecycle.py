"""Tests for Pipeline lifecycle: shutdown, checkpoint restore, recovery/council callbacks."""
import numpy as np
import os
import tempfile
from unittest.mock import MagicMock

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.infra_manager.infrastructure_manager import InfrastructureManager


def _make_trace(cycle_id=1, integrity=1.0, drift=0.0, health=0.5,
                validated=True, blocked=False, blocking_val=None):
    from telos.core.runtime import DecisionTrace
    from telos.world.facts import DomainFacts
    return DecisionTrace(
        cycle_id=cycle_id, timestamp=0.0,
        world_state_snapshot=np.zeros(2),
        domain_facts=DomainFacts(state=np.zeros(2), resources={},
                                  constraints=[], events=[], metrics={}),
        stream_activations=[], selected_intent=None, selected_action=None,
        representation="", budget_consumed_ms=0.0, budget_total_ms=100.0,
        worlds_simulated=0, cycle_duration_ms=0.0, health_score=health,
        council_validated=validated, decision_integrity=integrity,
        mission_drift=drift, blocking_validator=blocking_val,
        council_signals=[{"validator": "test", "passed": blocked}],
    )


def _make_result(trace, health=0.5, blocked=False):
    from telos.core.runtime import PipelineResult
    return PipelineResult(
        selected_trajectory=None, health_score=health,
        pipeline_phase=None, worlds_generated=0,
        council_blocked=blocked, decision_integrity=trace.decision_integrity,
        mission_drift=trace.mission_drift, decision_trace=trace,
    )


class TestPipelineLifecycle:

    def test_shutdown_does_not_crash(self):
        config = PipelineConfig()
        pipeline = TelosV14Pipeline(config)
        pipeline.shutdown()

    def test_shutdown_with_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(
                checkpoint_path=os.path.join(tmp, "ckpt"),
                knowledge_path=os.path.join(tmp, "kg.json"),
                ledger_path=os.path.join(tmp, "ledger.json"),
            )
            pipeline = TelosV14Pipeline(config)
            pipeline.shutdown()

    def test_recovery_listener_called(self):
        infra = InfrastructureManager()
        calls = []
        infra.on_recovery_event(lambda mode: calls.append(mode))
        infra.enter_recovery()
        assert "enter" in calls
        infra.exit_recovery()
        assert "exit" in calls

    def test_council_block_listener_called(self):
        infra = InfrastructureManager()
        calls = []
        infra.on_council_block(lambda info: calls.append(info))
        trace = _make_trace(blocking_val="test_val", blocked=False)
        result = _make_result(trace, blocked=True)
        infra.observe(result)
        assert len(calls) > 0

    def test_observe_starved_budget_records_failure(self):
        infra = InfrastructureManager()
        trace = _make_trace(health=0.2, validated=True, integrity=0.5, drift=0.5)
        result = _make_result(trace, health=0.2)
        infra.observe(result)
        recent = infra.failures.get_recent_failures(n=5)
        budget_fails = [f for f in recent if f.failure_type == "budget_starvation"]
        assert len(budget_fails) > 0

    def test_recovery_mode_entered_on_consecutive_failures(self):
        infra = InfrastructureManager()
        for i in range(5):
            trace = _make_trace(cycle_id=i, integrity=0.2, drift=6.0,
                                validated=False, blocked=True,
                                blocking_val="test")
            result = _make_result(trace, blocked=True)
            infra.observe(result, total_streams=4)
        assert infra.policy.current.recovery_mode

    def test_consult_knowledge_throttling(self):
        infra = InfrastructureManager()
        r1 = infra.consult_knowledge("test_domain", cycle=1)
        assert not r1.get("throttled", False)
        r2 = infra.consult_knowledge("test_domain", cycle=2)
        assert r2.get("throttled", True)
        r3 = infra.consult_knowledge("test_domain", cycle=5)
        assert not r3.get("throttled", False)
