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
from telos.core.handoff.recorder import DecisionRecorder
from telos.core.handoff.store import DecisionStore
from telos.core.handoff.graph import AssumptionRegistry, DecisionGraph
from telos.core.handoff.schema import (
    validate_record, is_valid, assert_valid, schema_dict, SchemaError,
)

__all__ = [
    "DecisionRecord", "EvidenceItem", "Assumption", "Alternative",
    "RevalidationCondition", "RecordStatus", "SCHEMA_VERSION",
    "DecisionRecorder", "DecisionStore",
    "AssumptionRegistry", "DecisionGraph",
    "validate_record", "is_valid", "assert_valid", "schema_dict", "SchemaError",
]
