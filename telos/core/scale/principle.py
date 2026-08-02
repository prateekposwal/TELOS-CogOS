"""
ScaleInvariancePrinciple — the same deliberation law at every granularity.

TELOS governs every decision with a single deliberation law: the pipeline
phase sequence plus the axiom constitution. This principle makes recursion
*deliberate*: a sub-task decision (micro), a project decision (meso), and
the meta-cognitive "which project next" decision (macro) are all produced
by the identical engine — not by special-cased heuristics per scale.

Formal statement:

    ∀ s ∈ Scales:  Law(P_s) = Law(P_meta)

    Law(P) = ⟨ phase_sequence(P), axiom_set(P) ⟩

    where:
      - phase_sequence(P) is the ordered deliberation phases executed by P
        (Perceive → Streams → Simulate → Evaluate → Synthesize → Select →
         Council → Act → Reflect in the v14 runtime)
      - axiom_set(P) is the axiom constitution verified after every cycle
        by the AxiomProver (the 42-axiom set documented in AXIOMS.md)

Corollary (deliberate recursion): the PipelineCoordinator's supervisor
and its sub-pipelines are the *same engine* at different granularities.
Deciding "what fee to bid" and "which project next" obey the same law;
every nested invocation is recorded in the RecursionLedger
(scale/ledger.py) and its structure is verified against this canonical
law (scale/verifier.py).

This is the deliberate-recursion embodiment of Axiom 1.1 (Architecture
Produces Outcomes): the architecture is scale-invariant.
"""

from dataclasses import dataclass, field
from typing import Tuple, FrozenSet


# Canonical phase sequence of the v14 runtime (must match runtime._build_phases()).
# Verified against the actual pipeline in tests/core/test_scale_invariance.py.
CANONICAL_PHASES: Tuple[str, ...] = (
    "perceive", "streams", "simulate", "evaluate", "synthesis",
    "select", "council", "act", "reflect",
)

# The 42-axiom constitution documented in AXIOMS.md, enforced by AxiomProver.
CANONICAL_AXIOM_COUNT: int = 42


@dataclass(frozen=True)
class ScaleInvariancePrinciple:
    """The invariant: one deliberation law at every granularity.

    Attributes:
        id: Principle identifier (P1.0 — Layer 1, Meta-Architectural).
        name: Human-readable name.
        formal: The formal statement of the invariant.
        canonical_phases: The canonical phase sequence every scale must run.
        canonical_axiom_count: Number of axioms in the constitution.
        scales: Recognized granularities of deliberation.
    """

    id: str = "P1.0"
    name: str = "Scale Invariance (Deliberate Recursion)"
    formal: str = (
        "∀ s ∈ Scales: Law(P_s) = Law(P_meta), "
        "where Law(P) = ⟨ phase_sequence(P), axiom_set(P) ⟩"
    )
    canonical_phases: Tuple[str, ...] = CANONICAL_PHASES
    canonical_axiom_count: int = CANONICAL_AXIOM_COUNT
    scales: Tuple[str, ...] = ("macro", "meso", "micro")

    def matches_phases(self, phase_signature: Tuple[str, ...]) -> bool:
        """True if a pipeline's phase sequence equals the canonical law.

        Args:
            phase_signature: the tuple of phase names executed by the pipeline.
        """
        return tuple(phase_signature) == self.canonical_phases

    def axiom_set_is_constitutional(self, axiom_ids: FrozenSet[str]) -> bool:
        """True if the verified axiom set spans the documented constitution.

        Cross-scale verification compares sets across scales (equality),
        so this is a lenient sanity check: the set must be non-empty and
        bounded by the documented constitution size.

        Args:
            axiom_ids: the set of axiom ids verified during an invocation.
        """
        return 0 < len(axiom_ids) <= self.canonical_axiom_count

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "formal": self.formal,
            "canonical_phases": list(self.canonical_phases),
            "canonical_axiom_count": self.canonical_axiom_count,
            "scales": list(self.scales),
        }


__all__ = [
    "ScaleInvariancePrinciple",
    "CANONICAL_PHASES",
    "CANONICAL_AXIOM_COUNT",
]
