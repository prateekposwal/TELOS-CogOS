"""
OutcomeRecorder — Record outcomes with full context.

Three modes:
  - success(domain, approach, score, tags)  → stores a win
  - failure(domain, approach, reason, tags) → stores a loss
  - from_user(domain, approach, user_said, tags) → stores with user sentiment

Usage:
    kg = KnowledgeGraph()
    rec = OutcomeRecorder(kg)

    rec.success("football_tracking", "yolo_csrt", 0.92)
    rec.failure("football_tracking", "hough_circles",
                "HUD contamination in bottom 25%")
    rec.from_user("football_tracking", "mog2_white",
                  "circle points to player shirt, not ball")
"""

from __future__ import annotations

from typing import Optional, Dict, List

from telos.core.knowledge.graph import KnowledgeGraph


class OutcomeRecorder:
    """Records outcomes into the graph with contextual metadata."""

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph

    def success(self, domain: str, approach: str, outcome: float,
                tags: Optional[List[str]] = None,
                params: Optional[Dict] = None) -> str:
        """Record a successful outcome."""
        all_tags = (tags or []) + ["success"]
        return self._graph.record(
            domain, approach, outcome,
            tags=all_tags, params=params,
        )

    def failure(self, domain: str, approach: str,
                failure_reason: str, tags: Optional[List[str]] = None,
                params: Optional[Dict] = None) -> str:
        """Record a failed approach with reason."""
        all_tags = (tags or []) + ["failure"]
        return self._graph.record_failure(
            domain, approach, 0.15,
            failure_reason=failure_reason,
            tags=all_tags, params=params,
        )

    def from_user(self, domain: str, approach: str,
                  user_said: str, tags: Optional[List[str]] = None) -> str:
        """Record user-reported failure with their verbatim feedback."""
        return self.failure(
            domain, approach,
            failure_reason=f"user_report: {user_said}",
            tags=(tags or []) + ["user_feedback"],
            params={"user_verbatim": user_said},
        )

    def record(self, domain: str, approach: str, outcome: float,
               tags: Optional[List[str]] = None,
               params: Optional[Dict] = None) -> str:
        """Record a generic outcome (neither success nor failure)."""
        return self._graph.record(
            domain, approach, outcome,
            tags=tags or [], params=params,
        )

    def record_params(self, domain: str, approach: str, outcome: float,
                      params: Dict) -> str:
        """Record with execution parameters (for reproducibility)."""
        return self._graph.record(domain, approach, outcome, params=params)

    def record_cycle(self, domain: str, approach: str, outcome: float,
                     cycle: int, di: float) -> str:
        """Record a pipeline cycle outcome."""
        return self._graph.record(
            domain, approach, outcome,
            params={"cycle": cycle, "di": di},
        )
