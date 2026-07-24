"""
Evaluate Phase — Rank intents with UCB exploration bonus (Lambda3.4) and
dominant-stream penalty (Lambda4.5).

Fix 3 (C2): After evaluating all options, compute F(s_T) = counterfactual_diversity
at the horizon endpoint. Adds terminal_value field to evaluation results and
includes it in the commitment score calculation.

The Evaluate phase ranks intents from the Simulation phase. After computing
base scores, it applies:
  1. UCB exploration bonus from MissionPolicyManager (Lambda3.4)
  2. Dominant-stream penalty when the same stream wins repeatedly (Lambda4.5)
  3. Terminal reward F(s_T) from counterfactual diversity at horizon endpoint (Fix 3)
"""

import logging

from telos.core.phases.base import Phase, PhaseContext
from telos.core.representation_selector import RepresentationSelector

logger = logging.getLogger('telos_pipeline')


class EvaluatePhase(Phase):
    name = "evaluate"

    def __init__(self):
        self._rep_selector = RepresentationSelector()

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        # P0 D9: Use RepresentationSelector for dynamic modality switching
        if ctx.domain_facts:
            metadata = ctx.domain_facts.metadata if hasattr(ctx.domain_facts, 'metadata') else None
            rep_type, rep_conf = self._rep_selector.select(ctx.domain_facts, metadata)
            ctx.representation = rep_type
            ctx.representation_confidence = rep_conf
            # Also store for backward compatibility with planner
            if pipeline._planner and hasattr(pipeline._planner, 'select_representation'):
                if hasattr(pipeline._planner, '_current_representation'):
                    pipeline._planner._current_representation = rep_type

        if not ctx.intents:
            return

        # ── Fix 3 (C2): Compute terminal reward F(s_T) = counterfactual_diversity at endpoint ──
        terminal_value = 0.0
        if hasattr(ctx, 'sim_options') and ctx.sim_options:
            # Counterfactual diversity at the horizon endpoint
            options = ctx.sim_options
            if len(options) >= 2:
                scores = [getattr(o, 'score', 0.0) for o in options]
                import numpy as np
                terminal_value = float(np.var(scores)) if len(scores) > 1 else 0.0
                # Normalize to [0, 1] range
                terminal_value = min(1.0, terminal_value)
                logger.debug(
                    "Fix 3 (terminal_value): F(s_T) = {:.4f} from {} options".format(
                        terminal_value, len(options)
                    )
                )

        # Store terminal_value in context for downstream phases
        ctx.terminal_value = terminal_value

        # --- Lambda3.4: Apply UCB exploration bonus ---
        infra = getattr(pipeline, '_infra_manager', None)
        if infra and hasattr(infra, 'policy') and infra.policy is not None:
            domain = getattr(pipeline.config.simulator, 'domain', 'unknown') if pipeline.config.simulator else 'unknown'
            for i, (intent, score) in enumerate(ctx.intents):
                bonus = infra.policy.exploration_bonus(domain)
                adjusted_score = score * (0.7 + 0.3 * bonus)
                ctx.intents[i] = (intent, adjusted_score)

            # Log when exploration bonus significantly changes ranking
            if len(ctx.intents) >= 2:
                sorted_base = sorted(ctx.intents, key=lambda x: x[1], reverse=True)
                top_base = sorted_base[0][0].intent_type
                if ctx.intents[0][0].intent_type != top_base:
                    logger.debug(
                        "Lambda3.4: exploration bonus changed top intent from '%s' "                        "to '%s' (domain=%s)",
                        top_base, ctx.intents[0][0].intent_type, domain
                    )

        # --- Lambda4.5: Penalize dominant stream if stuck ---
        if infra and hasattr(infra, 'calibrator'):
            calibrator = infra.calibrator
            if hasattr(calibrator, 'is_stuck') and calibrator.is_stuck():
                dominant = calibrator.dominant_stream
                if dominant:
                    logger.info(
                        "Lambda4.5: Applying -0.1 penalty to intents from dominant stream "                        "'%s' — forcing exploration of alternatives",
                        dominant
                    )
                    for i, (intent, score) in enumerate(ctx.intents):
                        for sa in ctx.stream_activations:
                            if (sa.activated and sa.intent is not None
                                    and sa.intent.intent_type == intent.intent_type
                                    and sa.stream_name == dominant):
                                ctx.intents[i] = (intent, score * 0.9)
                                break

        # ── Fix 8: Wire CommitmentOptimizer.evaluate() into pipeline ──
        if hasattr(pipeline, '_commitment_optimizer') and pipeline._commitment_optimizer is not None:
            commitment_opt = pipeline._commitment_optimizer
            try:
                # Gather signals for commitment evaluation
                cogs = getattr(ctx, 'sim_options', None)
                diversity = 0.0
                if cogs and len(cogs) >= 2:
                    scores_list = [getattr(o, 'score', 0.0) for o in cogs]
                    import numpy as np
                    diversity = float(np.var(scores_list)) if len(scores_list) > 1 else 0.0
                # Maintenance & recovery from resource budgets
                rb = getattr(ctx, 'resource_budgets', {})
                energy_util = rb.get('energy', {}).get('utilization', 0.5)
                recovery_val = rb.get('recovery', {}).get('recovery_mode_cycles', 0) / 10.0 if rb.get('recovery', {}).get('recovery_mode_cycles', 0) > 0 else 0.0
                id_entropy = rb.get('identity', {}).get('identity_entropy', 0.0)
                # Planning horizon
                horizon = getattr(ctx, 'planning_horizon', getattr(pipeline, 'planning_horizon', None))
                h_val = horizon.horizon if hasattr(horizon, 'horizon') else 1
                # Terminal value from optional context
                tv = getattr(ctx, 'terminal_value', 0.0)
                # Prediction error
                pred_err = getattr(ctx, 'prediction_error', 0.0)

                score = commitment_opt.evaluate(
                    expected_reward=float(max((s for _, s in ctx.intents), default=0.5)),
                    maintenance_cost=energy_util * 0.3,
                    recovery_cost=recovery_val * 0.5,
                    identity_cost=id_entropy * 0.2,
                    future_option_value=(1.0 - energy_util) * 0.2,
                    identity_entropy=id_entropy,
                    recovery_ratio=recovery_val / max(energy_util, 0.01),
                    counterfactual_diversity=diversity,
                    horizon=h_val,
                    terminal_value=tv,
                    prediction_error=pred_err,
                )
                ctx.commitment_score = score.commitment
                ctx.j_term_breakdown = score.to_dict()
                logger.debug(
                    "Fix 8 (CommitmentOptimizer): J(t)={:.3f}, breakdown={{{}}}".format(
                        score.commitment,
                        ", ".join(f"{k}={v:.3f}" for k, v in score.to_dict().items()
                                  if isinstance(v, (int, float)))
                    )
                )
            except Exception as e:
                logger.warning(f"Fix 8 (CommitmentOptimizer) failed: {e}")
                ctx.commitment_score = 0.5
