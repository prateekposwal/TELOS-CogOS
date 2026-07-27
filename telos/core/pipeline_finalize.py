"""Pipeline finalize — post-cycle: trace building, axiom verification,
v2 module wiring, resource accounting, checkpoint, experience observation.
"""

import logging
from typing import Any

from telos.core.accounting.resource_accounting import ResourceCost

logger = logging.getLogger('telos_pipeline')


def run_axiom_prover(pipeline, trace, ctx) -> None:
    """Verify all axioms against the current cycle."""
    try:
        results = pipeline._axiom_prover.verify(
            trace, ctx, stream_results=getattr(ctx, 'stream_activations', []),
        )
        passed = sum(1 for r in results.values() if r["passed"])
        failed = len(results) - passed
        if failed > 0:
            failed_list = [aid for aid, r in results.items() if not r["passed"]]
            logger.warning(f"Axiom compliance: {passed}/{len(results)} passed, "
                          f"{failed} failed: {', '.join(failed_list[:10])}")
        if hasattr(trace, 'axiom_results'):
            trace.axiom_results = results
    except Exception as e:
        logger.warning(f"Axiom verification skipped: {e}")


def run_v2_module_hooks(pipeline, ctx, trace) -> None:
    """Run all v2/v2.5 post-cycle module hooks."""
    was_blocked = getattr(ctx, 'council_blocked', False) or getattr(ctx, 'firewall_blocked', False)
    di = trace.decision_integrity if trace else 0.0
    md = trace.mission_drift if trace else 0.0

    # 1. CouncilReflector with REAL validator signals
    try:
        signals = []
        if ctx.verdict:
            for s in ctx.verdict.signals:
                signals.append({
                    "validator_name": s.validator_name,
                    "passed": s.passed,
                    "confidence": s.confidence,
                    "reason": s.reason,
                    "evidence_weight": getattr(s, 'evidence_weight', 0.5),
                })
        pipeline._council_reflector.record_decision(
            was_blocked=was_blocked, predicted_block=was_blocked,
            actual_block=was_blocked, validator_signals=signals,
        )
    except Exception:
        pass

    # 2. IntrospectionScheduler: consume tier results for pipeline behavior
    try:
        due_tiers = pipeline._introspection_scheduler.get_due_tiers(ctx.cycle_count)
        reports = pipeline._introspection_scheduler.introspect(ctx.cycle_count)
        if due_tiers:
            from telos.core.introspection.scheduler import IntrospectionTier
            for tier in due_tiers:
                if tier == IntrospectionTier.REFLECT and ctx.cycle_count > 0:
                    logger.info(f"Introspection: REFLECT tier due at cycle {ctx.cycle_count}")
                elif tier == IntrospectionTier.STRATEGIC:
                    logger.info(f"Introspection: STRATEGIC tier due at cycle {ctx.cycle_count}")
                    tb = getattr(pipeline, '_theory_builder', None)
                    if tb and tb.total_experiences > 0:
                        tb.cluster()
                        tb.hypothesize()
                        tb.promote()
    except Exception:
        pass

    # 3. UnknownUnknownDetector: wire into curiosity cycle
    try:
        uud = getattr(pipeline, '_unknown_unknown_detector', None)
        if uud is not None and hasattr(ctx, 'state') and ctx.state is not None:
            import numpy as np
            state = ctx.state
            predictions = {"state_norm": float(np.linalg.norm(state))}
            observations = {"state_norm": float(np.linalg.norm(state))}
            uud.record_observation(ctx.cycle_count, predictions, observations)
            questions = uud.promote_to_questions(ctx.cycle_count)
            if questions:
                logger.info(f"UnknownUnknownDetector: {len(questions)} new question(s) formed")
    except Exception:
        pass

    # 4. CognitiveEnergy
    try:
        pipeline._cognitive_energy.consume(1.0 if was_blocked else 0.3)
    except Exception:
        pass

    try:
        pipeline._dual_confidence.report(
            decision_id=f"cycle_{ctx.cycle_count}",
            dc=1.0 - md if trace else 0.5,
            ec=getattr(ctx, 'explanation_confidence', 0.0),
        )
    except Exception:
        pass

    try:
        pipeline._active_forgetting.auto_examine(ctx.cycle_count)
    except Exception:
        pass

    try:
        momentum_rec = pipeline._cognitive_momentum.recommend_unstick()
        if momentum_rec:
            logger.info(f"CognitiveMomentum: {momentum_rec} (M={pipeline._cognitive_momentum.momentum:.2f})")
    except Exception:
        pass

    # 5. Research cycle: seasons, discovery rate, ecology update
    try:
        season = pipeline._research_seasons.get_phase(ctx.cycle_count)
        bonus = pipeline._research_seasons.exploration_bonus(ctx.cycle_count)
        ctx.research_season = season.value
        ctx.research_bonus = bonus

        pipeline._discovery_rate.record(ctx.cycle_count, new_insights=1 if not was_blocked else 0)
        ctx.discovery_rate = pipeline._discovery_rate.marginal_rate

        pipeline._ecosystem.update_discovery_rate("core", 1 if not was_blocked else 0, 1.0)

        discovery_step = pipeline._discovery_orchestrator.cycle(
            ctx.cycle_count,
            identity_active=True,
            mission_active=True,
            project_active=getattr(ctx, 'selected_intent', None) is not None,
            n_theories=len(getattr(pipeline._theory_builder, '_theories', {})),
            n_bridges=len(pipeline._ecosystem.get_bridge_candidates()),
        )
        ctx.discovery_step = discovery_step
    except Exception:
        pass

    # 6. IdentityUtilityEngine: compute with active profile weights
    try:
        iu = pipeline._identity_utility
        profile = iu.active_profile
        if profile is not None:
            marker_value = 1.0 if getattr(pipeline, '_creator_present', False) else 0.5
            iu.compute_utility(
                dimension_scores={
                    "exploration": 0.5,
                    "correctness": 0.8,
                    "safety": 0.6,
                    "efficiency": 0.4,
                    "coherence": marker_value,
                },
                identity_markers=list(profile.identity_markers)[:3] if hasattr(profile, 'identity_markers') else None,
            )
    except Exception:
        pass

    try:
        pipeline._axiom_evolution.observe(
            cycle=ctx.cycle_count, di=di, md=md,
            was_blocked=was_blocked, council_signals=[],
            stream_activations={}, identity_state={},
        )
        pending = pipeline._axiom_evolution.get_pending_proposals()
        if pending and hasattr(pipeline, '_human_gateway') and pipeline._human_gateway is not None:
            for prop in pending[:1]:
                gw = pipeline._human_gateway
                if gw.should_review(council_validated=not was_blocked, decision_integrity=di):
                    verdict = gw.review(
                        intent=f"axiom_proposal:{prop.name}", council_signals=[],
                        decision_integrity=di,
                    )
                    if verdict.approved:
                        pipeline._axiom_evolution.review(prop.id, approved=True)
                    else:
                        pipeline._axiom_evolution.review(prop.id, approved=False)
    except Exception:
        pass

    try:
        if hasattr(ctx, 'verdict') and ctx.verdict and ctx.verdict.validated:
            pipeline._interpretation_engine.record_outcome(
                conflict_id="auto", outcome_quality=di,
            )
    except Exception:
        pass

    try:
        pipeline._assumption_auditor.auto_audit(ctx.cycle_count)
    except Exception:
        pass

    try:
        if was_blocked and hasattr(pipeline, '_error_attribution'):
            pipeline._error_attribution.attribute(
                ctx=ctx, trace=trace,
                stream_activations=getattr(ctx, 'stream_activations', []),
            )
    except Exception:
        pass


def record_resource_accounting(pipeline, ctx) -> None:
    """Record resource costs and enforce budget limits."""
    try:
        ra = pipeline._resource_accounting
        ra.set_cycle(ctx.cycle_count)
        if ctx.selected_intent:
            ra.record_action(
                f"intent:{ctx.selected_intent.intent_type}",
                ResourceCost(
                    compute_ms=pipeline.budget_manager.consumed_ms,
                    memory_traces=len(getattr(ctx, 'stream_activations', []) or []),
                    bandwidth_bytes=float(len(str(ctx.state))) if hasattr(ctx, 'state') else 0.0,
                    storage_entries=1,
                ),
                metadata={"governance": "APPROVED"},
            )
        for sa in getattr(ctx, 'stream_activations', []) or []:
            if getattr(sa, 'activated', False):
                ra.record_stream_activation(
                    stream_name=getattr(sa, 'stream_name', 'unknown'),
                    compute_ms=getattr(sa, 'cost_ms', 2.0),
                )
        ctx.resource_accounting_summary = ra.cycle_summary()
        budget_ok = ra.check_budget(
            max_compute_ms=pipeline.budget_manager.total_budget_ms,
            max_memory_traces=50, max_bandwidth_bytes=10000, max_storage_entries=20,
        )
        ctx.resource_accounting_budget_ok = budget_ok["within_budget"]
        if not budget_ok["within_budget"]:
            logger.warning(f"Resource budget exceeded: {budget_ok['exceeded_dimensions']}")
    except Exception as e:
        logger.warning(f"Resource Accounting failed: {e}")
