"""Tests for IdentityProjectionGate — F(I) formal domain restrictor."""

from telos.core.identity.projection_gate import IdentityProjectionGate
from telos.core.identity.system_self import IdentityCore, IdentityNarrative


class TestIdentityProjectionGate:

    def test_admits_reflex(self):
        gate = IdentityProjectionGate()
        assert gate.is_admissible("reflex") is True
        assert gate.is_admissible("halt") is True
        assert gate.is_admissible("emergency_stop") is True

    def test_admits_curiosity_with_core(self):
        gate = IdentityProjectionGate()
        assert gate.is_admissible("curiosity_explore", mission_active=True) is True

    def test_to_dict(self):
        gate = IdentityProjectionGate()
        d = gate.to_dict()
        assert "core_values" in d
        assert "narrative_role" in d
        assert "narrative_markers" in d
        assert "curiosity" in d["core_values"]

    def test_project_intents(self):
        gate = IdentityProjectionGate()
        class MockIntent:
            def __init__(self, t):
                self.intent_type = t
        intents = [MockIntent("reflex"), MockIntent("curiosity_explore"), MockIntent("plan_trajectory")]
        result = gate.project_intents(intents, mission_active=True, mission_ids=["m1"])
        assert len(result) == 3

    def test_custom_narrative(self):
        narrative = IdentityNarrative(role="explorer", markers={"curious", "bold"})
        gate = IdentityProjectionGate(identity_narrative=narrative)
        assert gate.to_dict()["narrative_role"] == "explorer"
        assert "bold" in gate.to_dict()["narrative_markers"]
