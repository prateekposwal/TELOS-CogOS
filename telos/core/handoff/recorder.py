"""
DecisionRecorder — emits a DecisionRecord for MEANINGFUL decisions only.

Wired into the REFLECT phase, but deliberately NOT one record per cycle: an
internal cycle that repeats the same committed intent is not a decision worth
handing off. A record is emitted when either

  * a **new governance event** occurs — the council did not validate, escalation
    was requested, or the firewall blocked, AND that event signature (the
    blocking validator / escalation / firewall reason) has not been recorded
    yet. A repeated refusal with the same cause is the same decision.
  * a **new committed decision** occurs — an action was emitted for an intent
    type not already recorded. This deliberately does NOT re-record a type that
    merely oscillates (A/B/A/B); only a genuinely new course is a decision.

This keeps the artifact high-signal and bounded (Λ4.7). The recorder holds the
records in memory (a cross-agent store is deliberately out of scope) and
exposes them for serialization.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from telos.core.handoff.decision_record import (
    DecisionRecord, RevalidationCondition,
)

if TYPE_CHECKING:
    from telos.core.handoff.store import DecisionStore
    from telos.core.handoff.graph import AssumptionRegistry
    from telos.core.phases.base import PhaseContext

# System-derived default revalidation: the pipeline's OWN world-model check.
_WORLD_MODEL_CONDITION = RevalidationCondition(
    condition="world-model prediction remains consistent with observation",
    watches="world_model",
)


class DecisionRecorder:
    """Emits and retains DecisionRecords for meaningful decisions.

    Args:
        max_records: bounded retention (Λ4.7); oldest records are dropped.
        enabled: when False, `observe` is a no-op (default on).
        store: an optional DecisionStore; when given, each emitted record is
            also persisted to disk (the file-backed exchange).
    """

    def __init__(self, max_records: int = 200, enabled: bool = True,
                 store: Optional["DecisionStore"] = None,
                 registry: Optional["AssumptionRegistry"] = None,
                 bind: Optional[Callable[[Optional[str], Optional[str]], List[str]]] = None):
        self.max_records = max(1, int(max_records))
        self.enabled = bool(enabled)
        self._store = store
        self._registry = registry
        self._bind = bind
        self._registry_persisted = False
        self._records: "deque[DecisionRecord]" = deque(maxlen=self.max_records)
        self._seen_types: set = set()
        self._seen_governance: set = set()
        self._emitted = 0
        self._skipped = 0

    def _bind_refs(self, intent_type: Optional[str],
                   domain: Optional[str]) -> List[str]:
        """Resolve the assumption IDs a live decision rests on.

        Args:
            intent_type: the selected intent type.
            domain: the decision domain (from domain_facts / adapter).

        Returns:
            Assumption IDs (empty when no registry/binder is configured).
        """
        if self._bind is not None:
            try:
                return list(self._bind(intent_type, domain) or [])
            except Exception:
                return []
        if self._registry is not None:
            return self._registry.refs_for(intent_type, domain)
        return []

    # ── Policy ───────────────────────────────────────────────────────────────

    @staticmethod
    def _governance_signature(ctx: "PhaseContext") -> Optional[str]:
        """A stable signature for a governance event, or None.

        Args:
            ctx: the post-ACT phase context.

        Returns:
            "block:<validator>" / "firewall:<reason>" / "escalation", or None.
        """
        verdict = getattr(ctx, "verdict", None)
        if verdict is not None and not getattr(verdict, "validated", True):
            return f"block:{getattr(verdict, 'blocking_validator', None) or 'unknown'}"
        if bool(getattr(ctx, "firewall_blocked", False)):
            fv = getattr(ctx, "firewall_verdict", None)
            return f"firewall:{getattr(fv, 'blocked_by', None) or 'unknown'}"
        if verdict is not None and getattr(verdict, "escalation_requested", False):
            return "escalation"
        return None

    def is_meaningful(self, ctx: "PhaseContext") -> bool:
        """Whether the cycle is a DISTINCT decision worth handing off.

        Args:
            ctx: the post-ACT phase context.

        Returns:
            True for a new committed intent type or a new governance signature.
        """
        intent = getattr(ctx, "selected_intent", None)
        action_emitted = getattr(ctx, "selected_action", None) is not None
        new_type = (intent is not None and action_emitted
                    and intent.intent_type not in self._seen_types)
        sig = self._governance_signature(ctx)
        new_governance = sig is not None and sig not in self._seen_governance
        return new_type or new_governance

    # ── Emission ─────────────────────────────────────────────────────────────

    def observe(self, pipeline: Any, ctx: "PhaseContext", **extras: Any) -> Optional[DecisionRecord]:
        """Build and retain a record when the cycle is meaningful.

        Args:
            pipeline: the running pipeline (source of mission + reality gap).
            ctx: the post-ACT phase context.
            **extras: optional caller-supplied DecisionRecord fields
                (assumptions, expected_consequences, revalidation_conditions,
                objective, owner, constraints).

        Returns:
            The emitted record, or None when the cycle was skipped/disabled.
        """
        if not self.enabled:
            return None
        if not self.is_meaningful(ctx):
            self._skipped += 1
            return None

        config = getattr(pipeline, "config", None)
        mission = getattr(config, "mission_name", None)
        conditions = extras.pop("revalidation_conditions", None)
        if conditions is None:
            # The system's own world-model consistency check — not invented.
            conditions = [RevalidationCondition(
                condition=_WORLD_MODEL_CONDITION.condition,
                watches=_WORLD_MODEL_CONDITION.watches,
            )]

        # Bind typed assumption IDs from the registry (so live cycles feed the
        # executable graph). Empty when no registry/binder is configured.
        intent_type = (ctx.selected_intent.intent_type
                       if getattr(ctx, "selected_intent", None) else None)
        domain = getattr(getattr(ctx, "domain_facts", None), "domain", None)
        refs = self._bind_refs(intent_type, domain)
        if (self._store is not None and self._registry is not None
                and not self._registry_persisted):
            try:
                self._store.write_registry(self._registry)
                self._registry_persisted = True
            except OSError:
                pass

        record = DecisionRecord.from_context(
            ctx,
            mission=mission,
            objective=extras.pop("objective", mission or ""),
            owner=extras.pop("owner", None),
            constraints=extras.pop("constraints", None),
            assumptions=extras.pop("assumptions", None),
            expected_consequences=extras.pop("expected_consequences", None),
            revalidation_conditions=conditions,
            reality_gap=extras.pop("reality_gap", None),
            assumption_refs=refs,
            depends_on=extras.pop("depends_on", None),
            guarded_deps=extras.pop("guarded_deps", None),
        )
        self._records.append(record)
        if getattr(ctx, "selected_intent", None) is not None:
            self._seen_types.add(ctx.selected_intent.intent_type)
        sig = self._governance_signature(ctx)
        if sig is not None:
            self._seen_governance.add(sig)
        self._emitted += 1
        # File-backed exchange: persist for other contexts (best-effort — a
        # store failure must never break a cycle).
        if self._store is not None:
            try:
                self._store.write(record)
            except OSError:
                pass
        return record

    # ── Access ───────────────────────────────────────────────────────────────

    @property
    def records(self) -> List[DecisionRecord]:
        """The retained records, oldest first.

        Returns:
            A list copy of the retained records.
        """
        return list(self._records)

    def latest(self) -> Optional[DecisionRecord]:
        """The most recent record, or None.

        Returns:
            The latest DecisionRecord.
        """
        return self._records[-1] if self._records else None

    def stats(self) -> Dict[str, int]:
        """Emission counters.

        Returns:
            {emitted, skipped, retained, max_records}.
        """
        return {"emitted": self._emitted, "skipped": self._skipped,
                "retained": len(self._records), "max_records": self.max_records}

    def to_json_list(self, indent: int = 2) -> str:
        """Serialize all retained records to a JSON array (deterministic).

        Args:
            indent: JSON indentation.

        Returns:
            A JSON array string.
        """
        return json.dumps([r.to_dict() for r in self._records], indent=indent)

    def reset(self) -> None:
        """Clear retained records and the emission cursor."""
        self._records.clear()
        self._seen_types.clear()
        self._seen_governance.clear()
        self._emitted = 0
        self._skipped = 0
