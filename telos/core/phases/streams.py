"""
StreamPhase — executes cognitive streams with attention auction.
"""
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
import numpy as np
import hashlib

from telos.core.phases.base import Phase, PhaseContext, StreamActivation
from telos.core.attention import AttentionBid, run_attention_auction
from telos.core.trace.psdt import PSDT, PartialDecision
from telos.core.phases.act import ACT_FIDELITY_STALE_CYCLES

logger = logging.getLogger('telos_pipeline')

# ThreadPoolExecutor for parallel stream execution
# Set to None to disable (default: enabled for 2+ workers)
_STREAM_EXECUTOR = None


def _get_executor():
    global _STREAM_EXECUTOR
    if _STREAM_EXECUTOR is None:
        _STREAM_EXECUTOR = ThreadPoolExecutor(max_workers=4)
    return _STREAM_EXECUTOR


def _process_stream(stream, world):
    """Process a single stream. Separated for parallel execution.
        Args:
            world: the World instance this call reads
    """
    t0 = time.time()
    intent = stream.process(world)
    cost = (time.time() - t0) * 1000
    return intent, cost


class StreamPhase(Phase):
    name = "streams"

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        # ── PSDT: Initialize Partially Signed Decision Trace for this cycle ──
        ctx.psdt = PSDT()

        plan_shortcut = pipeline.planning_horizon.has_plan
        if plan_shortcut:
            planned_intent = pipeline.planning_horizon.get_next_step()
            if planned_intent is not None:
                ctx.intents.append((planned_intent, 1.0))
        pipeline.budget_manager.reserve("PlanningStream", 12.0)

        # --- Lambda4.5: Check if stuck on dominant stream ---
        infra = getattr(pipeline, '_infra_manager', None)
        calibrator = getattr(infra, 'calibrator', None) if infra else None
        forced_exploration = False
        if calibrator is not None and hasattr(calibrator, 'is_stuck') and calibrator.is_stuck():
            dominant = calibrator.dominant_stream
            if dominant:
                forced_stream = calibrator.forced_exploration_stream()
                logger.warning(
                    "Lambda4.5: Stuck on stream '%s' for %d+ cycles — forcing exploration%s",
                    dominant,
                    len(getattr(calibrator, '_selection_history', [])),
                    f" towards '{forced_stream}'" if forced_stream else ""
                )
                ctx.effective_n_worlds = ctx.effective_n_worlds * 2
                forced_exploration = True

        # Pre-process streams: filter out skipped ones, prepare tasks for parallel execution

        # ── Inject tripartite uncertainty into world metadata for InquiryStream ──
        tripartite_u = getattr(pipeline, '_tripartite_u', None)
        if tripartite_u is not None:
            ctx.world.metadata["U_W"] = tripartite_u.U_W
            ctx.world.metadata["U_I"] = tripartite_u.U_I
            ctx.world.metadata["U_O"] = tripartite_u.U_O
            ctx.world.metadata["council_signals"] = getattr(ctx, '_council_signal_dicts', [])

        stream_tasks: List[Tuple] = []

        for stream in pipeline.streams:
            stream_name = stream.__class__.__name__

            if plan_shortcut and stream_name == "PlanningStream":
                continue

            if forced_exploration and calibrator and calibrator.dominant_stream == stream_name:
                influence = calibrator.get_influence_weight(stream_name) * 0.8
            else:
                influence = calibrator.get_influence_weight(stream_name) if calibrator else 1.0

            # ── Gap 2: Ω-Weighted Stream Selection ──
            # If omega_vector is available, adjust influence based on uncertainty dimensions
            omega_vector = getattr(ctx, 'inquiry_omega_vector', None) or {}
            if omega_vector and any(v > 0 for v in omega_vector.values()):
                ow = omega_vector.get('world', 0.0)
                oi = omega_vector.get('identity', 0.0)
                oo = omega_vector.get('other', 0.0)
                if stream_name == "PerceptionStream" and ow > 0:
                    boost = min(2.0, 1.0 + ow * 0.5)
                    influence *= boost
                    logger.debug(f"Ω boost: {stream_name} ×{boost:.2f} (Ω_W={ow:.2f})")
                elif stream_name == "MemoryStream" and oi > 0:
                    boost = min(2.0, 1.0 + oi * 0.5)
                    influence *= boost
                    logger.debug(f"Ω boost: {stream_name} ×{boost:.2f} (Ω_I={oi:.2f})")
                elif stream_name == "PlanningStream" and oo > 0:
                    boost = min(2.0, 1.0 + oo * 0.5)
                    influence *= boost
                    logger.debug(f"Ω boost: {stream_name} ×{boost:.2f} (Ω_O={oo:.2f})")

                # Store adjusted weights in context
                if not hasattr(ctx, 'stream_weights_omega_adjusted'):
                    ctx.stream_weights_omega_adjusted = {}
                ctx.stream_weights_omega_adjusted[stream_name] = round(influence, 3)

            if influence < pipeline.config.stream_skip_threshold:
                ctx.stream_activations.append(StreamActivation(
                    stream_name=stream_name, priority=stream.priority,
                    intent=None, cost_ms=0.0,
                    budget_remaining_ms=pipeline.budget_manager.total_budget_ms - pipeline.budget_manager.consumed_ms,
                    activated=False,
                ))
                logger.debug(f"Cycle {ctx.cycle_count}: {stream_name} skipped (influence={influence:.2f})")
                continue

            authorized = pipeline._trust_manager.authorize_stream(stream_name)
            if not authorized and stream.priority < 0.9:
                ctx.stream_activations.append(StreamActivation(
                    stream_name=stream_name, priority=stream.priority,
                    intent=None, cost_ms=0.0,
                    budget_remaining_ms=pipeline.budget_manager.total_budget_ms - pipeline.budget_manager.consumed_ms,
                    activated=False,
                ))
                logger.info(f"Governance: {stream_name} skipped (unauthorized)")
                continue

            est_cost = getattr(stream, 'estimated_cost_ms', 5.0)
            budget_ok = pipeline.budget_manager.check_budget(stream_name, est_cost)
            if not budget_ok:
                ctx.stream_activations.append(StreamActivation(
                    stream_name=stream_name, priority=stream.priority,
                    intent=None, cost_ms=0.0,
                    budget_remaining_ms=pipeline.budget_manager.total_budget_ms - pipeline.budget_manager.consumed_ms,
                    activated=False,
                ))
                continue

            if stream_name == "PlanningStream" and hasattr(stream, 'configure'):
                stream.configure(
                    horizon=ctx.effective_horizon if hasattr(ctx, 'effective_horizon') else None,
                    n_worlds=ctx.effective_n_worlds if hasattr(ctx, 'effective_n_worlds') else None,
                )

            stream_tasks.append((stream, stream_name, influence))

        # ── Bitcoin-inspired Attention Budget Auction ─────────────────────
        # Before executing streams, collect bids and run the auction.
        # Each stream bids for compute ms; the highest bidder wins priority.
        if stream_tasks:
            auction_bids = []
            for stream, name, influence in stream_tasks:
                base_budget = getattr(stream, 'estimated_cost_ms', 5.0)
                priority = stream.priority
                # Streams can bid their base budget plus extra from unused budget
                bid_amount = base_budget * (1.0 + influence * 0.5)  # influence-weighted bid
                auction_bids.append(AttentionBid(
                    stream_name=name,
                    bid_amount_ms=bid_amount,
                    priority_multiplier=priority,
                    base_budget_ms=base_budget,
                ))

            # Run the auction
            total_remaining = pipeline.budget_manager.total_budget_ms - pipeline.budget_manager.consumed_ms
            auction_results = run_attention_auction(auction_bids, total_remaining)
            logger.debug(f"Attention auction results: {auction_results}")

            # Apply auction results: filter out streams that got zero allocation
            stream_tasks = [
                (s, n, inf) for s, n, inf in stream_tasks
                if auction_results.get(n, 0) > 0
            ]

        # Execute streams — parallel if configured and enough streams
        parallel = getattr(pipeline.config, 'parallel_streams', False)
        if parallel and len(stream_tasks) >= 2:
            results = []
            executor = _get_executor()
            future_to_stream = {
                executor.submit(_process_stream, stream, ctx.world): (stream, name, influence)
                for stream, name, influence in stream_tasks
            }
            for future in as_completed(future_to_stream):
                stream, name, influence = future_to_stream[future]
                try:
                    result = future.result()
                    results.append((stream, name, influence, result))
                except Exception as e:
                    logger.error(f"Stream {name} failed: {e}")
                    ctx.stream_activations.append(StreamActivation(
                        stream_name=name, priority=stream.priority,
                        intent=None, cost_ms=0.0,
                        budget_remaining_ms=pipeline.budget_manager.total_budget_ms - pipeline.budget_manager.consumed_ms,
                        activated=False,
                    ))
        else:
            # Sequential execution (default, compatible with all tests)
            results = [
                (stream, name, influence, _process_stream(stream, ctx.world))
                for stream, name, influence in stream_tasks
            ]

        # Process results in priority order
        results.sort(key=lambda r: r[0].priority, reverse=True)
        for stream, stream_name, influence, (intent, cost) in results:
            if intent is None:
                logger.warning(f"Cycle {ctx.cycle_count}: {stream_name} produced None intent — skipping")
                pipeline.budget_manager.consume(stream_name, cost)
                ctx.stream_activations.append(StreamActivation(
                    stream_name=stream_name, priority=stream.priority,
                    intent=None, cost_ms=cost,
                    budget_remaining_ms=pipeline.budget_manager.total_budget_ms - pipeline.budget_manager.consumed_ms,
                    activated=False,
                ))
                continue
            pipeline.budget_manager.consume(stream_name, cost)
            ctx.stream_activations.append(StreamActivation(
                stream_name=stream_name, priority=stream.priority,
                intent=intent, cost_ms=cost,
                budget_remaining_ms=pipeline.budget_manager.total_budget_ms - pipeline.budget_manager.consumed_ms,
                activated=True,
            ))

            # ── PSDT: Record partial decision for this stream ──
            if hasattr(ctx, 'psdt') and ctx.psdt is not None:
                evidence_raw = f"{stream_name}:{int(intent.confidence * 100)}:{int(cost)}:{ctx.cycle_count}"
                evidence_hash = hashlib.sha256(evidence_raw.encode()).hexdigest()[:16]
                partial = PartialDecision(
                    stream_name=stream_name,
                    stream_priority=stream.priority,
                    intent_type=intent.intent_type,
                    confidence=intent.confidence,
                    evidence_hash=evidence_hash,
                )
                ctx.psdt.add_partial(partial)

            if intent.confidence < 0.3:
                if calibrator is not None:
                    calibrator.record_waste(stream_name, cost)
            else:
                cal = calibrator.get_calibration(stream_name) if calibrator else None
                if cal is not None:
                    cal.total_cost_ms += cost

            logger.debug(f"Cycle {ctx.cycle_count}: {stream_name} proposed {intent.intent_type} (conf={intent.confidence:.2f})")

            if stream_name == "ReflexStream":
                if intent.confidence > 0.7:
                    pipeline.budget_manager.reserve("PlanningStream", 6.0)
                elif intent.confidence < 0.3:
                    pipeline.budget_manager.reserve("PlanningStream", 18.0)

            weighted_score = stream.priority * intent.confidence * influence
            ctx.intents.append((intent, weighted_score))

        # --- Lambda4.5: Record pattern when stuck escape is triggered ---
        if forced_exploration and calibrator and calibrator.dominant_stream:
            from telos.core.pattern import PatternType
            from telos.core.pattern import PatternLibrary
            try:
                sig = PatternLibrary.signature_from_decision(
                    di=0.5, md=0.5, intent_type="escape_local_optima"
                )
                pipeline.pattern_library.record(
                    domain="meta",
                    pattern_type=PatternType.RECOVERY,
                    signature=sig,
                    action_taken=f"escape_from_{calibrator.dominant_stream}",
                    outcome_score=0.5,
                    metadata={"reason": "local_optima_escape", "dominant": calibrator.dominant_stream},
                )
            except Exception as e:
                logger.debug(f"Lambda4.5: pattern record skipped: {e}")
            # Record escape in calibrator for telemetry
            if hasattr(calibrator, 'record_escape'):
                calibrator.record_escape(
                    cycle=ctx.cycle_count,
                    escaped_from=calibrator.dominant_stream,
                    escaped_to=forced_stream,
                )
            # Tag PhaseContext so DecisionTrace picks it up
            ctx.local_optima_escape = {
                "cycle": ctx.cycle_count,
                "checked": True,
                "escaped": True,
                "escaped_from": calibrator.dominant_stream,
                "escaped_to": forced_stream,
            }
        elif calibrator is not None and hasattr(calibrator, 'is_stuck'):
            # Λ4.5 exposure: the local-vs-global check RAN this cycle and
            # found no dominant-stream lock-in. Record the PERFORMED check
            # (escaped=False) so the prover reads the detection outcome
            # instead of failing merely because no escape was needed. A
            # genuinely absent calibrator still leaves this unset (fail-closed).
            ctx.local_optima_escape = {
                "cycle": ctx.cycle_count,
                "checked": True,
                "escaped": False,
                "stuck": False,
                "dominant": calibrator.dominant_stream,
            }

        perception_intent = None
        for sa in ctx.stream_activations:
            if sa.activated and sa.intent and sa.intent.intent_type == "perceive":
                perception_intent = sa.intent
                break

        if perception_intent is not None:
            mission_dir = pipeline.config.state_dim if hasattr(pipeline.config, 'state_dim') else 2
            mission_dir_arr = np.zeros(mission_dir if isinstance(mission_dir, int) else 2)
            ctx.world = pipeline.ledger.enrich(
                ctx.world, perception_intent, cycle=ctx.cycle_count,
                mission_vector=mission_dir_arr,
            )

        if pipeline.config.memory_fast_path_enabled:
            for sa in ctx.stream_activations:
                if (sa.activated and sa.intent
                        and sa.intent.intent_type in ("memory_recall",)
                        and sa.intent.confidence >= 0.9
                        and ctx.effective_n_worlds > 5):
                    ctx.effective_n_worlds = max(5, ctx.effective_n_worlds // 3)
                    logger.debug(f"Cycle {ctx.cycle_count}: memory fast path triggered, worlds={ctx.effective_n_worlds}")
                    break

        # ── v9: Model-fidelity fast path ──
        # Mirrors the memory fast path above: a CURRENTLY validated model
        # (recent per-step fidelity >= 0.6 inside the SAME staleness window
        # the act gate uses) on a calm record (last cycle DI >= 0.7, zero
        # recent council blocks, last sim solve > 0.9) does not need a full
        # multi-world counterfactual sweep — cut to 1-2 worlds. predicted_state
        # stays honest: the simulate phase always sets it from sim_options[0]
        # and the act phase re-derives the one-step landing through the real
        # transition, so the deferred reality-gap record is unaffected.
        if pipeline.config.fidelity_fast_path_enabled:
            tracker = getattr(pipeline, '_reality_gap_tracker', None)
            mf = None
            if tracker is not None and not isinstance(tracker, type):
                try:
                    mf = tracker.model_fidelity(
                        "world",
                        now_cycle=getattr(ctx, "cycle_count", None),
                        stale_window=ACT_FIDELITY_STALE_CYCLES)
                except Exception:
                    mf = None
            last_di = getattr(pipeline, '_last_di_for_omega', None)
            recent_blocks = int(getattr(pipeline, '_council_recent_blocks', 0) or 0)
            last_solve = float(getattr(pipeline, '_last_sim_score', 0.0) or 0.0)
            calm_and_valid = (
                isinstance(mf, (int, float)) and not isinstance(mf, bool)
                and float(mf) >= 0.6
                and last_di is not None
                and float(last_di) >= 0.7
                and recent_blocks == 0
                and last_solve > 0.9
                and ctx.effective_n_worlds > 2
            )
            if calm_and_valid:
                ctx.effective_n_worlds = max(1, min(2, ctx.effective_n_worlds))
                logger.debug(
                    f"Cycle {ctx.cycle_count}: fidelity fast path — "
                    f"mf={float(mf):.2f} di={float(last_di):.2f} "
                    f"worlds={ctx.effective_n_worlds}"
                )

        # P0.3: Emit readiness signal if any stream produced high-confidence intent
        for sa in ctx.stream_activations:
            if sa.activated and sa.intent and sa.intent.confidence >= 0.9:
                pipeline.readiness_engine.emit_signal("high_confidence_intent", strength=sa.intent.confidence)
                break
