"""Contract tests for the council validator layer (Truth-Anchored Advisors).

Each validator is a specialized cognitive process that performs ONE kind of
truth-check and outputs a ValidationSignal. A passed=False signal blocks action.
These tests verify the REAL contracts: RealityValidator rejects NaN/Inf
states and over-magnitude actions; the governance base types carry their
documented fields.
"""
import numpy as np
import pytest

from telos.core.council.base import Validator, ValidationSignal
from telos.core.council.validators.reality import RealityValidator
from telos.core.governance.base import (
    AccessLevel, ReadinessState, ReadinessCondition, FirewallVerdict,
    GovernanceReport,
)
from telos.intent_ir import IntentIR
from telos.world.world import World


class TestRealityValidator:
    """The first line of defense against wishful reasoning."""

    def test_no_intent_passes_as_no_op(self):
        v = RealityValidator()
        sig = v.validate(World(state=np.zeros(2)), None)
        assert sig.passed is True
        assert sig.confidence == 0.0

    def test_clean_state_and_action_passes(self):
        v = RealityValidator()
        world = World(state=np.zeros(2))
        intent = IntentIR(
            intent_type="move", confidence=0.8,
            params={"action_vector": np.array([0.1, 0.2])},
        )
        sig = v.validate(world, intent)
        assert sig.passed is True, sig.reason
        assert sig.confidence == 0.9

    def test_nan_state_is_blocked(self):
        v = RealityValidator()
        world = World(state=np.array([0.0, np.nan]))
        sig = v.validate(world, IntentIR(intent_type="move", confidence=0.8))
        assert sig.passed is False
        assert "NaN" in sig.reason
        assert sig.metadata["issue_count"] >= 1

    def test_inf_state_is_blocked(self):
        v = RealityValidator()
        world = World(state=np.array([0.0, np.inf]))
        sig = v.validate(world, IntentIR(intent_type="move", confidence=0.8))
        assert sig.passed is False
        assert "Inf" in sig.reason

    def test_oversized_action_norm_is_blocked(self):
        v = RealityValidator()
        world = World(state=np.zeros(2))
        intent = IntentIR(
            intent_type="jump", confidence=0.8,
            params={"action_vector": np.array([0.0, 200.0])},
        )
        sig = v.validate(world, intent)
        assert sig.passed is False
        assert "exceeds 100" in sig.reason

    def test_bounds_constraint_blocked(self):
        import numpy as np2
        from telos.world.facts import DomainFacts
        v = RealityValidator()
        world = World(state=np.zeros(2))
        facts = DomainFacts(
            state=np.zeros(2), resources={}, constraints=["bounds"],
            events=[], metrics={},
        )
        sig = v.validate(world, IntentIR(intent_type="move", confidence=0.8),
                         domain_facts=facts)
        assert sig.passed is False
        assert "out-of-bounds" in sig.reason


class TestGovernanceBaseTypes:
    """The governance dataclass/enum contracts."""

    def test_access_level_members(self):
        assert {lv.value for lv in AccessLevel} == {
            "observe", "analyze", "actuate", "classified"}

    def test_readiness_state_members(self):
        assert {s.value for s in ReadinessState} == {
            "locked", "pending", "ready", "expired"}

    def test_readiness_condition_carries_documented_fields(self):
        rc = ReadinessCondition(condition_type="cycle_count", threshold=5.0)
        assert rc.condition_type == "cycle_count"
        assert rc.threshold == 5.0
        assert rc.description == ""
        assert rc.metadata == {}

    def test_firewall_verdict_contract(self):
        v = FirewallVerdict(passed=False, reason="low DI", blocked_by="low_integrity")
        assert v.passed is False
        assert v.blocked_by == "low_integrity"
        assert v.governance_signals == []

    def test_governance_report_defaults(self):
        r = GovernanceReport()
        assert r.stream_access_grants == 0
        assert r.firewall_blocked is False
        assert r.firewall_reason == ""