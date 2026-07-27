"""
Council Phase — Epistemic Integrity Validation with Alternative Fallback

The Council validates the selected intent through all registered
validators. If the primary intent is blocked AND alternative intents
exist (from other cognitive streams), the Council falls back to the
next-best alternative — satisfying Axiom 4.3 (Possibility Preservation).
"""

import logging

from telos.core.council.base import ValidationSignal, CouncilConfig
from telos.core.phases.base import Phase, PhaseContext
from telos.core.trace.psdt import PSDT

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

        # ── Configure voting threshold based on decision criticality ──
        criticality = getattr(ctx, 'decision_criticality', 'medium')
        pipeline.council._config = CouncilConfig.from_criticality(criticality)
        logger.debug(f"Council configured: criticality={criticality}, "
                      f"threshold={pipeline.council._config.voting_threshold}")

        # ── InternalDebate: multi-perspective deliberation loop ──
        debate_result = None
        deliberation_rounds = 0
        try:
            debate = getattr(pipeline, '_internal_debate', None)
            if debate is not None and ctx.selected_intent is not None:
                debate_result = debate.debate(
                    context={
                        "uncertainty": getattr(ctx, 'inquiry_omega_value', 0.5),
                        "options": [i.intent_type for i, _ in getattr(ctx, 'intents', [])[:3]],
                        "resources": {"budget": pipeline.budget_manager.total_budget_ms},
                        "goals": {"survival": 1.0},
                    },
                    context_description=f"Council review of {ctx.selected_intent.intent_type}",
                )
                ctx.latest_debate = {
                    "consensus": getattr(debate_result, 'consensus_level', 0.5) if debate_result else 0.5,
                    "rounds": getattr(debate_result, 'rounds', 1) if debate_result else 1,
                    "timestamp": __import__('time').time(),
                }
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

        # ── Resource Accounting: feed cost data into Council deliberation ──
        ra_summary = getattr(ctx, 'resource_accounting_summary', None)
        budget_ok = getattr(ctx, 'resource_accounting_budget_ok', True)
        if ra_summary and not budget_ok:
            logger.warning(
                f"Council: budget exceeded at cycle {ctx.cycle_count} — "
                f"compute={ra_summary['total_compute_ms']:.1f}ms"
            )
            # Flag over-budget as a signal for the verdict
            ctx.verdict.signals.append(ValidationSignal(
                validator_name="ResourceAccounting",
                passed=budget_ok,
                confidence=0.9,
                reason=f"resource_budget_exceeded: compute={ra_summary['total_compute_ms']:.1f}ms",
                evidence_weight=0.3,
                verdict="BLOCK" if not budget_ok else "PASS",
            ))

        # ── PSDT: Finalize with council verdict + debate transcript ──
        psdt = getattr(ctx, 'psdt', None)
        if psdt is None:
            psdt = PSDT()
            ctx.psdt = psdt
        debate_summary = ""
        if debate_result is not None and hasattr(debate_result, 'consensus_level'):
            try:
                cl = float(debate_result.consensus_level)
                debate_summary = f"|debate_c={cl:.2f}_r={deliberation_rounds}"
            except (TypeError, ValueError):
                debate_summary = f"|debate_r={deliberation_rounds}"
        verdict_summary = (f"{'VALIDATED' if ctx.verdict.validated else 'BLOCKED'}"
                          f":{ctx.verdict.decision_integrity:.3f}"
                          f":{ctx.verdict.mission_drift:.3f}{debate_summary}")
        psdt.finalize(verdict_summary)

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

        # ── Deliberation Loop: if debate low consensus AND blocked, generate counter-proposal ──
        dl_consensus = 0.5
        if debate_result is not None and hasattr(debate_result, 'consensus_level'):
            try:
                dl_consensus = float(debate_result.consensus_level)
            except (TypeError, ValueError):
                dl_consensus = 0.5
        if (not ctx.verdict.validated and debate_result is not None
                and dl_consensus < 0.5
                and ctx.cycle_count % 10 == 0):
            try:
                from telos.intent_ir import IntentIR
                import numpy as np
                logger.warning(
                    f"Council: deliberation loop triggered — low consensus "
                    f"({debate_result.consensus_level:.2f}), generating counter-proposal"
                )
                if hasattr(debate_result, 'perspectives_used') and debate_result.perspectives_used:
                    counter_type = f"deliberated_{'_'.join(debate_result.perspectives_used[:2])}"
                    counter_intent = IntentIR(
                        intent_type=counter_type,
                        confidence=max(0.3, dl_consensus),
                        params={
                            "deliberation": True,
                            "source": "council_deliberation",
                            "consensus": debate_result.consensus_level,
                        },
                        metadata={"stream": "council", "deliberation_round": deliberation_rounds},
                    )
                    alt_verdict = pipeline.council.evaluate(
                        ctx.world, counter_intent, ctx.domain_facts,
                        predicted_state=None, observed_state=None,
                    )
                    if alt_verdict.validated:
                        ctx.selected_intent = counter_intent
                        ctx.verdict = alt_verdict
                        deliberation_rounds += 1
                        logger.info(f"Council: counter-proposal '{counter_type}' accepted")
            except Exception:
                pass

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
