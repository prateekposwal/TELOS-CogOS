"""
Cooperative Intelligence (Λ4.11) — bounded multi-agent aggregation.

AXIOM 4.11
----------
    U_group − C_align ≥ max_i U_i

Collective optimization beats isolated optimization **whenever alignment
costs are sufficiently low**. This module makes that inequality executable:
it takes the independent per-agent verdicts already produced by the
DistributedCouncil crew and decides whether *cooperating* is justified for
this decision, or whether the agents' disagreement is too costly.

Sign of the alignment term (semantics decision; source of truth = AXIOMS.md
4.11's *Meaning* column + Λ5.3): C_align is a **cost**. Λ5.3 defines it as the
interaction cost ``λ·D(I_A, I_B)`` and Λ5.1's J enters it as the penalty
``−εC_align``. The axiom's proposition is that cooperation holds "whenever
alignment costs are sufficiently low", so the cost must be **overcome on the
group side**: a larger disagreement makes cooperation HARDER to justify. The
formal string previously shown here (``U_group > max_i U_i − C_align``) placed the
cost on the isolated side, which made high-cost/high-diversity crews *more*
likely to pass — the inverse of the axiom's stated meaning. Corrected at the
root.

Notation of the isolated side (source of truth = AXIOMS.md 4.11's *Meaning*
column + Λ6.11): the RHS is ``max_i U_i`` — the best single agent acting
alone — NOT ``Σ U_i``. "Isolated optimization" is singular: the utility the
best individual can achieve without cooperating. A sum would count every agent
again after the group already pooled them and, against the weighted-mean group
utility (mean ≤ max ≤ Σ for N ≥ 2), is either degenerate-false for every crew
or — with a summed group — reduces to a mere zero-disagreement test. Neither
is the substantive, falsifiable synergy claim the Meaning column states. The
executable predicate already used ``max_i u_i``; the formal notation was the
only slip, reconciled here at the root.

Formalization (bounded, per-decision)
-------------------------------------
Given N agents, each with a utility estimate `u_i ∈ [0,1]` (its decision
integrity through its role lens) and authority `w_i`:

    group_utility    = Σ w_i·u_i / Σ w_i        (the pooled collective)
    isolated_utility = max_i u_i                (the single best agent alone)
    di_spread        = max u_i − min u_i        (per-role decision-integrity spread)
    validation_disagreement = 2·min(yes, no)/N  (validated-set split, [0,1])
    diversity        = min(1, max(di_spread, validation_disagreement))
    alignment_cost   = λ · diversity            (cost of reconciling them)
    cooperative      = (group_utility − alignment_cost) >= isolated_utility

The diversity scalar captures BOTH axes of crew dissent in one canonical
number (see ``CooperativeVerdict.diversity``):

  * ``di_spread`` — the spread of the role utilities (the original metric).
  * ``validation_disagreement`` — the split in the roles' ``validated`` votes,
    normalized so unanimity (all pass OR all block) is 0.0 and an even split is
    1.0. This is the axis the original metric was blind to: a crew can report
    identical decision-integrity through every lens yet still disagree on
    ``validated`` (the live signature: all DIs 1.0 while CONSERVATIVE's
    ``md_cap`` fires and the crew consensus is 0.833).

Taking the per-axis maximum (rather than a sum) keeps the scalar interpretable
as "the largest disagreement along either axis" and bounded to [0,1] because
both axes are themselves in [0,1]. A pure-utility crew with no exposed
``validated`` flag contributes 0.0 on the validation axis, so the metric
degrades exactly to the original ``max u_i − min u_i``.

Cooperation is justified only when the collective decision, after paying the
cost of the crew's disagreement, still meets the best single agent acting
alone (`group − C_align >= isolated`). Disagreement raises `C_align`, so a
high-diversity crew must clear a *higher* bar. When one agent dominates and the
rest disagree (large spread, low pooled mean), the cost is not overcome and the
verdict is honestly `cooperative=False`.

Boundary (the live unanimity case): with perfect agreement every agent has the
same utility, so `group_utility == isolated_utility` and `diversity == 0` (hence
`alignment_cost == 0`). The comparison is `>=`, not `>`: zero-cost unanimous
cooperation is justified (the group is *at least* as good as the best agent
acting alone). A strict `>` would label maximal consensus as non-cooperative —
the inverse of the axiom's intent. Non-cooperation is still detected whenever
the pooled mean net of the alignment cost falls strictly below the best agent.

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
        diversity: widened disagreement scalar — max of the per-role utility
            spread and the normalized validated-set split, in [0, 1].
        di_spread: per-role decision-integrity spread (max − min utility).
        validation_disagreement: normalized validated-vote split in [0, 1].
        cooperative: True iff U_group − C_align >= U_isolated (cost overcome; boundary inclusive).
    """

    n_agents: int
    group_utility: float
    isolated_utility: float
    alignment_cost: float
    diversity: float
    cooperative: bool
    # Widened-metric components appended (defaulted) so the original six-field
    # positional construction stays valid for any external caller.
    di_spread: float = 0.0
    validation_disagreement: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the verdict to a plain dict."""
        return {
            "n_agents": self.n_agents,
            "group_utility": round(self.group_utility, 6),
            "isolated_utility": round(self.isolated_utility, 6),
            "alignment_cost": round(self.alignment_cost, 6),
            "diversity": round(self.diversity, 6),
            "di_spread": round(self.di_spread, 6),
            "validation_disagreement": round(self.validation_disagreement, 6),
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


def _validated_disagreement(agents: List[Any]) -> float:
    """Measure disagreement on the validated axis, normalized to [0, 1].

    Reads each agent's ``validated`` flag (present on the real
    ``AgentVerdict.to_dict()`` results the crew emits). The split is the
    minority vote fraction scaled by 2, so that a unanimous crew — all pass
    OR all block — yields 0.0, and an even split yields 1.0. This is the axis
    the original ``max u_i − min u_i`` metric could not see: identical
    per-role decision integrity with divergent ``validated`` votes.

    Args:
        agents: list of AgentVerdict objects or their to_dict() results.

    Returns:
        The normalized validated-set split in [0, 1]; 0.0 when no agent
        exposes a ``validated`` flag (a pure-utility crew).
    """
    flags: List[bool] = []
    for a in agents:
        if isinstance(a, dict):
            if "validated" in a:
                flags.append(bool(a["validated"]))
        else:
            value = getattr(a, "validated", None)
            if value is not None:
                flags.append(bool(value))
    n = len(flags)
    if n == 0:
        return 0.0
    yes = sum(1 for f in flags if f)
    minority = min(yes, n - yes)
    return 2.0 * minority / n


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
        di_spread = max(utilities) - min(utilities)
        validation_disagreement = _validated_disagreement(agents)
        # Single canonical scalar: the largest disagreement along either axis.
        # Both components are already in [0, 1], so the max is too.
        diversity = min(1.0, max(di_spread, validation_disagreement))
        alignment_cost = self._lambda * diversity
        # Strict cost semantics (Λ4.11, see the module docstring): the crew must
        # overcome its alignment cost — `group - cost >= isolated`. A unanimous
        # crew has cost == 0 and passes at the boundary (`>=`); a high-diversity
        # crew whose cost exceeds its surplus correctly fails. Falsifiability is
        # preserved: a dominated or too-diverse crew yields cooperative=False.
        cooperative = (group - alignment_cost) >= isolated

        return CooperativeVerdict(
            n_agents=n,
            group_utility=group,
            isolated_utility=isolated,
            alignment_cost=alignment_cost,
            diversity=diversity,
            di_spread=di_spread,
            validation_disagreement=validation_disagreement,
            cooperative=bool(cooperative),
        )


__all__ = ["CooperativeCouncil", "CooperativeVerdict", "DEFAULT_ALIGNMENT_LAMBDA"]
