"""Honest contract tests for telos/core/research/seasons.py (ResearchSeasons)."""

from telos.core.research.seasons import (
    ResearchSeasons, SeasonConfig, SeasonPhase, SEASON_CYCLE,
)


def test_season_cycle_constant():
    assert SEASON_CYCLE == 100


def test_initial_phase_is_rest():
    s = ResearchSeasons()
    assert s.phase == SeasonPhase.REST


def test_phase_sequence_over_default_config():
    s = ResearchSeasons()
    assert s.get_phase(0) == SeasonPhase.EXPLORATION
    assert s.get_phase(19) == SeasonPhase.EXPLORATION
    assert s.get_phase(20) == SeasonPhase.COLLECTION
    assert s.get_phase(34) == SeasonPhase.COLLECTION
    assert s.get_phase(35) == SeasonPhase.DEEP_FOCUS
    assert s.get_phase(59) == SeasonPhase.DEEP_FOCUS
    assert s.get_phase(60) == SeasonPhase.BREAKTHROUGH
    assert s.get_phase(69) == SeasonPhase.BREAKTHROUGH
    assert s.get_phase(70) == SeasonPhase.VERIFICATION
    assert s.get_phase(84) == SeasonPhase.VERIFICATION
    assert s.get_phase(85) == SeasonPhase.PUBLICATION
    assert s.get_phase(89) == SeasonPhase.PUBLICATION
    assert s.get_phase(90) == SeasonPhase.REST
    assert s.get_phase(99) == SeasonPhase.REST


def test_phase_repeats_each_cycle():
    s = ResearchSeasons()
    assert s.get_phase(100) == SeasonPhase.EXPLORATION
    assert s.get_phase(120) == SeasonPhase.COLLECTION
    assert s.get_phase(135) == SeasonPhase.DEEP_FOCUS


def test_phase_critical_last_offset_returns_rest():
    s = ResearchSeasons()
    assert s.get_phase(99) == SeasonPhase.REST


def test_exploration_bonus():
    s = ResearchSeasons()
    assert s.exploration_bonus(0) == 1.5
    assert s.exploration_bonus(19) == 1.5
    assert s.exploration_bonus(45) == 1.3
    assert s.exploration_bonus(95) == 0.5
    assert s.exploration_bonus(21) == 1.0
    assert s.exploration_bonus(70) == 1.0


def test_to_dict_reflects_current_phase():
    s = ResearchSeasons()
    s.get_phase(45)
    d = s.to_dict()
    assert d["phase"] == SeasonPhase.DEEP_FOCUS.value
    assert "phase_cycle" in d


def test_custom_config_alters_phase_lengths():
    cfg = SeasonConfig(
        exploration_cycles=1, collection_cycles=1, deep_focus_cycles=1,
        breakthrough_cycles=1, verification_cycles=1, publication_cycles=1,
        rest_cycles=1,
    )
    s = ResearchSeasons(config=cfg)
    assert s.get_phase(0) == SeasonPhase.EXPLORATION
    assert s.get_phase(1) == SeasonPhase.COLLECTION
    assert s.get_phase(2) == SeasonPhase.DEEP_FOCUS
    assert s.get_phase(3) == SeasonPhase.BREAKTHROUGH
    assert s.get_phase(4) == SeasonPhase.VERIFICATION
    assert s.get_phase(5) == SeasonPhase.PUBLICATION
    assert s.get_phase(6) == SeasonPhase.REST
