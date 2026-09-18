import logging
import numpy as np

from telos.core.phases.base import Phase, PhaseContext, PerceiveOutput
from telos.core.attention.projection import AttentionAllocation
from telos.world.world import World

logger = logging.getLogger('telos_pipeline')


def allocate_attention_budget(
    uncertainty: float,
    safety_score: float,
    domain_metrics: dict,
    total_budget: float = 100.0,
    commitment_mod: float = 1.0,
) -> AttentionAllocation:
    """Split 100 attention units across threat, opportunity, and maintenance modes.

    The allocation is inferred from the world state:
      - High uncertainty + low safety → threat-dominated (defensive focus)
      - Low uncertainty + high safety → opportunity-dominated (exploration)
      - Moderate conditions → balanced with maintenance
      
    When commitment is low (C* < 0.5), opportunity ratio is boosted to
    encourage exploration — the system searches more when uncertain.

    Args:
        uncertainty: World uncertainty level (0-1)
        safety_score: World safety score (0-1)
        domain_metrics: Domain-specific metrics dict
        total_budget: Total attention units to allocate (default 100)
        commitment_mod: Commitment score from Axiom 5.1 (default 1.0)

    Returns:
        AttentionAllocation with threat/opportunity/maintenance ratios
    """
    # Core signals
    threat_signal = float(np.clip(uncertainty * 0.7 + (1.0 - safety_score) * 0.3, 0.0, 1.0))
    opportunity_signal = float(np.clip(safety_score * 0.6 + (1.0 - uncertainty) * 0.4, 0.0, 1.0))
    maintenance_signal = float(np.clip(
        1.0 - abs(threat_signal - opportunity_signal), 0.0, 1.0
    ))

    # TELOS Commitment feedback: low C* → boost opportunity exploration
    if commitment_mod < 0.5:
        boost = (0.5 - commitment_mod) * 0.6
        opportunity_signal = min(1.0, opportunity_signal + boost)
        threat_signal = max(0.0, threat_signal - boost * 0.5)
        maintenance_signal = max(0.0, maintenance_signal - boost * 0.5)

    # Normalize to sum to 1.0
    total = threat_signal + opportunity_signal + maintenance_signal
    if total > 0:
        threat_ratio = threat_signal / total
        opportunity_ratio = opportunity_signal / total
        maintenance_ratio = maintenance_signal / total
    else:
        threat_ratio = 0.33
        opportunity_ratio = 0.33
        maintenance_ratio = 0.34

    # Stream breakdown: how the 100 units are distributed
    # Under threat: Reflex gets most allocation
    # Under opportunity: Planning gets most allocation
    stream_breakdown = {
        "reflex": max(5.0, total_budget * threat_ratio * 0.5),
        "perception": max(5.0, total_budget * (maintenance_ratio * 0.5 + opportunity_ratio * 0.2)),
        "memory": max(5.0, total_budget * (maintenance_ratio * 0.3 + threat_ratio * 0.2)),
        "planning": max(5.0, total_budget * opportunity_ratio * 0.6),
    }

    return AttentionAllocation(
        threat_ratio=threat_ratio,
        opportunity_ratio=opportunity_ratio,
        maintenance_ratio=maintenance_ratio,
        stream_breakdown=stream_breakdown,
        total_budget=total_budget,
    )


class PerceivePhase(Phase):
    name = "perceive"

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        domain_facts = None
        if pipeline.config.simulator:
            domain_facts = pipeline.config.simulator.get_facts(ctx.state)

        if ctx.user_name:
            user_profile = pipeline.ledger.upsert_user(ctx.user_name)
            world_metadata = {
                "cycle": ctx.cycle_count,
                "user_name": ctx.user_name,
                "user_trust": user_profile.trust_level,
                "user_relationship": user_profile.relationship_summary,
                "user_interactions": user_profile.total_interactions,
            }
        else:
            world_metadata = {"cycle": ctx.cycle_count}

        # P2.3: Authorize knowledge release for the domain
        domain = getattr(pipeline.config.simulator, 'domain', 'unknown') if pipeline.config.simulator else 'unknown'
        knowledge_released = pipeline.trust_manager.authorize_knowledge_release(domain)
        world_metadata["knowledge_released"] = knowledge_released
        if not knowledge_released:
            logger.info(f"TrustManager: knowledge release DENIED for domain '{domain}'")

        # Infer uncertainty and safety from domain facts or defaults
        default_uncertainty = 0.3
        default_safety = 1.0
        uncertainty = (
            domain_facts.metrics.get("uncertainty", default_uncertainty)
            if domain_facts else default_uncertainty
        )
        world_metadata["attention_uncertainty"] = uncertainty

        world = World(
            state=ctx.state.copy(),
            metadata=world_metadata,
            uncertainty=uncertainty,
            safety_score=domain_facts.metrics.get("safety_score", default_safety) if domain_facts else default_safety,
        )

        pipeline._readiness.tick()
        if domain_facts and domain_facts.constraints:
            from telos.core.governance.timing import ReadinessCondition
            for c in domain_facts.constraints:
                pipeline._readiness.register_fact(
                    f"constraint_{c}",
                    conditions=[ReadinessCondition("cycle_count", threshold=1)],
                )

        effective_n_worlds = pipeline.config.n_worlds
        if pipeline.config.adaptive_worlds_enabled and ctx.cycle_count > 1:
            if pipeline._last_sim_score > 0.9:
                effective_n_worlds = max(5, pipeline.config.n_worlds // 3)
            elif pipeline._last_sim_score < 0.4:
                effective_n_worlds = min(50, pipeline.config.n_worlds * 2)

        # P2.6: Reduce world count during recovery mode for faster, safer cycles
        if pipeline._infra_manager.policy.current.recovery_mode:
            effective_n_worlds = max(3, effective_n_worlds // 2)
            logger.debug(f"Cycle {ctx.cycle_count}: Recovery mode — reduced worlds to {effective_n_worlds}")

        # ── Attention Budget Allocation (Law of Attention) ──
        # Allocate 100 attention units based on world state
        # This determines which counterfactuals get generated downstream
        # Identity entropy feedback: when action-space is collapsing, boost opportunity
        entropy_mod = getattr(ctx, 'commitment_score', 1.0) or 1.0
        try:
            identity_entropy = getattr(pipeline, '_identity_entropy', None)
            if identity_entropy and identity_entropy.is_collapsing:
                entropy_mod = min(entropy_mod, 0.4)
        except Exception:
            pass
        attention_alloc = allocate_attention_budget(
            uncertainty=world.uncertainty,
            safety_score=world.safety_score,
            domain_metrics=domain_facts.metrics if domain_facts else {},
            commitment_mod=entropy_mod,
        )
        world.metadata["attention_allocation"] = {
            "threat_ratio": attention_alloc.threat_ratio,
            "opportunity_ratio": attention_alloc.opportunity_ratio,
            "maintenance_ratio": attention_alloc.maintenance_ratio,
            "stream_breakdown": attention_alloc.stream_breakdown,
            "total_budget": attention_alloc.total_budget,
        }
        ctx.attention_allocation = attention_alloc

        # Under threat-dominated attention, reduce world count to focus on safety
        # Under opportunity-dominated, increase worlds for diversity
        if attention_alloc.is_threat_dominated:
            effective_n_worlds = max(3, int(effective_n_worlds * (1.0 - attention_alloc.threat_ratio * 0.4)))
            logger.debug(
                f"Cycle {ctx.cycle_count}: Threat-dominated attention "
                f"({attention_alloc.threat_ratio:.2f}) — reduced worlds to {effective_n_worlds}"
            )
        elif attention_alloc.is_opportunity_dominated:
            effective_n_worlds = min(80, int(effective_n_worlds * (1.0 + attention_alloc.opportunity_ratio * 0.3)))
            logger.debug(
                f"Cycle {ctx.cycle_count}: Opportunity-dominated attention "
                f"({attention_alloc.opportunity_ratio:.2f}) — increased worlds to {effective_n_worlds}"
            )

        domain = getattr(pipeline.config.simulator, 'domain', 'unknown') if pipeline.config.simulator else 'unknown'
        knowledge_report = pipeline._infra_manager.consult_knowledge(domain, cycle=ctx.cycle_count)
        world.metadata["knowledge_report"] = knowledge_report

        # ── Phase 2: consult decision memory (CONSUMPTION, not just writes).
        #    The query is the domain + outcome vocabulary, so past outcomes for
        #    the situation at hand are recalled. A recall failure is logged and
        #    never blocks perception (Λ2.3). ──
        try:
            consult = getattr(pipeline, 'consult_memory', None)
            if callable(consult):
                query = f"{domain} outcome"
                recalled = consult(query, top_k=3)
                world.metadata["memory_recall"] = [
                    {"record_id": r.record_id, "content": r.content,
                     "outcome": r.outcome}
                    for r in recalled
                ]
                ctx.memory_recall = world.metadata["memory_recall"]
        except Exception as e:
            logger.warning(f"Cycle {ctx.cycle_count}: memory consultation failed: {e}")

        # P2.10: Inject session continuity essence into world for the next cycle
        if hasattr(ctx, 'session') and ctx.session and ctx.session.session_essence:
            world.metadata["session_essence"] = ctx.session.session_essence
            logger.debug(f"Session essence injected at cycle {ctx.cycle_count}")

        frame_w = world.metadata.get("frame_width", 0)
        frame_h = world.metadata.get("frame_height", 0)
        target_px = world.metadata.get("target_px", None)

        quality_adj = knowledge_report.get("quality_adjustment", 0.0) if isinstance(knowledge_report, dict) else 0.0
        if quality_adj != 0.0:
            current = pipeline._resolution_gate.threshold
            adjusted = max(0.05, min(0.95, current + quality_adj))
            pipeline._resolution_gate.threshold = adjusted
            logger.info(f"[Perception] Adjusted quality threshold: {current:.3f} → {adjusted:.3f}")

        quality_report = pipeline._perception_quality.assess(frame_w, frame_h, target_px)
        pipeline._last_quality_report = quality_report
        world.metadata["quality_report"] = quality_report.to_dict()

        gate_verdict = pipeline._resolution_gate.evaluate(
            quality_report,
            target_streams=world.metadata.get("detection_streams", []),
        )
        if gate_verdict.proxy_activated:
            pipeline._ensure_proxy_stream(has_visual_input=frame_w > 0 and frame_h > 0)

        world.metadata["gate_verdict"] = {
            "passed": gate_verdict.passed,
            "reason": gate_verdict.reason,
            "proxy_activated": gate_verdict.proxy_activated,
        }
        world.metadata["proxy_mode"] = gate_verdict.proxy_activated

        ctx.perceive = PerceiveOutput(
            world=world,
            domain_facts=domain_facts,
            quality_report=quality_report,
            gate_verdict=gate_verdict,
            knowledge_report=knowledge_report,
            effective_n_worlds=effective_n_worlds,
        )
        ctx.effective_n_worlds = effective_n_worlds
