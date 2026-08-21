"""
IntrospectionScheduler — Multi-Timescale Introspection.

Prateek's insight #5: "Introspection at multiple timescales —
every cycle (act), every 100 (reflect), every 1000 (rewrite strategy)."

The current system has cycle-level meta-cognition but no structured
multi-timescale introspection. This scheduler implements three tiers:

Tier 1 — Cycle-Level (every cycle):
  - "Did that action produce the expected outcome?"
  - Lightweight: compare predicted vs actual state
  - Time cost: O(1)

Tier 2 — Reflection (every ~100 cycles):
  - "What patterns are emerging in my behavior?"
  - Medium: analyze recent decision traces, identify recurring blocks
  - Time cost: O(N) where N = cycles since last reflection

Tier 3 — Strategic Rewrite (every ~1000 cycles):
  - "Should I change my core strategy?"
  - Deep: rewrite strategy parameters, re-evaluate axioms
  - Time cost: O(M) where M = full history

Architecture:
  The scheduler maintains three introspection tiers with independent
  intervals. Each tier produces a report. The pipeline calls
  introspect(cycle) which returns all due-tier reports.
"""

from __future__ import annotations

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_introspection')


class IntrospectionTier(Enum):
    CYCLE = "cycle"           # Every cycle
    REFLECT = "reflect"       # Every ~100 cycles
    STRATEGIC = "strategic"   # Every ~1000 cycles


@dataclass
class IntrospectionReport:
    """Output of a single introspection tier execution."""
    tier: IntrospectionTier
    cycle: int
    findings: List[str]
    metrics: Dict[str, float]
    recommendations: List[str]
    triggered: bool  # was this tier actually run?


@dataclass
class TierConfig:
    """Configuration for a single introspection tier."""
    interval: int  # cycles between executions
    enabled: bool = True
    min_cycles_before_first: int = 0  # don't run until N cycles


class IntrospectionScheduler:
    """Manages multi-timescale introspection cycles.

    Usage:
        scheduler = IntrospectionScheduler()
        reports = scheduler.introspect(cycle=101, ...)
        # Returns cycle-level reports + reflection report (due at ~100)

    Each tier collects different data:
      - CYCLE: predicted vs actual state divergence
      - REFLECT: decision trace patterns, recurring blocks
      - STRATEGIC: identity trajectory, axiom satisfaction, strategy revision
    """

    def __init__(self):
        # Configurable intervals
        self._tiers: Dict[IntrospectionTier, TierConfig] = {
            IntrospectionTier.CYCLE: TierConfig(interval=1),
            IntrospectionTier.REFLECT: TierConfig(
                interval=100,
                min_cycles_before_first=50,
            ),
            IntrospectionTier.STRATEGIC: TierConfig(
                interval=1000,
                min_cycles_before_first=500,
            ),
        }
        self._last_run: Dict[IntrospectionTier, int] = {
            t: 0 for t in IntrospectionTier
        }
        self._report_history: Dict[IntrospectionTier, List[IntrospectionReport]] = {
            t: [] for t in IntrospectionTier
        }
        self._max_history_per_tier: int = 20

    def should_run(self, tier: IntrospectionTier, cycle: int) -> bool:
        """Check if a tier is due to run at this cycle."""
        config = self._tiers[tier]
        if not config.enabled:
            return False
        if cycle < config.min_cycles_before_first:
            return False
        if self._last_run[tier] == 0:
            return cycle >= config.min_cycles_before_first
        return (cycle - self._last_run[tier]) >= config.interval

    def configure_tier(self, tier: IntrospectionTier, interval: Optional[int] = None,
                       enabled: Optional[bool] = None,
                       min_cycles: Optional[int] = None) -> None:
        """Update configuration for a specific tier.
        interval: the interval for this operation
        enabled: the enabled for this operation
        min_cycles: the min cycles for this operation
"""
        config = self._tiers[tier]
        if interval is not None:
            config.interval = interval
        if enabled is not None:
            config.enabled = enabled
        if min_cycles is not None:
            config.min_cycles_before_first = min_cycles

    def introspect(self, cycle: int,
                   cycle_data: Optional[Dict] = None,
                   reflection_data: Optional[Dict] = None,
                   strategic_data: Optional[Dict] = None) -> List[IntrospectionReport]:
        """Run introspection for all due tiers.

        Args:
            cycle: Current pipeline cycle
            cycle_data: Data for cycle-level introspection
                (predicted_state, actual_state, action_taken)
            reflection_data: Data for reflection-level introspection
                (recent_traces, recurring_blocks, skill_usage)
            strategic_data: Data for strategic-level introspection
                (full_history, identity_trajectory, axiom_scores)

        Returns:
            List of reports (one per tier that was due)
        """
        reports: List[IntrospectionReport] = []

        for tier in [IntrospectionTier.CYCLE,
                     IntrospectionTier.REFLECT,
                     IntrospectionTier.STRATEGIC]:
            if not self.should_run(tier, cycle):
                continue

            report = self._execute_tier(tier, cycle, {
                IntrospectionTier.CYCLE: cycle_data or {},
                IntrospectionTier.REFLECT: reflection_data or {},
                IntrospectionTier.STRATEGIC: strategic_data or {},
            })

            self._last_run[tier] = cycle
            self._report_history[tier].append(report)
            if len(self._report_history[tier]) > self._max_history_per_tier:
                self._report_history[tier].pop(0)

            reports.append(report)

            log_msg = f"Introspection [{tier.value}]: {len(report.findings)} findings, {len(report.recommendations)} recommendations"
            if tier == IntrospectionTier.REFLECT:
                logger.info(log_msg)
            elif tier == IntrospectionTier.STRATEGIC:
                logger.warning(log_msg)
            else:
                logger.debug(log_msg)

        return reports

    def _execute_tier(self, tier: IntrospectionTier, cycle: int,
                      data: Dict[IntrospectionTier, Dict]) -> IntrospectionReport:
        """Execute a specific introspection tier.
        cycle: the current pipeline cycle number
        data: the data for this operation
"""

        if tier == IntrospectionTier.CYCLE:
            return self._cycle_introspection(cycle, data[tier])
        elif tier == IntrospectionTier.REFLECT:
            return self._reflect_introspection(cycle, data[tier])
        elif tier == IntrospectionTier.STRATEGIC:
            return self._strategic_introspection(cycle, data[tier])

        return IntrospectionReport(
            tier=tier, cycle=cycle,
            findings=[], metrics={}, recommendations=[],
            triggered=False,
        )

    def _cycle_introspection(self, cycle: int,
                              data: Dict) -> IntrospectionReport:
        """Tier 1: Every-cycle introspection.

        Asks: "Did that action produce the expected outcome?"
        
        data: the data for this operation
"""
        findings: List[str] = []
        metrics: Dict[str, float] = {}
        recommendations: List[str] = []

        predicted = data.get('predicted_state')
        actual = data.get('actual_state')
        if predicted is not None and actual is not None:
            try:
                divergence = float(np.linalg.norm(
                    np.array(predicted) - np.array(actual)
                ))
                metrics['prediction_divergence'] = divergence
                if divergence > 5.0:
                    findings.append(
                        f"High prediction divergence ({divergence:.2f}) — "
                        f"world model may be inaccurate"
                    )
                    recommendations.append(
                        "Increase simulation n_worlds for better coverage"
                    )
                elif divergence < 0.1:
                    findings.append("Prediction accurate — world model is reliable")
            except Exception:
                pass

        action_taken = data.get('action_taken', 'none')
        metrics['action_taken'] = 1.0 if action_taken != 'none' else 0.0

        return IntrospectionReport(
            tier=IntrospectionTier.CYCLE,
            cycle=cycle,
            findings=findings or ["Cycle-level introspection complete"],
            metrics=metrics,
            recommendations=recommendations,
            triggered=True,
        )

    def _reflect_introspection(self, cycle: int,
                                data: Dict) -> IntrospectionReport:
        """Tier 2: Every ~100 cycles introspection.

        Asks: "What patterns are emerging in my behavior?"
        
        data: the data for this operation
"""
        findings: List[str] = []
        metrics: Dict[str, float] = {}
        recommendations: List[str] = []

        recent_traces = data.get('recent_traces', [])
        recurring_blocks = data.get('recurring_blocks', [])
        skill_usage = data.get('skill_usage', {})

        # Analyze recurring blocks
        if recurring_blocks:
            findings.append(
                f"Found {len(recurring_blocks)} recurring block patterns"
            )
            recommendations.append(
                "Consider adjusting validator thresholds for recurring blocks"
            )

        # Analyze skill usage diversity
        if skill_usage:
            used_skills = len(skill_usage)
            metrics['skill_diversity'] = used_skills / max(used_skills + 5, 1)
            if used_skills < 3:
                findings.append(
                    f"Low skill diversity ({used_skills} skills used recently)"
                )
                recommendations.append(
                    "Try alternative strategies outside current skill set"
                )

        # Analyze decision integrity trend
        if recent_traces:
            di_values = [t.get('decision_integrity', 1.0) for t in recent_traces[-20:]]
            if di_values:
                avg_di = sum(di_values) / len(di_values)
                metrics['avg_di'] = avg_di
                if avg_di < 0.6:
                    findings.append(
                        f"Decision Integrity trending low (avg={avg_di:.2f})"
                    )
                    recommendations.append(
                        "Enter epistemic repair mode to restore decision quality"
                    )

        return IntrospectionReport(
            tier=IntrospectionTier.REFLECT,
            cycle=cycle,
            findings=findings or ["Reflection-level introspection complete — no significant patterns detected"],
            metrics=metrics,
            recommendations=recommendations,
            triggered=True,
        )

    def _strategic_introspection(self, cycle: int,
                                  data: Dict) -> IntrospectionReport:
        """Tier 3: Every ~1000 cycles introspection.

        Asks: "Should I change my core strategy?"
        
        data: the data for this operation
"""
        findings: List[str] = []
        metrics: Dict[str, float] = {}
        recommendations: List[str] = []

        identity_trajectory = data.get('identity_trajectory', [])
        axiom_scores = data.get('axiom_scores', {})

        # Analyze identity trajectory
        if len(identity_trajectory) > 10:
            mood_changes = sum(
                1 for i in range(1, len(identity_trajectory))
                if identity_trajectory[i].get('mood') != identity_trajectory[i-1].get('mood')
            )
            metrics['mood_volatility'] = mood_changes / len(identity_trajectory)
            if mood_changes > len(identity_trajectory) * 0.3:
                findings.append(
                    f"High identity volatility ({mood_changes} mood changes)"
                )
                recommendations.append(
                    "Increase resilience parameter to stabilize identity"
                )

        # Analyze axiom satisfaction
        if axiom_scores:
            low_axioms = [
                f"{k}={v:.2f}" for k, v in axiom_scores.items()
                if v < 0.7
            ]
            if low_axioms:
                findings.append(
                    f"Axiom satisfaction below threshold: {', '.join(low_axioms)}"
                )
                recommendations.append(
                    "Review axiom implementation for low-scoring axioms"
                )
            metrics['axiom_coverage'] = sum(axiom_scores.values()) / max(len(axiom_scores), 1)

        # Strategic recommendation
        findings.append(
            f"Strategic review at cycle {cycle}: "
            f"{'No changes recommended' if not recommendations else f'{len(recommendations)} strategic changes proposed'}"
        )

        return IntrospectionReport(
            tier=IntrospectionTier.STRATEGIC,
            cycle=cycle,
            findings=findings,
            metrics=metrics,
            recommendations=recommendations,
            triggered=True,
        )

    def get_due_tiers(self, cycle: int) -> List[IntrospectionTier]:
        """Get list of tiers that are due at this cycle."""
        return [t for t in IntrospectionTier if self.should_run(t, cycle)]

    def to_dict(self) -> Dict:
        return {
            "tiers": {
                t.value: {
                    "interval": self._tiers[t].interval,
                    "enabled": self._tiers[t].enabled,
                    "last_run": self._last_run[t],
                }
                for t in IntrospectionTier
            },
        }
