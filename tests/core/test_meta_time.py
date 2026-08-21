"""Contract tests for MetaTime — the 5-scale temporal framework.

Each scale (REACTION→CIVILIZATIONAL) has a different decision architecture:
reaction scales reflect every cycle, civilizational every 100. get_active_scales
returns the scales whose reflection_interval divides the cycle; a decision's
impact horizon selects the smallest scale whose horizon can hold it.
"""
import pytest

from telos.core.timing.meta_time import MetaTime, TimeScale, TimeScaleConfig


def test_five_scales_exist():
    assert {s.value for s in TimeScale} == {
        "reaction", "learning", "project", "identity", "civilizational"}


def test_reaction_active_always():
    mt = MetaTime()
    for cycle in (0, 1, 2, 50):
        assert TimeScale.REACTION in mt.get_active_scales(cycle)


def test_scale_activates_on_reflection_interval():
    mt = MetaTime()
    active = mt.get_active_scales(10)  # learning reflects every 3; 10 % 3 != 0
    assert TimeScale.LEARNING not in active
    active = mt.get_active_scales(12)  # 12 % 3 == 0
    assert TimeScale.LEARNING in active


def test_civilizational_rarely_active():
    mt = MetaTime()
    assert TimeScale.CIVILIZATIONAL not in mt.get_active_scales(50)
    assert TimeScale.CIVILIZATIONAL in mt.get_active_scales(100)  # 100%100==0


def test_scale_for_decision_horizon():
    mt = MetaTime()
    assert mt.get_scale_for_decision(1) == TimeScale.REACTION
    assert mt.get_scale_for_decision(50) == TimeScale.PROJECT
    assert mt.get_scale_for_decision(100) == TimeScale.IDENTITY
    assert mt.get_scale_for_decision(100000) == TimeScale.CIVILIZATIONAL


def test_to_dict_shape():
    mt = MetaTime()
    d = mt.to_dict()
    assert "reaction" in d["scales"]
    assert d["scales"]["learning"]["horizon"] == 5