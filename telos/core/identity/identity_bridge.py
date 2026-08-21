"""IdentityBridge — the identity↔knowledge connection (Λ4.1 × Λ4.10 × Λ6.7).

Identity used to be a disconnected island: IdentityCore/IdentityNarrative/
IdentityState lived in system_self.py, the KnowledgeGraph refused
identity-domain writes, and the KnowledgeLinker's registry had no identity
entries. This bridge is the single architectural connection between the
MUTABLE identity layers and the knowledge web.

Constraints honored (system_self.py:44-45, graph.py:125):
  - IdentityCore is FROZEN — only the Axiom Evolution Engine + HumanGateway
    may change it. The bridge READS the core for provenance anchoring and
    never mutates it.
  - KnowledgeGraph treats 'identity' as an internal/read-only domain for
    arbitrary callers. This bridge is the ONLY trusted writer: every node it
    creates goes through KnowledgeGraph.record_internal() with
    provenance={'caller': 'identity_bridge', ...} — auditable by design.
  - The KnowledgeLinker remains the single canonical registry for cross-graph
    connectivity (Λ4.10); identity joins it as a fourth connected structure.

What the bridge records (as knowledge nodes in the identity domain):
  - self_snapshot_<cycle>: mood, confidence trend, markers, beliefs, DI/MD —
    one per pipeline cycle (a time series of self-state).
  - marker_<name> / mood_<name> / mission_<name> event nodes when the
    mutable layers change.

Queries it answers:
  - "what do I know about my own state?"  -> self_knowledge()
  - "what identity-relevant knowledge is hot right now?" -> hot_identity_knowledge()
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger('telos_identity_bridge')

# Provenance caller id trusted by KnowledgeGraph.record_internal().
BRIDGE_CALLER = "identity_bridge"
IDENTITY_DOMAIN = "identity"


class IdentityBridge:
    """Bidirectional wiring: mutable identity layers ↔ KnowledgeGraph ↔ Linker."""

    def __init__(self, system_self, knowledge, linker, identity_core=None):
        self.system_self = system_self
        self.knowledge = knowledge
        self.linker = linker
        self.identity_core = identity_core  # read-only provenance anchor (frozen)
        self._last_snapshot: Optional[Dict[str, Any]] = None
        self._last_markers: Set[str] = set()
        self._last_mood: Optional[str] = None
        self._snapshot_node_id: Optional[str] = None

    # ── Provenance ──────────────────────────────────────────────

    def _provenance(self, kind: str, cycle: int) -> Dict[str, Any]:
        core = self.identity_core
        return {
            "caller": BRIDGE_CALLER,
            "source": "system_self",
            "kind": kind,
            "cycle": cycle,
            "timestamp": time.time(),
            "core_anchor": {
                "values": list(core.core_values) if core is not None else [],
                "principles": list(core.core_principles) if core is not None else [],
                "genesis_mood": core.genesis_mood if core is not None else None,
                "axioms_count": core.axioms_count if core is not None else None,
            },
        }

    # ── Snapshot: one identity node per cycle ───────────────────

    def sync(self, cycle: int = 0, di: float = 1.0, md: float = 0.0,
             selected_intent: str = "none",
             verified_closures: int = 0) -> str:
        """Record this cycle's mutable identity state as an identity-domain
        knowledge node + refresh semantic marker links.

        Args:
            cycle: current pipeline cycle (used in node approach + provenance)
            di: decision integrity of this cycle (0-1) — the self-observation
                outcome stored on the node
            md: mission drift of this cycle
            selected_intent: intent_type chosen this cycle (or "none")
            verified_closures: count of PROVEN gap-closes this cycle (Λ2.3 —
                a measured soundness signal, piped from the fix loop audit).

        Returns:
            The node id (or "" if rate-limited/denied). Best-effort — never raises."""
        ss = self.system_self
        if ss is None:
            return ""
        state = ss.state if hasattr(ss, 'state') else None
        markers = set(getattr(state, 'identity_markers', set()) or set())
        mood = getattr(state, 'mood', None) or (ss.mood if hasattr(ss, 'mood') else "curious")
        trend = getattr(state, 'confidence_trend', "stable")
        beliefs = getattr(state, 'belief_state', {}) or {}

        params: Dict[str, Any] = {
            "mood": mood,
            "confidence_trend": trend,
            "identity_markers": sorted(markers),
            "belief_state": {k: dict(v) for k, v in beliefs.items()},
            "di": round(float(di), 4),
            "md": round(float(md), 4),
            "selected_intent": selected_intent,
            "verified_closures": int(max(0, verified_closures)),
            "role": getattr(state, 'role', None) if hasattr(state, 'role') else None,
        }
        tags = ["identity", "self", mood] + sorted(markers)
        node_id = self.knowledge.record_internal(
            domain=IDENTITY_DOMAIN,
            approach=f"self_snapshot_cycle_{cycle}",
            outcome=float(max(0.0, min(1.0, di))),  # self-observation quality
            tags=tags[:20],
            params=params,
            provenance=self._provenance("self_snapshot", cycle),
        )
        if node_id:
            self.linker.link_identity_node(node_id)
            self._snapshot_node_id = node_id
            self._last_snapshot = dict(params)
            # Event nodes for layer changes (mood / markers / missions)
            self._record_changes(cycle, mood, markers)
        return node_id

    def _record_changes(self, cycle: int, mood: str, markers: Set[str]) -> None:
        """Emit event-level identity nodes when mutable layers changed.

        Args:
            cycle: current pipeline cycle (stamped on event nodes)
            mood: the new mood after this cycle's sync
            markers: the full marker set after this cycle's sync
        """
        if self._last_mood is not None and mood != self._last_mood:
            self.record_mood_change(mood, cycle)
        if markers != self._last_markers:
            new_markers = markers - self._last_markers
            for m in sorted(new_markers):
                self.record_marker(m, cycle)
        self._last_mood = mood
        self._last_markers = set(markers)

    # ── Event nodes ─────────────────────────────────────────────

    def record_marker(self, marker: str, cycle: int = 0) -> str:
        node_id = self.knowledge.record_internal(
            domain=IDENTITY_DOMAIN,
            approach=f"marker_{marker}",
            outcome=0.9,
            tags=["identity", "marker", marker][:20],
            params={"marker": marker, "cycle": cycle},
            provenance=self._provenance("marker_added", cycle),
        )
        if node_id:
            self.linker.link_identity_node(node_id)
        return node_id

    def record_mood_change(self, mood: str, cycle: int = 0) -> str:
        node_id = self.knowledge.record_internal(
            domain=IDENTITY_DOMAIN,
            approach=f"mood_{mood}",
            outcome=0.9,
            tags=["identity", "mood", mood][:20],
            params={"mood": mood, "cycle": cycle},
            provenance=self._provenance("mood_change", cycle),
        )
        if node_id:
            self.linker.link_identity_node(node_id)
        return node_id

    def record_mission_completed(self, mission: str, cycle: int = 0) -> str:
        node_id = self.knowledge.record_internal(
            domain=IDENTITY_DOMAIN,
            approach=f"mission_{mission}",
            outcome=1.0,
            tags=["identity", "mission", mission][:20],
            params={"mission": mission, "cycle": cycle},
            provenance=self._provenance("mission_completed", cycle),
        )
        if node_id:
            self.linker.link_identity_node(node_id)
        return node_id

    # ── Semantic links: markers ↔ knowledge ─────────────────────

    def link_markers_to_knowledge(self, max_per_marker: int = 3) -> int:
        """Connect identity markers to knowledge nodes sharing semantics.

        For each current identity marker, search the knowledge graph for
        nodes whose tags or domain match the marker, then (a) add a typed KG
        edge identity_node -> knowledge_node (edge_type='identity_affinity')
        and (b) record the link so get_connected_structure(identity_node)
        returns a real neighborhood spanning identity ↔ knowledge.
        Args:
            max_per_marker: how many knowledge nodes to consider per marker

        Returns:
            The number of edges created.
        """
        ss = self.system_self
        if ss is None or self._snapshot_node_id is None:
            return 0
        markers = set(getattr(ss.state, 'identity_markers', set()) or set())
        created = 0
        for marker in sorted(markers):
            nodes = self.knowledge.search(tags=[marker], top_k=max_per_marker,
                                          min_outcome=0.0)
            for node in nodes:
                if node.node_id == self._snapshot_node_id:
                    continue
                try:
                    self.knowledge.add_edge(
                        self._snapshot_node_id, node.node_id,
                        edge_type="identity_affinity", weight=0.5,
                        metadata={"marker": marker, "caller": BRIDGE_CALLER},
                    )
                    created += 1
                except ValueError:
                    continue  # self-edge or dup — skip
        if created:
            logger.debug(
                f"IdentityBridge: linked {created} knowledge node(s) to "
                f"identity markers: {sorted(markers)[:5]}"
            )
        return created

    def rebind_from_graph(self) -> int:
        """Re-register identity-domain nodes into the linker registry.

        After a checkpoint restore, the KnowledgeGraph is reconstructed but
        the linker registry is not serialized — scan the graph for
        identity-domain self-observation nodes and re-bind them so
        identity_nodes() / get_connected_structure stay correct (Λ4.10 one
        canonical registry). Returns the number of nodes re-bound.
        """
        if self.knowledge is None or self.linker is None:
            return 0
        bound = 0
        for nid, node in getattr(self.knowledge, '_nodes', {}).items():
            if node.domain == IDENTITY_DOMAIN:
                self.linker.link_identity_node(nid)
                bound += 1
        for nid, node in getattr(self.knowledge, '_archived_nodes', {}).items():
            if node.domain == IDENTITY_DOMAIN:
                self.linker.link_identity_node(nid)
                bound += 1
        if bound:
            logger.info(f"IdentityBridge: rebound {bound} identity node(s) from graph")
        return bound

    # ── Queries ─────────────────────────────────────────────────

    def self_knowledge(self) -> Dict[str, Any]:
        """'What do I know about my own state?' — snapshot + connected
        neighborhood spanning identity ↔ knowledge ↔ theories."""
        snapshot = dict(self._last_snapshot or {})
        neighborhood = None
        if self._snapshot_node_id:
            neighborhood = self.linker.get_connected_structure(
                self._snapshot_node_id, knowledge_graph=self.knowledge,
            )
        return {
            "snapshot_node": self._snapshot_node_id,
            "snapshot": snapshot,
            "identity_nodes": self.linker.identity_nodes(),
            "connected_structure": neighborhood,
            "hot_identity_knowledge": self.hot_identity_knowledge(top_k=5),
        }

    def hot_identity_knowledge(self, top_k: int = 5) -> List[Dict[str, Any]]:
        """'What identity-relevant knowledge is hot right now?' — knowledge
        nodes sharing identity markers/tags, ranked by activation (Λ4.7 Law
        of Attention and Trajectory).

        Args:
            top_k: maximum number of deduplicated nodes to return.

        Returns:
            List of {node_id, domain, approach, outcome, activation, marker}.
        """
        ss = self.system_self
        if ss is None:
            return []
        markers = set(getattr(ss.state, 'identity_markers', set()) or set())
        hot: List[Dict[str, Any]] = []
        for marker in sorted(markers):
            for node in self.knowledge.search(tags=[marker], top_k=top_k,
                                              min_outcome=0.0):
                hot.append({
                    "node_id": node.node_id,
                    "domain": node.domain,
                    "approach": node.approach,
                    "outcome": node.outcome,
                    "activation": node.activation,
                    "marker": marker,
                })
        hot.sort(key=lambda x: -x["activation"])
        seen: Set[str] = set()
        dedup = []
        for h in hot:
            if h["node_id"] not in seen:
                seen.add(h["node_id"])
                dedup.append(h)
        return dedup[:top_k]
