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
from typing import Optional, Any, Dict

from telos.core.streams.base import CognitiveStream
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.core.ledger.skill_library import SkillLibrary
from telos.intent_ir import IntentIR
from telos.core.reasoning.theory_builder import TheoryBuilder

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
        """Update simulation parameters from pipeline config mid-cycle.
            Args:
                horizon: the horizon argument for this call.
                n_worlds: the n_worlds argument for this call.
        """
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
        # v9: consume the perceive-phase knowledge consultation (Λ4.7). The
        # report rides on world.metadata. A PROVEN approach labels this
        # cycle's plan as `domain_plan` carrying the approach + outcome so
        # the council (and the distributed DOMAIN_EXPERT lens) can weigh the
        # domain evidence. The action vector is still the stream's own
        # simulated best — only the intent TYPE and the knowledge labels
        # change, so the executor path (adapter reads params["action_vector"])
        # is untouched. Confidence uses the SAME 0.8 ceiling as
        # plan_trajectory, so the seeded intent can never out-bid the plan's
        # own ceiling in the attention auction; the semantic group merge in
        # synthesize treats domain_plan exactly like plan_trajectory.
        knowledge_report = None
        try:
            knowledge_report = (world.metadata or {}).get("knowledge_report") or None
        except Exception:
            knowledge_report = None
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

            approach = None
            outcome = 0.0
            is_domain_plan = False
            if knowledge_report and isinstance(knowledge_report, dict):
                approach = knowledge_report.get("approach")
                if approach is not None:
                    try:
                        outcome = float(knowledge_report.get("outcome") or 0.0)
                    except (TypeError, ValueError):
                        outcome = 0.0
                    is_domain_plan = outcome >= 0.51  # search min_outcome

            metadata = {
                "stream": "planning",
                "options_count": len(options),
                "best_score": best.score,
                "best_variance": best.variance,
                "sim_light": True,
            }
            if is_domain_plan:
                metadata["expert"] = knowledge_report.get("domain") or "unknown"
            if best.probabilistic:
                metadata["best_confidence"] = best.probabilistic.mean
                metadata["best_std"] = best.probabilistic.std
                metadata["ci_lower"] = best.probabilistic.ci_lower
                metadata["ci_upper"] = best.probabilistic.ci_upper

            params = {
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
            }
            if is_domain_plan:
                params["approach"] = approach
                params["outcome"] = outcome

            return IntentIR(
                intent_type="domain_plan" if is_domain_plan else "plan_trajectory",
                confidence=(min(0.8, max(0.3, outcome))
                            if is_domain_plan else min(0.8, best.score)),
                params=params,
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


class TheoryStream(CognitiveStream):
    """Proposes new hypotheses and theories from accumulated experience.

    Wraps TheoryBuilder as a first-class cognitive stream so that
    theory formation is unbypassable at the architecture level.

    Runs with priority 0.4 (after planning, before council) and
    proposes "propose_hypothesis" or "propose_theory" intents
    when abstraction progress has been made.
    """

    def __init__(self, skill_library: SkillLibrary,
                 theory_builder: Optional[TheoryBuilder] = None,
                 curriculum: Optional[Any] = None):
        super().__init__(skill_library)
        self._builder = theory_builder or TheoryBuilder()
        # Live curriculum (Λ6.5): the pipeline's novelty-ordered practice-task
        # source. Advisory — it shapes which hypothesis the stream proposes
        # first, it never acts. None = no curriculum wired (unchanged).
        self._curriculum = curriculum
        self._last_proposal_cycle: int = 0
        self._abstraction_level: str = "none"
        # How many cycles carried a curriculum-derived practice task. Measured,
        # not asserted (the live wiring is observable).
        self.curriculum_tasks_attached: int = 0
        self.last_practice_task: Optional[dict] = None


    @property
    def builder(self) -> TheoryBuilder:
        return self._builder

    def _frontier_task(self) -> Optional[dict]:
        """The top novelty-ordered practice task, or None when none applies."""
        if self._curriculum is None:
            return None
        try:
            frontier = self._curriculum.frontier()
        except Exception as e:
            logger.warning("TheoryStream: curriculum frontier failed: %r", e)
            return None
        if not frontier:
            return None
        top = frontier[0]
        return {
            "task_id": top.task_id,
            "kind": top.kind,
            "description": top.description,
            "novelty": round(float(top.novelty), 4),
            "difficulty": round(float(top.difficulty), 4),
        }

    @property
    def priority(self) -> float:
        return 0.4

    @property
    def estimated_cost_ms(self) -> float:
        return 4.0

    def process(self, world: World) -> IntentIR:
        # The cycle clock lives in world.metadata (set by PERCEIVE:
        # world_metadata = {"cycle": ctx.cycle_count}); World has no `cycle`
        # attribute, so the historical getattr() always read 0 and every
        # proposal cadence below was dead. Read the real metadata first.
        cycle = int(
            getattr(world, "cycle", 0)
            or (world.metadata.get("cycle", 0) if isinstance(world.metadata, dict) else 0)
            or 0
        )

        # Restore the hypothesis -> experiment -> evidence arrow BEFORE
        # abstraction: test active hypotheses against the newest real
        # observation. Without this, observe_outcome only adds experiences and
        # nothing ever calls test_hypotheses, so tests_passed stayed 0 and the
        # promotion criterion (>= min_tests_for_theory) was unsatisfiable.
        self._builder.test_latest_experience()

        # Cluster experiences into patterns
        patterns = self._builder.cluster()
        if patterns and len(patterns) > 0:
            self._abstraction_level = "pattern"

        # Generate hypotheses from patterns
        hypotheses = self._builder.hypothesize()
        if hypotheses and len(hypotheses) > 0:
            self._abstraction_level = "hypothesis"

        # Attempt to promote to theories
        promoted = self._builder.promote()
        if promoted and len(promoted) > 0:
            self._abstraction_level = "theory"

        theories = self._builder.get_active_theories()
        n_theories = len(theories) if theories else 0
        n_hypotheses = len(self._builder.get_active_hypotheses()) if hasattr(self._builder, 'get_active_hypotheses') else 0

        # Only propose intent when something changed
        if n_theories > 0 and cycle > self._last_proposal_cycle:
            self._last_proposal_cycle = cycle
            return IntentIR(
                intent_type="propose_theory",
                confidence=min(0.7, 0.3 + 0.1 * n_theories),
                params={
                    "n_theories": n_theories,
                    "n_hypotheses": n_hypotheses,
                    "abstraction_level": self._abstraction_level,
                },
                metadata={
                    "stream": "theory",
                    "n_theories": n_theories,
                    "abstraction_level": self._abstraction_level,
                },
            )

        if n_hypotheses > 0 and cycle > self._last_proposal_cycle + 3:
            self._last_proposal_cycle = cycle
            practice = self._frontier_task()
            if practice is not None:
                self.curriculum_tasks_attached += 1
                self.last_practice_task = practice
            # Confidence is nudged by the curriculum's top-task novelty
            # (bounded to <= 0.5 so advisory practice never outranks a real
            # proposal). No curriculum -> the exact historical 0.4.
            confidence = 0.4
            if practice is not None:
                confidence = min(0.5, 0.4 + 0.1 * float(practice["novelty"]))
            return IntentIR(
                intent_type="propose_hypothesis",
                confidence=confidence,
                params={
                    "n_hypotheses": n_hypotheses,
                    "n_theories": n_theories,
                    "practice_task": practice,
                },
                metadata={
                    "stream": "theory",
                    "n_hypotheses": n_hypotheses,
                    "practice_task": practice,
                },
            )

        return IntentIR(
            intent_type="theory_idle",
            confidence=0.2,
            params={
                "total_experiences": self._builder.total_experiences,
                "abstraction_level": self._abstraction_level,
            },
            metadata={"stream": "theory"},
        )
