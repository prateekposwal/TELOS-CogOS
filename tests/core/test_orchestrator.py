"""Contract tests for DiscoveryOrchestrator — the end-to-end discovery
pipeline state machine (theory → bridge → counterfactual → compression →
publication), gated by identity/mission/project readiness."""
import pytest

from telos.core.discovery.orchestrator import DiscoveryOrchestrator


def _orchestrator():
    return DiscoveryOrchestrator()


def test_awaiting_identity_when_not_ready():
    o = _orchestrator()
    step = o.cycle(1, identity_active=False, mission_active=True,
                   project_active=True, n_theories=1, n_bridges=1)
    assert step == "awaiting_identity"


def test_awaiting_mission_when_identity_ready_only():
    o = _orchestrator()
    step = o.cycle(1, identity_active=True, mission_active=False,
                   project_active=True, n_theories=1, n_bridges=1)
    assert step == "awaiting_mission"


def test_awaiting_project_when_mission_ready():
    o = _orchestrator()
    step = o.cycle(1, identity_active=True, mission_active=True,
                   project_active=False, n_theories=1, n_bridges=1)
    assert step == "awaiting_project"


def test_theory_formation_when_no_theories():
    o = _orchestrator()
    step = o.cycle(1, True, True, True, n_theories=0, n_bridges=1)
    assert step == "theory_formation"


def test_bridge_discovery_when_no_bridges():
    o = _orchestrator()
    step = o.cycle(1, True, True, True, n_theories=2, n_bridges=0)
    assert step == "bridge_discovery"


def test_active_research_when_ready():
    o = _orchestrator()
    step = o.cycle(5, True, True, True, n_theories=2, n_bridges=3)
    assert step == "active_research"


def test_state_and_event_log():
    o = _orchestrator()
    o.cycle(1, True, True, True, n_theories=2, n_bridges=3)
    state = o.state
    assert hasattr(state, "step")
    assert o.to_dict()["step"] == "active_research"
    assert any("cycle_1" in s for s in o._step_log)