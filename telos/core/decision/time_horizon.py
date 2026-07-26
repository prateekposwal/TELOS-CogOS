"""
TimeHorizonSeparation — Separate Utility Into Immediate/Short/Long/Irreversible.

Prateek's insight: "Separate utility into immediate, short-term, long-term,
and irreversible. Different weightings for each horizon."

Most systems compute a single utility value. This module decomposes utility
across four time horizons, each with its own discount factor and weighting.
A decision that looks good immediately might be catastrophic long-term,
and vice versa.

Horizons:
  1. IMMEDIATE (t=0):  Instant reward/punishment. No discount. Raw sensory outcome.
  2. SHORT-TERM (t<10): Near-future consequences. Moderate discount.
  3. LONG-TERM (t<100): Distant consequences. Heavy discount but still considered.
  4. IRREVERSIBLE (t→∞): Permanent effects. No discount — these are existential.
                         Irreversible outcomes are treated as constraints:
                         if an action leads to an irreversible negative outcome,
                         it is vetoed regardless of other horizon utilities.

Architecture:
  - Each horizon has a utility function U_h and weight w_h
  - Total utility U = Σ(w_h * U_h) with special handling for irreversible
  - Weight vector can shift based on identity (e.g., explorer weights long-term more)
  - Irreversible outcomes are flagged and can veto actions
"""

from __future__ import annotations

import logging
import math
import numpy as np
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_time_horizon')


class Horizon(Enum):
    IMMEDIATE = "immediate"           # t=0
    SHORT_TERM = "short_term"          # t<10
    LONG_TERM = "long_term"           # t<100
    IRREVERSIBLE = "irreversible"      # t→∞


HORIZON_ORDER = [Horizon.IMMEDIATE, Horizon.SHORT_TERM,
                 Horizon.LONG_TERM, Horizon.IRREVERSIBLE]


@dataclass
class HorizonUtility:
    """Utility score for a single time horizon."""
    horizon: Horizon
    utility: float          # 0-1 score
    confidence: float       # How certain we are about this horizon's prediction
    discount_factor: float  # γ for this horizon (1.0 for immediate/irreversible)
    description: str = ""

    @property
    def discounted_utility(self) -> float:
        return self.utility * self.discount_factor


@dataclass
class WeightedHorizonSet:
    """A complete utility profile across all horizons."""
    name: str
    weights: Dict[str, float]  # horizon.value -> weight (must sum to 1.0)
    irreversible_veto: bool = True  # If True, negative irreversible = veto
    description: str = ""


# ── Built-in horizon weighting profiles ──────────────────────

IMMEDIATE_BIAS = WeightedHorizonSet(
    name="immediate_bias",
    description="Prioritize immediate gratification. High discount on future.",
    weights={
        "immediate": 0.60,
        "short_term": 0.25,
        "long_term": 0.10,
        "irreversible": 0.05,
    },
)

BALANCED_HORIZON = WeightedHorizonSet(
    name="balanced",
    description="Equal consideration across all horizons with slight future bias.",
    weights={
        "immediate": 0.20,
        "short_term": 0.30,
        "long_term": 0.30,
        "irreversible": 0.20,
    },
)

FARSIGHTED = WeightedHorizonSet(
    name="farsighted",
    description="Heavy weight on long-term and irreversible consequences.",
    weights={
        "immediate": 0.05,
        "short_term": 0.20,
        "long_term": 0.45,
        "irreversible": 0.30,
    },
)

GUARDIAN_HORIZON = WeightedHorizonSet(
    name="guardian",
    description="Maximum weight on irreversible outcomes — avoid permanent harm.",
    weights={
        "immediate": 0.10,
        "short_term": 0.15,
        "long_term": 0.25,
        "irreversible": 0.50,
    },
)


@dataclass
class HorizonEvaluation:
    """Complete evaluation of an action across all time horizons."""
    action_id: str
    action_description: str
    horizon_utilities: Dict[str, HorizonUtility]  # horizon.value -> HorizonUtility
    total_utility: float
    vetoed: bool
    veto_reason: str = ""
    weight_profile: str = "balanced"


class TimeHorizonSeparator:
    """Separates utility into four time horizons with different weightings.

    The separator:
    1. Evaluates each action across all four horizons
    2. Applies horizon-specific discount factors
    3. Computes weighted total utility
    4. Flags irreversible outcomes as potential vetos
    5. Supports dynamic weight profiles

    Integration:
      - Called by SelectPhase to score candidate actions
      - Weights can change based on identity profile (IdentityUtilityEngine)
      - Irreversible vetos feed into Council validators
    """

    def __init__(self):
        self._profiles: Dict[str, WeightedHorizonSet] = {
            "immediate_bias": IMMEDIATE_BIAS,
            "balanced": BALANCED_HORIZON,
            "farsighted": FARSIGHTED,
            "guardian": GUARDIAN_HORIZON,
        }
        self._active_profile: WeightedHorizonSet = BALANCED_HORIZON
        self._evaluation_history: List[HorizonEvaluation] = []
        self._max_history = 200

        # Default discount factors (can be overridden)
        self._discount_factors = {
            Horizon.IMMEDIATE: 1.0,
            Horizon.SHORT_TERM: 0.85,
            Horizon.LONG_TERM: 0.6,
            Horizon.IRREVERSIBLE: 1.0,  # No discount — permanent is permanent
        }

    def register_profile(self, profile: WeightedHorizonSet) -> None:
        key = profile.name.lower().replace(" ", "_")
        self._profiles[key] = profile

    def set_active_profile(self, profile_name: str) -> bool:
        key = profile_name.lower().replace(" ", "_")
        if key in self._profiles:
            self._active_profile = self._profiles[key]
            logger.info(f"TimeHorizon: active profile = '{self._active_profile.name}'")
            return True
        logger.warning(f"TimeHorizon: unknown profile '{profile_name}'")
        return False

    def set_discount_factor(self, horizon: Horizon, factor: float) -> None:
        self._discount_factors[horizon] = max(0.0, min(1.0, factor))

    def evaluate(self, action_id: str, action_description: str,
                  horizon_scores: Dict[str, float],
                  irreversible_flag: bool = False,
                  irreversible_description: str = "") -> HorizonEvaluation:
        """Evaluate an action across all time horizons.

        Args:
            action_id: Identifier for the action
            action_description: Human-readable description
            horizon_scores: Dict mapping horizon.value -> utility score (0-1)
            irreversible_flag: If True, this action has irreversible consequences
            irreversible_description: What the irreversible consequence is

        Returns:
            HorizonEvaluation with total utility and veto status
        """
        horizon_utilities: Dict[str, HorizonUtility] = {}

        for horizon in HORIZON_ORDER:
            hkey = horizon.value
            raw_score = horizon_scores.get(hkey, 0.5)
            discount = self._discount_factors.get(horizon, 1.0)

            # Special handling: confidence decreases with horizon distance
            confidence_map = {
                Horizon.IMMEDIATE: 0.95,
                Horizon.SHORT_TERM: 0.80,
                Horizon.LONG_TERM: 0.55,
                Horizon.IRREVERSIBLE: 0.40,  # Hard to predict permanent effects
            }
            confidence = confidence_map.get(horizon, 0.5)

            horizon_utilities[hkey] = HorizonUtility(
                horizon=horizon,
                utility=raw_score,
                confidence=confidence,
                discount_factor=discount,
                description=f"{horizon.value}: score={raw_score:.3f}, γ={discount:.2f}",
            )

        # Check for irreversible veto
        vetoed = False
        veto_reason = ""
        if irreversible_flag and self._active_profile.irreversible_veto:
            irreversible_utility = horizon_scores.get('irreversible', 0.5)
            if irreversible_utility < 0.3:  # Negative irreversible outcome
                vetoed = True
                veto_reason = (f"Irreversible consequence vetoed: "
                              f"{irreversible_description}" if irreversible_description
                              else "Irreversible negative outcome")

        # Compute weighted total (excluding vetoed actions)
        if vetoed:
            total_utility = 0.0
        else:
            total_utility = self._compute_weighted_total(horizon_utilities)

        evaluation = HorizonEvaluation(
            action_id=action_id,
            action_description=action_description,
            horizon_utilities=horizon_utilities,
            total_utility=total_utility,
            vetoed=vetoed,
            veto_reason=veto_reason,
            weight_profile=self._active_profile.name,
        )

        self._evaluation_history.append(evaluation)
        if len(self._evaluation_history) > self._max_history:
            self._evaluation_history.pop(0)

        return evaluation

    def _compute_weighted_total(self,
                                 utilities: Dict[str, HorizonUtility]) -> float:
        """Compute weighted sum of horizon utilities using active profile."""
        total = 0.0
        weight_sum = 0.0

        for hkey, hu in utilities.items():
            weight = self._active_profile.weights.get(hkey, 0.0)
            total += weight * hu.discounted_utility
            weight_sum += weight

        if weight_sum <= 0:
            return 0.5

        return total / weight_sum

    def compare_actions(self, evaluations: List[HorizonEvaluation]) -> List[Tuple[int, float]]:
        """Rank multiple action evaluations by total utility.

        Returns list of (index, score) sorted by utility descending.
        Vetoed actions are ranked last.
        """
        indexed = []
        for i, ev in enumerate(evaluations):
            if ev.vetoed:
                indexed.append((i, -1.0))  # vetoed = worst
            else:
                indexed.append((i, ev.total_utility))
        indexed.sort(key=lambda x: -x[1])
        return indexed

    @property
    def active_profile(self) -> WeightedHorizonSet:
        return self._active_profile

    def to_dict(self) -> Dict:
        return {
            "active_profile": self._active_profile.name,
            "available_profiles": list(self._profiles.keys()),
            "discount_factors": {
                h.value: round(f, 3)
                for h, f in self._discount_factors.items()
            },
            "active_weights": self._active_profile.weights,
            "recent_evaluations": [
                {
                    "action": ev.action_description[:40],
                    "total_utility": round(ev.total_utility, 3),
                    "vetoed": ev.vetoed,
                    "veto_reason": ev.veto_reason[:40] if ev.veto_reason else "",
                    "profile": ev.weight_profile,
                }
                for ev in self._evaluation_history[-5:]
            ],
        }
