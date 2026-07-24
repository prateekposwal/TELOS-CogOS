"""
Knowledge — Spiderweb Memory of Proven Solutions.

Neutral layer. Zero dependencies on Pipeline, Agents, or InfraManager.
Any component can import and use this directly.

Architecture:
  graph.py       → KnowledgeGraph (domain → {successes, failures})
  recommender.py → recommend(domain) → best approach
  recorder.py    → record_outcome / record_failure with context
"""

from telos.core.knowledge.graph import KnowledgeGraph, ProjectNode
from telos.core.knowledge.recommender import KnowledgeRecommender
from telos.core.knowledge.recorder import OutcomeRecorder

__all__ = [
    "KnowledgeGraph", "ProjectNode",
    "KnowledgeRecommender",
    "OutcomeRecorder",
]
