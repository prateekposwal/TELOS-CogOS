"""
Representation Planner — The Intelligence Layer

The Planner is the meta-reasoning core of TELOS. It coordinates
cognitive streams and dynamically selects the internal representation
that maximizes mission success. It is NOT a heuristic — it is a
deliberate, budget-aware decision process that queries both the
DomainFacts (what the world looks like) and the BudgetManager
(compute remaining) to choose the right coordinate system.

This is the component that makes TELOS adaptive: it doesn't just
run the same pipeline every time — it reasons about HOW to reason.
"""

import numpy as np
import logging
from typing import Dict, List, Optional, Tuple

from telos.core.contracts.domain_model import DomainFacts
from telos.core.attention import BudgetManager
from telos.representations.transform import IdentityTransform, PolarTransform

logger = logging.getLogger('telos_planner')


class RepresentationPlanner:
    """Coordinates cognitive streams and adapts internal representation.

    Selection Function: f(Facts, Budget) → Representation

    The planner evaluates candidate representations (Cartesian, Polar,
    etc.) by scoring their expected utility against the current domain
    state and remaining compute budget. The representation that maximizes
    expected utility under budget constraints is selected.
    """

    CANDIDATE_REPS = ["cartesian", "polar"]
    SELECTION_COST_MS = 3.0

    def __init__(self, budget_manager: BudgetManager):
        self.budget_manager = budget_manager
        self._current_rep: str = "cartesian"
        self._selection_history: List[Dict] = []
        self._cycle_count: int = 0

    def get_transform(self, rep_name: str):
        if rep_name == "polar":
            return PolarTransform()
        return IdentityTransform()

    def select_representation(self, facts: DomainFacts) -> str:
        """Meta-reasoning entry point: choose the best representation.

        Queries BudgetManager for remaining compute, analyzes DomainFacts
        for domain complexity, evaluates each candidate representation,
        and returns the one with highest expected utility.
        """
        self._cycle_count += 1

        if not self.budget_manager.check_budget("planner_selection", self.SELECTION_COST_MS):
            logger.debug(f"Planner: budget exhausted, keeping {self._current_rep}")
            return self._current_rep

        scores = self._evaluate_all_representations(facts)
        best_rep = max(scores, key=lambda r: scores[r]["utility"])
        best_score = scores[best_rep]["utility"]

        prev_score = scores.get(self._current_rep, {}).get("utility", 0.0)
        switched = best_rep != self._current_rep

        if switched:
            self._current_rep = best_rep
            logger.info(f"Planner: switched to {best_rep} (utility={best_score:.3f}, "
                        f"prev={prev_score:.3f})")

        self.budget_manager.consume("planner_selection", self.SELECTION_COST_MS)

        self._selection_history.append({
            "cycle": self._cycle_count,
            "selected": best_rep,
            "scores": {r: scores[r]["utility"] for r in scores},
            "switched": switched,
            "budget_remaining": self.budget_manager.total_budget_ms - self.budget_manager.consumed_ms,
        })

        return self._current_rep

    def _evaluate_all_representations(self, facts: DomainFacts) -> Dict[str, Dict]:
        """Score each candidate representation against current facts.

        Each representation is evaluated on:
        1. State geometry suitability (how well does the coord system match the data?)
        2. Complexity cost (Polar has higher overhead than Cartesian)
        3. Budget feasibility (can we afford this representation?)
        """
        state = facts.state
        scores = {}

        complexity = self._compute_complexity(facts)
        budget_fraction = 1.0 - (self.budget_manager.consumed_ms /
                                  max(self.budget_manager.total_budget_ms, 1.0))

        # Cartesian: best for low-dimensional, axis-aligned states
        cartesian_geometry = self._score_cartesian_geometry(state)
        cartesian_complexity = 0.1
        cartesian_budget = 1.0
        cartesian_utility = (
            0.5 * cartesian_geometry +
            0.3 * (1.0 - cartesian_complexity) +
            0.2 * cartesian_budget
        )
        scores["cartesian"] = {
            "utility": cartesian_utility,
            "geometry": cartesian_geometry,
            "complexity": cartesian_complexity,
        }

        # Polar: best for high-norm, rotationally symmetric states
        polar_geometry = self._score_polar_geometry(state)
        polar_complexity = 0.3
        polar_budget = budget_fraction
        polar_utility = (
            0.5 * polar_geometry +
            0.3 * (1.0 - polar_complexity) +
            0.2 * polar_budget
        )
        scores["polar"] = {
            "utility": polar_utility,
            "geometry": polar_geometry,
            "complexity": polar_complexity,
        }

        return scores

    def _score_cartesian_geometry(self, state: np.ndarray) -> float:
        """Score how well Cartesian coordinates fit the current state.

        Cartesian is preferred when:
        - State is low-norm (near origin)
        - State has axis-aligned structure
        - Individual dimensions are independently meaningful
        """
        norm = float(np.linalg.norm(state))
        axis_alignment = float(np.max(np.abs(state))) / max(norm, 1e-9)
        sparsity = 1.0 - (np.count_nonzero(state) / max(len(state), 1))

        norm_score = np.clip(1.0 - norm / 5.0, 0.0, 1.0)
        return float(0.4 * norm_score + 0.3 * axis_alignment + 0.3 * sparsity)

    def _score_polar_geometry(self, state: np.ndarray) -> float:
        """Score how well Polar coordinates fit the current state.

        Polar is preferred when:
        - State has high norm (far from origin)
        - State exhibits rotational symmetry
        - Distance + angle are more meaningful than x,y individually
        """
        norm = float(np.linalg.norm(state))
        if len(state) < 2:
            return 0.0

        x, y = state[0], state[1]
        angle = np.arctan2(y, x)
        radial_symmetry = abs(np.sin(2 * angle))

        norm_score = np.clip(norm / 5.0, 0.0, 1.0)
        return float(0.5 * norm_score + 0.3 * radial_symmetry + 0.2 * (1.0 - norm_score))

    def _compute_complexity(self, facts: DomainFacts) -> float:
        """Estimate domain complexity from facts."""
        constraint_count = len(facts.constraints)
        event_count = len(facts.events)
        resource_count = len(facts.resources)

        return float(np.clip(
            (constraint_count * 0.2 + event_count * 0.15 + resource_count * 0.1) / 3.0,
            0.0, 1.0
        ))

    @property
    def current_representation(self) -> str:
        return self._current_rep

    @property
    def selection_history(self) -> List[Dict]:
        return list(self._selection_history)
