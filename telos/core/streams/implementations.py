"""
Cognitive Stream Implementations

Each stream is a specialized, persistent process that operates on the
shared World model. Together, they embody the Principle of Latent
Cognition: invisible coordination producing visible coherent action.

Streams are ranked by intrinsic priority. The pipeline processes them
in order, consuming attention budget. Streams that exhaust the budget
are silently skipped — this IS the attention mechanism.

NOTE: The old `uncertainty > 0.8 → Reflex` rule has been removed.
ReflexStream no longer triggers on uncertainty alone — it remains as a
safety check for NaN/Inf detection and safety_score violations.
"""

import hashlib
import numpy as np
import logging
from typing import Optional

from telos.core.streams.base import CognitiveStream
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.core.ledger.skill_library import SkillLibrary
from telos.intent_ir import IntentIR

logger = logging.getLogger('telos_streams')


class ReflexStream(CognitiveStream):
    """Fast, low-latency stream for immediate reactivity.

    Scans the World for critical conditions: safety violations,
    terminal states, NaN/Inf in state. Returns an immediate
    action intent when danger is detected, bypassing deeper
    planning. This is the system's "spinal reflex."

    NOTE: The old `uncertainty > 0.8` trigger has been REMOVED.
    Uncertainty-driven exploration is now handled by the InquiryStream
    (priority 0.8) and the Ω Operator. ReflexStream remains for
    genuine safety-critical conditions only.
    """

    @property
    def priority(self) -> float:
        return 1.0

    @property
    def estimated_cost_ms(self) -> float:
        return 2.0

    def process(self, world: World) -> IntentIR:
        urgency = 0.0
        action = np.zeros(2)

        # Removed: world.uncertainty > 0.8 → reflex trigger
        # Uncertainty-driven exploration is now handled by InquiryStream + Ω Operator

        if world.safety_score < 0.3:
            urgency = 0.99
            action = np.zeros(2)
            logger.warning(f"Reflex: safety breach ({world.safety_score:.2f}), "
                           f"halting proposed")

        nans = np.isnan(world.state).sum()
        if nans > 0:
            urgency = 1.0
            action = np.zeros(2)
            logger.error(f"Reflex: {nans} NaN values in state, emergency halt")

        return IntentIR(
            intent_type="reflex",
            target=action,
            confidence=urgency,
            params={"action_vector": action, "urgency": urgency},
            metadata={"stream": "reflex", "trigger": "safety" if urgency > 0.5 else "nominal"},
        )


class PerceptionStream(CognitiveStream):
    """Ingests raw state and builds semantic understanding.

    Extracts features from the World state and DomainFacts to
    populate the World's entity and affordance lists. This stream
    transforms raw numbers into meaningful labels that other
    streams can reason about.

    Entity IDs are computed deterministically from state features,
    allowing the WorldLedger to track entities across decision cycles.
    """

    @property
    def priority(self) -> float:
        return 0.9

    @property
    def estimated_cost_ms(self) -> float:
        return 5.0

    def process(self, world: World) -> IntentIR:
        entities = []
        affordances = []
        features = {}

        state = world.state
        features["state_norm"] = float(np.linalg.norm(state))
        features["state_mean"] = float(np.mean(state))
        features["state_std"] = float(np.std(state))
        features["state_dim"] = len(state)

        nonzero = np.count_nonzero(state)
        features["sparsity"] = 1.0 - (nonzero / max(len(state), 1))
        features["energy"] = float(np.sum(state ** 2))

        # Determine entity type from state geometry
        if features["state_norm"] > 5.0:
            entity_type = "high_energy_region"
            base_affordances = ["dampen"]
        elif features["state_norm"] < 0.1:
            entity_type = "quiescent_zone"
            base_affordances = ["explore"]
        else:
            entity_type = "active_region"
            base_affordances = ["maintain"]

        if features["sparsity"] > 0.7:
            base_affordances.append("densify")

        # Compute a deterministic entity ID from the state fingerprint
        feature_bytes = str(sorted(features.items())).encode()
        entity_id = f"ent_{hashlib.md5(feature_bytes).hexdigest()[:8]}"

        entities.append(entity_type)
        affordances.extend(base_affordances)

        world.entities = entities
        world.affordances = affordances
        world.metadata["perception_features"] = features
        world.metadata["entity_id"] = entity_id
        world.metadata["entity_type"] = entity_type

        return IntentIR(
            intent_type="perceive",
            confidence=0.85,
            params={
                "features": features,
                "entities": entities,
                "affordances": affordances,
                "entity_ids": [entity_id],
                "entity_types": {entity_id: entity_type},
            },
            metadata={
                "stream": "perception",
                "entity_id": entity_id,
                "entity_type": entity_type,
            },
        )


class MemoryStream(CognitiveStream):
    """Queries the SkillLibrary for relevant past trajectories.

    Instead of re-planning from scratch, this stream retrieves
    known-viable paths from memory. It seeds the planning process
    with historical context — the system's "procedural memory."
    """

    @property
    def priority(self) -> float:
        return 0.7

    @property
    def estimated_cost_ms(self) -> float:
        return 3.0

    def process(self, world: World) -> IntentIR:
        relevant = self.skill_library.find_relevant_skills(world.state, threshold=0.5)

        if not relevant:
            return IntentIR(
                intent_type="memory_miss",
                confidence=0.3,
                params={"suggestion": "plan_from_scratch"},
                metadata={"stream": "memory", "match_count": 0},
            )

        best = max(relevant, key=lambda s: s.utility_score)
        suggestion = best.trajectory if hasattr(best, 'trajectory') else None

        return IntentIR(
            intent_type="memory_recall",
            confidence=min(best.utility_score, 1.0),
            params={
                "skill_id": best.skill_id,
                "suggestion": suggestion,
                "utility_score": best.utility_score,
                "match_count": len(relevant),
            },
            metadata={"stream": "memory", "match_count": len(relevant)},
        )


class PlanningStream(CognitiveStream):
    """Deep simulation for long-horizon planning.

    Uses the CounterfactualEngine to generate multiple future
    realities, evaluate their trajectories, and propose the
    highest-utility path. This is the system's "deliberative
    reasoning" — slow but thorough.
    """

    def __init__(self, skill_library: SkillLibrary, sim_engine=None, horizon=None, n_worlds=None):
        super().__init__(skill_library)
        self._sim_engine = sim_engine
        self.horizon = horizon if horizon is not None else 8
        self.n_worlds = n_worlds if n_worlds is not None else 30

    def configure(self, horizon: int = None, n_worlds: int = None) -> None:
        """Update simulation parameters from pipeline config mid-cycle."""
        if horizon is not None:
            self.horizon = horizon
        if n_worlds is not None:
            self.n_worlds = n_worlds

    @property
    def priority(self) -> float:
        return 0.5

    @property
    def estimated_cost_ms(self) -> float:
        return 12.0

    def process(self, world: World) -> IntentIR:
        if self._sim_engine is None:
            return IntentIR(
                intent_type="plan_noop",
                confidence=0.1,
                params={"reason": "no_simulator_registered"},
                metadata={"stream": "planning"},
            )

        state = world.state
        try:
            options = self._sim_engine.generate_options(state, horizon=self.horizon, n_worlds=self.n_worlds)
            if not options:
                return IntentIR(
                    intent_type="plan_empty",
                    confidence=0.2,
                    params={"reason": "no_viable_trajectories"},
                    metadata={"stream": "planning"},
                )

            best = options[0]
            best_state = getattr(best.world, 'state', best.world)
            action = best_state[:2] - state[:2] if len(best_state) >= 2 else np.zeros(2)

            metadata = {
                "stream": "planning",
                "options_count": len(options),
                "best_score": best.score,
                "best_variance": best.variance,
                "sim_light": True,
            }
            if best.probabilistic:
                metadata["best_confidence"] = best.probabilistic.mean
                metadata["best_std"] = best.probabilistic.std
                metadata["ci_lower"] = best.probabilistic.ci_lower
                metadata["ci_upper"] = best.probabilistic.ci_upper

            return IntentIR(
                intent_type="plan_trajectory",
                confidence=min(0.8, best.score),
                params={
                    "action_vector": action,
                    "trajectory": best.world,
                    "options_count": len(options),
                    "best_score": best.score,
                    "variance": best.variance,
                    "probabilistic": {
                        "mean": best.probabilistic.mean,
                        "std": best.probabilistic.std,
                        "ci_lower": best.probabilistic.ci_lower,
                        "ci_upper": best.probabilistic.ci_upper,
                    } if best.probabilistic else None,
                },
                metadata=metadata,
            )
        except Exception as e:
            logger.error(f"PlanningStream simulation failed: {e}")
            return IntentIR(
                intent_type="plan_error",
                confidence=0.0,
                params={"error": str(e)},
                metadata={"stream": "planning"},
            )
