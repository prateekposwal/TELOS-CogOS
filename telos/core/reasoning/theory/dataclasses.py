"""
TheoryBuilder — Experience → Cluster → Hypothesis → Test → Theory.

Prateek's insight #7: "Theory Builder — experience → cluster → hypothesis →
test → promote to theory. Abstraction."

The system currently stores experiences (ExperienceManager) and skills
(SkillLibrary) but never abstracts from them. The TheoryBuilder:
  1. Clusters similar experiences into patterns
  2. Generates hypotheses from patterns ("when X happens, Y follows")
  3. Tests hypotheses against new experiences (falsification)
  4. Promotes confirmed hypotheses to "theories" (high-confidence abstractions)
  5. Uses theories to make predictions and guide decisions

A theory is a falsifiable generalization: "in context C, action A
leads to outcome O with probability P."

Architecture:
  - TheoryBuilder maintains a hierarchy: Experiences → Patterns → Hypotheses → Theories
  - Each level has confidence scores
  - Confirmation strengthens; falsification weakens or discards
  - Theories can be cross-domain (abstract patterns that span domains)
"""

from __future__ import annotations

import logging
import time
import hashlib
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger('telos_theory_builder')


class AbstractionLevel(Enum):
    EXPERIENCE = "experience"      # Raw observation
    PATTERN = "pattern"            # Clustered experiences
    HYPOTHESIS = "hypothesis"      # Falsifiable claim
    THEORY = "theory"              # High-confidence abstraction


@dataclass
class Experience:
    """A single observed experience."""
    id: str
    context: Dict[str, Any]  # state features, domain, goals
    action: str
    outcome: float  # 0-1 success score
    confidence: float  # 0-1 observation confidence
    timestamp: float
    domain: str = "unknown"


@dataclass
class Pattern:
    """A cluster of similar experiences."""
    id: str
    name: str
    experiences: List[str]  # experience IDs
    common_context: Dict[str, Any]  # shared features
    avg_outcome: float
    confidence: float
    created: float
    last_updated: float
    support_count: int  # number of experiences supporting


@dataclass
class Hypothesis:
    """A falsifiable claim derived from patterns.

    Format: "In context C, action A leads to outcome O with probability P"
    """
    id: str
    description: str
    context_signature: Dict[str, Any]  # defining features
    action: str
    predicted_outcome: float
    confidence: float
    supporting_patterns: List[str]  # pattern IDs
    tests_passed: int = 0
    tests_failed: int = 0
    created: float = 0.0
    falsified: bool = False
    parent_theory_id: Optional[str] = None

    @property
    def test_ratio(self) -> float:
        total = self.tests_passed + self.tests_failed
        if total == 0:
            return 0.0
        return self.tests_passed / total

    def test(self, actual_outcome: float, tolerance: float = 0.2) -> bool:
        """Test the hypothesis against an actual outcome.

        Returns True if hypothesis survives (within tolerance).
        Args:
            actual_outcome: the actual_outcome argument for this call.
        """
        error = abs(self.predicted_outcome - actual_outcome)
        survived = error <= tolerance
        if survived:
            self.tests_passed += 1
            self.confidence = min(1.0, self.confidence + 0.1)
        else:
            self.tests_failed += 1
            self.confidence = max(0.0, self.confidence - 0.2)
            if self.confidence < 0.1:
                self.falsified = True
        return survived


@dataclass
class Theory:
    """A high-confidence, well-tested abstraction.

    A theory is a hypothesis that has survived multiple tests
    and has high confidence. It can be used for prediction.
    """
    id: str
    name: str
    description: str
    hypothesis_id: str
    context_signature: Dict[str, Any]
    action: str
    predicted_outcome: float
    confidence: float
    tests_passed: int
    tests_failed: int
    domains: List[str]  # which domains this theory applies to
    created: float
    promoted_from: AbstractionLevel = AbstractionLevel.HYPOTHESIS
    parent_theory_id: Optional[str] = None
