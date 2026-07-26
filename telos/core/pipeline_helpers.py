"""Pipeline helpers — extracted from runtime.py for testability.

Contains: timelock penalties, resource budgets, proxy streams,
perception assessment, and query options.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger('telos_pipeline')


def apply_timelock_penalties(pipeline, ctx):
    """Apply Bitcoin-inspired timelock penalties after EVALUATE phase."""
    try:
        timelock_acc = getattr(ctx, '_timelock_accountant', None)
        if timelock_acc is None:
            return
        di = getattr(ctx, 'decision_integrity', 1.0)
        n_penalties = len(timelock_acc._penalty_history) if hasattr(timelock_acc, '_penalty_history') else 0
        if n_penalties > 3:
            timelock_acc.apply_penalty(di)
    except Exception:
        pass


def compute_resource_budgets(pipeline, ctx) -> Dict[str, Dict]:
    """Compute multi-resource budget tracking (P1 D3)."""
    bm = pipeline.budget_manager if hasattr(pipeline, 'budget_manager') else None
    ie = pipeline._identity_entropy if hasattr(pipeline, '_identity_entropy') else None
    im = pipeline._infra_manager if hasattr(pipeline, '_infra_manager') else None
    rg = pipeline._resource_gradient_tracker if hasattr(pipeline, '_resource_gradient_tracker') else None

    energy_util = (bm.consumed_ms / max(bm.total_budget_ms, 1)) if bm else 0.0
    collapse_rate = ie.collapse_rate if ie else 0.0
    recovery_cycles = im.policy.current.recovery_mode if (im and im.policy) else 0.0
    trace_length = 0
    if im and hasattr(im, 'knowledge'):
        trace_length = len(im.knowledge._entries) if hasattr(im.knowledge, '_entries') else 0

    if rg:
        rg.record(
            energy=energy_util,
            memory=trace_length,
            identity=collapse_rate,
            recovery=recovery_cycles,
        )

    return {
        "energy": {
            "consumed_ms": bm.consumed_ms if bm else 0.0,
            "total_ms": bm.total_budget_ms if bm else 0.0,
            "utilization": energy_util,
        },
        "memory": {
            "trace_history_length": trace_length,
            "description": "Knowledge graph entry count",
        },
        "identity": {
            "collapse_rate": collapse_rate,
        },
        "recovery": {
            "recovery_cycles": recovery_cycles,
        },
    }


def ensure_proxy_stream(pipeline) -> None:
    """Ensure at least one stream is registered (proxy if none)."""
    if not hasattr(pipeline, '_streams') or not pipeline._streams:
        from telos.core.streams.base import CognitiveStream
        from telos.intent_ir import IntentIR
        import numpy as np

        class ProxyStream(CognitiveStream):
            @property
            def priority(self): return 0.0
            @property
            def estimated_cost_ms(self): return 0.0
            def process(self, world):
                return IntentIR(intent_type="proxy", params={}, metadata={})

        skill_lib = getattr(pipeline, '_skill_library', None) or pipeline.config.adapter if hasattr(pipeline.config, 'adapter') else None
        pipeline._streams = [ProxyStream(skill_lib)]
        logger.info("Pipeline: registered proxy stream (no streams configured)")


def assess_perception(pipeline, world, domain_facts) -> Dict[str, Any]:
    """Assess perception quality and build quality report."""
    gate_verdict = pipeline._resolution_gate.evaluate(
        pipeline._perception_explainer.build_report(world, domain_facts),
    )
    explanation = pipeline._perception_explainer.explain(gate_verdict)
    return {
        "gate_verdict": gate_verdict,
        "explanation": explanation,
    }
