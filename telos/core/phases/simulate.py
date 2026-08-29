import logging

from telos.core.phases.base import Phase, PhaseContext
from telos.core.reasoning.causal.scm import StructuralCausalModel

logger = logging.getLogger('telos_pipeline')


def counterfactual_budget(mode: str, n_worlds: int, peak_confidence: float) -> int:
    """v7 E: per-cycle counterfactual simulation budget.

    Fast mode makes the budget explicit: high-confidence routine cycles
    (peak stream confidence >= 0.8) roll a single world (C_simulate ~= 0);
    all other fast cycles run at half the configured budget. Standard /
    research / debug modes are UNCHANGED (full budget) — behavior-preserving.

    Args:
        mode: pipeline mode string.
        n_worlds: configured (effective) world count.
        peak_confidence: max confidence across this cycle's stream intents.

    Returns:
        World count for this cycle's counterfactual generation (>= 1).
    """
    if mode != "fast":
        return max(1, int(n_worlds))
    if peak_confidence >= 0.8:
        return 1
    return max(1, int(n_worlds) // 2)


class SimulatePhase(Phase):
    name = "simulate"

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        base_horizon = pipeline._infra_manager.adaptive_horizon or pipeline.config.horizon
        ctx.effective_horizon = max(base_horizon, pipeline.config.feedback_lag + 1)

        if pipeline._sim_engine and pipeline.config.simulator:
            est_sim_cost = 15.0
            if pipeline.budget_manager.check_budget("simulation", est_sim_cost):
                # ── Fix 1 (C1): Integrate SCM for causal counterfactuals ──
                # Build/update the StructuralCausalModel from domain facts
                scm = getattr(pipeline, '_scm', None)
                if scm is None:
                    scm = StructuralCausalModel()
                    pipeline._scm = scm

                domain_facts = getattr(ctx, 'domain_facts', None)
                if domain_facts is not None:
                    scm.parse_domain_facts(domain_facts)

                # Store causal graph in context for decision trace
                ctx.causal_graph = scm.graph_summary if scm else None

                # A1: Pass attention allocation to weight simulation diversity
                alloc = getattr(ctx, 'attention_allocation', None)
                alloc_dict = {
                    "threat_ratio": alloc.threat_ratio,
                    "opportunity_ratio": alloc.opportunity_ratio,
                    "maintenance_ratio": alloc.maintenance_ratio,
                } if alloc else None

                # ── v7 E: Counterfactual budget (fast mode, confidence-gated) ──
                # Routine high-confidence cycles do NOT need full multi-world
                # counterfactuals: confidence >= 0.8 -> 1 world (cheap
                # roll-ahead, C_simulate ~= 0); otherwise the configured world
                # count stands. Standard mode is UNCHANGED (full budget).
                sim_n_worlds = ctx.effective_n_worlds
                if pipeline.config.is_fast_mode:
                    peak_conf = 0.0
                    for _intent, _conf in (getattr(ctx, "intents", None) or []):
                        try:
                            peak_conf = max(peak_conf, float(_conf))
                        except (TypeError, ValueError):
                            pass
                    sim_n_worlds = counterfactual_budget(
                        pipeline.config.mode, ctx.effective_n_worlds, peak_conf)

                # Use SCM-based generation when possible, fallback to standard
                ctx.sim_options = pipeline._sim_engine.generate_options(
                    ctx.state, ctx.effective_horizon, sim_n_worlds,
                    attention_allocation=alloc_dict,
                    cycle=getattr(ctx, 'cycle_count', 0),
                )
                ctx.worlds_generated = len(ctx.sim_options)
                ctx.strategic_options_data = [
                    {
                        "rank": o.rank,
                        "score": o.score,
                        "horizon": o.horizon,
                        "metadata": o.metadata,
                        "variance": o.variance,
                        "probabilistic": {
                            "mean": o.probabilistic.mean,
                            "std": o.probabilistic.std,
                            "ci_lower": o.probabilistic.ci_lower,
                            "ci_upper": o.probabilistic.ci_upper,
                            "n_samples": o.probabilistic.n_samples,
                        } if o.probabilistic else None,
                    }
                    for o in ctx.sim_options
                ]
                if ctx.sim_options:
                    ctx.predicted_state = getattr(ctx.sim_options[0].world, 'state', None)
                    pipeline._last_predicted_state = ctx.predicted_state
                    best = ctx.sim_options[0]
                    best_score = best.score
                    if best.probabilistic:
                        eps = 1e-6
                        cv = best.probabilistic.std / max(abs(best.probabilistic.mean), eps)
                        ctx.simulation_confidence = max(0.3, min(1.5, 1.0 - cv + 0.5 * best_score))
                    else:
                        ctx.simulation_confidence = max(0.5, min(1.5, 1.0 + 0.1 * best_score))
                    logger.debug(f"Cycle {ctx.cycle_count}: Simulation best score={best_score:.2f}, confidence_mult={ctx.simulation_confidence:.2f}")

                pipeline.budget_manager.consume("simulation", est_sim_cost)
