"""Meta-Time — 5-scale temporal framework.

Reaction Time -> Learning -> Project -> Identity -> Civilizational.
Each scale has different decision architecture.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict

logger = logging.getLogger('telos_meta_time')


class TimeScale(str, Enum):
    REACTION = "reaction"
    LEARNING = "learning"
    PROJECT = "project"
    IDENTITY = "identity"
    CIVILIZATIONAL = "civilizational"


@dataclass
class TimeScaleConfig:
    scale: TimeScale
    cycle_multiplier: int
    reflection_interval: int
    decision_horizon: int


SCALES = {
    TimeScale.REACTION: TimeScaleConfig(TimeScale.REACTION, 1, 1, 1),
    TimeScale.LEARNING: TimeScaleConfig(TimeScale.LEARNING, 10, 3, 5),
    TimeScale.PROJECT: TimeScaleConfig(TimeScale.PROJECT, 100, 10, 50),
    TimeScale.IDENTITY: TimeScaleConfig(TimeScale.IDENTITY, 1000, 50, 500),
    TimeScale.CIVILIZATIONAL: TimeScaleConfig(TimeScale.CIVILIZATIONAL, 10000, 100, 5000),
}


class MetaTime:
    def get_active_scales(self, cycle: int) -> Dict[TimeScale, TimeScaleConfig]:
        return {s: c for s, c in SCALES.items() if cycle % c.reflection_interval == 0}

    def get_scale_for_decision(self, impact_horizon: int) -> TimeScale:
        for scale, config in SCALES.items():
            if impact_horizon <= config.decision_horizon:
                return scale
        return TimeScale.CIVILIZATIONAL

    def to_dict(self) -> dict:
        return {
            "scales": {s.value: {"mult": c.cycle_multiplier, "reflect": c.reflection_interval,
                                 "horizon": c.decision_horizon} for s, c in SCALES.items()},
        }
