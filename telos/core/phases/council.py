"""
Council Phase — Epistemic Integrity Validation with Alternative Fallback

The Council validates the selected intent through all registered
validators. If the primary intent is blocked AND alternative intents
exist (from other cognitive streams), the Council falls back to the
next-best alternative — satisfying Axiom 4.3 (Possibility Preservation).
"""

import logging

from telos.core.council.base import ValidationSignal
from telos.core.phases.base import Phase, PhaseContext

logger = logging.getLogger('telos_pipeline')


class CouncilPhase(Phase):
    name = "council"

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        # Phase 1: Gather evidence influence weights from StreamCalibrator
        evidence_weights = None
        try:
            infra = getattr(pipeline, 'infra_manager', None)
            if infra and hasattr(infra, 'calibrator'):
                weight = infra.calibrator.get_evidence_weighted_influence
                evidence_weights = {
                    v.name: weight(v.name)["evidence"]
                    for v in pipeline.council._validators
                } if hasattr(pipeline.council, '_validators') else None
        except Exception:
            pass

        # Evaluate the primary selected intent
        ctx.verdict = pipeline.council.evaluate(
            ctx.world, ctx.selected_intent, ctx.domain_facts,
            predicted_state=ctx.predicted_state,
            observed_state=ctx.state,
            evidence_influence_weights=evidence_weights,
        )
        for sig in ctx.verdict.signals:
            logger.debug(f"Cycle {ctx.cycle_count}: Council {sig.validator_name} verdict={sig.verdict} (conf={sig.confidence:+.2f}, weight={sig.evidence_weight:.2f})")

        if ctx.verdict.escalation_requested:
            logger.warning(f"Cycle {ctx.cycle_count}: Council escalation requested — "
                           f"{ctx.verdict.escalation_reason}")

        # P2.1: Consume synthesis irreconcilable flag — inject ESCALATE if Council missed it
        if ctx.synthesis and ctx.synthesis.irreconcilable and ctx.verdict.validated:
            logger.warning(
                f"Cycle {ctx.cycle_count}: Synthesis flagged irreconcilable intents but Council passed — "
                f"injecting auto-ESCALATE"
            )
            ctx.verdict.signals.append(ValidationSignal(
                validator_name="synthesis_conflict_detector",
                passed=True,
                confidence=0.5,
                reason="Irreconcilable stream intents — possible internal conflict",
                evidence_weight=0.6,
                verdict="ESCALATE",
            ))
            ctx.verdict.escalation_requested = True
            if not ctx.verdict.escalation_reason:
                ctx.verdict.escalation_reason = "Irreconcilable stream intents — possible internal conflict"

        # Λ4.3 — Fall back to alternative intents if the primary is blocked
        if not ctx.verdict.validated and ctx.intents and len(ctx.intents) > 1:
            ctx._council_fallback_attempted = True
            # Sort intents by weighted score descending (skip the first = selected)
            alternatives = sorted(
                [(i, w) for i, w in ctx.intents if i is not ctx.selected_intent],
                key=lambda x: x[1],
                reverse=True,
            )
            for rank, (alt_intent, alt_weight) in enumerate(alternatives, start=1):
                alt_verdict = pipeline.council.evaluate(
                    ctx.world, alt_intent, ctx.domain_facts,
                    predicted_state=None,
                    observed_state=None,
                )
                if alt_verdict.validated:
                    blocking_validator = ctx.verdict.blocking_validator or "unknown"
                    logger.info(
                        f"Council: fell back to option {rank} (score={alt_weight:.2f}) "
                        f"after {blocking_validator} blocked primary"
                    )
                    ctx.selected_intent = alt_intent
                    ctx.verdict = alt_verdict
                    break
            else:
                # All alternatives also blocked — keep original verdict
                logger.warning(
                    f"Council: no alternative passed validation "
                    f"({len(alternatives)} alternatives tried)"
                )
