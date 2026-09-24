"""
DecisionRecord schema — typed, closed outputs; no malformed results.

Jev habit #2/#3: define the output shape in advance, and make an ill-formed
result structurally impossible. This module is the single contract every consumer
can rely on: `validate_record` returns the exact list of violations, and
`DecisionStore.write` refuses to persist a record that fails them.

Closed value sets (no free-text enums):
  * status        -> RecordStatus (OPEN/VALIDATED/FALSIFIED/SUPERSEDED)
  * evidence source -> EvidenceSource; validation -> ValidationStatus
  * each record MUST declare a decision with a non-empty `intent_type` or
    `choice`, a confidence in [0,1], and a valid status.
"""

from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

from telos.core.handoff.decision_record import DecisionRecord, RecordStatus
from telos.world.evidence import EvidenceInfo, EvidenceSource, ValidationStatus

if TYPE_CHECKING:
    pass


class SchemaError(ValueError):
    """Raised when a DecisionRecord violates the frozen schema."""


def _is_prob(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= float(v) <= 1.0


def validate_record(record: DecisionRecord) -> List[str]:
    """Return the list of schema violations (empty = valid).

    Args:
        record: the record to validate.

    Returns:
        A list of human-readable error strings.
    """
    errors: List[str] = []

    if not isinstance(record.decision_id, str) or not record.decision_id.strip():
        errors.append("decision_id: must be a non-empty string")

    if not isinstance(record.decision, dict):
        errors.append("decision: must be a dict")
    elif not (str(record.decision.get("intent_type") or "").strip()
              or str(record.decision.get("choice") or "").strip()):
        errors.append("decision: must carry a non-empty 'intent_type' or 'choice'")

    if not _is_prob(record.confidence):
        errors.append(f"confidence: must be in [0,1], got {record.confidence!r}")
    if record.calibrated_confidence is not None and not _is_prob(record.calibrated_confidence):
        errors.append(f"calibrated_confidence: must be in [0,1] or None, got "
                      f"{record.calibrated_confidence!r}")

    if not isinstance(record.status, RecordStatus):
        errors.append(f"status: must be a RecordStatus, got {type(record.status).__name__}")

    for i, e in enumerate(record.evidence):
        if not getattr(e, "claim", ""):
            errors.append(f"evidence[{i}].claim: must be non-empty")
        if not isinstance(getattr(e, "evidence", None), EvidenceInfo):
            errors.append(f"evidence[{i}].evidence: must be an EvidenceInfo")
        else:
            if not isinstance(e.evidence.source, EvidenceSource):
                errors.append(f"evidence[{i}].source: must be an EvidenceSource")
            if not isinstance(e.evidence.validation_status, ValidationStatus):
                errors.append(f"evidence[{i}].validation_status: must be a ValidationStatus")

    for i, a in enumerate(record.assumptions):
        if not getattr(a, "statement", ""):
            errors.append(f"assumptions[{i}].statement: must be non-empty")
        if not isinstance(getattr(a, "status", None), ValidationStatus):
            errors.append(f"assumptions[{i}].status: must be a ValidationStatus")

    chosen = 0
    for i, alt in enumerate(record.alternatives):
        if not getattr(alt, "option", ""):
            errors.append(f"alternatives[{i}].option: must be non-empty")
        chosen += 1 if getattr(alt, "chosen", False) else 0
    if chosen > 1:
        errors.append("alternatives: at most one option may be marked chosen")

    for i, c in enumerate(record.revalidation_conditions):
        if not getattr(c, "condition", ""):
            errors.append(f"revalidation_conditions[{i}].condition: must be non-empty")
        if not isinstance(getattr(c, "status", None), ValidationStatus):
            errors.append(f"revalidation_conditions[{i}].status: must be a ValidationStatus")

    for name in ("assumption_refs", "depends_on", "guarded_deps"):
        vals = getattr(record, name, None)
        if not isinstance(vals, list) or any(not isinstance(v, str) or not v for v in vals):
            errors.append(f"{name}: must be a list of non-empty strings")

    # Typed consistency: a guarded dep must also be a declared dep.
    if isinstance(record.guarded_deps, list) and isinstance(record.depends_on, list):
        stray = sorted(set(record.guarded_deps) - set(record.depends_on))
        if stray:
            errors.append(f"guarded_deps: must be a subset of depends_on (stray: {stray})")

    return errors


def is_valid(record: DecisionRecord) -> bool:
    """Whether a record satisfies the schema.

    Args:
        record: the record.

    Returns:
        True when there are no violations.
    """
    return not validate_record(record)


def assert_valid(record: DecisionRecord) -> None:
    """Raise SchemaError when a record is malformed.

    Args:
        record: the record.

    Raises:
        SchemaError: with the violation list.
    """
    errors = validate_record(record)
    if errors:
        raise SchemaError(f"malformed DecisionRecord '{record.decision_id}': "
                          + "; ".join(errors))


def schema_dict() -> Dict[str, Any]:
    """A machine-readable description of the closed schema.

    Returns:
        A JSON-serializable schema description for external consumers.
    """
    return {
        "type": "DecisionRecord",
        "required": ["decision_id", "decision", "confidence", "status"],
        "closed_enums": {
            "status": [s.value for s in RecordStatus],
            "evidence.source": [s.value for s in EvidenceSource],
            "validation_status": [v.value for v in ValidationStatus],
        },
        "types": {
            "decision_id": "non-empty string",
            "decision": "dict with non-empty 'intent_type' or 'choice'",
            "confidence": "float in [0,1]",
            "calibrated_confidence": "float in [0,1] or null",
            "assumption_refs": "list[str]",
            "depends_on": "list[str]",
            "guarded_deps": "list[str], subset of depends_on",
        },
    }
