"""
TELOS v15: Latent Role Manifold & Affordance Semantics

Implements dynamic affordance management and progressive semantic resolution
to overcome functional fixedness during simulated trajectory generation.
"""

import numpy as np
import time
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum


@dataclass
class LatentRole:
    """A single potential affordance for an entity."""
    role_id: str
    label: str
    embedding: np.ndarray
    base_weight: float = 1.0  # Historical success weight (prior calibration)
    material_properties: Dict[str, Any] = field(default_factory=dict)
    safety_rating: float = 1.0

    def score(self, mission_vector: np.ndarray, context_vector: np.ndarray) -> float:
        """Score role relevance based on mission, context, and historical prior."""
        # Alignments via cosine similarity (normalized dot product)
        mn = np.linalg.norm(mission_vector)
        cn = np.linalg.norm(context_vector)
        rn = np.linalg.norm(self.embedding)
        
        align_mission = float(np.dot(self.embedding, mission_vector) / (rn * mn + 1e-9)) if rn > 1e-9 and mn > 1e-9 else 0.0
        align_context = float(np.dot(self.embedding, context_vector) / (rn * cn + 1e-9)) if rn > 1e-9 and cn > 1e-9 else 0.0
        
        # Combined score f(r_i, M, C) scaled by historical weight
        # J_r = w_r * (0.7 * Align_M + 0.3 * Align_C)
        composite = 0.7 * align_mission + 0.3 * align_context
        return float(self.base_weight * composite)


@dataclass
class EntityManifold:
    """Collection of potential roles for an entity."""
    entity_id: str
    roles: List[LatentRole] = field(default_factory=list)
    active_roles: List[LatentRole] = field(default_factory=list)

    def clip(self, mission_vector: np.ndarray, context_vector: np.ndarray, k: int) -> List[LatentRole]:
        """Keep only top-K roles based on mission-conditioned scoring."""
        scored = [(role.score(mission_vector, context_vector), role) for role in self.roles]
        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        self.active_roles = [role for _, role in scored[:k]]
        return self.active_roles


class FeasibilityEnvelopeFilter:
    """Validates roles against physical, material, and safety constraints."""

    def is_feasible(self, role: LatentRole, constraints: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if role satisfies constraints (material consistency, safety).
        E.g. glass cannot be load-bearing, low safety ratings rejected under tight rules.
        """
        if role.safety_rating < 0.2:
            return False  # Inherently dangerous affordance

        if not constraints:
            return True

        # Check material conflicts
        # E.g. constraints = {'required_properties': ['load_bearing'], 'disallowed_properties': ['fragile']}
        required = constraints.get("required_properties", [])
        disallowed = constraints.get("disallowed_properties", [])
        props = role.material_properties

        for req in required:
            if not props.get(req, False):
                return False

        for dis in disallowed:
            if props.get(dis, False):
                return False

        # Tight safety threshold check
        min_safety = constraints.get("min_safety_rating", 0.0)
        if role.safety_rating < min_safety:
            return False

        return True


class RelationalAffordanceGraph:
    """Combines active roles from separate entities to unlock emergent capabilities."""

    def __init__(self):
        self.entities: Dict[str, EntityManifold] = {}
        self.emergent_links: Dict[Tuple[str, ...], LatentRole] = {}

    def register_entity(self, manifold: EntityManifold) -> None:
        self.entities[manifold.entity_id] = manifold

    def combine(self, entity_ids: List[str], 
                mission_vector: np.ndarray, 
                context_vector: np.ndarray,
                feasibility_filter: Optional[FeasibilityEnvelopeFilter] = None,
                constraints: Optional[Dict[str, Any]] = None) -> Optional[LatentRole]:
        """
        Emergent combination: takes top active roles of the given entities,
        combines them mathematically, filters via FeasibilityEnvelope, and returns
        the composite emergent role.
        """
        if len(entity_ids) < 2:
            return None

        active_roles: List[LatentRole] = []
        for eid in entity_ids:
            if eid in self.entities and self.entities[eid].active_roles:
                active_roles.append(self.entities[eid].active_roles[0])

        if len(active_roles) < 2:
            return None

        # Emergent capability logic: combine embeddings (mean)
        emergent_embedding = np.mean([r.embedding for r in active_roles], axis=0)
        norm = np.linalg.norm(emergent_embedding)
        if norm > 1e-9:
            emergent_embedding /= norm

        # Combine material properties and check feasibility
        combined_properties = {}
        for r in active_roles:
            combined_properties.update(r.material_properties)

        # Emergent safety: bottleneck safety rating
        emergent_safety = min([r.safety_rating for r in active_roles])

        emergent_role = LatentRole(
            role_id=f"emergent-{'|'.join([r.role_id for r in active_roles])}",
            label=f"Combined: {' + '.join([r.label for r in active_roles])}",
            embedding=emergent_embedding,
            base_weight=float(np.mean([r.base_weight for r in active_roles])),
            material_properties=combined_properties,
            safety_rating=emergent_safety,
        )

        # Feasibility check
        if feasibility_filter and not feasibility_filter.is_feasible(emergent_role, constraints):
            return None

        key = tuple(sorted(entity_ids))
        self.emergent_links[key] = emergent_role
        return emergent_role


class SemanticExpansionEngine:
    """
    Expands entities into latent role manifolds using Progressive Semantic Depth.
    """

    def __init__(self, k_roles: int = 5):
        self.k_roles = k_roles
        self._historical_weights: Dict[str, float] = {}
        self.feasibility_filter = FeasibilityEnvelopeFilter()

    def expand(self, entity_id: str, 
               potential_roles: List[LatentRole], 
               mission_vector: np.ndarray, 
               context_vector: np.ndarray,
               progressive_tier: str = "medium",
               constraints: Optional[Dict[str, Any]] = None) -> EntityManifold:
        """
        Expand entity based on simulation progressive depth tier:
          - 'fast': retain 1 role (default / maximum score)
          - 'medium': retain up to 3 roles
          - 'deep': full multi-role manifold activation (up to 5 roles)
        """
        # Calibrate weights with historical priors
        for role in potential_roles:
            role.base_weight = self._historical_weights.get(role.role_id, role.base_weight)

        # Filter out unfeasible roles early
        feasible_roles = [
            r for r in potential_roles 
            if self.feasibility_filter.is_feasible(r, constraints)
        ]

        # Determine K based on progressive semantic depth
        if progressive_tier == "fast":
            k = 1
        elif progressive_tier == "medium":
            k = min(3, self.k_roles)
        else:
            k = self.k_roles

        manifold = EntityManifold(entity_id=entity_id, roles=feasible_roles)
        manifold.clip(mission_vector, context_vector, k)
        return manifold

    def update_historical_weight(self, role_id: str, success: bool) -> float:
        """Update role weight based on outcomes (Prior Calibration)."""
        current = self._historical_weights.get(role_id, 1.0)
        # Learning rate is calibrated to prevent unstable spikes
        adjustment = 0.1 if success else -0.05
        new_weight = max(0.1, min(3.0, current + adjustment))
        self._historical_weights[role_id] = new_weight
        return new_weight

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'historical_priors_count': len(self._historical_weights),
            'avg_historical_weight': (
                float(np.mean(list(self._historical_weights.values())))
                if self._historical_weights else 1.0
            )
        }
