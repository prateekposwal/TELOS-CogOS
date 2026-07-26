"""
Meta-cognitive Reflect Phase — Post-action reflection and pattern discovery.

The Reflect Phase runs after Act. It does not produce an action — it
produces meta-insights: recurring patterns, cross-domain transfers,
and adaptive horizon recommendations.

This is the system "thinking about its own thinking" — the meta-cognitive
layer that closes the full cognition loop.

Architecture:
  1. Scan recent decision history (AuditController DI/MD, FailureLedger)
  2. Build a PatternSignature from the current cycle's metrics
  3. Query PatternLibrary for similar past patterns (including cross-domain)
  4. If a recurring pattern is detected, store a meta-pattern
  5. Recommend adaptive horizon adjustment based on stability trends
  6. Inject cross-domain knowledge into the KnowledgeGraph for future cycles
"""

import logging
from typing import Optional, Dict, List, Any
import numpy as np

from telos.core.phases.base import Phase, PhaseContext
from telos.core.pattern import PatternLibrary, PatternType, PatternSignature

logger = logging.getLogger('telos_pipeline')

# How many recent cycles to scan for pattern detection
_RECENT_CYCLES_SCAN = 20

# Minimum times a pattern must repeat before it's flagged as "recurring"
_RECURRING_THRESHOLD = 3


class ReflectPhase(Phase):
    name = "reflect"

    def __init__(self, pattern_library: Optional[PatternLibrary] = None):
        self._pattern_lib = pattern_library or PatternLibrary()
        self._di_history: List[float] = []
        self._md_history: List[float] = []
        self._block_history: List[str] = []
        self._verdicts: List[str] = []

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        verdict = ctx.verdict
        if verdict is None:
            return

        di = verdict.decision_integrity
        md = verdict.mission_drift
        self._di_history.append(di)
        self._md_history.append(md)

        validators = [s.validator_name for s in verdict.signals if not s.passed]
        if validators:
            for v in validators:
                self._block_history.append(v)

        # 1. Store the current cycle as a pattern
        intent_type = ctx.selected_intent.intent_type if ctx.selected_intent else "none"
        sig = PatternLibrary.signature_from_decision(
            di=di, md=md, intent_type=intent_type,
        )

        if not verdict.validated:
            ptype = PatternType.COUNCIL_BLOCK
        elif md > 5.0:
            ptype = PatternType.HIGH_DRIFT
        elif di < 0.3:
            ptype = PatternType.LOW_INTEGRITY
        elif verdict.escalation_requested:
            ptype = PatternType.ESCALATION
        else:
            ptype = PatternType.SUCCESS

        domain = getattr(pipeline.config.simulator, 'domain', 'unknown') if pipeline.config.simulator else 'unknown'
        outcome = min(di, 1.0) if verdict.validated else max(0.0, di - 0.5)
        self._pattern_lib.record(
            domain=domain,
            pattern_type=ptype,
            signature=sig,
            action_taken=intent_type,
            outcome_score=outcome,
            metadata={
                "cycle": ctx.cycle_count,
                "validated": verdict.validated,
                "escalation": verdict.escalation_requested,
            },
        )

        # 2. Cross-domain transfer: query patterns from OTHER domains
        cross = self._pattern_lib.cross_domain_query(sig, exclude_domain=domain, top_k=3)
        if cross:
            logger.info(
                f"Cycle {ctx.cycle_count}: Reflect found {len(cross)} cross-domain pattern(s)"
            )
            for pat, sim in cross:
                logger.debug(
                    f"  → domain '{pat.domain}' {pat.pattern_type} sim={sim:.2f} "
                    f"action={pat.action_taken} score={pat.outcome_score:.2f}"
                )
                # Record the transfer suggestion in the KnowledgeGraph
                if hasattr(pipeline, '_infra_manager') and pipeline._infra_manager:
                    kg = pipeline._infra_manager.knowledge
                    kg.record(
                        domain=f"transfer::{domain}",
                        approach=pat.action_taken or "unknown",
                        outcome=pat.outcome_score,
                        tags=["cross_domain", pat.domain, pat.pattern_type.value],
                        params={
                            "source_domain": pat.domain,
                            "similarity": round(sim, 3),
                            "source_pattern_id": pat.pattern_id,
                        },
                    )

        # 3. Detect recurring patterns
        recent_blocks = self._block_history[-_RECENT_CYCLES_SCAN:]
        if recent_blocks:
            from collections import Counter
            counts = Counter(recent_blocks)
            for validator, count in counts.items():
                if count >= _RECURRING_THRESHOLD:
                    logger.warning(
                        f"Cycle {ctx.cycle_count}: Recurring pattern detected — "
                        f"'{validator}' blocked {count}x in last {_RECENT_CYCLES_SCAN} cycles"
                    )
                    self._pattern_lib.record(
                        domain=f"recurring::{domain}",
                        pattern_type=PatternType.COUNCIL_BLOCK,
                        signature=sig,
                        action_taken=f"blocked_by_{validator}",
                        outcome_score=max(0.0, 0.5 - 0.1 * count),
                        metadata={
                            "validator": validator,
                            "block_count": count,
                            "window": _RECENT_CYCLES_SCAN,
                        },
                    )

        # 4. Recommend adaptive horizon adjustment (no longer directly sets infra.adaptive_horizon)
        stable = self._detect_stability()
        new_horizon = self._compute_adaptive_horizon(pipeline)
        horizon_reason = "stable" if stable else ("unstable" if (
            len(self._di_history) >= 3 and self._di_history[-1] < self._di_history[0] - 0.2
        ) or (
            len(self._md_history) >= 3 and self._md_history[-1] > self._md_history[0] + 1.0
        ) else "neutral")

        # 5. Detect policy mode for telemetry
        infra = getattr(pipeline, '_infra_manager', None)
        policy_mode = float(infra.policy.current.recovery_mode) if (infra and infra.policy) else 0.0

        # 6. TheoryBuilder: abstraction during reflection
        tb = getattr(pipeline, '_theory_builder', None)
        if tb is not None and tb.total_experiences > 0:
            try:
                patterns = tb.cluster()
                hypotheses = tb.hypothesize()
                promoted = tb.promote()
                if promoted:
                    logger.info(
                        f"Cycle {ctx.cycle_count}: TheoryBuilder promoted "
                        f"{len(promoted)} hypothesis(es) to theory during reflection"
                    )
            except Exception:
                pass

        # 7. Attach reflection data to context for telemetry
        ctx.reflection = {
            "pattern_count": len(self._pattern_lib.stats()["domains"]),
            "cross_domain_hits": len(cross),
            "stable": stable,
            "adaptive_horizon": new_horizon,
            "recommended_horizon": new_horizon,
            "horizon_reason": horizon_reason,
            "policy_mode": policy_mode,
            "recurring_blocks": list(set(
                v for v in self._block_history[-_RECENT_CYCLES_SCAN:]
                if self._block_history[-_RECENT_CYCLES_SCAN:].count(v) >= _RECURRING_THRESHOLD
            )),
        }

    def _detect_stability(self) -> bool:
        """Check if the last N cycles show stable DI/MD."""
        if len(self._di_history) < 5:
            return False
        recent_di = self._di_history[-5:]
        recent_md = self._md_history[-5:]
        di_std = float(np.std(recent_di))
        md_std = float(np.std(recent_md))
        return di_std < 0.1 and md_std < 0.5 and np.mean(recent_di) > 0.8

    def _compute_adaptive_horizon(self, pipeline) -> Optional[int]:
        """Compute a suggested horizon based on recent stability.

        Returns:
            int > 0 to set a new horizon, or None to leave unchanged.
        """
        if len(self._di_history) < 3:
            return None

        base = pipeline.config.horizon if hasattr(pipeline.config, 'horizon') else 3
        stable = self._detect_stability()
        recent_di = self._di_history[-3:]
        di_dropping = len(recent_di) >= 3 and recent_di[-1] < recent_di[0] - 0.2
        recent_md = self._md_history[-3:]
        md_rising = len(recent_md) >= 3 and recent_md[-1] > recent_md[0] + 1.0

        if stable:
            return min(base + 2, base * 2)
        elif di_dropping or md_rising:
            return max(2, base - 1)
        return None

    @property
    def pattern_library(self) -> PatternLibrary:
        return self._pattern_lib
