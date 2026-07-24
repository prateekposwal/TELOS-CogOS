"""
VideoDomainAdapter — Bridges TELOS Pipeline to video ball tracking.

Usage:
    adapter = VideoDomainAdapter()
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=adapter,
        simulator=VideoDomainSimulator(),
    ))
    pipeline.register_stream(ProxyStream(skill_lib))
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
import numpy as np

from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR

logger = logging.getLogger('telos_video')


class VideoDomainSimulator(DomainSimulator):

    DOMAIN = "video_analysis"

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        return [np.array([1, 0]), np.array([-1, 0]), np.array([0, 1]), np.array([0, -1])]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        return state + action

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        return [World(state=state.copy()) for _ in range(5)]

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        return DomainFacts(
            state=state.copy(),
            resources={},
            constraints=[],
            events=[],
            metrics={
                "frame_count": float(state[0]) if len(state) > 0 else 0,
                "detection_rate": float(state[1]) if len(state) > 1 else 0,
                "quality_score": float(state[2]) if len(state) > 2 else 0,
            },
        )

    def terminal(self, state: np.ndarray) -> bool:
        return False

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        quality = float(state[2]) if len(state) > 2 else 0
        return EvaluationReport(
            objectives={"quality": quality},
            risks=1.0 - quality,
        )

    @property
    def domain(self) -> str:
        return self.DOMAIN


class VideoDomainAdapter(DomainAdapter):

    def forward(self, state: np.ndarray) -> np.ndarray:
        return state

    def inverse(self, action: np.ndarray) -> np.ndarray:
        return action

    def intent_to_action(self, intent: IntentIR,
                          state: np.ndarray,
                          mission_dir: np.ndarray) -> np.ndarray:
        intent_type = intent.intent_type
        if intent_type == "proxy_track":
            proxy_params = intent.params or {}
            pos = proxy_params.get("estimated_position")
            if pos is not None:
                return np.array([pos[0], pos[1], 0.0], dtype=float)
            return np.zeros(3)
        elif intent_type == "reflex":
            return state * -0.5
        return np.zeros(3)

    @property
    def name(self) -> str:
        return "video"
