"""Contract tests for telos/core/governance/base.py.

The Governance subsystem core types: AccessLevel and ReadinessState enums,
and the ReadinessCondition / FirewallVerdict / GovernanceReport dataclasses.
"""
from telos.core.governance.base import (
    AccessLevel,
    ReadinessState,
    ReadinessCondition,
    FirewallVerdict,
    GovernanceReport,
)


class TestAccessLevel:
    def test_values(self):
        assert AccessLevel.OBSERVE.value == "observe"
        assert AccessLevel.ANALYZE.value == "analyze"
        assert AccessLevel.ACTUATE.value == "actuate"
        assert AccessLevel.CLASSIFIED.value == "classified"

    def test_membership_and_lookup(self):
        # The four levels are disjoint members of one enum.
        assert AccessLevel.OBSERVE in AccessLevel
        assert AccessLevel.ANALYZE in AccessLevel
        assert AccessLevel.ACTUATE in AccessLevel
        assert AccessLevel.CLASSIFIED in AccessLevel
        assert AccessLevel("observe") is AccessLevel.OBSERVE


class TestReadinessState:
    def test_values(self):
        assert ReadinessState.LOCKED.value == "locked"
        assert ReadinessState.PENDING.value == "pending"
        assert ReadinessState.READY.value == "ready"
        assert ReadinessState.EXPIRED.value == "expired"


class TestReadinessCondition:
    def test_defaults(self):
        c = ReadinessCondition(condition_type="cycle_count", threshold=5.0)
        assert c.description == ""
        assert c.metadata == {}

    def test_fields(self):
        c = ReadinessCondition(
            condition_type="signal_detected", threshold=0.8,
            description="wait for the signal", metadata={"signal": "s1"},
        )
        assert c.condition_type == "signal_detected"
        assert c.threshold == 0.8
        assert c.description == "wait for the signal"
        assert c.metadata == {"signal": "s1"}


class TestFirewallVerdict:
    def test_defaults(self):
        v = FirewallVerdict(passed=True, reason="clear")
        assert v.blocked_by is None
        assert v.governance_signals == []

    def test_blocked_verdict(self):
        v = FirewallVerdict(
            passed=False, reason="loop detected",
            blocked_by="decision_firewall",
            governance_signals=[{"rule": "loop_trap"}],
        )
        assert v.passed is False
        assert v.blocked_by == "decision_firewall"
        assert v.governance_signals == [{"rule": "loop_trap"}]


class TestGovernanceReport:
    def test_defaults(self):
        r = GovernanceReport()
        assert r.stream_access_grants == 0
        assert r.stream_access_denials == 0
        assert r.locked_facts == 0
        assert r.ready_facts == 0
        assert r.firewall_blocked is False
        assert r.firewall_reason == ""

    def test_field_assignment(self):
        r = GovernanceReport(
            stream_access_grants=3,
            stream_access_denials=1,
            locked_facts=2,
            ready_facts=4,
            firewall_blocked=True,
            firewall_reason="trap detected",
        )
        assert r.stream_access_grants == 3
        assert r.stream_access_denials == 1
        assert r.locked_facts == 2
        assert r.ready_facts == 4
        assert r.firewall_blocked is True
        assert r.firewall_reason == "trap detected"