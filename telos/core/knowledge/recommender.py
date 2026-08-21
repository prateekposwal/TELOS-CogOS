"""
KnowledgeRecommender — Ask "what works?" before you start.

Single-purpose: given a domain, return the single best-proven approach.
Read-only — never writes to the graph.

Usage:
    kg = KnowledgeGraph()
    kg.load("/tmp/knowledge.json")

    rec = KnowledgeRecommender(kg)
    approach = rec.recommend("football_tracking")
    # → "yolo_csrt"
    print(rec.summarize("football_tracking"))
    # → "Proven: yolo_csrt (0.92), csrt_kcf (0.75). Avoid: hough_circles (failed: HUD)"
"""

from typing import Optional, List, Dict

from telos.core.knowledge.graph import KnowledgeGraph


class KnowledgeRecommender:
    """Read-only advisor. Queries the graph for proven approaches."""

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph

    def recommend(self, domain: str) -> Optional[str]:
        """Single best approach for a domain."""
        return self._graph.best_approach(domain)

    def recommend_top(self, domain: str, top_k: int = 3) -> List[Dict]:
        """Top-k proven approaches with scores.
            Args:
                domain: the domain name
                top_k: the top_k argument for this call.
        """
        nodes = self._graph.search(domain, top_k=top_k, min_outcome=0.51)
        return [
            {"approach": n.approach, "outcome": n.outcome, "tags": n.tags}
            for n in nodes
        ]

    def failures(self, domain: str, top_k: int = 3) -> List[Dict]:
        """Known failures to avoid.
            Args:
                domain: the domain name
                top_k: the top_k argument for this call.
        """
        nodes = self._graph.search_failures(domain, top_k=top_k)
        return [
            {"approach": n.approach, "outcome": n.outcome,
             "failure_reason": n.failure_reason}
            for n in nodes
        ]

    def summarize(self, domain: str) -> str:
        """Human-readable summary of what's known.
            Args:
                domain: the domain name
        """
        proven = [f"{s['approach']} ({s['outcome']})" for s in self.recommend_top(domain)]
        failed = [f"{f['approach']} (failed: {f['failure_reason']})" for f in self.failures(domain)]
        parts = [f"Proven: {', '.join(proven)}"]
        if failed:
            parts.append(f"Avoid: {', '.join(failed)}")
        return ". ".join(parts)

    def would_repeat_failure(self, domain: str, approach: str) -> bool:
        """Check if this approach already failed in this domain."""
        return any(
            f["approach"] == approach
            for f in self.failures(domain)
        )
