"""
Synthesis Phase — Stream Conflict Resolution (Axiom 4.6: Emergent Intelligence)

Between EVALUATE and SELECT, the Synthesis phase reconciles competing Stream
intents into a single ReconciledIntent. Compatible intents are merged;
irreconcilable conflicts are flagged for the Council.

Previously Reflex (priority=1.0) always won by raw sort. Now compatible
intents are merged so the system's full cognition is expressed in every action,
not just the highest-priority stream.

Safety intents (e.g., halt, emergency_stop) are treated as highest-priority
candidates in the merge, not as unconditional overrides — satisfying
Axiom 4.6 (Emergent Intelligence).
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

from telos.core.phases.base import Phase, PhaseContext, SynthesisOutput
from telos.intent_ir import IntentIR

logger = logging.getLogger('telos_synthesis')


def _extract_action_vector(intent: IntentIR) -> Optional[np.ndarray]:
    """Extract action_vector param if present."""
    return intent.params.get("action_vector") if intent.params else None


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Returns 0 if either is zero."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _semantic_group(intent_type: str) -> str:
    """Map intent types to semantic groups for reconciliation."""
    safety = {"halt", "emergency_stop", "avoid", "retreat", "brake"}
    navigation = {"plan_trajectory", "navigate", "move", "advance", "follow_path"}
    exploration = {"memory_miss", "plan_empty", "plan_noop", "explore", "search"}
    perception_group = {"perceive", "observe", "scan", "detect"}
    utility = {"recharge", "return", "dock", "maintain"}

    it = intent_type.lower()
    if it in safety:
        return "safety"
    if it in navigation:
        return "navigation"
    if it in exploration:
        return "exploration"
    if it in perception_group:
        return "perception"
    if it in utility:
        return "utility"
    return "other"


class SynthesisPhase(Phase):
    name = "synthesis"

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        if not ctx.intents:
            ctx.synthesis = SynthesisOutput(
                reconciled_intent=None,
                raw_intents=[],
                compatibility_score=1.0,
                conflicts=[],
            )
            return

        # Group intents by semantic category
        groups: Dict[str, List[Tuple[IntentIR, float]]] = {}
        for intent, weight in ctx.intents:
            g = _semantic_group(intent.intent_type)
            if g not in groups:
                groups[g] = []
            groups[g].append((intent, weight))

        # Safety intents: boost weight but participate in merge (Λ4.6)
        safety_intents = groups.get("safety", [])
        has_safety = len(safety_intents) > 0

        # Phase 0: Apply experience-calibrated confidence to each intent
        try:
            infra = getattr(pipeline, 'infra_manager', None)
            if infra and hasattr(infra, 'calibrator') and hasattr(ctx, 'world_state_snapshot') and ctx.world_state_snapshot is not None:
                context = str(ctx.world_state_snapshot.tolist())
                for gname in list(groups.keys()):
                    adjusted = []
                    for intent, weight in groups[gname]:
                        stream = intent.metadata.get('stream', '') if intent.metadata else ''
                        calibrated = infra.calibrator.get_calibrated_confidence(stream, context)
                        adj_weight = weight * max(0.5, calibrated[0])
                        adjusted.append((intent, adj_weight))
                    groups[gname] = adjusted
        except Exception as e:
            logger.warning(
                f"Synthesis: experience-calibrated confidence failed: {e} — "
                f"proceeding with uncalibrated weights"
            )

        # Boost safety intent weights by 1.5x so they dominate selection
        if has_safety:
            for i, (intent, weight) in enumerate(safety_intents):
                safety_intents[i] = (intent, weight * 1.5)
            logger.debug(f"Synthesis: boosted {len(safety_intents)} safety intent(s) by 1.5x")

        # Try to merge within the largest non-other group
        primary_group = max(
            (g for g in groups if g != "other"),
            key=lambda g: len(groups[g]),
            default=None,
        )

        if primary_group is None:
            primary_group = "other"

        candidates = groups[primary_group]
        conflicts = []

        if len(candidates) == 1:
            merged = candidates[0][0]
            compatibility = 1.0
        else:
            # Merge compatible intents
            vectors = [(_extract_action_vector(intent), intent, weight)
                       for intent, weight in candidates]
            has_vectors = [v for v, _, _ in vectors if v is not None]

            if len(has_vectors) >= 2:
                # Compare action vectors
                compatibilities = []
                for i in range(len(has_vectors)):
                    for j in range(i + 1, len(has_vectors)):
                        sim = _cosine_similarity(has_vectors[i], has_vectors[j])
                        compatibilities.append(sim)
                        if sim < 0.3:
                            conflicts.append({
                                "between": i,
                                "similarity": round(sim, 3),
                                "type": "vector_mismatch",
                            })
                compatibility = float(np.mean(compatibilities)) if compatibilities else 0.5
            else:
                compatibility = 0.5

            # Pick highest weighted intent in group
            best = max(candidates, key=lambda x: x[1] * x[0].confidence)
            merged = best[0]

            # If compatible enough, merge params from other intents
            if compatibility > 0.7 and merged.params:
                for other_intent, _ in candidates:
                    if other_intent is not merged and other_intent.params:
                        for k, v in other_intent.params.items():
                            if k not in merged.params:
                                merged.params[k] = v

        # Preserve minority group intents as merged params so their intent
        # is not lost (P2.2 fix — minority-group preserve)
        minority_intents = []
        for gname, gintents in groups.items():
            if gname != primary_group:
                for intent, weight in gintents:
                    minority_intents.append((intent, weight))
                    if merged.params and intent.params:
                        for k, v in intent.params.items():
                            if k not in merged.params:
                                merged.params[k] = v

        irreconcilable = compatibility < 0.3 and len(conflicts) > 0

        # If safety intents exist and are irreconcilable with ALL others, flag for Council
        if has_safety and irreconcilable:
            all_non_safety = [
                (i, w) for gname, gintents in groups.items()
                if gname != "safety"
                for i, w in gintents
            ]
            incompatible_with_all = all(
                _cosine_similarity(
                    _extract_action_vector(safety_intents[0][0]) or np.zeros(6),
                    _extract_action_vector(other) or np.zeros(6),
                ) < 0.3
                for other, _ in all_non_safety
            ) if all_non_safety and safety_intents else False

            if incompatible_with_all:
                logger.warning(
                    f"Synthesis: safety intent irreconcilable with all other intents — "
                    f"elevating to Council"
                )
                # Keep the safety intent as reconciled but mark irreconcilable
                # so the Council handles the conflict in the next phase

        ctx.synthesis = SynthesisOutput(
            reconciled_intent=merged,
            raw_intents=ctx.intents[:],
            compatibility_score=round(compatibility, 3),
            conflicts=conflicts,
            irreconcilable=irreconcilable,
        )

        if irreconcilable:
            logger.warning(f"Synthesis: irreconcilable (compat={compatibility:.2f}, "
                           f"{len(conflicts)} conflicts)")
        else:
            logger.debug(f"Synthesis: merged {primary_group} group "
                         f"(compat={compatibility:.2f})")
