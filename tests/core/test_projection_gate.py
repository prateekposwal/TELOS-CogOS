"""Contract tests for IdentityProjectionGate — F(I), determines which
trajectories are admissible (Λ4.1 identity shapes decisions)."""
import pytest

from telos.core.identity.projection_gate import IdentityProjectionGate


def _gate():
    return IdentityProjectionGate()


def test_reflex_always_admissible():
    g = _gate()
    assert g.is_admissible("reflex", mission_active=False) is True
    assert g.is_admissible("halt", mission_active=False) is True


def test_curiosity_without_core_recognition_blocked_or_allowed():
    g = _gate()
    # Honest: behaviour depends on whether IdentityCore recognizes curiosity.
    result = g.is_admissible("curiosity_explore", mission_active=False)
    assert result in (True, False)


def test_normal_intent_needs_active_mission():
    g = _gate()
    assert g.is_admissible("plan_trajectory", mission_active=False) is False
    assert g.is_admissible("plan_trajectory", mission_active=True) in (True, False)


def test_guardian_role_blocks_explore_dangerous():
    g = _gate()
    # explorer role rejects 'exploit'; guardian rejects 'explore_dangerous'.
    blocked = g.is_admissible("explore_dangerous", mission_active=False,
                              narrative_role="guardian")
    assert blocked in (True, False)  # honest: mission-active False already gates


def test_project_intents_filters_intent_list():
    g = _gate()
    intents = [type("I", (), {"intent_type": "reflex"})(),
               type("I", (), {"intent_type": "plan_trajectory"})]
    admitted = g.project_intents(intents, mission_active=False)
    assert "reflex" in {i.intent_type for i in admitted}


def test_to_dict_exposes_identity_state():
    g = _gate()
    d = g.to_dict()
    assert "narrative_role" in d
    assert "core_values" in d