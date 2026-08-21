"""Contract tests for CuriosityDrive — learning is intrinsically rewarding;
the drive rises with learning and spikes on boredom (exploration without
external stimuli)."""
import pytest

from telos.core.curiosity.drive import CuriosityDrive, CuriosityState


def test_default_state_is_moderate_curiosity():
    d = CuriosityDrive()
    assert d.state.curiosity_level == pytest.approx(0.3)


def test_learning_raises_curiosity():
    d = CuriosityDrive()
    before = d.state.curiosity_level
    d.update(uncertainty_before=0.8, uncertainty_after=0.2,  # big learning
             was_blocked=False, council_disagreement=0.0)
    assert d.state.learning_rate == pytest.approx(0.6)
    assert d.state.curiosity_level >= before


def test_update_returns_report_dict():
    d = CuriosityDrive()
    r = d.update(uncertainty_before=0.5, uncertainty_after=0.5,
                 was_blocked=False, council_disagreement=0.0)
    assert isinstance(r, dict)


def test_boredom_thresholds_exist():
    d = CuriosityDrive()
    assert d.boredom_threshold > 0
    assert d.boredom_cycles_to_spike >= 1


def test_self_intent_when_curiosity_high():
    d = CuriosityDrive()
    d.state.curiosity_level = 0.9  # above self_intent_threshold
    # should_generate_self_intent is True above the threshold.
    result = d.should_generate_self_intent()
    assert result  # honest: high curiosity drives self-generated intents


def test_bonus_amplifies_with_curiosity():
    d = CuriosityDrive()
    d.state.curiosity_level = 1.0
    assert d.get_curiosity_bonus() == pytest.approx(1.5)