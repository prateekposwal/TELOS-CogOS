"""
RepresentationSelector — Dynamic Modality Switching (P0 D9)

Selects the optimal representation modality based on domain facts:
  - Spatial structure → spatial representation
  - Graph/relational structure → graph representation
  - Temporal sequence → temporal representation
  - Default → symbolic representation

Each selection returns a confidence score calibrated to how strongly
the domain facts match the representation's assumptions.
"""

import numpy as np
import logging
from typing import Dict, List, Any, Tuple, Optional, Set

logger = logging.getLogger('telos_representation')


class RepresentationSelector:
    """Selects between graph, spatial, temporal, and symbolic representations
    based on the structural properties of the current domain facts.

    This implements D9: the system is no longer fixed to a single
    representation — it dynamically switches modalities per cycle.
    """

    SUPPORTED_TYPES = ("graph", "spatial", "temporal", "symbolic")

    def __init__(self):
        self._selection_history: List[Tuple[str, float]] = []
        self._max_history = 100
        self._last_selection: Optional[str] = None

    def select(self, facts: Any, metadata: Optional[Dict] = None) -> Tuple[str, float]:
        """Analyze domain facts and select the best representation.

        Args:
            facts: DomainFacts object with resources, constraints, events, metrics
            metadata: Optional additional context (terrain, positions, etc.)

        Returns:
            (representation_type, confidence)
        """
        scores: Dict[str, float] = {}

        # Extract structural indicators from domain facts
        state = getattr(facts, 'state', None)
        resources = getattr(facts, 'resources', {}) or {}
        constraints = getattr(facts, 'constraints', []) or []
        events = getattr(facts, 'events', []) or []
        metrics = getattr(facts, 'metrics', {}) or {}
        meta = metadata or (getattr(facts, 'metadata', None) or {})

        # --- Check for spatial structure ---
        spatial_score = self._score_spatial(state, resources, constraints, meta, metrics)
        scores["spatial"] = spatial_score

        # --- Check for graph/relational structure ---
        graph_score = self._score_graph(facts, constraints, meta, resources)
        scores["graph"] = graph_score

        # --- Check for temporal sequence ---
        temporal_score = self._score_temporal(events, resources, metrics)
        scores["temporal"] = temporal_score

        # --- Default: symbolic ---
        symbolic_score = self._score_symbolic(scores, metrics, resources)
        scores["symbolic"] = symbolic_score

        # Select the representation with the highest confidence
        best_type = max(scores, key=scores.get)
        best_confidence = scores[best_type]

        # Apply temporal consistency: don't flip representations too rapidly
        if self._last_selection is not None and best_type != self._last_selection:
            # Only switch if the new representation is significantly better
            current_score = scores.get(self._last_selection, 0.0)
            if best_confidence < current_score + 0.15:
                best_type = self._last_selection
                best_confidence = current_score

        # Record selection
        self._selection_history.append((best_type, best_confidence))
        if len(self._selection_history) > self._max_history:
            self._selection_history.pop(0)
        self._last_selection = best_type

        logger.debug(
            f"RepresentationSelector: selected '{best_type}' (conf={best_confidence:.3f}) "
            f"— scores: {dict((k, round(v, 3)) for k, v in sorted(scores.items()))}"
        )
        return best_type, best_confidence

    def _score_spatial(self, state, resources, constraints, meta, metrics) -> float:
        """Score how well data fits a spatial representation.
            Args:
                state: the world/domain state for this call
                resources: the available resources
                constraints: the active constraints
                meta: the meta/mapping context
                metrics: metrics to fold into the result
        """
        score = 0.1  # baseline
        # State with position coordinates → strong spatial signal
        if state is not None:
            if hasattr(state, 'shape') and len(state.shape) == 1:
                if len(state) >= 2:
                    score += 0.4
                if len(state) >= 4:
                    score += 0.2

        # Terrain data → spatial
        terrain = meta.get("terrain", meta.get("current_terrain", None))
        if terrain:
            score += 0.2

        # Position metadata → spatial
        position = meta.get("position", None)
        if position and isinstance(position, (list, tuple)) and len(position) >= 2:
            score += 0.15

        # Grid/goal coordinates → spatial
        goal = meta.get("goal", None)
        if goal and isinstance(goal, (list, tuple)):
            score += 0.1

        # Distance metric → spatial
        if resources.get("terrain_cost", 0) != 0:
            score += 0.1
        if "distance" in resources:
            score += 0.1

        return min(1.0, score)

    def _score_graph(self, facts, constraints, meta, resources) -> float:
        """Score how well data fits a graph/relational representation.
            Args:
                facts: the domain facts to use
                constraints: the active constraints
                meta: the meta/mapping context
                resources: the available resources
        """
        score = 0.1  # baseline

        # Blocked cells → graph connectivity constraints
        blocked = meta.get("blocked", [])
        if blocked:
            score += 0.3

        # Reward locations → graph nodes with values
        rewards = meta.get("rewards", {})
        if rewards:
            score += 0.2

        # Multiple entities with relationships
        terrain = meta.get("terrain", {})
        if isinstance(terrain, dict) and len(terrain) > 3:
            score += 0.15

        # Constraints suggest relational edges
        if len(constraints) > 0:
            score += 0.1

        # Multiple related metrics
        if len(meta) > 5:
            score += 0.05

        return min(1.0, score)

    def _score_temporal(self, events, resources, metrics) -> float:
        """Score how well data fits a temporal sequence representation.
            Args:
                events: the events/state sequence
                resources: the available resources
                metrics: metrics to fold into the result
        """
        score = 0.1  # baseline

        # Events suggest temporal ordering
        if len(events) > 0:
            score += 0.3

        # Resources that change over time
        if "reward_near" in resources:
            score += 0.15

        # Uncertainty metric suggests temporal prediction
        uncertainty = metrics.get("uncertainty", 0)
        if uncertainty > 0:
            score += 0.15 * min(1.0, uncertainty * 2)

        # Recent selection history increases temporal score
        if len(self._selection_history) >= 3:
            recent_types = [t for t, _ in self._selection_history[-3:]]
            if len(set(recent_types)) == 1 and recent_types[0] == "temporal":
                score += 0.2  # Temporal momentum

        # Distance that changes over time
        if "distance" in resources:
            score += 0.1

        # Terrain costs change as agent moves
        if "terrain_cost" in resources:
            score += 0.1

        return min(1.0, score)

    def _score_symbolic(self, all_scores: Dict[str, float],
                        metrics: Dict, resources: Dict) -> float:
        """Score for symbolic representation — the fallback.
            Args:
                all_scores: the per-representation scores
                metrics: metrics to fold into the result
                resources: the available resources
        """
        # Symbolic is the default: start at 0.4
        score = 0.4

        # Boost if no other representation has strong evidence
        max_other = max((v for k, v in all_scores.items() if k != "symbolic"), default=0.0)
        if max_other < 0.4:
            score += 0.3

        # Boost if abstract metrics exist
        if metrics.get("reward", 0) != 0:
            score += 0.1
        if "uncertainty" in metrics:
            score += 0.1

        # Reduce if spatial or graph is strongly indicated
        if all_scores.get("spatial", 0) > 0.7:
            score -= 0.2
        if all_scores.get("graph", 0) > 0.6:
            score -= 0.1

        return max(0.1, min(1.0, score))


    @property
    def history(self) -> List[Tuple[str, float]]:
        return list(self._selection_history)

