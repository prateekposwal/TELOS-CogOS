"""
DecisionTraceBuilder — Extracts DecisionTrace construction from runtime.py.

Reduces Pipeline.execute() by encapsulating all trace assembly logic,
making the main pipeline flow readable and the trace construction testable.
"""

from typing import Optional, Any
import time
import logging

logger = logging.getLogger('telos_trace')

from telos.core.types import DecisionTrace
from telos.core.proof.merkle_reasoning import MerkleReasoningProof


def build_trace(
    ctx: Any,
    state: Any,
    cycle_count: int,
    budget_manager: Any,
    cycle_duration: float,
    infra_manager: Any,
    last_quality_report: Any,
    perception_explanation: Optional[str] = None,
    prev_trace_id: Optional[str] = None,
) -> DecisionTrace:
    """Build a DecisionTrace from pipeline context and state.
    
    Args:
        ctx: PhaseContext with all phase outputs
        state: Current world state numpy array
        cycle_count: Current pipeline cycle
        budget_manager: BudgetManager for compute tracking
        cycle_duration: Wall-clock time for this cycle
        infra_manager: InfrastructureManager for system mood
        last_quality_report: PerceptionQuality report
        perception_explanation: Optional explanation string
        prev_trace_id: previous cycle's produced ctx id (for chaining)

    Returns:
        A complete DecisionTrace for this cycle.
    """
    health = 1.0 - (budget_manager.consumed_ms / budget_manager.total_budget_ms
                     if budget_manager.total_budget_ms > 0 else 0.0)

    # Log once if council did not run (should not happen in normal operation)
    if ctx.verdict is None:
        logger.warning("build_trace: council did not run — using default verdict values")

    verdict = ctx.verdict

    # ── PSDT: Serialize from ctx ──
    psdt_dict = None
    psdt_obj = getattr(ctx, 'psdt', None)
    if psdt_obj is not None:
        try:
            psdt_dict = psdt_obj.to_dict()
        except Exception as e:
            logger.warning(f"PSDT serialization failed: {e}")

    # ── Decision Timelock: Capture timelock state ──
    intent_timelock = getattr(ctx, '_intent_timelock_state', None)

    # ── Inquiry summary for decision_core ──
    inquiry_summary = None
    if hasattr(ctx, 'selected_question'):
        inquiry_summary = {
            "selected_question": ctx.selected_question,
            "omega_value": getattr(ctx, 'inquiry_omega_value', 0.0),
            "omega_vector": getattr(ctx, 'inquiry_omega_vector', None),
            "blend": getattr(ctx, 'inquiry_blend', 0.0),
            "skipped": getattr(ctx, 'inquiry_skipped', False),
        }

    trace = DecisionTrace(
        cycle_id=cycle_count,
        timestamp=time.time(),
        world_state_snapshot=state.copy(),
        domain_facts=ctx.domain_facts,
        stream_activations=ctx.stream_activations,
        selected_intent=ctx.selected_intent,
        selected_action=ctx.selected_action,
        representation=ctx.representation,
        budget_consumed_ms=budget_manager.consumed_ms,
        budget_total_ms=budget_manager.total_budget_ms,
        budget_carryover_ms=getattr(budget_manager, 'budget_carryover_ms', 0.0),
        worlds_simulated=ctx.worlds_generated,
        cycle_duration_ms=cycle_duration,
        health_score=health,
        council_validated=verdict.validated if verdict else True,
        decision_integrity=verdict.decision_integrity if verdict else 1.0,
        mission_drift=verdict.mission_drift if verdict else 0.0,
        blocking_validator=verdict.blocking_validator if verdict else None,
        council_signals=[
            {
                "validator": s.validator_name,
                "passed": s.passed,
                "confidence": s.confidence,
                "reason": s.reason,
                "evidence_weight": s.evidence_weight,
                "verdict": s.verdict,
            }
            for s in (verdict.signals if verdict else [])
        ],
        escalation_requested=verdict.escalation_requested if verdict else False,
        escalation_reason=verdict.escalation_reason if verdict else None,
        semantic_depths=ctx.semantic_depths,
        governance_signals=ctx.firewall_verdict.governance_signals if ctx.firewall_verdict else [],
        firewall_blocked=ctx.firewall_blocked,
        firewall_blocked_by=ctx.firewall_verdict.blocked_by if ctx.firewall_verdict else None,
        strategic_options=ctx.strategic_options_data,
        perception_quality=last_quality_report.to_dict() if last_quality_report else None,
        perception_explanation=perception_explanation,
        system_mood=(infra_manager.system_self.mood
                    if getattr(infra_manager, 'system_self', None) is not None
                    else None),
        knowledge_report=ctx.perceive.knowledge_report if ctx.perceive else None,
        gate_verdict=ctx.world.metadata.get("gate_verdict") if ctx.world else None,
        attention_metrics=ctx.attention_metrics,
        reflection=ctx.reflection,
        local_optima_escape=ctx.local_optima_escape,
        # P0 D9: Representation confidence
        representation_confidence=getattr(ctx, 'representation_confidence', 0.0),
        # P1 D1: Causal annotations
        causal_annotations=getattr(ctx, 'causal_annotations', None),
        # P1 D4: Identity tuple
        distributed_verdict=getattr(ctx, 'distributed_verdict', None),
            identity_state=getattr(ctx, 'identity_state', None),
        # P1 D3: Multi-resource budgets
        resource_budgets=getattr(ctx, 'resource_budgets', None),
        # P0 D8: Meta-cognition state
        meta_cognition=getattr(ctx, 'meta_cognition', None),
        # Fix 1: Causal graph from SCM
        causal_graph=getattr(ctx, 'causal_graph', None),
        # Fix 2: Gamma discount
        gamma_discount=0.95,
        # Fix 3: Terminal value
        terminal_value=getattr(ctx, 'terminal_value', 0.0),
        # Fix 4: Belief state from identity
        belief_state=(getattr(infra_manager.system_self, 'get_belief_state', lambda: {})()
                    if getattr(infra_manager, 'system_self', None) is not None else {}),
        # Fix 5: Capabilities K_t from identity state
        capabilities_k=(getattr(ctx, 'identity_state', {}) or {}).get('K_t'),
        j_term_breakdown=getattr(ctx, "j_term_breakdown", None),
        # ── Inquiry Stream / Ω Operator fields ──────────────────────────────
        inquiry_skipped=getattr(ctx, 'inquiry_skipped', False),
        selected_question=getattr(ctx, 'selected_question', None),
        inquiry_omega_value=getattr(ctx, 'inquiry_omega_value', 0.0),
        inquiry_omega_vector=getattr(ctx, 'inquiry_omega_vector', None),
        inquiry_blend=getattr(ctx, 'inquiry_blend', 0.0),
        # ── UTXO Chain ──────────────────────────────────────────────────
        spent_ctx_id=prev_trace_id,
        produced_ctx_id=f"ctx_{cycle_count}_{int(time.time()*1000)}",
        # ── PSDT ────────────────────────────────────────────────────────
        psdt=psdt_dict,
        # ── Decision Timelock ───────────────────────────────────────────
        intent_timelock=intent_timelock,
        # ── Inquiry Summary ─────────────────────────────────────────────
        inquiry_summary=inquiry_summary,
        # ── Curiosity Drive ──────────────────────────────────────────────
        curiosity_state=getattr(ctx, 'curiosity_state', None),
        curiosity_bonus=getattr(ctx, 'curiosity_bonus', 1.0),
        # ── Real tool-use channel audit record ─────────────────────────────
        tool_audit=getattr(ctx, 'tool_audit', None),
        # ── Research Amplification Gate verdict (Λ6.5, pre-PERCEIVE) ──────
        amplification_report=getattr(ctx, 'amplification_report', None),
    )

    # ── Merkle Proof of Reasoning (Bitcoin-inspired) ──────────────────────
    try:
        merkle_proof = MerkleReasoningProof.build(trace)
        trace.merkle_root = merkle_proof.merkle_root
    except Exception as e:
        logger.warning(f"MerkleProof build failed: {e}")
        trace.merkle_root = ""

    # ── SegWit-style Separation: Populate reasoning_witness and decision_core ──
    try:
        # decision_core: lightweight output fields
        trace.decision_core = {
            "selected_intent": {
                "type": trace.selected_intent.intent_type,
                "confidence": trace.selected_intent.confidence,
            } if trace.selected_intent else None,
            "selected_action": trace.selected_action.tolist() if trace.selected_action is not None else None,
            "decision_integrity": trace.decision_integrity,
            "mission_drift": trace.mission_drift,
            "council_validated": trace.council_validated,
            "identity_state": trace.identity_state,
            "merkle_root": trace.merkle_root,
            "inquiry_summary": inquiry_summary,
            "blocking_validator": trace.blocking_validator,
            "firewall_blocked": trace.firewall_blocked,
        }

        # reasoning_witness: heavy reasoning data
        trace.reasoning_witness = {
            "council_signals": trace.council_signals,
            "strategic_options": trace.strategic_options,
            "stream_activations": [
                {
                    "name": sa.stream_name,
                    "priority": sa.priority,
                    "activated": sa.activated,
                    "intent_type": sa.intent.intent_type if sa.intent else None,
                    "cost_ms": sa.cost_ms,
                }
                for sa in trace.stream_activations
            ],
            "causal_graph": trace.causal_graph,
            "resource_budgets": trace.resource_budgets,
            "meta_cognition": trace.meta_cognition,
            "psdt": psdt_dict,
            "j_term_breakdown": trace.j_term_breakdown,
            "capabilities_k": trace.capabilities_k,
            "belief_state": trace.belief_state,
            "attention_metrics": trace.attention_metrics,
            "local_optima_escape": trace.local_optima_escape,
            "reflection": trace.reflection,
        }
    except Exception as e:
        logger.warning(f"SegWit separation failed: {e}")

    return trace
