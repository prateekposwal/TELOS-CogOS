"""
Act Phase — Final action execution with governance checks and human-in-the-loop.

The Act Phase:
1. Syncs the Firewall DI threshold from MissionPolicy (Λ3.1 Recovery Mode)
2. Runs the Decision Firewall inspect
3. Checks if human review is needed (HumanGateway integration)
4. Converts the selected intent to an action via the domain adapter
5. Records semantic depths for the decision trace
"""

import logging
import numpy as np

from telos.core.phases.base import Phase, PhaseContext

logger = logging.getLogger('telos_pipeline')


class ActPhase(Phase):
    name = "act"

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        # P1.3: Sync Firewall DI threshold from MissionPolicy before inspect
        try:
            infra = getattr(pipeline, '_infra_manager', None)
            if infra and hasattr(infra, 'policy') and infra.policy is not None:
                threshold = infra.policy.firewall_di_threshold
                old_threshold = pipeline._firewall.config.min_decision_integrity
                pipeline._firewall.set_di_threshold(threshold)
                logger.debug(f"Firewall: DI threshold synced to {threshold:.3f} (was {old_threshold:.3f})")
            else:
                logger.warning("Firewall: DI threshold sync skipped — no infra_manager")
        except Exception as e:
            logger.warning(f"Firewall: DI threshold sync failed — {e}")

        ctx.firewall_verdict = pipeline._firewall.inspect(
            ctx.world, ctx.selected_intent,
            council_validated=ctx.verdict.validated if ctx.verdict else True,
            decision_integrity=ctx.verdict.decision_integrity if ctx.verdict else 1.0,
            mission_violation=False,
        )

        ctx.council_blocked = not (ctx.verdict.validated if ctx.verdict else True)
        ctx.firewall_blocked = not ctx.firewall_verdict.passed
        ctx.governance_blocked = ctx.firewall_blocked or (ctx.council_blocked and pipeline._firewall.config.block_on_council_rejection)

        # HumanGateway override: if firewall blocked AND escalation requested, ask human
        if ctx.firewall_blocked and ctx.verdict and ctx.verdict.escalation_requested:
            human_gateway = getattr(pipeline, 'human_gateway', None)
            if human_gateway is not None:
                try:
                    verdict = human_gateway.review(
                        intent=ctx.selected_intent,
                        council_signals=[
                            {"validator": s.validator_name, "passed": s.passed,
                             "confidence": s.confidence, "reason": s.reason}
                            for s in (ctx.verdict.signals if ctx.verdict else [])
                        ],
                        decision_integrity=ctx.verdict.decision_integrity if ctx.verdict else 1.0,
                        mission_drift=ctx.verdict.mission_drift if ctx.verdict else 0.0,
                        blocking_validator=ctx.firewall_verdict.blocked_by,
                        context={"cycle": ctx.cycle_count,
                                  "reason": ctx.firewall_verdict.reason},
                    )
                    if verdict.approved:
                        ctx.governance_blocked = False
                        ctx.firewall_blocked = False
                        ctx.blocking_reason = ""
                        logger.info(
                            f"Cycle {ctx.cycle_count}: HumanGateway overrode firewall block — "
                            f"{verdict.override_reason}"
                        )
                    else:
                        logger.warning(
                            f"Cycle {ctx.cycle_count}: HumanGateway upheld firewall block — "
                            f"{verdict.override_reason}"
                        )
                except Exception as e:
                    logger.warning(f"HumanGateway firewall review failed: {e}")

        # Handle escalation: check if human review is needed
        ctx.escalation_pending = False
        if ctx.verdict and ctx.verdict.escalation_requested and not ctx.governance_blocked:
            ctx.escalation_pending = True

            # P1.6: Check HumanGateway for escalation review
            human_gateway = getattr(pipeline, 'human_gateway', None)
            if human_gateway is not None:
                try:
                    should_review = human_gateway.should_review(
                        council_validated=ctx.verdict.validated,
                        decision_integrity=ctx.verdict.decision_integrity,
                    )
                    if should_review:
                        escalation_data = {
                            "intent": ctx.selected_intent,
                            "council_signals": [
                                {
                                    "validator": s.validator_name,
                                    "passed": s.passed,
                                    "confidence": s.confidence,
                                    "reason": s.reason,
                                    "verdict": s.verdict,
                                }
                                for s in (ctx.verdict.signals if ctx.verdict else [])
                            ],
                            "decision_integrity": ctx.verdict.decision_integrity if ctx.verdict else 1.0,
                            "mission_drift": ctx.verdict.mission_drift if ctx.verdict else 0.0,
                            "blocking_validator": ctx.verdict.blocking_validator if ctx.verdict else None,
                            "context": {
                                "cycle": ctx.cycle_count,
                                "escalation_reason": ctx.verdict.escalation_reason if ctx.verdict else None,
                            },
                        }
                        verdict = human_gateway.review(
                            intent=ctx.selected_intent,
                            council_signals=escalation_data["council_signals"],
                            decision_integrity=escalation_data["decision_integrity"],
                            mission_drift=escalation_data["mission_drift"],
                            blocking_validator=escalation_data["blocking_validator"],
                            context=escalation_data["context"],
                        )
                        if not verdict.approved:
                            ctx.governance_blocked = True
                            ctx.blocking_reason = "human_review_blocked"
                            logger.warning(
                                f"Cycle {ctx.cycle_count}: HumanGateway BLOCKED action — "
                                f"{verdict.override_reason}"
                            )
                        else:
                            logger.info(
                                f"Cycle {ctx.cycle_count}: HumanGateway approved action — "
                                f"{verdict.override_reason}"
                            )
                except Exception as e:
                    logger.warning(f"HumanGateway review failed: {e}")

            if not ctx.governance_blocked:
                logger.warning(
                    f"Council escalation: {ctx.verdict.escalation_reason}. "
                    "Proceeding with action but escalation logged."
                )

        firewall_passed = ctx.firewall_verdict.passed
        council_ok = (ctx.verdict.validated if ctx.verdict else True) or (ctx.verdict and ctx.verdict.escalation_requested)

        if firewall_passed and council_ok and not ctx.governance_blocked:
            if pipeline.config.adapter and ctx.selected_intent:
                state_dim = ctx.state.shape[0]
                mission_dir = np.zeros(state_dim)

                ctx.selected_action = pipeline.config.adapter.intent_to_action(
                    ctx.selected_intent, ctx.state, mission_dir
                )
                # P1 D1: Causal annotations for the selected action
                predicted = getattr(ctx, 'predicted_state', None)
                ctx.causal_annotations = {
                    "intended_effect": {
                        "action_type": ctx.selected_intent.intent_type if ctx.selected_intent else "unknown",
                        "target_position": ctx.selected_action.tolist() if ctx.selected_action is not None else None,
                        "expected_outcome": "reduce_distance_to_goal",
                    },
                    "unintended_consequences": {
                        "action_vector_magnitude": float(np.linalg.norm(ctx.selected_action)) if ctx.selected_action is not None else 0.0,
                        "governance_blocked": ctx.governance_blocked,
                        "council_signals": [
                            s.validator_name for s in (ctx.verdict.signals if ctx.verdict else [])
                            if not s.passed
                        ],
                    },
                    "downstream_shift": {
                        "predicted_state_diff": (
                            (predicted - ctx.state).tolist()
                            if predicted is not None and ctx.state is not None
                            else None
                        ),
                        "world_model_updated": True,
                    },
                }
                if ctx.escalation_pending:
                    logger.info(
                        f"Action taken despite escalation: {ctx.selected_intent.intent_type} "
                        f"(DI={ctx.verdict.decision_integrity:.3f})"
                    )
        else:
            ctx.blocking_reason = ctx.firewall_verdict.blocked_by or (ctx.verdict.blocking_validator if ctx.verdict else None) or "governance"
            if ctx.verdict and ctx.verdict.escalation_requested:
                ctx.blocking_reason += f" [ESCALATED: {ctx.verdict.escalation_reason}]"
            logger.warning(
                f"Governance BLOCKED action. Check: {ctx.blocking_reason}. "
                f"DI={ctx.verdict.decision_integrity:.3f}"
            )

        # Emit readiness signal based on action outcome
        if ctx.governance_blocked:
            pipeline.readiness_engine.emit_signal("action_blocked", strength=0.5)
        else:
            pipeline.readiness_engine.emit_signal("action_completed", strength=1.0)

        if ctx.world:
            depths = ctx.world.metadata.get("semantic_depths", [])
            for d in depths:
                ctx.semantic_depths.append({
                    "entity_id": d.entity_id,
                    "observable_state": d.observable_state,
                    "historical_context": d.historical_context,
                    "mission_context": d.mission_context,
                    "semantic_identity": d.semantic_identity,
                })
