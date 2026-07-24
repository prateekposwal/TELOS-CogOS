"""
TELOS v14: Progressive Compute Allocator

Allocates compute budget across three simulation tiers:

  ┌─────────────────────────────────────────────────┐
  │  Fast: Low-fidelity, hundreds of futures        │  ← Screening
  │  Detailed: Medium-fidelity, tens of futures     │  ← Evaluation
  │  Deep: High-fidelity, few futures               │  ← Stress test
  └─────────────────────────────────────────────────┘

Budget = total milliseconds available per step
Allocation: Fast (40%) → Detailed (35%) → Deep (25%)

The allocator dynamically adjusts based on:
  - Tier throughput (ms per trajectory)
  - Interest score (how promising are remaining candidates)
  - Remaining budget
"""


import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum


class ComputeTier(Enum):
    FAST = "fast"
    DETAILED = "detailed"
    DEEP = "deep"


TIER_ORDER = [ComputeTier.FAST, ComputeTier.DETAILED, ComputeTier.DEEP]


@dataclass
class TierBudget:
    tier: ComputeTier
    allocated_ms: float
    used_ms: float = 0.0
    trajectory_count: int = 0
    avg_ms_per_trajectory: float = 0.0

    @property
    def remaining_ms(self) -> float:
        return max(0.0, self.allocated_ms - self.used_ms)

    @property
    def utilization(self) -> float:
        return self.used_ms / self.allocated_ms if self.allocated_ms > 0 else 0.0

    def record_usage(self, ms: float) -> None:
        self.used_ms += ms
        self.trajectory_count += 1
        total = self.avg_ms_per_trajectory * (self.trajectory_count - 1) + ms
        self.avg_ms_per_trajectory = total / self.trajectory_count


@dataclass
class AllocationDecision:
    fast_count: int
    detailed_count: int
    deep_count: int
    fast_ms: float
    detailed_ms: float
    deep_ms: float
    total_budget_ms: float
    interest_score: float
    rationale: str


@dataclass
class TierResult:
    tier: ComputeTier
    trajectory_scores: List[float] = field(default_factory=list)
    best_score: float = 0.0
    avg_score: float = 0.0
    survival_rate: float = 0.0
    elapsed_ms: float = 0.0
    promoted_ids: List[str] = field(default_factory=list)


class ProgressiveComputeAllocator:
    """
    Allocates simulation budget across three tiers.

    Allocation strategy:
      - Fast tier: 40% of budget, high throughput, low fidelity
      - Detailed tier: 35% of budget, medium throughput, medium fidelity
      - Deep tier: 25% of budget, low throughput, high fidelity

    Dynamic adjustment:
      - If fast tier finds few promising futures → reduce detailed/deep allocation
      - If fast tier finds many promising futures → increase downstream allocation
      - Interest score = fraction of fast-tier trajectories above threshold
    """

    def __init__(self, total_budget_ms: float = 50.0,
                 fast_ratio: float = 0.40,
                 detailed_ratio: float = 0.35,
                 deep_ratio: float = 0.25,
                 interest_threshold: float = 0.5,
                 min_trajectories: int = 5):
        total = fast_ratio + detailed_ratio + deep_ratio
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Ratios must sum to 1.0, got {total}")

        self.total_budget_ms = total_budget_ms
        self.fast_ratio = fast_ratio
        self.detailed_ratio = detailed_ratio
        self.deep_ratio = deep_ratio
        self.interest_threshold = interest_threshold
        self.min_trajectories = min_trajectories

        self._budgets: Dict[ComputeTier, TierBudget] = {
            ComputeTier.FAST: TierBudget(
                tier=ComputeTier.FAST,
                allocated_ms=total_budget_ms * fast_ratio,
            ),
            ComputeTier.DETAILED: TierBudget(
                tier=ComputeTier.DETAILED,
                allocated_ms=total_budget_ms * detailed_ratio,
            ),
            ComputeTier.DEEP: TierBudget(
                tier=ComputeTier.DEEP,
                allocated_ms=total_budget_ms * deep_ratio,
            ),
        }
        self._step_count = 0
        self._allocation_history: deque = deque(maxlen=200)

    def allocate(self, available_budget_ms: Optional[float] = None) -> AllocationDecision:
        budget = available_budget_ms or self.total_budget_ms
        self._step_count += 1

        fast_ms = budget * self.fast_ratio
        detailed_ms = budget * self.detailed_ratio
        deep_ms = budget * self.deep_ratio

        self._budgets[ComputeTier.FAST].allocated_ms = fast_ms
        self._budgets[ComputeTier.DETAILED].allocated_ms = detailed_ms
        self._budgets[ComputeTier.DEEP].allocated_ms = deep_ms

        estimated_fast_per = 0.5
        estimated_detailed_per = 2.0
        estimated_deep_per = 8.0

        fast_count = max(self.min_trajectories, int(fast_ms / estimated_fast_per))
        detailed_count = max(self.min_trajectories, int(detailed_ms / estimated_detailed_per))
        deep_count = max(2, int(deep_ms / estimated_deep_per))

        decision = AllocationDecision(
            fast_count=fast_count,
            detailed_count=detailed_count,
            deep_count=deep_count,
            fast_ms=fast_ms,
            detailed_ms=detailed_ms,
            deep_ms=deep_ms,
            total_budget_ms=budget,
            interest_score=0.0,
            rationale="Initial allocation",
        )

        self._allocation_history.append({
            'step': self._step_count,
            'fast_count': fast_count,
            'detailed_count': detailed_count,
            'deep_count': deep_count,
            'budget_ms': budget,
        })

        return decision

    def adjust_allocation(self, fast_scores: List[float],
                          current_decision: AllocationDecision) -> AllocationDecision:
        if not fast_scores:
            return current_decision

        interest = sum(1 for s in fast_scores if s > self.interest_threshold) / len(fast_scores)

        budget = current_decision.total_budget_ms

        if interest < 0.2:
            fast_r = 0.60
            detailed_r = 0.30
            deep_r = 0.10
        elif interest < 0.5:
            fast_r = 0.45
            detailed_r = 0.35
            deep_r = 0.20
        else:
            fast_r = 0.30
            detailed_r = 0.35
            deep_r = 0.35

        fast_ms = budget * fast_r
        detailed_ms = budget * detailed_r
        deep_ms = budget * deep_r

        self._budgets[ComputeTier.FAST].allocated_ms = fast_ms
        self._budgets[ComputeTier.DETAILED].allocated_ms = detailed_ms
        self._budgets[ComputeTier.DEEP].allocated_ms = deep_ms

        fast_count = max(self.min_trajectories, int(fast_ms / 0.5))
        detailed_count = max(self.min_trajectories, int(detailed_ms / 2.0))
        deep_count = max(2, int(deep_ms / 8.0))

        adjusted = AllocationDecision(
            fast_count=fast_count,
            detailed_count=detailed_count,
            deep_count=deep_count,
            fast_ms=fast_ms,
            detailed_ms=detailed_ms,
            deep_ms=deep_ms,
            total_budget_ms=budget,
            interest_score=interest,
            rationale=f"Adjusted for interest={interest:.2f}",
        )

        self._allocation_history.append({
            'step': self._step_count,
            'adjusted': True,
            'interest': interest,
        })

        return adjusted

    def record_tier_usage(self, tier: ComputeTier, elapsed_ms: float) -> None:
        self._budgets[tier].record_usage(elapsed_ms)

    def process_tier(self, tier: ComputeTier, scores: List[float],
                     elapsed_ms: float,
                     promotion_percentile: Optional[float] = 70) -> TierResult:
        self.record_tier_usage(tier, elapsed_ms)

        if promotion_percentile is not None and scores:
            threshold = np.percentile(scores, promotion_percentile)
            promoted = [i for i, s in enumerate(scores) if s >= threshold]
            survival_rate = len(promoted) / len(scores) if scores else 0.0
        else:
            promoted = list(range(len(scores)))
            survival_rate = 1.0

        return TierResult(
            tier=tier,
            trajectory_scores=scores,
            best_score=max(scores) if scores else 0.0,
            avg_score=float(np.mean(scores)) if scores else 0.0,
            survival_rate=survival_rate,
            elapsed_ms=elapsed_ms,
            promoted_ids=[str(i) for i in promoted],
        )

    def process_fast_tier(self, scores: List[float],
                          elapsed_ms: float) -> TierResult:
        return self.process_tier(ComputeTier.FAST, scores, elapsed_ms, promotion_percentile=70)

    def process_detailed_tier(self, scores: List[float],
                              elapsed_ms: float) -> TierResult:
        return self.process_tier(ComputeTier.DETAILED, scores, elapsed_ms, promotion_percentile=75)

    def process_deep_tier(self, scores: List[float],
                          elapsed_ms: float) -> TierResult:
        return self.process_tier(ComputeTier.DEEP, scores, elapsed_ms, promotion_percentile=None)

    def get_tier_stats(self, tier: ComputeTier) -> Dict[str, Any]:
        b = self._budgets[tier]
        return {
            'tier': tier.value,
            'allocated_ms': b.allocated_ms,
            'used_ms': b.used_ms,
            'remaining_ms': b.remaining_ms,
            'utilization': b.utilization,
            'trajectory_count': b.trajectory_count,
            'avg_ms_per_trajectory': b.avg_ms_per_trajectory,
        }

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_budget_ms': self.total_budget_ms,
            'total_steps': self._step_count,
            'allocation_history_length': len(self._allocation_history),
            'tiers': {tier.value: self.get_tier_stats(tier) for tier in TIER_ORDER},
        }
