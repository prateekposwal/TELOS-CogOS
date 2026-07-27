"""Representation Ecology — representations compete, cooperate, merge, split, die.

Implements insights 3 (Knowledge Ecology) and 14 (Representation Ecology).
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Any

logger = logging.getLogger('telos_ecology')


class EcologicalRole(str, Enum):
    KEYSTONE = "keystone"
    CANOPY = "canopy"
    BRIDGE = "bridge"
    SPECIALIST = "specialist"
    PIONEER = "pioneer"
    DECOMPOSER = "decomposer"
    HYBRID = "hybrid"


class NicheRelation(str, Enum):
    COMPETING = "competing"
    SYMBIOTIC = "symbiotic"
    BRIDGED = "bridged"
    NEUTRAL = "neutral"
    SPECIALIZED = "specialized"


@dataclass
class Niche:
    id: str
    name: str
    description: str = ""
    role: EcologicalRole = EcologicalRole.SPECIALIST
    birth_cycle: int = 0
    marginal_discovery_rate: float = 0.0
    exploration_depth: float = 0.0
    stagnation_cycles: int = 0
    bridge_count: int = 0
    lifecycle_stage: str = "birth"
    peak_productivity: float = 0.0
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    @property
    def is_exhausted(self) -> bool:
        return self.marginal_discovery_rate < 0.01 and self.exploration_depth > 0.5


@dataclass
class EcosystemRelation:
    source_id: str
    target_id: str
    relation: NicheRelation
    strength: float


class Ecosystem:
    """Manages the ecosystem of representations."""

    def __init__(self):
        self._niches: Dict[str, Niche] = {}
        self._relations: List[EcosystemRelation] = []
        self._count: int = 0

    def register(self, name: str, role: EcologicalRole = EcologicalRole.PIONEER,
                 parent_id: Optional[str] = None, cycle: int = 0) -> Niche:
        nid = f"niche_{int(time.time() * 1000)}_{self._count}"
        self._count += 1
        n = Niche(id=nid, name=name, role=role,
                  birth_cycle=cycle, parent_id=parent_id)
        self._niches[nid] = n
        if parent_id and parent_id in self._niches:
            self._niches[parent_id].children_ids.append(nid)
        logger.info(f"Ecosystem: registered niche '{name}' ({nid}) role={role.value}")
        return n

    def relate(self, source_id: str, target_id: str,
               relation: NicheRelation, strength: float = 0.5) -> None:
        self._relations.append(EcosystemRelation(source_id, target_id, relation, strength))

    def update_discovery_rate(self, niche_id: str, new_discoveries: int,
                               total_effort: float) -> None:
        n = self._niches.get(niche_id)
        if n is None:
            return
        n.marginal_discovery_rate = new_discoveries / max(total_effort, 1)
        if n.marginal_discovery_rate < 0.01 and n.exploration_depth > 0.3:
            n.stagnation_cycles += 1
        else:
            n.stagnation_cycles = 0
        if new_discoveries > 0:
            n.exploration_depth += 0.1 * (1.0 - n.exploration_depth)
            n.stagnation_cycles = 0
            if n.marginal_discovery_rate > n.peak_productivity:
                n.peak_productivity = n.marginal_discovery_rate

        # Lifecycle stage transitions
        if n.stagnation_cycles > 15 and n.lifecycle_stage in ("growth", "peak"):
            n.lifecycle_stage = "plateau"
        if n.stagnation_cycles > 30 and n.lifecycle_stage == "plateau":
            n.lifecycle_stage = "decline"
        if n.marginal_discovery_rate > 0.1 and n.lifecycle_stage in ("birth", "plateau"):
            n.lifecycle_stage = "growth"
        if n.peak_productivity > 0 and n.marginal_discovery_rate >= n.peak_productivity * 0.8:
            n.lifecycle_stage = "peak"
        if n.lifecycle_stage == "decline" and n.stagnation_cycles > 50:
            n.lifecycle_stage = "archived"

    def find_competing(self, niche_id: str) -> List[Niche]:
        n = self._niches.get(niche_id)
        if n is None:
            return []
        return [self._niches[r.target_id] for r in self._relations
                if r.source_id == niche_id and r.relation == NicheRelation.COMPETING
                and r.target_id in self._niches]

    def get_exhausted_niches(self) -> List[Niche]:
        return [n for n in self._niches.values() if n.is_exhausted]

    def get_bridge_candidates(self) -> List[Niche]:
        return [n for n in self._niches.values()
                if n.role == EcologicalRole.BRIDGE or n.bridge_count > 0]

    def to_dict(self) -> Dict:
        return {
            "niche_count": len(self._niches),
            "exhausted": len(self.get_exhausted_niches()),
            "bridges": len(self.get_bridge_candidates()),
            "relations": len(self._relations),
        }
