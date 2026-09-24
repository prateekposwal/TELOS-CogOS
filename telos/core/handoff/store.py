"""
DecisionStore — the minimal file-backed exchange.

A `DecisionRecord` is only *serializable* until something lets it travel
without a human ferrying it. This is the smallest thing that closes that loop:
records are written as JSON files in one directory, and any other context
(Claude, Codex, a human, another TELOS) can list, search, read, and revalidate
them — no server, no database, no API.

Deliberately minimal. It is NOT concurrent-safe, multi-writer, real-time, or
access-controlled; those are the infrastructure problem for later. It IS enough
to prove the exchange: a record written by one process is found, reconstructed,
and revalidated by another.

Layout:
    <root>/<decision_id>.json      one DecisionRecord per file (atomic writes)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from telos.core.handoff.decision_record import DecisionRecord, RecordStatus
from telos.core.handoff.graph import AssumptionRegistry, DecisionGraph, REGISTRY_FILE

if TYPE_CHECKING:
    from telos.world.epistemic import ModelRealityGap


def _safe_name(decision_id: str) -> str:
    """Map a decision id to a filesystem-safe base name.

    Args:
        decision_id: the record's id.

    Returns:
        A safe file base name (no extension).
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", decision_id or "")
    return safe or "decision"


class DecisionStore:
    """A directory of DecisionRecord JSON files.

    Args:
        root: the directory holding the records (created if absent).
    """

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    # ── Paths ────────────────────────────────────────────────────────────────

    def _path(self, decision_id: str) -> str:
        """Absolute path of a record's file.

        Args:
            decision_id: the record's id.

        Returns:
            The file path.
        """
        return os.path.join(self.root, f"{_safe_name(decision_id)}.json")

    # ── Write / read ─────────────────────────────────────────────────────────

    def write(self, record: DecisionRecord) -> str:
        """Persist a record atomically (temp file + rename).

        Args:
            record: the record to store.

        Returns:
            The path written.
        """
        path = self._path(record.decision_id)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(record.to_json())
        os.replace(tmp, path)
        return path

    def load(self, decision_id: str) -> Optional[DecisionRecord]:
        """Load a record by id.

        Args:
            decision_id: the record's id.

        Returns:
            The record, or None when it does not exist.
        """
        path = self._path(decision_id)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            return DecisionRecord.from_dict(json.load(f))

    def all(self) -> List[DecisionRecord]:
        """Load every stored record, ordered by (timestamp, id).

        Returns:
            All records in the store.
        """
        records: List[DecisionRecord] = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json") or name == REGISTRY_FILE:
                continue
            try:
                with open(os.path.join(self.root, name), encoding="utf-8") as f:
                    records.append(DecisionRecord.from_dict(json.load(f)))
            except (OSError, ValueError, TypeError):
                continue
        records.sort(key=lambda r: (r.timestamp, r.decision_id))
        return records

    # ── Query ────────────────────────────────────────────────────────────────

    def index(self) -> List[Dict[str, Any]]:
        """A lightweight, serializable index of the store.

        Returns:
            One dict per record (no full evidence/alternatives payload).
        """
        return [{
            "decision_id": r.decision_id,
            "objective": r.objective,
            "owner": r.owner,
            "intent_type": r.decision.get("intent_type"),
            "status": r.status.value,
            "cycle": r.provenance.get("cycle"),
            "domain": r.provenance.get("domain"),
        } for r in self.all()]

    def find(self, *, domain: Optional[str] = None,
             objective: Optional[str] = None,
             status: Optional[Any] = None,
             intent_type: Optional[str] = None,
             owner: Optional[str] = None,
             limit: Optional[int] = None) -> List[DecisionRecord]:
        """Find records matching the given filters.

        Args:
            domain: exact provenance domain.
            objective: exact objective.
            status: a RecordStatus or its string value.
            intent_type: exact decision intent type.
            owner: exact owner.
            limit: maximum results (after ordering).

        Returns:
            Matching records, ordered by (timestamp, id).
        """
        want_status = status.value if isinstance(status, RecordStatus) else status

        def _matches(r: DecisionRecord) -> bool:
            if domain is not None and r.provenance.get("domain") != domain:
                return False
            if objective is not None and r.objective != objective:
                return False
            if want_status is not None and r.status.value != want_status:
                return False
            if intent_type is not None and r.decision.get("intent_type") != intent_type:
                return False
            if owner is not None and r.owner != owner:
                return False
            return True

        results = [r for r in self.all() if _matches(r)]
        return results[:limit] if limit is not None else results

    # ── Revalidation / lifecycle ─────────────────────────────────────────────

    def revalidate(self, reality_gap: "ModelRealityGap",
                   cycle: Optional[int] = None,
                   only: Optional[Any] = None) -> List[str]:
        """Revalidate every record against reality; persist the changes.

        This is the loop that keeps the exchange CURRENT: a record that reality
        has contradicted flips to FALSIFIED on disk, so the next reader sees it
        without anyone remembering to re-check.

        Args:
            reality_gap: the model's reality-gap state.
            cycle: the cycle at which this check ran.
            only: an optional predicate selecting which conditions to update
                (see `DecisionRecord.apply_reality_gap`). None = all.

        Returns:
            The ids of records whose status or conditions changed.
        """
        changed: List[str] = []
        for r in self.all():
            before = (r.status, [c.status for c in r.revalidation_conditions])
            r.apply_reality_gap(reality_gap, cycle=cycle, only=only)
            after = (r.status, [c.status for c in r.revalidation_conditions])
            if before != after:
                self.write(r)
                changed.append(r.decision_id)
        return changed

    def supersede(self, old_id: str, new_id: str) -> bool:
        """Mark a record SUPERSEDED and link it to its replacement.

        Args:
            old_id: the record being replaced.
            new_id: the record that replaces it.

        Returns:
            True when the old record existed and was updated.
        """
        r = self.load(old_id)
        if r is None:
            return False
        r.status = RecordStatus.SUPERSEDED
        r.provenance["superseded_by"] = new_id
        self.write(r)
        return True

    # ── Assumption graph ─────────────────────────────────────────────────────

    def write_registry(self, registry: AssumptionRegistry) -> str:
        """Persist the shared assumption registry alongside the records.

        Args:
            registry: the assumption registry.

        Returns:
            The path written.
        """
        path = os.path.join(self.root, REGISTRY_FILE)
        registry.save(path)
        return path

    def load_registry(self) -> AssumptionRegistry:
        """Load the shared assumption registry (empty when absent).

        Returns:
            The registry.
        """
        return AssumptionRegistry.load(os.path.join(self.root, REGISTRY_FILE))

    def graph(self) -> DecisionGraph:
        """Build the executable decision graph over this store.

        Returns:
            A DecisionGraph (records + assumption registry).
        """
        return DecisionGraph.from_store(self)

    def count(self) -> int:
        """Number of stored records.

        Returns:
            The count of ``*.json`` files in the store (excludes the registry).
        """
        return sum(1 for n in os.listdir(self.root)
                   if n.endswith(".json") and n != REGISTRY_FILE)

    def clear(self) -> None:
        """Remove every record file from the store (keeps the registry)."""
        for name in os.listdir(self.root):
            if name.endswith(".json") and name != REGISTRY_FILE:
                try:
                    os.remove(os.path.join(self.root, name))
                except OSError:
                    pass
