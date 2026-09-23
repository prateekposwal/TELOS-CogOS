"""
Context Handoff — a portable, agent-agnostic decision artifact.

The problem this addresses: across agents and humans, information survives but
the *reasoning* does not. "We chose PostgreSQL" travels; "because we expect
relational consistency to matter more than horizontal scale" does not.

TELOS already carries the primitives — evidence provenance
(`telos/world/evidence.py`), a per-cycle decision trace (`telos/core/types.py`),
falsification state (`telos/world/epistemic.py`). This package composes them
into ONE serializable object a human, Claude, Codex, or another TELOS instance
can pick up without inheriting a distorted version of the reasoning.

See `decision_record.DecisionRecord`.
"""

from telos.core.handoff.decision_record import (
    DecisionRecord,
    EvidenceItem,
    Assumption,
    Alternative,
    RevalidationCondition,
    RecordStatus,
    SCHEMA_VERSION,
)

__all__ = [
    "DecisionRecord", "EvidenceItem", "Assumption", "Alternative",
    "RevalidationCondition", "RecordStatus", "SCHEMA_VERSION",
]
