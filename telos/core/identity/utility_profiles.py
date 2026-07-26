"""
IdentityUtilityProfiles — Identity Changes Utility Functions, Not Thresholds.

Prateek's insight #4: "Identity changes utility functions — not thresholds.
Aviku = maximize collaboration. TELOS = maximize correctness."

The current SystemSelf changes mood (which adjusts thresholds) but never
changes the fundamental utility function that evaluates outcomes. This
module defines utility functions per identity profile.

Architecture:
  - Each identity profile has a different utility function
  - Utility = weighted combination of correctness, collaboration, exploration, etc.
  - Identity markers determine which profile is active
  - The utility function replaces the single fixed scoring in SelectPhase

Profiles:
  - AVIIKU: Maximize collaboration + user satisfaction + maintain harmony
  - TELOS: Maximize correctness + epistemic integrity + truth
  - EXPLORER: Maximize learning + novelty + uncertainty reduction
  - GUARDIAN: Maximize safety + constraint satisfaction + risk avoidance
  - BALANCED: Equal weights across all dimensions (default)

The utility function U(x) = Σ(w_i * f_i(x)) where:
  - w_i are profile-specific weights
  - f_i are feature functions (correctness, collaboration, learning, safety)
  - The profile can shift during operation based on identity state
"""

from __future__ import annotations

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_utility_profiles')


class UtilityDimension(str, Enum):
    CORRECTNESS = "correctness"        # Epistemic integrity, truth-alignment
    COLLABORATION = "collaboration"    # User satisfaction, helpfulness
    EXPLORATION = "exploration"        # Learning progress, novelty
    SAFETY = "safety"                  # Risk avoidance, constraint satisfaction
    EFFICIENCY = "efficiency"          # Resource utilization, speed
    COHERENCE = "coherence"            # Internal consistency, identity stability


@dataclass
class UtilityProfile:
    """A named profile with per-dimension weights."""
    name: str
    description: str
    weights: Dict[str, float]  # dimension -> weight (sums to 1.0)
    identity_markers: List[str]  # which markers activate this profile
    default: bool = False

    def compute(self, scores: Dict[str, float]) -> float:
        """Compute weighted utility from dimension scores.

        Args:
            scores: Dict mapping dimension -> score (0-1)

        Returns:
            Total utility (0-1)
        """
        total = 0.0
        weight_sum = 0.0
        for dim, score in scores.items():
            weight = self.weights.get(dim, 0.0)
            total += weight * score
            weight_sum += weight

        if weight_sum == 0.0:
            return 0.5  # default

        return total / weight_sum


# ── Built-in Profiles ────────────────────────────────────────────

AVIKU_PROFILE = UtilityProfile(
    name="Aviku",
    description="Maximize collaboration and user satisfaction. "
                "Prioritizes being helpful over being technically correct.",
    weights={
        "collaboration": 0.40,
        "correctness": 0.20,
        "safety": 0.15,
        "coherence": 0.15,
        "exploration": 0.05,
        "efficiency": 0.05,
    },
    identity_markers=["collaborative", "helpful", "aviku_mode"],
)

TELOS_PROFILE = UtilityProfile(
    name="TELOS",
    description="Maximize correctness and epistemic integrity. "
                "Prioritizes truth over user satisfaction.",
    weights={
        "correctness": 0.40,
        "coherence": 0.25,
        "safety": 0.15,
        "collaboration": 0.10,
        "exploration": 0.05,
        "efficiency": 0.05,
    },
    identity_markers=["precise", "rigorous", "telos_mode"],
)

EXPLORER_PROFILE = UtilityProfile(
    name="Explorer",
    description="Maximize learning and novelty. "
                "Prioritizes discovering new patterns over exploiting known ones.",
    weights={
        "exploration": 0.40,
        "correctness": 0.20,
        "efficiency": 0.15,
        "collaboration": 0.10,
        "safety": 0.10,
        "coherence": 0.05,
    },
    identity_markers=["curious", "exploring", "novelty_seeking"],
)

GUARDIAN_PROFILE = UtilityProfile(
    name="Guardian",
    description="Maximize safety and constraint satisfaction. "
                "Prioritizes avoiding harm over all other objectives.",
    weights={
        "safety": 0.50,
        "correctness": 0.20,
        "coherence": 0.15,
        "collaboration": 0.10,
        "efficiency": 0.05,
        "exploration": 0.00,
    },
    identity_markers=["cautious", "protective", "recovery_mode"],
)

BALANCED_PROFILE = UtilityProfile(
    name="Balanced",
    description="Equal weights across all dimensions — the default profile.",
    weights={
        "correctness": 0.20,
        "collaboration": 0.20,
        "exploration": 0.15,
        "safety": 0.20,
        "efficiency": 0.10,
        "coherence": 0.15,
    },
    identity_markers=[],
    default=True,
)


class IdentityUtilityEngine:
    """Selects and applies utility profiles based on identity state.

    The engine:
    1. Reads the current identity markers from SystemSelf
    2. Selects the best-matching profile
    3. Computes utility using the profile's weights
    4. Returns both the utility value and the profile used

    This replaces hardcoded threshold adjustments with proper
    utility-theoretic decision making.
    """

    def __init__(self):
        self._profiles: Dict[str, UtilityProfile] = {
            "aviku": AVIKU_PROFILE,
            "telos": TELOS_PROFILE,
            "explorer": EXPLORER_PROFILE,
            "guardian": GUARDIAN_PROFILE,
            "balanced": BALANCED_PROFILE,
        }
        self._active_profile: UtilityProfile = BALANCED_PROFILE
        self._profile_history: List[Dict] = []
        self._max_history = 100

    def register_profile(self, profile: UtilityProfile) -> None:
        """Register a custom utility profile."""
        key = profile.name.lower().replace(" ", "_")
        self._profiles[key] = profile

    def select_profile(self, identity_markers: List[str],
                       mood: Optional[str] = None) -> UtilityProfile:
        """Select the best-matching profile for current identity state.

        Args:
            identity_markers: Current identity markers from SystemSelf
            mood: Current mood (for additional context)

        Returns:
            The best-matching UtilityProfile
        """
        if not identity_markers:
            return BALANCED_PROFILE

        marker_set = set(m.lower() for m in identity_markers)

        # Score each profile by marker overlap
        best_profile = BALANCED_PROFILE
        best_score = -1.0

        for profile in self._profiles.values():
            profile_markers = set(m.lower() for m in profile.identity_markers)
            if not profile_markers:
                continue  # skip balanced (it's the fallback)

            # Jaccard similarity between current markers and profile markers
            intersection = len(marker_set & profile_markers)
            union = len(marker_set | profile_markers)
            if union == 0:
                continue

            score = intersection / union

            # Boost if mood aligns with profile
            if mood:
                mood_alignments = {
                    "curious": "explorer",
                    "confident": "telos",
                    "cautious": "guardian",
                    "uncertain": "guardian",
                    "fatigued": "balanced",
                }
                expected_profile = mood_alignments.get(mood)
                if expected_profile and profile.name.lower() == expected_profile:
                    score += 0.2

            if score > best_score:
                best_score = score
                best_profile = profile

        self._active_profile = best_profile

        # Record profile change
        self._profile_history.append({
            "profile": best_profile.name,
            "match_score": best_score,
            "markers": list(marker_set),
            "mood": mood,
        })
        if len(self._profile_history) > self._max_history:
            self._profile_history.pop(0)

        if best_profile.name != BALANCED_PROFILE.name:
            logger.info(
                f"IdentityUtility: selected '{best_profile.name}' "
                f"(score={best_score:.2f}, markers={marker_set})"
            )

        return best_profile

    def compute_utility(self, dimension_scores: Dict[str, float],
                        identity_markers: Optional[List[str]] = None,
                        mood: Optional[str] = None) -> Tuple[float, UtilityProfile]:
        """Compute utility using the appropriate profile.

        Args:
            dimension_scores: Dict of dimension -> score (0-1)
            identity_markers: Current identity markers (for profile selection)
            mood: Current mood

        Returns:
            Tuple of (utility_value, profile_used)
        """
        if identity_markers:
            profile = self.select_profile(identity_markers, mood)
        else:
            profile = self._active_profile

        utility = profile.compute(dimension_scores)
        return utility, profile

    def get_profile(self, name: str) -> Optional[UtilityProfile]:
        """Get a registered profile by name."""
        key = name.lower().replace(" ", "_")
        return self._profiles.get(key)

    @property
    def active_profile(self) -> UtilityProfile:
        return self._active_profile

    def to_dict(self) -> Dict:
        return {
            "active_profile": self._active_profile.name,
            "available_profiles": list(self._profiles.keys()),
            "profile_weights": self._active_profile.weights,
            "history": self._profile_history[-10:],
        }
