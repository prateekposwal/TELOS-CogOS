"""
TransparencyMonitor tests — decision trace capture, report generation.
"""

import numpy as np

from telos.audit.monitor import TransparencyMonitor
from telos.core.runtime import DecisionTrace
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR


def test_transparency_monitor():
    monitor = TransparencyMonitor()

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
    assert len(monitor.get_traces()) == 3


def test_monitor_empty_report():
    """TransparencyMonitor returns a placeholder when no cycles recorded."""
    monitor = TransparencyMonitor()
    report = monitor.generate_report()
    assert "No decision cycles recorded" in report
    assert len(monitor.get_traces()) == 0


def test_monitor_clear():
    """TransparencyMonitor.clear() empties the trace buffer."""
    monitor = TransparencyMonitor()
    trace = DecisionTrace(
        cycle_id=1, timestamp=0.0,
        world_state_snapshot=np.array([0.0, 0.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("test"), selected_action=np.array([0.0]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
    )
    monitor.record(trace)
    assert len(monitor.get_traces()) == 1
    monitor.clear()
    assert len(monitor.get_traces()) == 0


def test_monitor_max_entries_truncation():
    """TransparencyMonitor truncates to max_entries/2 when limit exceeded."""
    from telos.audit.monitor import MonitorConfig
    config = MonitorConfig(max_entries=10, auto_flush=False)
    monitor = TransparencyMonitor(config)

    for i in range(25):
        trace = DecisionTrace(
            cycle_id=i + 1, timestamp=float(i),
            world_state_snapshot=np.array([float(i)]),
            domain_facts=None, stream_activations=[],
            selected_intent=IntentIR("test"), selected_action=np.array([0.0]),
            representation="cartesian",
            budget_consumed_ms=10.0, budget_total_ms=50.0,
            worlds_simulated=5, cycle_duration_ms=8.0,
        )
        monitor.record(trace)

    assert len(monitor.get_traces()) < 10  # truncated below max_entries


def test_monitor_report_with_infra_stats():
    """TransparencyMonitor.generate_report includes infra stats when provided."""
    monitor = TransparencyMonitor()
    trace = DecisionTrace(
        cycle_id=1, timestamp=0.0,
        world_state_snapshot=np.array([0.0, 0.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR("test"), selected_action=np.array([0.0]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
    )
    monitor.record(trace)

    infra_stats = {
        "calibrator": {"calibrations": {}},
        "failures": {"by_type": {}, "total_failures": 0, "root_causes": {}},
        "policy": {"mission": "test", "risk_tolerance": 0.5, "exploration_budget": 0.3, "ambition_level": 0.5, "firewall_di_threshold": 0.5, "policy_changes": 0},
        "audit": {"cycles_observed": 1, "failures": 0, "governance_blocks": 0, "di_trend": 0.9, "md_trend": 0.1},
    }
    report = monitor.generate_report(infra_stats=infra_stats)
    assert "Infrastructure Health" in report
    assert "Mission Policy" in report
    assert "Audit Controller" in report
