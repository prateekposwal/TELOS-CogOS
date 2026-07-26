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

    try:
        # CouncilReflector
        pipeline._council_reflector.record_decision(
            was_blocked=was_blocked, predicted_block=was_blocked,
            actual_block=was_blocked, validator_signals=[],
        )
    except Exception:
        pass

    try:
        pipeline._introspection_scheduler.get_due_tiers(ctx.cycle_count)
        pipeline._introspection_scheduler.introspect(ctx.cycle_count)
    except Exception:
        pass

    try:
        if ctx.cycle_count % 1000 == 0 and hasattr(pipeline, '_theory_builder'):
            tb = pipeline._theory_builder
            if tb.total_experiences > 0:
                tb.cluster()
                tb.hypothesize()
                tb.promote()
    except Exception:
        pass

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

    try:
        iu = pipeline._identity_utility
        iu.compute_utility(is_creator=getattr(pipeline, '_creator_present', False))
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
