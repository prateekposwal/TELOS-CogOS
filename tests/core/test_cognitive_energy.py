"""Contract tests for CognitiveEnergy — mental fatigue and decision quality.

Energy starts full; hard decisions consume energy and degrade decision
quality (less exploration, more noise, overconfidence). Rest and recharge
restore energy. apply_effects modulates pipeline config only when fatigued
(below 50% ratio).
"""
import pytest

from telos.core.reasoning.energy.cognitive_energy import (
    CognitiveEnergy, EnergyState, EnergyEffects,
)


def test_starts_full():
    e = CognitiveEnergy()
    assert e.energy_ratio == pytest.approx(1.0)
    assert e.is_fatigued is False


def test_energy_state_ratio_properties():
    s = EnergyState(current_energy=20.0, max_energy=100.0, recharge_rate=5.0,
                    fatigue_level=0.0)
    assert s.energy_ratio == pytest.approx(0.2)
    assert s.is_fatigued is True
    s2 = EnergyState(95.0, 100.0, 5.0, 0.0)
    assert s2.is_rested is True


def test_consume_drains_energy_on_hard_decision():
    e = CognitiveEnergy(max_energy=100.0, base_cost=2.0, difficulty_scale=10.0)
    before = e._state.current_energy
    e.consume(1.0)  # max difficulty
    assert e._state.current_energy < before


def test_many_hard_decisions_lead_to_fatigue():
    e = CognitiveEnergy(max_energy=20.0, base_cost=2.0, difficulty_scale=10.0)
    for _ in range(10):
        e.consume(1.0)
    assert e.is_fatigued is True


def test_rest_recovers_energy_bounded_by_max():
    e = CognitiveEnergy(max_energy=100.0, recharge_rate=5.0)
    e._state.current_energy = 10.0
    e.rest(cycles=3)
    assert e._state.current_energy == pytest.approx(25.0)
    e.rest(cycles=100)
    assert e._state.current_energy == pytest.approx(100.0)


def test_recharge_full():
    e = CognitiveEnergy(max_energy=100.0)
    e._state.current_energy = 5.0
    e.recharge()
    assert e._state.current_energy == pytest.approx(100.0)


def test_effects_fields_present_and_ranged():
    e = CognitiveEnergy()
    effects = e.consume(1.0)
    assert isinstance(effects, EnergyEffects)
    assert 0.0 <= effects.exploration_modifier <= 1.0
    assert -1.0 <= effects.confidence_bias <= 1.0
    assert 0.0 <= effects.decision_noise <= 1.0
    assert 0.0 <= effects.default_bias <= 1.0
    assert 0.0 <= effects.novelty_modifier <= 1.0
    assert 0.5 <= effects.speed_modifier <= 1.5


def test_apply_effects_untouched_when_rested():
    e = CognitiveEnergy(max_energy=100.0)
    cfg = {"exploration_budget": 0.5, "evaluation_noise": 0.1}
    out = e.apply_effects(cfg)
    assert out == cfg


def test_apply_effects_reduces_exploration_when_fatigued():
    e = CognitiveEnergy(max_energy=20.0, base_cost=2.0, difficulty_scale=10.0)
    for _ in range(8):
        e.consume(1.0)
    cfg = {"exploration_budget": 0.5}
    out = e.apply_effects(cfg)
    assert out["exploration_budget"] < 0.5


def test_to_dict_snapshot():
    e = CognitiveEnergy()
    e.consume(0.5)
    d = e.to_dict()
    assert "energy_ratio" in d and "fatigue_level" in d
    assert "current_effects" in d
    import json
    json.dumps(d)