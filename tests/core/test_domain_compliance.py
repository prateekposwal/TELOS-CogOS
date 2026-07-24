"""
Domain plugin compliance tests — verify every plugin satisfies the DSI contract.

Each domain Simulator must implement all DomainSimulator abstract methods,
and each Adapter must implement all DomainAdapter abstract methods.
"""

import numpy as np

from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter


def _check_domain_simulator(sim, name: str):
    """Verify a simulator implements all DSI contract methods correctly."""
    assert isinstance(sim, DomainSimulator), f"{name} is not a DomainSimulator"

    sim.initialize()

    state = sim.initial_state() if hasattr(sim, 'initial_state') else np.zeros(2)
    assert isinstance(state, np.ndarray), f"{name}.initial_state() must return ndarray"

    transitions = sim.legal_transitions(state)
    assert isinstance(transitions, list), f"{name}.legal_transitions() must return list"
    if transitions:
        assert isinstance(transitions[0], np.ndarray), f"{name}.legal_transitions() items must be ndarray"

    if transitions:
        next_state = sim.transition(state, transitions[0])
        assert isinstance(next_state, np.ndarray), f"{name}.transition() must return ndarray"
        assert next_state.shape == state.shape, f"{name}.transition() shape mismatch"

    worlds = sim.simulate(state, horizon=3)
    assert isinstance(worlds, list), f"{name}.simulate() must return list"
    if worlds:
        from telos.world.world import World
        assert isinstance(worlds[0], World), f"{name}.simulate() items must be World"

    facts = sim.get_facts(state)
    from telos.world.facts import DomainFacts
    assert isinstance(facts, DomainFacts), f"{name}.get_facts() must return DomainFacts"
    assert hasattr(facts, 'resources'), f"{name}.get_facts().resources missing"
    assert hasattr(facts, 'constraints'), f"{name}.get_facts().constraints missing"

    terminal = sim.terminal(state)
    assert isinstance(terminal, (bool, np.bool_)), f"{name}.terminal() must return bool"

    report = sim.evaluate(state)
    from telos.core.contracts.domain_model import EvaluationReport
    assert isinstance(report, EvaluationReport), f"{name}.evaluate() must return EvaluationReport"
    assert isinstance(report.score, float), f"{name}.evaluate().score must be float"

    sim.cleanup()


def _check_domain_adapter(adapter, name: str):
    """Verify an adapter implements all DomainAdapter contract methods."""
    assert isinstance(adapter, DomainAdapter), f"{name} is not a DomainAdapter"

    state = np.zeros(6)
    fwd = adapter.forward(state)
    assert isinstance(fwd, np.ndarray), f"{name}.forward() must return ndarray"

    action = np.zeros(6)
    inv = adapter.inverse(action)
    assert isinstance(inv, np.ndarray), f"{name}.inverse() must return ndarray"


def test_gridworld_compliance():
    from telos.examples.gridworld.simulator import GridWorldSimulator
    _check_domain_simulator(GridWorldSimulator(size=5), "GridWorldSimulator")


def test_chess_compliance():
    from telos.examples.chess.simulator import ChessDomainSimulator
    _check_domain_simulator(ChessDomainSimulator(), "ChessDomainSimulator")


def test_synthetic_compliance():
    from telos.examples.synthetic.simulator import SyntheticWorld
    _check_domain_simulator(SyntheticWorld(noise_std=0.0), "SyntheticWorld")


def test_mock_simulator_compliance():
    from tests.core.conftest import MockSimulator
    _check_domain_simulator(MockSimulator(), "MockSimulator")


def test_market_adapter_compliance():
    from telos.adapters.base_adapter import MarketAdapter
    _check_domain_adapter(MarketAdapter(), "MarketAdapter")


def test_chess_adapter_compliance():
    from telos.adapters.base_adapter import ChessAdapter
    _check_domain_adapter(ChessAdapter(), "ChessAdapter")
