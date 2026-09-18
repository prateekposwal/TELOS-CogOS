"""
Cooperative Intelligence (Λ4.11) — bounded multi-agent aggregation.

AXIOM 4.11
----------
    U_group > Σ U_i − C_align

Collective optimization beats isolated optimization **whenever alignment
costs are sufficiently low**. This module makes that inequality executable:
it takes the independent per-agent verdicts already produced by the
DistributedCouncil crew and decides whether *cooperating* is justified for
this decision, or whether the agents' disagreement is too costly.

Formalization (bounded, per-decision)
-------------------------------------
Given N agents, each with a utility estimate `u_i ∈ [0,1]` (its decision
integrity through its role lens) and authority `w_i`:

    group_utility    = Σ w_i·u_i / Σ w_i        (the pooled collective)
    isolated_utility = max_i u_i                (the single best agent alone)
    diversity        = max u_i − min u_i        (how much the agents disagree)
    alignment_cost   = λ · diversity            (cost of reconciling them)
    cooperative      = group_utility >= isolated_utility − alignment_cost

Cooperation is justified when the collective decision is not much worse than
the best single agent, net of the cost of the disagreement between them. When
one agent dominates and the rest disagree (large spread, low pooled mean),
cooperation is NOT justified and the verdict is honestly `cooperative=False`.

Boundary (the live unanimity case): with perfect agreement every agent has the
same utility, so `group_utility == isolated_utility` and `diversity == 0` (hence
`alignment_cost == 0`). The comparison is `>=`, not `>`: the group is *at least*
as good as the best agent acting alone, so zero-cost unanimous cooperation is
justified. A strict `>` would label maximal consensus as non-cooperative — the
inverse of the axiom's intent. Non-cooperation is still detected whenever the
pooled mean falls strictly below the best agent net of the alignment cost.

This is a bounded MVP: in-process advisory agents, not federated external
instances. It upgrades Λ4.11 from *aspirational* to an enforced scaffold with
a falsifiable predicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

# Default alignment-cost coefficient (λ). Larger = cooperation must clear a
# higher bar before it is judged worthwhile.
DEFAULT_ALIGNMENT_LAMBDA = 0.6


@dataclass
class CooperativeVerdict:
    """The outcome of one cooperative aggregation across agents.

    Attributes:
        n_agents: number of agents in the crew.
        group_utility: pooled collective utility (authority-weighted mean).
        isolated_utility: best single agent's utility alone.
        alignment_cost: reconciliation cost (λ · diversity).
        diversity: spread between the most and least optimistic agent.
        cooperative: True iff U_group >= U_isolated − C_align (boundary inclusive).
    """

    n_agents: int
    group_utility: float
    isolated_utility: float
    alignment_cost: float
    diversity: float
    cooperative: bool

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the verdict to a plain dict."""
        return {
            "n_agents": self.n_agents,
            "group_utility": round(self.group_utility, 6),
            "isolated_utility": round(self.isolated_utility, 6),
            "alignment_cost": round(self.alignment_cost, 6),
            "diversity": round(self.diversity, 6),
            "cooperative": self.cooperative,
        }


def _field(agent: Any, name: str, default: float) -> float:
    """Read a numeric field from a dict or object agent.

    Args:
        agent: an AgentVerdict or its to_dict() result.
        name: the field name.
        default: fallback when absent.

    Returns:
        The field value as a float.
    """
    if isinstance(agent, dict):
        value = agent.get(name, default)
    else:
        value = getattr(agent, name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


class CooperativeCouncil:
    """Evaluates whether cooperation is justified for a crew of agents."""

    def __init__(self, alignment_lambda: float = DEFAULT_ALIGNMENT_LAMBDA):
        """Initialize the cooperative council.

        Args:
            alignment_lambda: coefficient λ applied to agent diversity to
                price the cost of alignment.
        """
        self._lambda = alignment_lambda

    def evaluate(self, agents: List[Any]) -> CooperativeVerdict:
        """Run the Λ4.11 inequality over a crew of agent verdicts.

        Args:
            agents: list of AgentVerdict objects or their to_dict() results.

        Returns:
            A CooperativeVerdict with the inequality outcome.
        """
        utilities = [_field(a, "decision_integrity", 1.0) for a in agents]
        weights = [max(0.0, _field(a, "weight", 1.0)) for a in agents]
        n = len(utilities)
        if n == 0:
            return CooperativeVerdict(0, 0.0, 0.0, 0.0, 0.0, False)

        total_w = sum(weights) or float(n)
        group = sum(u * w for u, w in zip(utilities, weights)) / total_w
        isolated = max(utilities)
        diversity = max(utilities) - min(utilities)
        alignment_cost = self._lambda * diversity
        # Boundary-inclusive: see the module docstring. A unanimous crew has
        # group == isolated and alignment_cost == 0; `>` would call that
        # non-cooperative. `>=` still rejects a dominated crew (group strictly
        # below isolated - alignment_cost), preserving falsifiability.
        cooperative = group >= isolated - alignment_cost

        return CooperativeVerdict(
            n_agents=n,
            group_utility=group,
            isolated_utility=isolated,
            alignment_cost=alignment_cost,
            diversity=diversity,
            cooperative=bool(cooperative),
        )


__all__ = ["CooperativeCouncil", "CooperativeVerdict", "DEFAULT_ALIGNMENT_LAMBDA"]
