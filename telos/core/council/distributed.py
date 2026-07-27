"""Distributed Council — multi-agent validation with secondary agents.

Each secondary agent runs its own pipeline instance and reports verdicts.
The primary council aggregates all verdicts into a weighted consensus.
"""

from __future__ import annotations
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

from telos.core.council.base import ValidationSignal, CouncilVerdict

logger = logging.getLogger('telos_distributed_council')


class AgentRole(str, Enum):
    PRIMARAY = "primary"
    SKEPTIC = "skeptic"
    EXPLORER = "explorer"
    CONSERVATIVE = "conservative"
    ANALYST = "analyst"


@dataclass
class AgentVerdict:
    agent_id: str
    role: AgentRole
    validated: bool
    decision_integrity: float
    mission_drift: float
    signals: List[Dict] = field(default_factory=list)
    weight: float = 1.0


class DistributedCouncil:
    """Multi-agent council that aggregates verdicts from secondary agents."""

    def __init__(self):
        self._agents: Dict[str, AgentRole] = {}
        self._agent_votes: Dict[str, AgentVerdict] = {}
        self._min_agents = 1

    def register_agent(self, agent_id: str, role: AgentRole = AgentRole.ANALYST) -> None:
        self._agents[agent_id] = role
        logger.info(f"DistributedCouncil: registered agent '{agent_id}' as {role.value}")

    def submit_verdict(self, agent_id: str, validated: bool, di: float, md: float,
                       signals: Optional[List[Dict]] = None) -> None:
        role = self._agents.get(agent_id, AgentRole.ANALYST)
        weight = {"primary": 1.0, "skeptic": 0.8, "explorer": 0.6,
                  "conservative": 0.7, "analyst": 0.5}.get(role, 0.5)
        self._agent_votes[agent_id] = AgentVerdict(
            agent_id=agent_id, role=role, validated=validated,
            decision_integrity=di, mission_drift=md,
            signals=signals or [], weight=weight,
        )

    def aggregate(self) -> AgentVerdict:
        votes = list(self._agent_votes.values())
        if not votes:
            return AgentVerdict("none", AgentRole.PRIMARAY, True, 1.0, 0.0)

        total_weight = sum(v.weight for v in votes)
        if total_weight == 0:
            total_weight = 1.0

        avg_di = sum(v.decision_integrity * v.weight for v in votes) / total_weight
        avg_md = sum(v.mission_drift * v.weight for v in votes) / total_weight
        validated_count = sum(1 for v in votes if v.validated)
        validated = validated_count > len(votes) / 2

        all_signals = []
        for v in votes:
            all_signals.extend(v.signals)

        return AgentVerdict(
            agent_id="aggregated", role=AgentRole.PRIMARAY,
            validated=validated, decision_integrity=avg_di,
            mission_drift=avg_md, signals=all_signals,
            weight=1.0,
        )

    def to_dict(self) -> Dict:
        return {
            "registered_agents": len(self._agents),
            "voting_agents": len(self._agent_votes),
            "agents": {aid: r.value for aid, r in self._agents.items()},
        }
