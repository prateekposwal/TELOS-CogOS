"""Contract tests for telos/core/contracts/domain_model.py."""

import pytest

from telos.core.contracts.domain_model import (
    WorldSpec, DomainSimulator, DomainAdapter, EvaluationReport,
    Constraint, RiskProfile, Objectives,
)
from tests.core.conftest import MockSimulator


def test_world_spec_valid():
    ws = WorldSpec(name='grid', state_dim=3)
    assert ws.validate() is None


def test_world_spec_missing_name_invalid():
    assert WorldSpec(name='', state_dim=2).validate() \
        == 'WorldSpec.name is required and must be non-empty'


def test_world_spec_bad_state_dim_invalid():
    assert WorldSpec(name='x', state_dim=0).validate() \
        == 'WorldSpec.state_dim must be a positive integer'


def test_world_spec_unknown_mode_invalid():
    ws = WorldSpec(name='x', state_dim=2, authorized_modes={'ACT', 'BOGUS'})
    assert 'unknown modes' in ws.validate()


def test_world_spec_bad_escalation_policy_invalid():
    ws = WorldSpec(name='x', state_dim=2, escalation_policy='sometimes')
    assert 'escalation_policy' in ws.validate()


def test_world_spec_required_escalation_valid():
    ws = WorldSpec(name='x', state_dim=2, escalation_policy='required')
    assert ws.validate() is None


def test_world_spec_default_authorized_modes():
    modes = WorldSpec(name='x', state_dim=1).authorized_modes
    assert {'ACT', 'DEFER', 'ABSTAIN', 'ESCALATE', 'BLOCK'} <= modes


def test_world_spec_to_dict():
    ws = WorldSpec(name='grid', state_dim=3, action_dim=2,
                   escalation_policy='required')
    d = ws.to_dict()
    assert d['name'] == 'grid'
    assert d['state_dim'] == 3
    assert d['action_dim'] == 2
    assert d['escalation_policy'] == 'required'
    assert 'ACT' in d['authorized_modes']


def test_mock_simulator_world_spec():
    spec = MockSimulator().world_spec()
    assert spec.name == 'mock'
    assert spec.state_dim == 2
    assert spec.observability == 'high'


def test_domain_simulator_default_world_spec():
    class SimpleSim(DomainSimulator):
        name = 'mysim'
        state_dim = 4
        action_dim = 2

        def initialize(self): pass
        def cleanup(self): pass
        def legal_transitions(self, state): return []
        def transition(self, state, action): return state
        def simulate(self, state, horizon): return []
        def get_facts(self, state): pass
        def terminal(self, state): return False
        def evaluate(self, state): return EvaluationReport()

    spec = SimpleSim().world_spec()
    assert spec.name == 'mysim'
    assert spec.state_dim == 4
    assert spec.action_dim == 2


def test_domain_simulator_is_abstract():
    with pytest.raises(TypeError):
        DomainSimulator()


def test_domain_adapter_is_abstract_name():
    class BadAdapter(DomainAdapter):
        def forward(self, d): return d

    with pytest.raises(TypeError):
        BadAdapter()


def test_domain_adapter_declared_state_dim():
    class Adapter(DomainAdapter):
        state_dim = 6

        def forward(self, d): return d
        def inverse(self, a): return a

        @property
        def name(self): return 'ad'

        def intent_to_action(self, i, s, md): return s

    assert Adapter().declared_state_dim() == 6


def test_domain_adapter_no_state_dim():
    class Adapter(DomainAdapter):
        def forward(self, d): return d
        def inverse(self, a): return a

        @property
        def name(self): return 'ad'

        def intent_to_action(self, i, s, md): return s

    assert Adapter().declared_state_dim() is None


def test_evaluation_report_score():
    er = EvaluationReport(objectives={'utility': 5.0}, risks=2.0)
    assert er.score == 3.0


def test_evaluation_report_default_score():
    assert EvaluationReport().score == 0.0


def test_supporting_dataclasses():
    c = Constraint(name='c', description='d')
    assert c.name == 'c'
    r = RiskProfile(harm_types=['x'], threshold=0.5)
    assert r.harm_types == ['x']
    assert r.threshold == 0.5
    o = Objectives(goals=['g'])
    assert o.goals == ['g']
