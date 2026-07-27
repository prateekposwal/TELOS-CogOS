"""
SelectPhase — selects the best intent from synthesized options.

Also integrates the Ω Operator (InquiryStream) to decide whether to
enter Inquiry Mode (generate a question) or proceed with normal action
selection.

When the InquiryStream produces a high-value question (Ω > 0.5), the
pipeline enters Inquiry Mode and the question becomes the selected intent.
Otherwise, proceeds with normal action selection (commitment optimization).

Fix 3 (Inquiry-to-Action Bridge): Maps question types to concrete sub-pipeline
actions instead of just setting a passive question intent.

Changes for Continuous Omega Modulator:
- Sigmoid blend replaces binary inquiry gate
- Per-axis modulation via omega_vector
- Tripartite U computed from available SELECT-phase data
"""

import math
import logging
import numpy as np

from telos.core.phases.base import Phase, PhaseContext

logger = logging.getLogger('telos_pipeline')
from telos.core.uncertainty.tripartite import TripartiteUncertainty


class SelectPhase(Phase):
    name = "select"

    def _compute_tripartite_from_available(self, pipeline, ctx):
        """Compute tripartite uncertainty from data available during SELECT phase.
        
        This fixes the timing issue where tripartite U was computed in ACT phase
        but consumed in SELECT phase.
        """
        # Prediction error from attention trajectory divergences
        attn = getattr(pipeline, '_attention_engine', None)
        prediction_error = 0.0
        if attn and hasattr(attn, '_trajectory_divergences') and attn._trajectory_divergences:
            recent_divs = attn._trajectory_divergences[-3:]
            prediction_error = min(1.0, sum(recent_divs) / max(len(recent_divs), 1) * 0.5)
        
        # Identity entropy — guard against mock/non-numeric values in tests
        identity_entropy = getattr(pipeline, '_identity_entropy', None)
        identity_entropy_val = 0.0
        if identity_entropy is not None:
            try:
                raw = identity_entropy.collapse_rate
                identity_entropy_val = abs(float(raw))
            except (TypeError, ValueError):
                identity_entropy_val = 0.0
        
        # Council signals (from current or previous cycle)
        council_signals = []
        if ctx.verdict:
            try:
                council_signals = ctx.verdict.signals
            except Exception:
                council_signals = []
        elif ctx.council and ctx.council.verdict:
            try:
                council_signals = ctx.council.verdict.signals
            except Exception:
                council_signals = []
        
        # Use the classmethod to compute from available data
        return TripartiteUncertainty.compute_from_available(
            prediction_error=prediction_error,
            identity_entropy=identity_entropy_val,
            council_signals=council_signals,
        )

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        # ── Phase 0: Compute tripartite U from SELECT-phase data (Change 3) ──
        # This replaces the stale ACT-phase values that were previously consumed here
        tripartite_u = self._compute_tripartite_from_available(pipeline, ctx)
        pipeline._tripartite_u = tripartite_u
        
        # ── Phase 1: Check if InquiryStream has a question worth asking ──
        # Run the Ω Operator to determine if we should enter Inquiry Mode
        inquiry_stream = None
        for stream in pipeline.streams:
            if stream.__class__.__name__ == "InquiryStream":
                inquiry_stream = stream
                break

        if inquiry_stream is not None:
            # Gather inputs for Ω Operator
            council_signals = []
            if ctx.verdict:
                council_signals = [
                    {
                        "validator_name": s.validator_name,
                        "passed": s.passed,
                        "confidence": s.confidence,
                        "reason": s.reason,
                        "evidence_weight": s.evidence_weight,
                        "verdict": s.verdict,
                    }
                    for s in ctx.verdict.signals
                ]
            elif ctx.council and ctx.council.verdict:
                council_signals = [
                    {
                        "validator_name": s.validator_name,
                        "passed": s.passed,
                        "confidence": s.confidence,
                        "reason": s.reason,
                        "evidence_weight": s.evidence_weight,
                        "verdict": s.verdict,
                    }
                    for s in ctx.council.verdict.signals
                ]

            meta_state = ctx.meta_cognition if hasattr(ctx, 'meta_cognition') else None
            budget = {
                "remaining_ms": max(
                    0, getattr(pipeline.budget_manager, 'total_budget_ms', 100)
                    - getattr(pipeline.budget_manager, 'consumed_ms', 0)
                )
            }

            # Get or create the OmegaOperator
            omega_operator = getattr(pipeline, '_omega_operator', None)
            if omega_operator is None:
                from telos.core.decision.omega_operator import OmegaOperator
                omega_operator = OmegaOperator()
                pipeline._omega_operator = omega_operator

            # Compute the best question and its Ω value
            sim_engine = getattr(pipeline, '_sim_engine', None)
            if tripartite_u is not None:
                best_question, omega_value, omega_vector = omega_operator.compute(
                    tripartite_u, council_signals, meta_state, budget,
                    sim_engine=sim_engine,
                )
            else:
                best_question, omega_value, omega_vector = None, 0.0, {
                    'world': 0.0, 'identity': 0.0, 'other': 0.0,
                }

            # Store omega_vector in PhaseContext for DecisionTrace
            ctx.inquiry_omega_vector = omega_vector

            # ── Change 1: Continuous sigmoid blend replaces binary gate ──
            steepness = 10.0
            omega_threshold = 0.5
            if hasattr(pipeline, '_omega_threshold_learner'):
                omega_threshold = pipeline._omega_threshold_learner.get_threshold()
            
            blend = 1.0 / (1.0 + math.exp(-steepness * (omega_value - omega_threshold)))
            
            # ── Curiosity Drive Modulation ─────────────────────────────────
            # When curiosity is high (>0.6), the blend shifts toward inquiry
            # (more exploration) regardless of the omega value.
            curiosity_state = getattr(ctx, 'curiosity_state', None)
            if curiosity_state and curiosity_state.get('curiosity_level', 0.0) > 0.6:
                curiosity_boost = (curiosity_state['curiosity_level'] - 0.6) * 2.0  # 0-0.8 boost
                blend = min(1.0, blend + curiosity_boost * 0.3)
                logger.debug(
                    f"Curiosity boosted blend: {getattr(ctx, 'inquiry_blend', 0.0):.3f} "
                    f"-> {blend:.3f} (curiosity={curiosity_state['curiosity_level']:.2f})"
                )
            
            ctx.inquiry_blend = blend

            # ── Change 2: Per-axis modulation ──
            base_n_worlds = getattr(ctx, 'effective_n_worlds', 5) or 5
            modulated_n_worlds = int(base_n_worlds * (1.0 + omega_vector.get('world', 0.0) * 2.0))
            modulated_n_worlds = max(1, min(100, modulated_n_worlds))
            ctx.effective_n_worlds = modulated_n_worlds
            
            identity_cost_weight = 1.0 + omega_vector.get('identity', 0.0)
            ctx.identity_cost_weight = identity_cost_weight
            
            # Store modulation params for downstream phases
            ctx.omega_modulation = {
                'n_worlds': modulated_n_worlds,
                'identity_cost_weight': identity_cost_weight,
                'other_tolerance': 1.0 + 0.2 * omega_vector.get('other', 0.0),
            }

            # ── Three regimes based on blend ──
            if blend < 0.05:
                # Pure action mode (matches current behavior for Ω << threshold)
                ctx.inquiry_skipped = True
                ctx.selected_question = None
                ctx.inquiry_omega_value = omega_value
                if inquiry_stream:
                    inquiry_stream.inquiry_active = False
                    inquiry_stream.last_question = None
                    inquiry_stream.last_omega = omega_value

            elif blend > 0.95:
                # Pure inquiry mode (matches current behavior for Ω >> threshold)
                ctx.inquiry_skipped = False
                ctx.selected_question = best_question
                ctx.inquiry_omega_value = omega_value
                if inquiry_stream:
                    inquiry_stream.inquiry_active = True
                    inquiry_stream.last_question = best_question
                    inquiry_stream.last_omega = omega_value

                # ── Inquiry-to-Action Bridge (unchanged from original) ──
                from telos.intent_ir import IntentIR
                question_id = best_question.get('id', '') if best_question else ''
                question_type = best_question.get('type', 'proceed') if best_question else 'proceed'

                skip_inquiry = False

                if question_id == 'explore_terrain':
                    angle = np.random.uniform(0, 2 * np.pi)
                    action_vec = np.array([np.cos(angle), np.sin(angle)]) * 0.5
                    ctx.selected_intent = IntentIR(
                        intent_type="inquiry_explore",
                        confidence=min(1.0, omega_value),
                        params={
                            "question": best_question,
                            "omega_value": omega_value,
                            "inquiry_mode": True,
                            "action_vector": action_vec,
                            "is_exploratory": True,
                        },
                        metadata={
                            "stream": "inquiry",
                            "question_id": question_id,
                            "bridge_action": "random_walk",
                        },
                    )

                elif question_id == 'recalibrate_identity':
                    ctx.selected_intent = IntentIR(
                        intent_type="inquiry_recalibrate",
                        confidence=min(1.0, omega_value),
                        params={
                            "question": best_question,
                            "omega_value": omega_value,
                            "inquiry_mode": True,
                            "identity_repair": True,
                            "recovery_mode": True,
                        },
                        metadata={
                            "stream": "inquiry",
                            "question_id": question_id,
                            "bridge_action": "identity_repair",
                        },
                    )
                    if hasattr(pipeline, '_meta_cognition'):
                        try:
                            pipeline._meta_cognition._force_recovery = True
                        except AttributeError:
                            pass

                elif question_id == 'resolve_disagreement':
                    if hasattr(pipeline, 'council') and ctx.verdict:
                        for signal in ctx.verdict.signals:
                            signal.evidence_weight = min(
                                1.0, signal.evidence_weight * 1.5
                            )
                    ctx.selected_intent = IntentIR(
                        intent_type="inquiry_resolve",
                        confidence=min(1.0, omega_value),
                        params={
                            "question": best_question,
                            "omega_value": omega_value,
                            "inquiry_mode": True,
                            "re_run_council": True,
                            "higher_evidence_weight": True,
                        },
                        metadata={
                            "stream": "inquiry",
                            "question_id": question_id,
                            "bridge_action": "re_weight_council",
                        },
                    )

                elif question_id == 'default_navigate':
                    skip_inquiry = True

                else:
                    ctx.selected_intent = IntentIR(
                        intent_type=f"inquiry_{question_type}",
                        confidence=min(1.0, omega_value),
                        params={
                            "question": best_question,
                            "omega_value": omega_value,
                            "inquiry_mode": True,
                        },
                        metadata={
                            "stream": "inquiry",
                            "question_id": question_id,
                        },
                    )

                # Record the answer in tripartite uncertainty
                if hasattr(tripartite_u, 'record_answer'):
                    tripartite_u.record_answer(question_type)

                if not skip_inquiry:
                    return  # Skip normal action selection, we're in Inquiry Mode
                else:
                    ctx.selected_question = None
                    ctx.inquiry_skipped = True
                    ctx.selected_intent = None
                    if inquiry_stream:
                        inquiry_stream.inquiry_active = False
                        inquiry_stream.last_question = None

            else:
                # Blended mode: composite intent between action and inquiry
                ctx.inquiry_skipped = False
                ctx.selected_question = best_question
                ctx.inquiry_omega_value = omega_value
                if inquiry_stream:
                    inquiry_stream.inquiry_active = True
                    inquiry_stream.last_question = best_question
                    inquiry_stream.last_omega = omega_value

                # Build a blended intent that mixes action and exploration
                from telos.intent_ir import IntentIR
                question_id = best_question.get('id', '') if best_question else ''
                question_type = best_question.get('type', 'proceed') if best_question else 'proceed'

                # action_vector = (1-blend) * goal_direction + blend * explore_direction
                # Use the question type to determine exploration direction
                if question_id == 'explore_terrain':
                    angle = np.random.uniform(0, 2 * np.pi)
                    explore_vec = np.array([np.cos(angle), np.sin(angle)]) * 0.5
                else:
                    explore_vec = np.array([0.0, 0.0])

                # Get goal direction from world state if available
                goal_dir = np.array([0.0, 0.0])
                if hasattr(pipeline, '_goal') and pipeline._goal is not None:
                    goal = pipeline._goal
                    if hasattr(ctx, 'state') and ctx.state is not None:
                        diff = np.array(goal, dtype=float) - ctx.state[:2]
                        norm = np.linalg.norm(diff)
                        if norm > 0:
                            goal_dir = diff / norm

                blended_action = (1.0 - blend) * goal_dir + blend * explore_vec
                blended_confidence = max(0.5, omega_value) * (0.5 + 0.5 * blend)

                ctx.selected_intent = IntentIR(
                    intent_type="blended_inquiry",
                    confidence=min(1.0, blended_confidence),
                    params={
                        "question": best_question,
                        "omega_value": omega_value,
                        "inquiry_blend": blend,
                        "inquiry_mode": True,
                        "action_vector": blended_action,
                        "is_blended": True,
                        "goal_weight": 1.0 - blend,
                        "explore_weight": blend,
                    },
                    metadata={
                        "stream": "inquiry",
                        "question_id": question_id,
                        "bridge_action": "blended",
                        "blend": round(blend, 3),
                    },
                )

                # Record the answer in tripartite uncertainty
                if hasattr(tripartite_u, 'record_answer'):
                    tripartite_u.record_answer(question_type)

                # Fall through to normal action selection (don't return early)
                # The blended intent is already set in ctx.selected_intent

        # ── Phase 2: Normal action selection (Commitment Optimization) ──
        # If Synthesis produced a reconciled intent (and it's not irreconcilable), use it
        if ctx.synthesis and ctx.synthesis.reconciled_intent and not ctx.synthesis.irreconcilable:
            # In blended mode, blend the reconciled intent with inquiry intent
            blend = getattr(ctx, 'inquiry_blend', 0.0)
            if 0.05 <= blend <= 0.95 and ctx.selected_intent is not None:
                # Blend: use inquiry intent's action but synthesis confidence
                blended_conf = max(ctx.selected_intent.confidence, ctx.synthesis.reconciled_intent.confidence) * (0.5 + 0.5 * blend)
                ctx.selected_intent.confidence = min(1.0, blended_conf)
                # Keep the blended intent as primary
            else:
                ctx.selected_intent = ctx.synthesis.reconciled_intent
            return

        if ctx.intents:
            # ── Interpretation Phase: choose between competing perspectives ──
            # Uses InternalDebate + InterpretationEngine as the core choice mechanism.
            # The winning perspective's confidence modulates J(τ).
            try:
                debate = getattr(pipeline, '_internal_debate', None)
                ie = getattr(pipeline, '_interpretation_engine', None)
                debate_winner_weight = 1.0
                if debate is not None and ctx.selected_intent is not None:
                    debate_ctx = {
                        "uncertainty": getattr(ctx, 'inquiry_omega_value', 0.5),
                        "options": [i.intent_type for i, _ in ctx.intents[:3]],
                        "goals": {"survival": 1.0},
                        "resources": {"budget": getattr(pipeline.budget_manager, 'total_budget_ms', 100)},
                    }
                    result = debate.debate(
                        context=debate_ctx,
                        context_description=f"Select best action from {len(ctx.intents)} options",
                    )
                    if hasattr(result, 'consensus_level'):
                        debate_winner_weight = 0.5 + 0.5 * result.consensus_level
                # Detect principle conflicts among intents via InterpretationEngine
                if ie is not None and hasattr(ie, 'detect_conflict'):
                    from telos.core.reasoning.interpretation_engine import Principle
                    principles = []
                    for intent, _ in ctx.intents[:5]:
                        stream = intent.metadata.get('stream', 'unknown') if intent.metadata else 'unknown'
                        principles.append(Principle(
                            name=intent.intent_type, description=f"from {stream}",
                            axiom_ref="4.6", current_priority=float(intent.confidence),
                        ))
                    if principles:
                        conflict = ie.detect_conflict(principles=principles, context={
                            "cycle": ctx.cycle_count, "n_intents": len(ctx.intents),
                        })
                        if conflict is not None:
                            record = ie.interpret(
                                conflict_type=conflict, principles=principles,
                                context={"n_intents": len(ctx.intents)},
                            )
                            ctx.interpretation_conflict = {
                                "type": conflict.value if hasattr(conflict, 'value') else str(conflict),
                                "resolution": getattr(record, 'resolution', ''),
                            }
            except Exception as e:
                logger.debug(f"Interpretation debate failed: {e}")
                debate_winner_weight = 1.0

            # ── TELOS Commitment Theory (Axiom 5.1): compute C* from all signals ──
            score = None
            try:
                commitment_opt = getattr(pipeline, '_commitment_optimizer', None)
                infra = getattr(pipeline, '_infra_manager', None)
                sim = getattr(pipeline, '_sim_engine', None)
                identity_entropy = getattr(pipeline, '_identity_entropy', None)
                attn = getattr(pipeline, '_attention_engine', None)

                if commitment_opt and infra:
                    # Gather signals from tracked components
                    cost = getattr(infra, 'cost_tracker', None)
                    if cost is None:
                        recovery_r = 0.0
                        maint_r = 0.5
                    else:
                        recovery_r = cost.recovery_ratio
                        maint_r = cost.maintenance_ratio
                    collapse_rate = identity_entropy.collapse_rate if identity_entropy else 0.0
                    div = sim.rolling_diversity if sim else 0.0
                    # Prediction error from attention trajectory divergences
                    pe = 0.0
                    if attn and hasattr(attn, '_trajectory_divergences') and attn._trajectory_divergences:
                        recent_divs = attn._trajectory_divergences[-3:]
                        pe = min(1.0, sum(recent_divs) / max(len(recent_divs), 1) * 0.5)

                    # Per-axis modulation: identity cost weight
                    identity_cost_weight = getattr(ctx, 'identity_cost_weight', 1.0)

                    # IdentityUtilityEngine: profile-aware identity cost
                    iu = getattr(pipeline, '_identity_utility', None)
                    if iu is not None and iu.active_profile is not None:
                        profile = iu.active_profile
                        action_type = ctx.selected_intent.intent_type if ctx.selected_intent else "unknown"
                        action_scores = {
                            "exploration": 0.5 if "explore" in action_type or "inquiry" in action_type else 0.2,
                            "correctness": 0.7,
                            "safety": 0.3 if "reflex" in action_type else 0.6,
                            "efficiency": 0.5,
                            "coherence": 0.8,
                        }
                        dot = sum(action_scores.get(k, 0) * v for k, v in profile.weights.items())
                        norm_a = max(1e-6, sum(v*v for v in action_scores.values())**0.5)
                        norm_p = max(1e-6, sum(v*v for v in profile.weights.values())**0.5)
                        profile_similarity = dot / (norm_a * norm_p)
                        identity_cost_weight = max(identity_cost_weight, 1.0 - profile_similarity)

                    # Low diversity penalty
                    future_val = min(1.0, div * 2.0) if div > 0 else 0.0
                    if div < 0.3 and sim and sim.rolling_diversity < 0.3:
                        future_val = max(0.0, future_val - 0.3)

                    # ── Unified Cognitive Functional: compute all J terms ──
                    # ηI_gain: expected information gain from SurpriseBudget
                    sb = getattr(pipeline, '_surprise_budget', None)
                    ig = sb.compute_information_gain(error=pe, expected=0.1,
                                                     novelty=div) if sb else 0.0

                    # ζG_theory: theory gain from TheoryBuilder
                    tb = getattr(pipeline, '_theory_builder', None)
                    tg = tb.estimate_theory_gain(context={"state": str(ctx.state)[:50]},
                                                  action=ctx.selected_intent.intent_type
                                                  if ctx.selected_intent else "unknown") if tb else 0.0

                    # αU: uncertainty bonus from tripartite U
                    tu = getattr(pipeline, '_tripartite_u', None)
                    u_val = tu.composite if tu else 0.0

                    # κA: aesthetic heuristic — parsimony, compression, symmetry
                    av = 0.0
                    try:
                        mc = getattr(pipeline, '_model_competition', None)
                        parsimony = 0.5
                        if mc and hasattr(mc, 'dominant_model') and mc.dominant_model:
                            parsimony = getattr(mc.dominant_model, 'parsimony', 0.5)
                        ic = getattr(pipeline, '_identity_compression', None)
                        compression = ic.overall_compression_rate if ic and hasattr(ic, 'overall_compression_rate') else 0.0
                        av = min(0.3, parsimony * 0.5 + compression * 0.5)
                    except Exception:
                        av = 0.0

                    # Season bonus: research phases modulate exploration
                    season_bonus = getattr(ctx, 'research_bonus', 1.0)
                    discovery_rate = getattr(ctx, 'discovery_rate', 0.0)
                    belief_capital_value = discovery_rate * 0.1

                    # Mission -> Project connection: auto-spawn if no project
                    try:
                        mp = getattr(pipeline, '_mission_portfolio', None)
                        pp = getattr(pipeline, '_project_portfolio', None)
                        if mp and pp and pp.active_project is None:
                            active_missions = mp.active_missions()
                            if active_missions:
                                mp.spawn_project(
                                    active_missions[0].id, pp,
                                    f"auto_{ctx.selected_intent.intent_type if ctx.selected_intent else 'task'}",
                                    ctx.cycle_count,
                                )
                    except Exception:
                        pass

                    # F(I) Projection Gate: is this trajectory admissible?
                    # Identity is no longer a penalty term — it constrains
                    # the admissible optimization space.
                    admissibility = commitment_opt.is_trajectory_admissible(
                        intent_type=ctx.selected_intent.intent_type if ctx.selected_intent else "unknown",
                        project_id=getattr(getattr(ctx, 'project_coherence', None), 'project_id', None),
                    )
                    if not admissibility:
                        logger.warning(
                            f"F(I) blocked: {ctx.selected_intent.intent_type if ctx.selected_intent else 'unknown'} "
                            f"— trajectory incompatible with Identity Core"
                        )

                    # εC_align: alignment cost from trust manager
                    trust = getattr(pipeline, '_trust_manager', None)
                    ac = 0.0
                    if trust is not None and hasattr(trust, 'get_trust_score'):
                        trust_score = trust.get_trust_score("system")
                        ac = max(0.0, 0.5 - trust_score) if trust_score is not None else 0.0

                    # θE_interpret: interpretation energy from InterpretationEngine
                    ie_mod = getattr(pipeline, '_interpretation_engine', None)
                    ie_val = min(0.3, ie_mod.total_conflicts * 0.05) if ie_mod else 0.0

                    # C_o: opportunity cost = max(alternative_utility) - chosen_utility
                    co = 0.0
                    if ctx.intents and len(ctx.intents) > 1:
                        best_score = ctx.intents[0][1] if ctx.intents else 0.0
                        second_score = ctx.intents[1][1] if len(ctx.intents) > 1 else best_score
                        co = max(0.0, best_score - second_score)

                    # Modulate expected reward by debate consensus (interpretation as choice)
                    modulated_reward = (ctx.simulation_confidence or 1.0) * debate_winner_weight

                    # θE_interpret: now computed from debate disagreement + conflicts
                    debate_disagreement = 1.0 - (debate_winner_weight - 0.5) * 2.0 if debate_winner_weight > 0.5 else 0.5
                    ie_val = min(0.3, ie_val + debate_disagreement * 0.1)

                    # πG_project: strategic coherence gain from project alignment
                    pg = 0.0
                    sc = getattr(pipeline, '_strategic_coherence', None)
                    if sc is not None:
                        pp = getattr(pipeline, '_project_portfolio', None)
                        active_project = pp.active_project if pp else None
                        if active_project:
                            coherence = sc.evaluate(
                                action_type=ctx.selected_intent.intent_type if ctx.selected_intent else "unknown",
                                project_id=active_project.id,
                                project_value=active_project.value,
                                project_stagnation=active_project.stagnation_cycles,
                            )
                            pg = coherence.score
                            ctx.project_coherence = coherence

                    # Modulate reward by research season + belief capital
                    modulated_reward = modulated_reward * season_bonus + belief_capital_value

                    score = commitment_opt.evaluate(
                        expected_reward=modulated_reward,
                        maintenance_cost=maint_r,
                        recovery_cost=recovery_r,
                        identity_cost=abs(collapse_rate) * 0.5 * identity_cost_weight,
                        future_option_value=future_val,
                        identity_entropy=collapse_rate,
                        recovery_ratio=recovery_r,
                        counterfactual_diversity=div,
                        prediction_error=pe,
                        information_gain=ig,
                        theory_gain=tg,
                        uncertainty_bonus=u_val * 0.3,
                        alignment_cost=ac,
                        interpretation_energy=ie_val,
                        opportunity_cost=co,
                        project_coherence_gain=pg,
                        aesthetic_value=av,
                    )
                    commitment_mod = score.commitment

                    # Record strain
                    commitment_opt.strain.record_strain(maint_r, recovery_r)
                    # Store per-term J(τ) breakdown in context
                    ctx.j_term_breakdown = {
                        "expected_reward": score.expected_reward,
                        "maintenance_cost": score.maintenance_cost,
                        "recovery_cost": score.recovery_cost,
                        "identity_cost": score.identity_cost,
                        "alignment_cost": score.alignment_cost,
                        "identity_violation": score.identity_violation,
                        "future_option_value": score.future_option_value,
                        "counterfactual_diversity": score.counterfactual_diversity,
                        "prediction_error": score.prediction_error,
                        "information_gain": score.information_gain,
                        "theory_gain": score.theory_gain,
                        "uncertainty_bonus": score.uncertainty_bonus,
                        "interpretation_energy": score.interpretation_energy,
                        "opportunity_cost": score.opportunity_cost,
                        "project_coherence_gain": score.project_coherence_gain,
                        "aesthetic_value": score.aesthetic_value,
                        "commitment": score.commitment,
                    }
                else:
                    commitment_mod = 1.0
            except Exception as e:
                logger.warning(f"Commitment optimization failed: {e}")
                commitment_mod = 1.0

            ctx.commitment_score = score.commitment if score is not None else None
            
            # Apply blend to intent weighting
            blend = getattr(ctx, 'inquiry_blend', 0.0)
            if 0.05 <= blend <= 0.95 and ctx.selected_intent is not None:
                # In blended mode, keep the blended intent but adjust its weight
                pass  # ctx.selected_intent already set from blended mode
            else:
                ctx.intents = [
                    (intent, weight * ctx.simulation_confidence * commitment_mod)
                    for intent, weight in ctx.intents
                ]
                ctx.intents.sort(key=lambda x: x[1], reverse=True)
                ctx.selected_intent = ctx.intents[0][0]

        # ── RegretMemory: capture counterfactuals from selection ──
        regret = getattr(pipeline, '_regret_memory', None)
        if regret is not None and ctx.selected_intent is not None:
            try:
                cf_options = []
                for i, (intent, score) in enumerate(getattr(ctx, 'intents', [])[:5]):
                    cf_options.append({"intent": intent.intent_type, "estimated_score": score})
                # Only record if we have alternatives
                if len(cf_options) > 1:
                    regret.record_decision(
                        cycle=ctx.cycle_count,
                        chosen_intent=ctx.selected_intent.intent_type,
                        chosen_score=ctx.simulation_confidence or 0.5,
                        chosen_outcome=True,  # optimistic at selection time
                        counterfactual_options=cf_options[1:],
                        decision_type="selection",
                    )
            except Exception as e:
                logger.debug(f"RegretMemory recording failed: {e}")
