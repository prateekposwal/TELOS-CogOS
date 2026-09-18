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

# Layer-3 exemption set: intent types that carry no mission-service claim
# (reflex keeper, idle theory ticks, recall) and therefore cannot be
# "mission-less" in the Layer-3 sense. ONE canonical source (Λ6.7).
MISSION_EXEMPT = ("reflex", "theory_idle", "memory_recall")

# Layer-2 role -> incompatible intent-type substrings. ONE canonical source.
# A specialized role forbids its anti-pattern (explorer must not exploit-refine,
# guardian must not take dangerous exploration). The default generalist role
# 'agent' forbids intents that CEDE AGENCY or terminate the agent — an agent is
# by identity the acting party, so abdicating control contradicts who it is.
# This is role-specific and distinct from Layer 1 (which covers integrity
# 'steal'/'deceive' and the exploit+explore+harm humility pattern); it is
# deliberately conservative: no live GridWorld stream emits these types, so
# Layer 2 remains defense-in-depth, but it is no longer structurally inert.
ROLE_INCOMPATIBLE: Dict[str, List[str]] = {
    "explorer": ["exploit", "refine", "optimize"],
    "mathematician": ["exploit", "random_walk"],
    "guardian": ["explore_dangerous", "high_risk"],
    "agent": ["abdicate", "surrender", "self_destruct", "self_terminate",
              "delegate_all"],
}


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


    def is_admissible(self, intent_type: str, project_id: Optional[str] = None,
                      mission_active: bool = False, mission_ids: Optional[List[str]] = None,
                      narrative_role: Optional[str] = None,
                      missionless_bootstrap: bool = False,
                      mission_defined: bool = False) -> bool:
        """F(I) projection: is this trajectory admissible?

        Checks trajectory τ against all 6 identity layers:
        1. Core values — does the intent violate core values?
        2. Narrative role — is this intent compatible with who the system is?
        3. Active missions — does this serve a current mission?
        4. Project assignment — is this project still valid?

        Args:
            intent_type: the intent_type argument for this call.
            project_id: the project_id argument for this call.
            mission_active: the mission_active argument for this call.
            mission_ids: ids in the active mission scope (active mission ids
                plus the projects they own) — Layer 4 validates project_id
                against this scope.
            narrative_role: the narrative_role argument for this call.
            missionless_bootstrap: DOCUMENTED GENUINE-bootstrap path (default
                False = strict). True ONLY when the kernel has NEVER defined an
                objective — no declared mission name/description and no mission
                ever created. Then Layer 3 has nothing to reference and is
                skipped while Layers 1–2 remain enforced. It is NOT "no mission
                currently active": a kernel that DECLARED an objective but whose
                portfolio currently has no active mission must pass False, so a
                mission-less trajectory is projected out. Passing True together
                with mission_defined=True is a caller error and is IGNORED
                (treated as strict) — a mis-set flag can never re-open the
                Layer-3 bypass.
            mission_defined: whether the kernel declares/has hosted an
                objective (PipelineConfig.mission_name/-_description, or any
                mission ever created in the portfolio). This is the REAL
                mission-scope signal: it distinguishes "no objective exists"
                (genuine bootstrap) from "an objective exists but no active
                mission currently backs this trajectory" (must be enforced).
        """
        if intent_type in ("reflex", "halt", "emergency_stop"):
            return True

        # Layer 1: Core values check
        if intent_type == "curiosity_explore" and not self._core.recognizes("curiosity"):
            logger.debug(f"F(I) blocked {intent_type}: violates core curiosity")
            return False

        if "steal" in intent_type or "deceive" in intent_type:
            if self._core.recognizes("integrity"):
                logger.debug(f"F(I) blocked {intent_type}: violates core integrity")
                return False

        if "exploit" in intent_type and "explore" in intent_type and self._core.recognizes("epistemic_humility"):
            if "harm" in intent_type:
                logger.debug(f"F(I) blocked {intent_type}: violates epistemic humility")
                return False

        # Layer 2: Narrative role consistency
        if narrative_role:
            incompatible = ROLE_INCOMPATIBLE.get(narrative_role, [])
            if any(inc in intent_type for inc in incompatible):
                logger.debug(f"F(I) blocked {intent_type}: incompatible with role '{narrative_role}'")
                return False

        # Layer 3: Active mission-scope check.
        #
        # The check is about the kernel's REAL objective scope, not a bare
        # on/off flag. A non-exempt trajectory is mission-less (projected out)
        # when the kernel has a defined objective but the trajectory is not
        # backed by a currently-active mission scope.
        #
        # The old live caller set `missionless_bootstrap = not mission_active`,
        # which made this guard `not mission_active and mission_active` ≡ False
        # — an unconditional bypass (tautology). Genuine bootstrap now means
        # "no objective has EVER been defined", and is honored only when no
        # objective exists, so a mis-set flag cannot re-open the bypass.
        genuine_bootstrap = missionless_bootstrap and not mission_defined
        if (not mission_active and not genuine_bootstrap
                and intent_type not in MISSION_EXEMPT):
            logger.debug(f"F(I) blocked {intent_type}: no active mission scope")
            return False

        # Layer 4: Project validity (if specified). `mission_ids` is the
        # active mission scope — mission ids plus the ids of projects those
        # missions own; a project not in that scope is not backed by an active
        # mission and is projected out.
        if project_id and mission_ids and mission_ids[0] and project_id not in mission_ids:
            logger.debug(f"F(I) blocked {intent_type}: project {project_id} not in active missions")
            return False

        return True

    def project_intents(self, intents: List[Any], mission_active: bool = False,
                        mission_ids: Optional[List[str]] = None,
                        missionless_bootstrap: bool = False,
                        mission_defined: bool = False) -> List[Any]:
        """Filter a list of intents through F(I), returning only admissible ones.

            Args:
                intents: the candidate intents to project.
                mission_active: the mission_active argument for this call.
                mission_ids: ids in the active mission scope (active mission
                    ids plus the projects they own).
                missionless_bootstrap: documented GENUINE-bootstrap path (see
                    is_admissible); skips only the mission-existence layer.
                mission_defined: whether an objective has ever been defined;
                    the real mission-scope signal for Layer 3.
        """
        admissible = []
        for intent in intents:
            intent_type = "unknown"
            if hasattr(intent, 'intent_type'):
                intent_type = intent.intent_type
            elif isinstance(intent, tuple) and hasattr(intent[0], 'intent_type'):
                intent_type = intent[0].intent_type

            if self.is_admissible(intent_type, mission_active=mission_active,
                                 mission_ids=mission_ids, narrative_role=self._narrative.role,
                                 missionless_bootstrap=missionless_bootstrap,
                                 mission_defined=mission_defined):
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
