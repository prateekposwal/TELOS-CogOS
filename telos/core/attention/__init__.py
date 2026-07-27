"""TELOS Attention Management.

Contains:
  - BudgetManager: Global budget governor for pipeline phases
  - ResourceBudgetTracker: Multi-resource budget tracking
  - TokenBudgetManager: Intelligent chat history truncation
  - AttentionProjectionEngine: Law of Attention and Trajectory modeling
  - IdentityEntropyTracker: Perceived action-space tracking under stress
"""

from telos.core.attention.token_budget import TokenBudgetManager, estimate_tokens, estimate_message_tokens
from telos.core.attention.projection import (
    AttentionProjectionEngine, AttentionAllocation, TrajectoryProjection,
)
from telos.core.attention.identity_entropy import (
    IdentityEntropyTracker, EntropySignal,
)
from telos.core.attention.resource_budget import (
    ResourceBudgetTracker, BudgetManager, AttentionBid, run_attention_auction,
)

__all__ = [
    "TokenBudgetManager", "estimate_tokens", "estimate_message_tokens",
    "AttentionProjectionEngine", "AttentionAllocation", "TrajectoryProjection",
    "IdentityEntropyTracker", "EntropySignal",
    "ResourceBudgetTracker", "BudgetManager", "AttentionBid", "run_attention_auction",
]
