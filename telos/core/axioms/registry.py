"""
Axiom registry — the machine-readable single source of truth for the
42-axiom constitution (Λ5.2: A → Proposal → Human → Update).

Every declared axiom carries an honest `enforcement` status:
  - "enforced": the AxiomProver has a real predicate for it.
  - "scaffold": the predicate exists but verifies scaffold presence (e.g.
    RelationalContext) — honest, meaningful, never an always-true stub.
  - "aspirational": declared but NOT implementable with the current
    architecture. Such axioms are FAIL-CLOSED by the prover: they can never
    silently pass. (Λ4.11 Cooperative Intelligence moved from aspirational to
    scaffold once `coordination/cooperative.py` gave it a real, falsifiable
    predicate.)

This registry is what self_audit checks: the declared constitution (42 in
AXIOMS.md) must equal the accounted constitution here — a future drift like
the historical "39/42" can never recur invisibly.
"""
from __future__ import annotations

from typing import Dict, List

# The canonical axiom ids, in constitution order, with their honest
# enforcement status (must match the AxiomProver's actual predicate set).
AXIOMS: List[Dict[str, str]] = [
    {"id": "1.1", "enforcement": "enforced"},
    {"id": "1.2", "enforcement": "enforced"},
    {"id": "1.3", "enforcement": "enforced"},
    {"id": "1.4", "enforcement": "enforced"},
    {"id": "2.1", "enforcement": "enforced"},
    {"id": "2.2", "enforcement": "enforced"},
    {"id": "2.3", "enforcement": "enforced"},
    {"id": "2.4", "enforcement": "enforced"},
    {"id": "2.5", "enforcement": "enforced"},
    {"id": "2.6", "enforcement": "enforced"},
    {"id": "2.7", "enforcement": "enforced"},
    {"id": "3.1", "enforcement": "enforced"},
    {"id": "3.2", "enforcement": "enforced"},
    {"id": "3.3", "enforcement": "enforced"},
    {"id": "3.4", "enforcement": "enforced"},
    {"id": "3.5", "enforcement": "enforced"},
    {"id": "3.6", "enforcement": "enforced"},
    {"id": "4.1", "enforcement": "enforced"},
    {"id": "4.2", "enforcement": "enforced"},
    {"id": "4.3", "enforcement": "enforced"},
    {"id": "4.4", "enforcement": "enforced"},
    {"id": "4.5", "enforcement": "enforced"},
    {"id": "4.6", "enforcement": "enforced"},
    {"id": "4.7", "enforcement": "enforced"},
    {"id": "4.8", "enforcement": "enforced"},
    {"id": "4.9", "enforcement": "scaffold"},   # RelationalContext scaffold
    {"id": "4.10", "enforcement": "enforced"},
    {"id": "4.11", "enforcement": "scaffold"},  # CooperativeCouncil; fail-closed
    {"id": "5.1", "enforcement": "enforced"},
    {"id": "5.2", "enforcement": "enforced"},
    {"id": "5.3", "enforcement": "enforced"},
    {"id": "6.1", "enforcement": "enforced"},
    {"id": "6.2", "enforcement": "enforced"},
    {"id": "6.3", "enforcement": "enforced"},   # InterpretationEngine predicate
    {"id": "6.4", "enforcement": "enforced"},
    {"id": "6.5", "enforcement": "enforced"},
    {"id": "6.6", "enforcement": "enforced"},
    {"id": "6.7", "enforcement": "enforced"},
    {"id": "6.8", "enforcement": "enforced"},
    {"id": "6.9", "enforcement": "enforced"},
    {"id": "6.10", "enforcement": "enforced"},
    {"id": "6.11", "enforcement": "enforced"},
]

AXIOM_IDS: List[str] = [a["id"] for a in AXIOMS]


def registry() -> List[Dict[str, str]]:
    """The canonical axiom registry (id + enforcement status).

    Returns:
        A list of {id, enforcement} dicts in constitution order.
    """
    return [dict(a) for a in AXIOMS]


def accounted_count() -> int:
    """Total axioms accounted for in the registry.

    Returns:
        The registry length (should equal AXIOMS.md's declared count).
    """
    return len(AXIOMS)


def enforced_ids() -> List[str]:
    """Axiom ids with a real (non-aspirational) predicate.

    Returns:
        The ids whose enforcement is "enforced" or "scaffold".
    """
    return [a["id"] for a in AXIOMS if a["enforcement"] != "aspirational"]


def accounting() -> Dict[str, int]:
    """Honest enforcement accounting (enforced/scaffold/aspirational counts).

    Returns:
        dict with the per-status counts and the total.
    """
    from collections import Counter
    counts = Counter(a["enforcement"] for a in AXIOMS)
    return {
        "enforced": counts.get("enforced", 0),
        "scaffold": counts.get("scaffold", 0),
        "aspirational": counts.get("aspirational", 0),
        "total": len(AXIOMS),
    }


__all__ = ["AXIOMS", "AXIOM_IDS", "registry", "accounted_count",
           "enforced_ids", "accounting"]