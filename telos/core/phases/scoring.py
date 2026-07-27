"""Commitment scoring computation."""
import numpy as np

def compute_unified_score(pipeline, ctx):
    """Compute J(τ) score for current context."""
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
    
                        # Project-centric cognition: project owns the decision context
                        try:
                            mp = getattr(pipeline, '_mission_portfolio', None)
                            pp = getattr(pipeline, '_project_portfolio', None)
                            if pp:
                                active_proj = pp.active_project
                                if mp and pp and active_proj is None:
                                    active_missions = mp.active_missions()
                                    if active_missions:
                                        proj = mp.spawn_project(
                                            active_missions[0].id, pp,
                                            f"auto_{ctx.selected_intent.intent_type if ctx.selected_intent else 'task'}",
                                            ctx.cycle_count,
                                        )
                                        if proj:
                                            pp.activate(proj.id, ctx.cycle_count)
                                            active_proj = pp.active_project
                                if active_proj:
                                    active_proj.stagnation_cycles = active_proj.stagnation_cycles + 1
                                    ctx.project_context = {
                                        "project_id": active_proj.id,
                                        "project_name": active_proj.name,
                                        "project_stagnation": active_proj.stagnation_cycles,
                                    }
                        except Exception:
                            pass
    
                        # ROI computation for current representation (Insight 7)
                        try:
                            mc = getattr(pipeline, '_model_competition', None)
                            if mc and hasattr(mc, 'dominant_model') and mc.dominant_model:
                                dom = mc.dominant_model
                                roi = dom.market_price / max(getattr(dom, 'age_cycles', 1), 1)
                                ctx.representation_roi = roi
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
