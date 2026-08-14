"""
KnowledgeLinker — one canonical registry for cross-graph references.

Binds the knowledge islands into one connected structure:
  - KnowledgeGraph nodes     (telos/core/knowledge/graph.py)
  - TheoryGenealogy theories (telos/core/reasoning/genealogy.py)
  - SCM causal structures    (telos/core/reasoning/causal/scm.py)
  - Identity nodes           (telos/core/identity/identity_bridge.py) —
    self-observation nodes written by the IdentityBridge (Λ4.1 × Λ4.10)

A single linkage table lives here; nothing else owns node↔theory↔scm
references, so there is exactly one source of truth for cross-graph
connectivity (Λ4.10 Recursive World Models).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger('telos_knowledge_links')


class KnowledgeLinker:
    """Single linkage table: knowledge node ↔ theory ↔ SCM structure.

    Links are undirected at the table level: node_to_theory and
    theory_to_node are kept in sync by link_node_to_theory, and each
    theory points at exactly one SCM structure snapshot.
    """

    def __init__(self) -> None:
        self._node_to_theory: Dict[str, Set[str]] = defaultdict(set)
        self._theory_to_node: Dict[str, Set[str]] = defaultdict(set)
        self._theory_to_scm: Dict[str, str] = {}
        self._scm_structures: Dict[str, Dict[str, Any]] = {}
        self._scm_counter: int = 0
        self._genealogy = None
        # Identity nodes: self-observation knowledge nodes registered here so
        # "what do I know about my own state?" is a registry query, not a guess.
        self._identity_nodes: Set[str] = set()

    # ── Identity node registry ───────────────────────────────────

    def link_identity_node(self, node_id: str) -> None:
        """Register a knowledge node as a self-observation (identity) node.

        Args:
            node_id: knowledge-graph node id to register as identity.
        """
        self._identity_nodes.add(node_id)

    def identity_nodes(self) -> List[str]:
        """All registered identity self-observation nodes."""
        return sorted(self._identity_nodes)

    def is_identity_node(self, node_id: str) -> bool:
        return node_id in self._identity_nodes

    # ── Wiring ───────────────────────────────────────────────────

    def attach_genealogy(self, genealogy) -> None:
        """Attach the TheoryGenealogy for theory-name lookups in queries."""
        self._genealogy = genealogy

    # ── Link operations ──────────────────────────────────────────

    def link_node_to_theory(self, node_id: str, theory_id: str) -> None:
        """Register a knowledge node ↔ theory reference (both directions).

        Args:
            node_id: knowledge-graph node id.
            theory_id: genealogy theory id.
        """
        self._node_to_theory[node_id].add(theory_id)
        self._theory_to_node[theory_id].add(node_id)

    def unlink_node(self, node_id: str) -> None:
        """Remove every theory reference for a knowledge node.

        Args:
            node_id: knowledge-graph node id to unlink from all theories.
        """
        for tid in self._node_to_theory.pop(node_id, set()):
            self._theory_to_node[tid].discard(node_id)

    def link_theory_to_scm(self, theory_id: str, scm) -> str:
        """Attach an SCM's causal structure to a theory.

        Snapshots the structure (edges, variables, intervention count) at
        link time. Re-linking the same theory replaces its snapshot with
        the latest one.

        Args:
            theory_id: genealogy theory id.

        Returns:
            The structure id.
        """
        summary = getattr(scm, 'graph_summary', {}) or {}
        sid = f"scm_{self._scm_counter}"
        self._scm_counter += 1
        self._scm_structures[sid] = {
            "edges": summary.get("edges", []),
            "variables": summary.get("variables", []),
            "interventions": summary.get("interventions", 0),
        }
        self._theory_to_scm[theory_id] = sid
        return sid

    # ── Queries ──────────────────────────────────────────────────

    def theories_for_node(self, node_id: str) -> List[str]:
        return sorted(self._node_to_theory.get(node_id, set()))

    def nodes_for_theory(self, theory_id: str) -> List[str]:
        return sorted(self._theory_to_node.get(theory_id, set()))

    def scm_for_theory(self, theory_id: str) -> Optional[Dict[str, Any]]:
        sid = self._theory_to_scm.get(theory_id)
        if sid is None:
            return None
        return self._scm_structures.get(sid)

    def get_connected_structure(self, node_id: str,
                                knowledge_graph=None) -> Dict[str, Any]:
        """Reachable neighborhood across all three graphs from a node.

        node_id → linked theories → (their SCM structures, sibling
        knowledge nodes) plus node_id → knowledge-graph edge neighbors.

        Args:
            node_id: starting node id.
            knowledge_graph: optional KnowledgeGraph for edge neighbors.

        Returns:
            Dict with knowledge_neighbors, theories, linked_theory_count,
            identity_node and sibling_identity_nodes.
        """
        theories = self.theories_for_node(node_id)

        knowledge_neighbors: List[Dict[str, Any]] = []
        if knowledge_graph is not None:
            for nbr in knowledge_graph.get_neighbors(node_id):
                info: Dict[str, Any] = {"node_id": nbr}
                node = knowledge_graph._nodes.get(nbr)
                if node is None:
                    node = knowledge_graph._archived_nodes.get(nbr)
                if node is not None:
                    info["domain"] = node.domain
                    info["approach"] = node.approach
                    info["outcome"] = node.outcome
                knowledge_neighbors.append(info)

        theory_views: List[Dict[str, Any]] = []
        for tid in theories:
            view: Dict[str, Any] = {"theory_id": tid}
            if self._genealogy is not None:
                gnode = getattr(self._genealogy, '_nodes', {}).get(tid)
                if gnode is not None:
                    view["name"] = gnode.name
                    view["parent_id"] = gnode.parent_id
                    view["birth_cycle"] = gnode.birth_cycle
            scm_view = self.scm_for_theory(tid)
            if scm_view is not None:
                view["scm"] = scm_view
            siblings = self.nodes_for_theory(tid)
            others = [s for s in siblings if s != node_id]
            if others:
                view["related_nodes"] = others
            theory_views.append(view)

        return {
            "node_id": node_id,
            "knowledge_neighbors": knowledge_neighbors,
            "theories": theory_views,
            "linked_theory_count": len(theories),
            "identity_node": node_id in self._identity_nodes,
            "sibling_identity_nodes": sorted(self._identity_nodes - {node_id}),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Full linkage table for serialization/inspection."""
        return {
            "node_to_theory": {k: sorted(v) for k, v in self._node_to_theory.items()},
            "theory_to_scm": dict(self._theory_to_scm),
            "scm_structures": self._scm_structures,
            "identity_nodes": sorted(self._identity_nodes),
        }
