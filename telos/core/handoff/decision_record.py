"""
DecisionRecord — the portable unit of decision context.

A `DecisionRecord` is what should travel between agents and humans instead of a
prose summary. It composes EXISTING TELOS primitives rather than duplicating
them:

  * `telos.world.evidence.EvidenceInfo`  — source + validation status on every
    belief (the difference between ASSUMED and MEASURED).
  * `telos.intent_ir.IntentIR`           — the decision itself.
  * `telos.core.types.DecisionTrace`     — the cycle provenance it is built from.
  * `telos.core.knowledge.graph.ProjectNode` — the durable knowledge-graph node
    a record can be stamped into.
  * `telos.world.epistemic.ModelRealityGap` — the falsification state that turns
    a revalidation CONDITION from prose into something executable.

Design rule (Λ1.2, process over outcomes): a record is *observed*, never
invented. Every field that can be derived from a trace is derived; everything
else is supplied explicitly and defaults to an honest "unknown/assumed", never
a fabricated value.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from telos.world.evidence import (
    EvidenceInfo, EvidenceSource, ValidationStatus,
)
from telos.intent_ir import IntentIR

if TYPE_CHECKING:
    from telos.core.types import DecisionTrace
    from telos.world.epistemic import ModelRealityGap

# Bump when the wire format changes incompatibly.
SCHEMA_VERSION = "1.0"


class RecordStatus(str, Enum):
    """Lifecycle of a decision record (distinct from per-belief validation)."""
    OPEN = "OPEN"              # decided; consequences not yet observed
    VALIDATED = "VALIDATED"    # consequences observed and consistent
    FALSIFIED = "FALSIFIED"    # consequences contradicted the expectation
    SUPERSEDED = "SUPERSEDED"  # a later record replaced this one


# ── Composed parts ───────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    """One grounded claim with its provenance envelope.

    Args:
        claim: the statement the evidence supports.
        evidence: the provenance stamp (source + validation status).
        ref: where the evidence lives (KG node id, url, cycle, tool output).
    """
    claim: str
    evidence: EvidenceInfo = field(default_factory=EvidenceInfo)
    ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict.

        Returns:
            The item as a JSON-serializable dict.
        """
        return {"claim": self.claim, "evidence": self.evidence.to_dict(),
                "ref": self.ref}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvidenceItem":
        """Rebuild an EvidenceItem from its dict form.

        Args:
            d: a dict produced by to_dict.

        Returns:
            The reconstructed item.
        """
        ev = d.get("evidence") or {}
        info = EvidenceInfo(
            source=_as_enum(EvidenceSource, ev.get("source"), EvidenceSource.DERIVED_INFERENCE),
            validation_status=_as_enum(ValidationStatus, ev.get("validation_status"), ValidationStatus.UNVALIDATED),
            confidence=ev.get("confidence"),
            fidelity=ev.get("fidelity"),
            timestamp=ev.get("timestamp", time.time()),
        )
        return cls(claim=d.get("claim", ""), evidence=info, ref=d.get("ref"))


@dataclass
class Assumption:
    """A belief the decision rests on, with its own validation status.

    Args:
        statement: the assumption in plain language.
        evidence: provenance for the assumption (often ASSUMED by default).
        status: the current validation status (kept in sync with evidence).
    """
    statement: str
    evidence: EvidenceInfo = field(default_factory=lambda: EvidenceInfo(
        source=EvidenceSource.DERIVED_INFERENCE,
        validation_status=ValidationStatus.ASSUMED,
    ))
    status: ValidationStatus = ValidationStatus.ASSUMED

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict.

        Returns:
            The assumption as a JSON-serializable dict.
        """
        return {"statement": self.statement, "evidence": self.evidence.to_dict(),
                "status": self.status.value}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Assumption":
        """Rebuild an Assumption from its dict form.

        Args:
            d: a dict produced by to_dict.

        Returns:
            The reconstructed assumption.
        """
        item = EvidenceItem.from_dict({"claim": d.get("statement", ""),
                                       "evidence": d.get("evidence")})
        return cls(statement=d.get("statement", ""), evidence=item.evidence,
                   status=_as_enum(ValidationStatus, d.get("status"), ValidationStatus.ASSUMED))


@dataclass
class Alternative:
    """An option that was considered — and why it was not chosen.

    Args:
        option: the option's name/description.
        score: the option's evaluated score, when available.
        rejected_reason: why it lost (the part prose handoffs drop).
        chosen: whether this is the option that was selected.
    """
    option: str
    score: Optional[float] = None
    rejected_reason: Optional[str] = None
    chosen: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict.

        Returns:
            The alternative as a JSON-serializable dict.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Alternative":
        """Rebuild an Alternative from its dict form.

        Args:
            d: a dict produced by to_dict.

        Returns:
            The reconstructed alternative.
        """
        return cls(option=d.get("option", ""), score=d.get("score"),
                   rejected_reason=d.get("rejected_reason"),
                   chosen=bool(d.get("chosen", False)))


@dataclass
class RevalidationCondition:
    """What would invalidate the decision — and what evidence would settle it.

    This is the field that makes the record executable rather than archival:
    `status` can be driven by the falsification machinery
    (`ModelRealityGap`) instead of a human remembering to re-read a doc.

    Args:
        condition: the trigger in plain language.
        watches: the evidence/model that would settle the condition.
        status: current validation status of the condition.
        last_checked_cycle: the cycle the condition was last evaluated.
    """
    condition: str
    watches: Optional[str] = None
    status: ValidationStatus = ValidationStatus.UNVALIDATED
    last_checked_cycle: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict.

        Returns:
            The condition as a JSON-serializable dict.
        """
        return {"condition": self.condition, "watches": self.watches,
                "status": self.status.value,
                "last_checked_cycle": self.last_checked_cycle}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RevalidationCondition":
        """Rebuild a condition from its dict form.

        Args:
            d: a dict produced by to_dict.

        Returns:
            The reconstructed condition.
        """
        return cls(condition=d.get("condition", ""), watches=d.get("watches"),
                   status=_as_enum(ValidationStatus, d.get("status"), ValidationStatus.UNVALIDATED),
                   last_checked_cycle=d.get("last_checked_cycle"))


# ── The record ───────────────────────────────────────────────────────────────

@dataclass
class DecisionRecord:
    """The portable decision-context artifact.

    Args:
        decision_id: stable id (trace id when derived, else a uuid).
        objective: what the decision was trying to achieve.
        owner: who owns the decision (creator name, agent, team).
        timestamp: when it was made.
        decision: the choice — {intent_type, action, params}.
        confidence: the decision's claimed confidence (calibratable).
        state: the observed state snapshot at decision time.
        evidence: grounded claims supporting the decision.
        assumptions: beliefs the decision rests on.
        constraints: hard constraints active at decision time.
        alternatives: options considered, with rejection reasons.
        expected_consequences: what the decision is expected to produce.
        revalidation_conditions: what would invalidate it.
        validation: council/DI/MD verdict (decision integrity, drift, dissent).
        provenance: where it came from (cycle, domain, mission, schema version).
        status: lifecycle status of the record.
    """
    decision_id: str
    objective: str = ""
    owner: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    decision: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    state: Dict[str, Any] = field(default_factory=dict)
    evidence: List[EvidenceItem] = field(default_factory=list)
    assumptions: List[Assumption] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    alternatives: List[Alternative] = field(default_factory=list)
    expected_consequences: List[str] = field(default_factory=list)
    revalidation_conditions: List[RevalidationCondition] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    status: RecordStatus = RecordStatus.OPEN

    # ── Construction from existing types ─────────────────────────────────────

    @classmethod
    def from_trace(cls, trace: "DecisionTrace", *,
                   objective: str = "",
                   owner: str = "unknown",
                   constraints: Optional[List[str]] = None,
                   assumptions: Optional[List[Assumption]] = None,
                   expected_consequences: Optional[List[str]] = None,
                   revalidation_conditions: Optional[List[RevalidationCondition]] = None,
                   reality_gap: Optional["ModelRealityGap"] = None,
                   mission: Optional[str] = None) -> "DecisionRecord":
        """Build a record from a pipeline DecisionTrace.

        Everything the trace knows is derived; everything else is supplied by
        the caller and defaults to an honest empty/assumed value.

        Args:
            trace: the cycle's DecisionTrace.
            objective: the goal the decision serves (not in the trace).
            owner: the decision owner (creator/agent/team).
            constraints: active hard constraints.
            assumptions: beliefs the decision rests on.
            expected_consequences: expected outcomes.
            revalidation_conditions: what would invalidate the decision.
            reality_gap: the model's falsification state, when available — used
                to honestly stamp evidence as ASSUMED vs MEASURED and to seed
                the record status.
            mission: the active mission name, when known.

        Returns:
            A DecisionRecord composed from the trace and the supplied context.
        """
        intent = trace.selected_intent
        action = trace.selected_action
        decision: Dict[str, Any] = {}
        confidence = 0.0
        if intent is not None:
            decision = {
                "intent_type": intent.intent_type,
                "confidence": intent.confidence,
                "params": _json_safe(intent.params),
                "action": action.tolist() if hasattr(action, "tolist") else action,
            }
            confidence = float(intent.confidence or 0.0)

        # Evidence honesty: an untested simulation-derived decision is ASSUMED,
        # not MEASURED. A tested model with a low reality gap is MEASURED.
        source = EvidenceSource.SIMULATION
        if reality_gap is not None and getattr(reality_gap, "tested", False):
            source = EvidenceSource.MEASUREMENT
            vstatus = (ValidationStatus.FALSIFIED if getattr(reality_gap, "is_falsified", False)
                       else ValidationStatus.MEASURED)
            fidelity = None
        else:
            vstatus = ValidationStatus.ASSUMED
            fidelity = None
        stamp = EvidenceInfo(source=source, validation_status=vstatus,
                             confidence=confidence, fidelity=fidelity)
        evidence: List[EvidenceItem] = []
        if intent is not None:
            evidence.append(EvidenceItem(
                claim=f"action '{intent.intent_type}' selected",
                evidence=stamp,
                ref=getattr(trace, "produced_ctx_id", None),
            ))

        # Alternatives: derive from the trace's strategic options, marking the
        # chosen intent. The rejection reason is the score gap to the winner.
        alternatives = _alternatives_from_trace(trace)

        # Validation verdict (council integrity / drift / dissent).
        validation = {
            "council_validated": bool(getattr(trace, "council_validated", True)),
            "decision_integrity": getattr(trace, "decision_integrity", None),
            "mission_drift": getattr(trace, "mission_drift", None),
            "blocking_validator": getattr(trace, "blocking_validator", None),
            "firewall_blocked": bool(getattr(trace, "firewall_blocked", False)),
            "escalation_requested": bool(getattr(trace, "escalation_requested", False)),
        }

        status = RecordStatus.OPEN
        if reality_gap is not None and getattr(reality_gap, "is_falsified", False):
            status = RecordStatus.FALSIFIED

        return cls(
            decision_id=(getattr(trace, "produced_ctx_id", None)
                         or f"cycle-{getattr(trace, 'cycle_id', '?')}"),
            objective=objective,
            owner=owner,
            timestamp=float(getattr(trace, "timestamp", time.time())),
            decision=decision,
            confidence=confidence,
            state={"world_state": _json_safe(getattr(trace, "world_state_snapshot", None))},
            evidence=evidence,
            assumptions=list(assumptions or []),
            constraints=list(constraints or []),
            alternatives=alternatives,
            expected_consequences=list(expected_consequences or []),
            revalidation_conditions=list(revalidation_conditions or []),
            validation=validation,
            provenance={
                "schema_version": SCHEMA_VERSION,
                "cycle": getattr(trace, "cycle_id", None),
                "representation": getattr(trace, "representation", None),
                "mission": mission,
                "domain": getattr(getattr(trace, "domain_facts", None), "domain", None),
            },
            status=status,
        )

    # ── Revalidation (executable, not archival) ──────────────────────────────

    def apply_reality_gap(self, reality_gap: "ModelRealityGap",
                          cycle: Optional[int] = None) -> "DecisionRecord":
        """Update the record's validity from the model's falsification state.

        This is the point of the schema: a revalidation condition is not prose
        to re-read — it is bound to the SAME reality-gap machinery the pipeline
        uses. A falsified model falsifies the record and its watched conditions.

        Args:
            reality_gap: the model's reality-gap state.
            cycle: the cycle at which this check ran (for the audit trail).

        Returns:
            self (mutated), for chaining.
        """
        falsified = bool(getattr(reality_gap, "is_falsified", False))
        tested = bool(getattr(reality_gap, "tested", False))
        new_status = (ValidationStatus.FALSIFIED if falsified
                      else ValidationStatus.MEASURED if tested
                      else ValidationStatus.UNVALIDATED)
        for cond in self.revalidation_conditions:
            cond.status = new_status
            cond.last_checked_cycle = cycle
        if falsified:
            self.status = RecordStatus.FALSIFIED
        elif tested and self.status == RecordStatus.OPEN:
            self.status = RecordStatus.VALIDATED
        return self

    def to_knowledge_node(self, domain: str) -> Dict[str, Any]:
        """Project the record onto the KnowledgeGraph node shape.

        Args:
            domain: the knowledge domain to file the decision under.

        Returns:
            A dict matching `ProjectNode`'s fields (for `graph.record`).
        """
        outcome = {"VALIDATED": 1.0, "FALSIFIED": 0.0,
                   "OPEN": 0.5, "SUPERSEDED": 0.5}.get(self.status.value, 0.5)
        return {
            "domain": domain,
            "approach": self.decision.get("intent_type", "unknown"),
            "outcome": outcome,
            "failure_reason": ("falsified by reality"
                               if self.status == RecordStatus.FALSIFIED else None),
            "tags": ["decision_record", self.status.value.lower()],
            "params": {"decision_id": self.decision_id,
                       "objective": self.objective},
            "provenance": {"schema_version": SCHEMA_VERSION,
                           "owner": self.owner,
                           "cycle": self.provenance.get("cycle")},
        }

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Return the record as a JSON-serializable dict.

        Returns:
            The full record dict.
        """
        return {
            "schema_version": SCHEMA_VERSION,
            "decision_id": self.decision_id,
            "objective": self.objective,
            "owner": self.owner,
            "timestamp": self.timestamp,
            "decision": self.decision,
            "confidence": self.confidence,
            "state": self.state,
            "evidence": [e.to_dict() for e in self.evidence],
            "assumptions": [a.to_dict() for a in self.assumptions],
            "constraints": list(self.constraints),
            "alternatives": [a.to_dict() for a in self.alternatives],
            "expected_consequences": list(self.expected_consequences),
            "revalidation_conditions": [c.to_dict() for c in self.revalidation_conditions],
            "validation": self.validation,
            "provenance": self.provenance,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DecisionRecord":
        """Rebuild a record from its dict form (round-trip safe).

        Args:
            d: a dict produced by to_dict.

        Returns:
            The reconstructed record.
        """
        return cls(
            decision_id=d.get("decision_id", ""),
            objective=d.get("objective", ""),
            owner=d.get("owner", "unknown"),
            timestamp=d.get("timestamp", time.time()),
            decision=d.get("decision", {}),
            confidence=d.get("confidence", 0.0),
            state=d.get("state", {}),
            evidence=[EvidenceItem.from_dict(e) for e in d.get("evidence", [])],
            assumptions=[Assumption.from_dict(a) for a in d.get("assumptions", [])],
            constraints=list(d.get("constraints", [])),
            alternatives=[Alternative.from_dict(a) for a in d.get("alternatives", [])],
            expected_consequences=list(d.get("expected_consequences", [])),
            revalidation_conditions=[RevalidationCondition.from_dict(c)
                                     for c in d.get("revalidation_conditions", [])],
            validation=d.get("validation", {}),
            provenance=d.get("provenance", {}),
            status=_as_enum(RecordStatus, d.get("status"), RecordStatus.OPEN),
        )

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON.

        Args:
            indent: JSON indentation.

        Returns:
            The record as a JSON string.
        """
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def to_markdown(self) -> str:
        """Render the record as the human/agent handoff artifact.

        Returns:
            A markdown document preserving the reasoning, not just the answer.
        """
        lines = [
            f"# Decision {self.decision_id}",
            "",
            f"- **Objective:** {self.objective or '_(unspecified)_'}",
            f"- **Owner:** {self.owner}",
            f"- **Status:** {self.status.value}",
            f"- **Confidence:** {self.confidence:.2f}",
            f"- **Cycle:** {self.provenance.get('cycle')}  ·  "
            f"**Domain:** {self.provenance.get('domain')}",
            "",
            "## Decision",
            f"- **{self.decision.get('intent_type', 'unknown')}**"
            + (f" → action `{self.decision.get('action')}`"
               if self.decision.get("action") is not None else ""),
        ]
        if self.evidence:
            lines += ["", "## Evidence"]
            for e in self.evidence:
                ev = e.evidence
                lines.append(f"- {e.claim}  "
                             f"_[{ev.source.value} / {ev.validation_status.value}]_"
                             + (f" (ref: {e.ref})" if e.ref else ""))
        if self.assumptions:
            lines += ["", "## Assumptions"]
            for a in self.assumptions:
                lines.append(f"- {a.statement}  _[{a.status.value}]_")
        if self.constraints:
            lines += ["", "## Constraints"]
            lines += [f"- {c}" for c in self.constraints]
        if self.alternatives:
            lines += ["", "## Alternatives considered"]
            for a in self.alternatives:
                tag = " **(chosen)**" if a.chosen else ""
                why = f" — {a.rejected_reason}" if a.rejected_reason else ""
                score = f" (score {a.score:.3f})" if a.score is not None else ""
                lines.append(f"- {a.option}{tag}{score}{why}")
        if self.expected_consequences:
            lines += ["", "## Expected consequences"]
            lines += [f"- {c}" for c in self.expected_consequences]
        if self.revalidation_conditions:
            lines += ["", "## Revalidation conditions"]
            for c in self.revalidation_conditions:
                watch = f" (watches: {c.watches})" if c.watches else ""
                lines.append(f"- {c.condition}{watch}  _[{c.status.value}]_")
        if self.validation:
            lines += ["", "## Validation",
                      f"- council_validated: {self.validation.get('council_validated')}",
                      f"- decision_integrity: {self.validation.get('decision_integrity')}",
                      f"- mission_drift: {self.validation.get('mission_drift')}"]
            if self.validation.get("blocking_validator"):
                lines.append(f"- blocked_by: {self.validation['blocking_validator']}")
        return "\n".join(lines) + "\n"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _as_enum(enum_cls, value, default):
    """Coerce a value into an enum member, falling back to a default.

    Args:
        enum_cls: the Enum class.
        value: the raw value (member, name, or value string).
        default: the fallback member.

    Returns:
        An enum member.
    """
    if isinstance(value, enum_cls):
        return value
    if value is None:
        return default
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        try:
            return enum_cls[str(value).upper()]
        except (ValueError, KeyError):
            return default


def _json_safe(value: Any) -> Any:
    """Best-effort conversion of numpy/array-ish values to JSON-safe forms.

    Args:
        value: any value.

    Returns:
        A JSON-serializable equivalent (arrays -> lists, else str fallback).
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _alternatives_from_trace(trace: "DecisionTrace") -> List[Alternative]:
    """Derive the alternatives list from a trace's strategic options.

    Args:
        trace: the cycle's DecisionTrace.

    Returns:
        Alternatives, with the selected intent marked chosen.
    """
    selected_type = (trace.selected_intent.intent_type
                     if trace.selected_intent is not None else None)
    options = getattr(trace, "strategic_options", None) or []
    alts: List[Alternative] = []
    for opt in options:
        if isinstance(opt, dict):
            score = opt.get("score")
            label = (opt.get("metadata", {}) or {}).get("intent_type") \
                or opt.get("intent_type") or opt.get("label") or f"option-{opt.get('rank', '?')}"
        else:
            score = getattr(opt, "score", None)
            label = getattr(opt, "intent_type", None) or f"option-{getattr(opt, 'rank', '?')}"
        alts.append(Alternative(
            option=str(label), score=score,
            chosen=(selected_type is not None and str(label) == selected_type)))
    # If the chosen intent isn't among the options, prepend it explicitly.
    if selected_type is not None and not any(a.chosen for a in alts):
        alts.insert(0, Alternative(option=selected_type, score=None, chosen=True))
    # Rejection reasons: only claim "below chosen" when the chosen option's
    # score is actually known and greater; otherwise state the score honestly.
    chosen_score = next((a.score for a in alts if a.chosen and a.score is not None), None)
    for a in alts:
        if a.chosen or a.score is None:
            continue
        if chosen_score is not None and a.score < chosen_score:
            a.rejected_reason = f"scored {a.score:.3f}, below chosen {chosen_score:.3f}"
        else:
            a.rejected_reason = f"scored {a.score:.3f}; not selected"
    return alts
