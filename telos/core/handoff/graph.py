"""
DecisionGraph — the executable layer: typed assumptions + propagation.

`DecisionRecord` alone is a document. This module makes its relationships
*queryable*: decisions reference **assumption IDs** (an AssumptionRegistry), and
decisions reference **other decisions** (deps, some of which do NOT propagate).
Given a changed assumption, `affected_decisions(G)` returns the exact set of
decisions to revisit — by graph traversal, not text search.

This is the capability the scale experiment isolated: structure wins not at
single-decision judgment but at *queryability under scale*, where prose retrieval
degrades. Provenance: `experiments/context_fidelity/scale/`.

Edges:
  * assumption -> decision : a record whose `assumption_refs` contains the ID.
  * decision -> decision   : record `e` with `d in e.depends_on` — propagates
    unless `d in e.guarded_deps` (the change does not affect e's outcome).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from telos.core.handoff.decision_record import DecisionRecord

if TYPE_CHECKING:
    from telos.core.handoff.store import DecisionStore

REGISTRY_FILE = "assumptions.json"


@dataclass
class AssumptionNode:
    """A shared, typed assumption.

    Args:
        id: the stable assumption ID (e.g. "G17").
        text: the human-readable statement.
    """
    id: str
    text: str

    def to_dict(self) -> Dict[str, str]:
        """Return a plain dict.

        Returns:
            {id, text}.
        """
        return {"id": self.id, "text": self.text}


class AssumptionRegistry:
    """A stable ID → assumption-text registry (shared across decisions).

    Also carries **bindings**: a map from a decision key (intent type or domain)
    to the assumption IDs that key rests on. This is what lets live cycles
    populate `assumption_refs` automatically.

    Args:
        assumptions: optional {id: text} seed.
        bindings: optional {key: [assumption_id, ...]} seed.
    """

    def __init__(self, assumptions: Optional[Dict[str, str]] = None,
                 bindings: Optional[Dict[str, List[str]]] = None):
        self._by_id: Dict[str, str] = dict(assumptions or {})
        self._bindings: Dict[str, List[str]] = {
            str(k): list(v) for k, v in (bindings or {}).items()}

    def add(self, assumption_id: str, text: str) -> None:
        """Register or update an assumption.

        Args:
            assumption_id: the stable ID.
            text: the statement.
        """
        self._by_id[assumption_id] = text

    def bind(self, key: str, assumption_ids: List[str]) -> None:
        """Bind a decision key (intent type / domain) to assumption IDs.

        Args:
            key: the intent type or domain.
            assumption_ids: the assumption IDs the key rests on.
        """
        self._bindings[str(key)] = list(assumption_ids)

    def bindings(self) -> Dict[str, List[str]]:
        """All bindings as a plain dict.

        Returns:
            {key: [assumption_id, ...]}.
        """
        return {k: list(v) for k, v in self._bindings.items()}

    def refs_for(self, *keys: Optional[str]) -> List[str]:
        """The assumption IDs bound to any of the given keys (order-preserving).

        Args:
            *keys: intent type / domain (None values ignored).

        Returns:
            A de-duplicated, order-preserving list of assumption IDs.
        """
        out: List[str] = []
        for k in keys:
            if not k:
                continue
            for a in self._bindings.get(str(k), []):
                if a not in out:
                    out.append(a)
        return out

    def get(self, assumption_id: str) -> Optional[str]:
        """Text for an assumption ID, or None.

        Args:
            assumption_id: the ID.

        Returns:
            The text or None.
        """
        return self._by_id.get(assumption_id)

    def ids(self) -> List[str]:
        """All assumption IDs, sorted.

        Returns:
            Sorted IDs.
        """
        return sorted(self._by_id)

    def __contains__(self, assumption_id: str) -> bool:
        return assumption_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)

    def to_dict(self) -> Dict[str, str]:
        """Return the assumptions as a plain dict.

        Returns:
            {id: text}.
        """
        return dict(self._by_id)

    def to_config(self) -> Dict[str, Any]:
        """Return the full config (assumptions + bindings).

        Returns:
            {"assumptions": {id: text}, "bindings": {key: [ids]}}.
        """
        return {"assumptions": dict(self._by_id), "bindings": self.bindings()}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AssumptionRegistry":
        """Rebuild from a flat {id: text} dict.

        Args:
            d: {id: text}.

        Returns:
            The registry.
        """
        return cls({str(k): str(v) for k, v in (d or {}).items()})

    @classmethod
    def from_config(cls, c: Dict[str, Any]) -> "AssumptionRegistry":
        """Rebuild from either the wrapped config or a legacy flat dict.

        Args:
            c: {"assumptions": ..., "bindings": ...} or a flat {id: text}.

        Returns:
            The registry.
        """
        if isinstance(c, dict) and "assumptions" in c:
            return cls(c.get("assumptions") or {}, c.get("bindings") or {})
        return cls.from_dict(c or {})

    def save(self, path: str) -> None:
        """Persist to JSON (wrapped config; backward-compatible on load).

        Args:
            path: file path.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_config(), f, indent=2, sort_keys=True)

    @classmethod
    def load(cls, path: str) -> "AssumptionRegistry":
        """Load from JSON (empty registry when absent; accepts legacy flat form).

        Args:
            path: file path.

        Returns:
            The registry.
        """
        if not os.path.isfile(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            return cls.from_config(json.load(f))


class DecisionGraph:
    """A queryable graph over a set of DecisionRecords.

    Args:
        records: the decisions.
        registry: the shared assumption registry (optional).
    """

    def __init__(self, records: List[DecisionRecord],
                 registry: Optional[AssumptionRegistry] = None):
        self.records = list(records)
        self.registry = registry or AssumptionRegistry()
        self._by_id: Dict[str, DecisionRecord] = {r.decision_id: r for r in self.records}

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def from_records(cls, records: List[DecisionRecord],
                     registry: Optional[AssumptionRegistry] = None) -> "DecisionGraph":
        """Build a graph from records (+ optional registry).

        Args:
            records: the decisions.
            registry: the assumption registry.

        Returns:
            The graph.
        """
        return cls(records, registry)

    @classmethod
    def from_store(cls, store: "DecisionStore") -> "DecisionGraph":
        """Build a graph from a DecisionStore (records + assumptions.json).

        Args:
            store: the decision store.

        Returns:
            The graph.
        """
        return cls(store.all(), store.load_registry())

    # ── Queries ──────────────────────────────────────────────────────────────

    def direct_dependents(self, assumption_id: str) -> List[str]:
        """Decisions that directly reference an assumption.

        Args:
            assumption_id: the assumption ID.

        Returns:
            Sorted decision IDs.
        """
        return sorted(r.decision_id for r in self.records
                      if assumption_id in r.assumption_refs)

    def _propagating_children(self, decision_id: str) -> List[str]:
        """Decisions that depend on `decision_id` via a PROPAGATING edge.

        Args:
            decision_id: the parent decision.

        Returns:
            Sorted child decision IDs.
        """
        out = []
        for r in self.records:
            if decision_id in r.depends_on and decision_id not in r.guarded_deps:
                out.append(r.decision_id)
        return sorted(out)

    def affected_decisions(self, assumption_id: str) -> List[str]:
        """The exact set of decisions to revisit when an assumption changes.

        Traverses assumption→decision and propagating decision→decision edges
        transitively. Guarded edges (non-propagating) are excluded — a decision
        may depend on another without its outcome changing.

        Args:
            assumption_id: the changed assumption ID.

        Returns:
            Sorted decision IDs (the closure).
        """
        seen: Set[str] = set()
        frontier = self.direct_dependents(assumption_id)
        while frontier:
            cur = frontier.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for child in self._propagating_children(cur):
                if child not in seen:
                    frontier.append(child)
        return sorted(seen)

    def explain(self, assumption_id: str) -> Dict[str, Any]:
        """A transparent explanation of the propagation.

        Args:
            assumption_id: the changed assumption ID.

        Returns:
            {assumption, text, direct, transitive, affected, guarded_excluded}.
        """
        direct = self.direct_dependents(assumption_id)
        affected = self.affected_decisions(assumption_id)
        guarded_excluded = sorted({
            r.decision_id for r in self.records
            for d in r.guarded_deps if d in set(affected) | set(direct) and d in r.depends_on
        })
        return {
            "assumption": assumption_id,
            "text": self.registry.get(assumption_id),
            "direct": direct,
            "transitive": sorted(set(affected) - set(direct)),
            "affected": affected,
            "guarded_excluded": guarded_excluded,
        }

    def assumptions_of(self, decision_id: str) -> List[str]:
        """The assumption refs of a decision.

        Args:
            decision_id: the decision ID.

        Returns:
            Sorted assumption IDs.
        """
        r = self._by_id.get(decision_id)
        return sorted(r.assumption_refs) if r else []

    def to_dict(self) -> Dict[str, Any]:
        """A serializable snapshot.

        Returns:
            {assumptions, decisions}.
        """
        return {
            "assumptions": self.registry.to_dict(),
            "decisions": [{"decision_id": r.decision_id,
                           "assumption_refs": list(r.assumption_refs),
                           "depends_on": list(r.depends_on),
                           "guarded_deps": list(r.guarded_deps)}
                          for r in self.records],
        }
