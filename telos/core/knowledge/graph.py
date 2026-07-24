"""
KnowledgeGraph — Spiderweb Memory of Proven Solutions.

Structures past project outcomes (successes AND failures) into a
searchable graph. Actively maintains "hot" nodes for fast retrieval;
archives cold nodes to keep the working set lean.

Usage:
    kg = KnowledgeGraph()

    # Record what worked
    kg.record("football_tracking", "yolo_csrt", 0.92,
              tags=["deep_learning", "real_time"])

    # Record what failed
    kg.record("football_tracking", "hough_circles", 0.18,
              failure_reason="HUD_contamination",
              tags=["cv_filter", "false_positive"])

    # Ask what works
    kg.recommend("football_tracking")  # → "yolo_csrt"

    # Persist
    kg.save("/tmp/knowledge.json")
    kg.load("/tmp/knowledge.json")
"""

from __future__ import annotations

import time
import json
import hashlib
import logging
import math
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger('telos_knowledge')

_HOT_DECAY_PER_CYCLE = 0.05
_ARCHIVE_FLOOR = 0.01
_DEFAULT_MAX_HOT = 100
_DEFAULT_MAX_RECORDS_PER_MINUTE = 60


@dataclass
class ProjectNode:
    """A node in the knowledge graph — one past project or approach."""
    node_id: str
    domain: str
    approach: str
    outcome: float
    failure_reason: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    activation: float = 1.0
    access_count: int = 1
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.outcome > 0.5

    @property
    def is_failure(self) -> bool:
        return self.outcome <= 0.5

    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "approach": self.approach,
            "outcome": self.outcome,
            "failure_reason": self.failure_reason,
            "tags": self.tags,
            "params": self.params,
            "timestamp": self.timestamp,
            "provenance": self.provenance,
        }


class KnowledgeGraph:
    """Spiderweb memory — fast-forward index, auto-archive cold nodes.
    
    Security:
      - INTERNAL_DOMAINS: read-only from KG perspective (cannot be written)
      - ALLOWED_WRITE_DOMAINS: only these domains can be recorded
      - Provenance tracking: every record stores source/cycle/caller
    """

    INTERNAL_DOMAINS: frozenset = frozenset({
        "mission_policy", "stream_calibrator", "failure_ledger",
        "system_self", "identity", "governance", "firewall",
    })
    ALLOWED_WRITE_DOMAINS: frozenset = frozenset({
        "d", "x", "search", "domain", "d1", "d2", "multi",
        "gridworld", "devdomain", "navigation", "perception",
        "planning", "simulation", "communication", "meta_cognition",
        "pattern", "reflection", "test", "test_domain", "test_domain_2", "video",
        "conversation", "blocker", "preference", "unknown", "user_preference",
    })

    def __init__(self, max_hot_nodes: int = _DEFAULT_MAX_HOT, max_archived: int = 500,
                 max_records_per_minute: int = _DEFAULT_MAX_RECORDS_PER_MINUTE):
        self._nodes: Dict[str, ProjectNode] = {}
        self._domain_index: Dict[str, Set[str]] = defaultdict(set)
        self._tag_index: Dict[str, Set[str]] = defaultdict(set)
        self._max_hot_nodes = max_hot_nodes
        self._archived_nodes: Dict[str, ProjectNode] = {}
        self._max_archived = max_archived
        self._cycle = 0
        self._max_records_per_minute = max_records_per_minute
        self._record_timestamps: Dict[str, List[float]] = defaultdict(list)

    # ── Validation ───────────────────────────────────────────────

    def _validate_record(self, domain: str, approach: str, outcome: float,
                         failure_reason: Optional[str] = None,
                         tags: Optional[List[str]] = None,
                         params: Optional[Dict] = None) -> None:
        """Validate record inputs before storing. Raises ValueError on invalid data."""

        # domain: string, 1-256 chars
        if not isinstance(domain, str):
            raise ValueError(f"domain must be a string, got {type(domain).__name__}")
        if len(domain) < 1 or len(domain) > 256:
            raise ValueError(f"domain must be 1-256 characters, got {len(domain)}")

        # approach: string, 1-256 chars
        if not isinstance(approach, str):
            raise ValueError(f"approach must be a string, got {type(approach).__name__}")
        if len(approach) < 1 or len(approach) > 256:
            raise ValueError(f"approach must be 1-256 characters, got {len(approach)}")

        # outcome: float between 0.0 and 1.0
        if not isinstance(outcome, (int, float)):
            raise ValueError(f"outcome must be a number, got {type(outcome).__name__}")
        if isinstance(outcome, float) and (math.isnan(outcome) or math.isinf(outcome)):
            raise ValueError(f"outcome must not be NaN or Inf, got {outcome}")
        if outcome < 0.0 or outcome > 1.0:
            raise ValueError(f"outcome must be between 0.0 and 1.0, got {outcome}")

        # failure_reason: string or None
        if failure_reason is not None and not isinstance(failure_reason, str):
            raise ValueError(
                f"failure_reason must be a string or None, got {type(failure_reason).__name__}"
            )

        # tags: list of strings, max 20
        if tags is not None:
            if not isinstance(tags, list):
                raise ValueError(f"tags must be a list, got {type(tags).__name__}")
            if len(tags) > 20:
                raise ValueError(f"tags must have at most 20 items, got {len(tags)}")
            for i, t in enumerate(tags):
                if not isinstance(t, str):
                    raise ValueError(f"tags[{i}] must be a string, got {type(t).__name__}")

        # params: dict, no keys starting with '_'
        if params is not None:
            if not isinstance(params, dict):
                raise ValueError(f"params must be a dict, got {type(params).__name__}")
            for k in params:
                if not isinstance(k, str):
                    raise ValueError(f"params keys must be strings, got {type(k).__name__}")
                if k.startswith('_'):
                    raise ValueError(f"params keys must not start with '_', got {k!r}")

    # ── Record API ──────────────────────────────────────────────

    def record(self, domain: str, approach: str, outcome: float,
               failure_reason: Optional[str] = None,
               tags: Optional[List[str]] = None,
               params: Optional[Dict] = None,
               provenance: Optional[Dict] = None) -> str:
        """Record any outcome — success or failure.
        
        Args:
            provenance: Optional dict with source/cycle/caller info.
                Attached to the node for audit trail.
        """
        # Domain whitelist check — block only internal domains, warn for unknown
        if domain in self.INTERNAL_DOMAINS:
            logger.warning(
                f"KnowledgeGraph: WRITE DENIED — domain '{domain}' is internal/read-only"
            )
            return ""
        if not any(domain == d or domain.startswith(d + "/") for d in self.ALLOWED_WRITE_DOMAINS):
            logger.warning(
                f"KnowledgeGraph: blocked write to unregistered domain '{domain}' "
                f"(add to ALLOWED_WRITE_DOMAINS to allow)"
            )
            return ""

        # Validate inputs before any mutation
        self._validate_record(domain, approach, outcome, failure_reason, tags, params)

        # Per-domain sliding window rate limiter
        now = time.time()
        window = 60.0

        # Clean up old timestamps (>60 seconds)
        domain_times = self._record_timestamps[domain]
        cutoff = now - window
        self._record_timestamps[domain] = [t for t in domain_times if t > cutoff]

        # Check rate limit
        if len(self._record_timestamps[domain]) >= self._max_records_per_minute:
            logger.warning(
                "Rate limit exceeded for domain '%s': %d records in the last 60s (max %d). Skipping.",
                domain, len(self._record_timestamps[domain]), self._max_records_per_minute,
            )
            return ""

        # Track this record timestamp
        self._record_timestamps[domain].append(now)

        node_id = self._make_id(domain, approach)
        self._nodes[node_id] = ProjectNode(
            node_id=node_id, domain=domain, approach=approach,
            outcome=min(outcome, 1.0), failure_reason=failure_reason,
            tags=tags or [], params=params or {},
            timestamp=now, activation=1.0,
            provenance=provenance or {},
        )
        self._domain_index[domain].add(node_id)
        for tag in (tags or []):
            self._tag_index[tag].add(node_id)
        return node_id

    def record_success(self, domain: str, approach: str, outcome: float,
                       tags: Optional[List[str]] = None,
                       params: Optional[Dict] = None,
                       provenance: Optional[Dict] = None) -> str:
        return self.record(domain, approach, outcome, tags=tags, params=params,
                           provenance=provenance)

    def record_failure(self, domain: str, approach: str, outcome: float,
                       failure_reason: str, tags: Optional[List[str]] = None,
                       params: Optional[Dict] = None,
                       provenance: Optional[Dict] = None) -> str:
        return self.record(domain, approach, outcome,
                           failure_reason=failure_reason, tags=tags, params=params,
                           provenance=provenance)

    # ── Query API ───────────────────────────────────────────────

    def recommend(self, domain: str, top_k: int = 1) -> List[ProjectNode]:
        """Get the best-proven solutions for a domain (successes only)."""
        return self.search(domain=domain, top_k=top_k, min_outcome=0.51)

    def search(self, domain: Optional[str] = None,
               tags: Optional[List[str]] = None,
               top_k: int = 5, min_outcome: float = 0.0) -> List[ProjectNode]:
        candidates = self._get_candidates(domain, tags)
        now = time.time()
        scored = []
        for nid in candidates:
            node = self._nodes.get(nid)
            if node is None or node.outcome < min_outcome:
                continue
            recency = max(0.0, 1.0 - (now - node.timestamp) / 86400)
            score = node.outcome * 0.6 + recency * 0.3 + node.activation * 0.1
            scored.append((score, node))
        # Also query archived nodes with a cold penalty (Λ4.7 System Memory)
        archived_candidates = self._get_archived_candidates(domain, tags)
        for nid in archived_candidates:
            node = self._archived_nodes.get(nid)
            if node is None or node.outcome < min_outcome:
                continue
            recency = max(0.0, 1.0 - (now - node.timestamp) / 86400)
            # Cold penalty: archived nodes have 0 activation, reduced score
            score = node.outcome * 0.6 + recency * 0.3 - 0.3
            scored.append((score, node))
        scored.sort(key=lambda x: -x[0])
        return [n for _, n in scored[:top_k]]

    def search_failures(self, domain: Optional[str] = None,
                        tags: Optional[List[str]] = None,
                        top_k: int = 5) -> List[ProjectNode]:
        candidates = self._get_candidates(domain, tags)
        scored = []
        for nid in candidates:
            node = self._nodes.get(nid)
            if node is None or node.outcome > 0.5:
                continue
            scored.append((1.0 - node.outcome + node.activation * 0.1, node))
        # Also query archived failures with a cold penalty (Λ2.3 Kintsugi)
        archived_candidates = self._get_archived_candidates(domain, tags)
        for nid in archived_candidates:
            node = self._archived_nodes.get(nid)
            if node is None or node.outcome > 0.5:
                continue
            score = 1.0 - node.outcome - 0.2  # cold penalty
            scored.append((score, node))
        scored.sort(key=lambda x: -x[0])
        return [n for _, n in scored[:top_k]]

    def best_approach(self, domain: str) -> Optional[str]:
        """Quick answer: what approach works best for this domain?"""
        nodes = self.recommend(domain, top_k=1)
        return nodes[0].approach if nodes else None

    def activate(self, node_id: str, boost: float = 0.5) -> None:
        """Boost a node's activation when reused."""
        node = self._nodes.get(node_id)
        if node:
            node.activation = min(2.0, node.activation + boost)
            node.access_count += 1
            node.timestamp = time.time()

    # ── Lifecycle ───────────────────────────────────────────────

    def tick(self) -> int:
        """Decay activation, archive cold nodes. Returns archived count."""
        self._cycle += 1
        to_archive = []
        for nid, node in self._nodes.items():
            node.activation = max(0.0, node.activation - _HOT_DECAY_PER_CYCLE * 0.3)
            if node.activation <= _ARCHIVE_FLOOR:
                to_archive.append(nid)
        for nid in to_archive:
            self._archive(nid)
        if len(self._nodes) > self._max_hot_nodes:
            cold = sorted(self._nodes.items(), key=lambda x: x[1].activation)[:50]
            for nid, _ in cold:
                self._archive(nid)
        return len(to_archive)

    def domain_summary(self, domain: str) -> Dict:
        successes = self.search(domain, top_k=5, min_outcome=0.51)
        failures = self.search_failures(domain, top_k=3)
        return {
            "domain": domain,
            "best_approach": successes[0].approach if successes else None,
            "best_outcome": successes[0].outcome if successes else None,
            "known_solutions": [n.approach for n in successes],
            "known_failures": [
                {"approach": n.approach, "reason": n.failure_reason}
                for n in failures
            ],
        }

    # ── Persistence ─────────────────────────────────────────────

    def save(self, path: str) -> None:
        data = {
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            "archived_nodes": {nid: n.to_dict() for nid, n in self._archived_nodes.items()},
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        try:
            with open(path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return
        for nid, ndata in data.get("nodes", {}).items():
            self._nodes[nid] = ProjectNode(
                node_id=nid, domain=ndata["domain"],
                approach=ndata["approach"], outcome=ndata["outcome"],
                failure_reason=ndata.get("failure_reason"),
                tags=ndata.get("tags", []),
                params=ndata.get("params", {}),
                activation=ndata.get("activation", 0.5),
                access_count=ndata.get("access_count", 1),
                timestamp=ndata.get("timestamp", 0.0),
            )
            self._domain_index[ndata["domain"]].add(nid)
            for tag in ndata.get("tags", []):
                self._tag_index[tag].add(nid)
        for nid, ndata in data.get("archived_nodes", {}).items():
            self._archived_nodes[nid] = ProjectNode(
                node_id=nid, domain=ndata["domain"],
                approach=ndata["approach"], outcome=ndata["outcome"],
                failure_reason=ndata.get("failure_reason"),
                tags=ndata.get("tags", []),
                params=ndata.get("params", {}),
                activation=ndata.get("activation", 0.0),
                access_count=ndata.get("access_count", 1),
                timestamp=ndata.get("timestamp", 0.0),
            )

    # ─── Properties ──────────────────────────────────────────────

    @property
    def stats(self) -> Dict:
        successes = sum(1 for n in self._nodes.values() if n.is_success)
        failures = sum(1 for n in self._nodes.values() if n.is_failure)
        return {
            "total_nodes": len(self._nodes),
            "hot_nodes": sum(1 for n in self._nodes.values() if n.activation >= 0.5),
            "successes": successes,
            "failures": failures,
            "domains": list(self._domain_index.keys()),
            "archived_nodes": len(self._archived_nodes),
            "cycle": self._cycle,
        }

    # ── Internal ────────────────────────────────────────────────

    def restore(self, node_id: str) -> bool:
        """Restore an archived node back to the active set.
        Returns True if the node was found and restored, False otherwise."""
        node = self._archived_nodes.pop(node_id, None)
        if node is None:
            return False
        node.activation = 1.0
        node.timestamp = time.time()
        self._nodes[node_id] = node
        self._domain_index[node.domain].add(node_id)
        for tag in node.tags:
            self._tag_index[tag].add(node_id)
        return True

    def _make_id(self, domain: str, approach: str) -> str:
        raw = f"{domain}::{approach}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _get_candidates(self, domain: Optional[str],
                        tags: Optional[List[str]]) -> Set[str]:
        candidates: Optional[Set[str]] = None
        if domain:
            candidates = self._domain_index.get(domain, set()).copy()
        if tags:
            tag_ids = set.union(*(self._tag_index.get(t, set()) for t in tags)) if tags else set()
            candidates = (candidates & tag_ids) if candidates else tag_ids
        return candidates if candidates is not None else set(self._nodes.keys())

    def _get_archived_candidates(self, domain: Optional[str],
                                  tags: Optional[List[str]]) -> Set[str]:
        """Get candidates from archived nodes matching domain/tags."""
        candidates: Set[str] = set()
        for nid, node in self._archived_nodes.items():
            if domain and node.domain != domain:
                continue
            if tags and not all(t in node.tags for t in tags):
                continue
            candidates.add(nid)
        return candidates

    def _archive(self, node_id: str) -> None:
        node = self._nodes.pop(node_id, None)
        if node is None:
            return
        node.activation = 0.0
        self._archived_nodes[node_id] = node
        for idx in (self._domain_index, self._tag_index):
            for s in idx.values():
                s.discard(node_id)
        # Evict oldest archived nodes if over capacity
        while len(self._archived_nodes) > self._max_archived:
            oldest_id = min(self._archived_nodes, key=lambda nid: self._archived_nodes[nid].timestamp)
            del self._archived_nodes[oldest_id]
