"""Discovery Operating System — orchestrates the full discovery pipeline.

Identity -> Mission -> Project -> ResearchWorkspace ->
  (TheoryBuilder, Ecology, Evidence) ->
  ScientificTaste -> BridgeDiscovery -> ExperimentDesign ->
  CounterfactualTests -> KnowledgeCompression -> Publication
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger('telos_discovery_os')


@dataclass
class DiscoveryPipelineState:
    step: str = "idle"
    identity_ready: bool = False
    mission_ready: bool = False
    project_ready: bool = False
    theories_active: int = 0
    bridges_found: int = 0
    experiments_run: int = 0
    counterfactuals_run: int = 0
    compressions_done: int = 0
    publications_done: int = 0


class DiscoveryOrchestrator:
    """Orchestrates the full discovery pipeline end-to-end."""

    def __init__(self):
        self._state = DiscoveryPipelineState()
        self._step_log: List[str] = []

    def cycle(self, cycle: int, identity_active: bool, mission_active: bool,
              project_active: bool, n_theories: int, n_bridges: int) -> str:
        """Run one cycle of the discovery pipeline.
            Args:
                identity_active: the identity_active argument for this call.
                mission_active: the mission_active argument for this call.
                project_active: the project_active argument for this call.
                n_theories: the n_theories argument for this call.
                n_bridges: the n_bridges argument for this call.
        """
        self._state.identity_ready = identity_active
        self._state.mission_ready = mission_active
        self._state.project_ready = project_active
        self._state.theories_active = n_theories
        self._state.bridges_found = n_bridges

        if not identity_active:
            step = "awaiting_identity"
        elif not mission_active:
            step = "awaiting_mission"
        elif not project_active:
            step = "awaiting_project"
        elif n_theories == 0:
            step = "theory_formation"
        elif n_bridges == 0:
            step = "bridge_discovery"
        else:
            step = "active_research"

        self._state.step = step
        self._step_log.append(f"cycle_{cycle}:{step}")
        if len(self._step_log) > 100:
            self._step_log = self._step_log[-100:]
        return step

    @property
    def state(self) -> DiscoveryPipelineState:
        return self._state

    def to_dict(self) -> dict:
        return {
            "step": self._state.step,
            "theories": self._state.theories_active,
            "bridges": self._state.bridges_found,
            "log_length": len(self._step_log),
        }
