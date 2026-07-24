"""
KGInferenceEngine — Similarity and Pattern Detection for KnowledgeGraph.
"""
from __future__ import annotations
import math
from typing import Dict, List, Any, Optional
from telos.core.knowledge.graph import KnowledgeGraph, ProjectNode

class KGInferenceEngine:
    """Inference engine for KnowledgeGraph — similarity and failure patterns."""

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg

    def find_similar_outcomes(self, current_params: Dict[str, Any], top_k: int = 3) -> List[ProjectNode]:
        """Find related past outcomes using Euclidean distance on params."""
        scored = []
        for node in self.kg._nodes.values():
            if not node.params:
                continue
            dist = self._euclidean_distance(current_params, node.params)
            scored.append((dist, node))
        
        # Sort by distance ascending (closer is better)
        scored.sort(key=lambda x: x[0])
        return [node for _, node in scored[:top_k]]

    def _euclidean_distance(self, p1: Dict, p2: Dict) -> float:
        keys = set(p1.keys()) | set(p2.keys())
        sum_sq = 0.0
        for k in keys:
            v1 = float(p1.get(k, 0.0))
            v2 = float(p2.get(k, 0.0))
            sum_sq += (v1 - v2) ** 2
        return math.sqrt(sum_sq)

    def detect_failure_patterns(self, domain: str) -> List[Dict]:
        """Cluster failures by (domain, validator, context_delta)."""
        # Simple clustering by validator (as proxy for validator+context_delta)
        failures = self.kg.search_failures(domain=domain)
        patterns: Dict[str, List[ProjectNode]] = {}
        for node in failures:
            validator = node.params.get('blocking_validator', 'unknown')
            if validator not in patterns:
                patterns[validator] = []
            patterns[validator].append(node)
        
        return [
            {"validator": v, "count": len(nodes), "reason": nodes[0].failure_reason}
            for v, nodes in patterns.items()
        ]
