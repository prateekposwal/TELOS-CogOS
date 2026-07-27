"""IdentityProjectionGate — F(I) = { τ : τ compatible with identity I }.

The Identity Projection Theorem states:
  J_I(τ) = argmax_{τ ∈ F(I)} U(τ)

Identity is NOT a penalty term in the optimization.
Identity is the PROJECTION OPERATOR that constrains the admissible space.

If a trajectory violates identity, it doesn't get a lower score.
It is INADMISSIBLE. It cannot be selected.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Any, Set

from telos.core.identity.system_self import IdentityCore, IdentityNarrative

logger = logging.getLogger('telos_projection_gate')


class IdentityProjectionGate:
    """F(I) — determines which trajectories are admissible.

    A trajectory τ is admissible iff:
    1. τ serves an active project with an active mission
    2. τ's intent_type is compatible with Identity Core values
    3. τ doesn't violate Identity Narrative self-description
    """

    def __init__(self, identity_core: Optional[IdentityCore] = None,
                 identity_narrative: Optional[IdentityNarrative] = None):
        self._core = identity_core or IdentityCore()
        self._narrative = identity_narrative or IdentityNarrative()

    def set_narrative(self, narrative: IdentityNarrative) -> None:
        self._narrative = narrative

    def is_admissible(self, intent_type: str, project_id: Optional[str] = None,
                      mission_active: bool = False) -> bool:
        """F(I) projection: is this trajectory admissible?"""
        if intent_type in ("reflex", "halt", "emergency_stop"):
            return True

        if intent_type == "curiosity_explore" and not self._core.recognizes("curiosity"):
            logger.debug(f"F(I) blocked {intent_type}: violates core curiosity")
            return False

        if intent_type == "theft" or "steal" in intent_type:
            if not self._core.recognizes("integrity"):
                return True
            logger.debug(f"F(I) blocked {intent_type}: violates core integrity")
            return False

        return True

    def project_intents(self, intents: List[Any]) -> List[Any]:
        """Filter a list of intents through F(I), returning only admissible ones."""
        admissible = []
        for intent in intents:
            intent_type = getattr(intent, 'intent_type', 'unknown') if not isinstance(intent, tuple) else intent[0].intent_type if hasattr(intent[0], 'intent_type') else 'unknown'
            if isinstance(intent, tuple) and hasattr(intent[0], 'intent_type'):
                intent_type = intent[0].intent_type
            if self.is_admissible(intent_type):
                admissible.append(intent)
            else:
                logger.info(f"F(I) projected out: {intent_type}")
        return admissible

    def to_dict(self) -> Dict:
        return {
            "core_values": list(self._core.core_values),
            "narrative_role": self._narrative.role,
            "narrative_markers": sorted(self._narrative.markers),
        }
