"""Research Seasons — exploration → collection → deep focus → breakthrough → verification → publication → rest."""

from __future__ import annotations
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger('telos_research_seasons')


class SeasonPhase(str, Enum):
    EXPLORATION = "exploration"
    COLLECTION = "collection"
    DEEP_FOCUS = "deep_focus"
    BREAKTHROUGH = "breakthrough"
    VERIFICATION = "verification"
    PUBLICATION = "publication"
    REST = "rest"


SEASON_CYCLE = 100  # full season cycle length in pipeline cycles


@dataclass
class SeasonConfig:
    exploration_cycles: int = 20
    collection_cycles: int = 15
    deep_focus_cycles: int = 25
    breakthrough_cycles: int = 10
    verification_cycles: int = 15
    publication_cycles: int = 5
    rest_cycles: int = 10


class ResearchSeasons:
    """Manages research season phase transitions."""

    def __init__(self, config: Optional[SeasonConfig] = None):
        self._config = config or SeasonConfig()
        self._phase = SeasonPhase.REST
        self._phase_start = 0

    def get_phase(self, cycle: int) -> SeasonPhase:
        offset = cycle % SEASON_CYCLE
        cum = 0
        for phase, length in [
            (SeasonPhase.EXPLORATION, self._config.exploration_cycles),
            (SeasonPhase.COLLECTION, self._config.collection_cycles),
            (SeasonPhase.DEEP_FOCUS, self._config.deep_focus_cycles),
            (SeasonPhase.BREAKTHROUGH, self._config.breakthrough_cycles),
            (SeasonPhase.VERIFICATION, self._config.verification_cycles),
            (SeasonPhase.PUBLICATION, self._config.publication_cycles),
            (SeasonPhase.REST, self._config.rest_cycles),
        ]:
            cum += length
            if offset < cum:
                if self._phase != phase:
                    self._phase = phase
                    self._phase_start = cycle
                    logger.info(f"ResearchSeasons: entering {phase.value} phase")
                return phase
        return SeasonPhase.REST

    @property
    def phase(self) -> SeasonPhase:
        return self._phase

    def exploration_bonus(self, cycle: int) -> float:
        p = self.get_phase(cycle)
        if p == SeasonPhase.EXPLORATION:
            return 1.5
        if p == SeasonPhase.DEEP_FOCUS:
            return 1.3
        if p == SeasonPhase.REST:
            return 0.5
        return 1.0

    def to_dict(self) -> dict:
        return {"phase": self._phase.value, "phase_cycle": self._phase_start}
