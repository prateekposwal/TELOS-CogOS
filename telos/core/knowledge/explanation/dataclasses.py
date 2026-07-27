"""Explanation compression dataclasses."""
from __future__ import annotations
"""
ExplanationCompression — Store One Rule That Explains 9,200 Out of 10,000 Problems.

Prateek's insight: "Explanation compression — store one rule that explains
9,200 out of 10,000 problems instead of 10,000 traces. Expertise is compression."

Most systems store every explanation trace. This module compresses many
individual explanations into a single compact rule that covers most cases.
Expertise IS compression: the ability to replace 10,000 special cases with
one general principle.

Key insight: If 9,200 out of 10,000 problems are explained by the same rule,
storing 9,200 traces is wasteful. Store the rule with its coverage statistics.

Architecture:
  - Explanation: a single instance of "why X happened" (what/why/how)
  - Rule: a compressed explanation that covers many instances
  - Coverage: what fraction of explanations does this rule explain?
  - Compression: merging overlapping explanations into generalized rules
  - Rule Lifecycle: formation → coverage expansion → refinement → retirement

Compression types:
  1. COVERAGE: One rule explains many instances (breadth)
  2. DEPTH: Rule explains instances more precisely (accuracy)
  3. HIERARCHY: Rules organized by specificity (general→specific)

Metrics:
  - Compression Ratio: instances / rules
  - Coverage: fraction of all instances explained by top-K rules
  - Accuracy: how well rules predict explanation features
  - Parsimony: Occam's razor — simpler rules preferred
"""


import logging
import time
import math
import hashlib
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Set, Callable
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger('telos_explanation_compression')


class RuleStatus(Enum):
    FORMING = "forming"              # Being constructed from examples
    ACTIVE = "active"                # Currently used for explanations
    REFINING = "refining"            # Being updated with new examples
    RETIRED = "retired"              # Superseded by better rule


@dataclass
class ExplanationInstance:
    """A single explanation of why something happened."""
    id: str
    phenomenon: str                  # What is being explained
    cause: str                       # Why it happened
    mechanism: str                   # How the cause led to the effect
    context: Dict[str, Any]          # Surrounding state
    confidence: float                # How confident is this explanation
    source: str                      # Where this explanation came from
    timestamp: float = field(default_factory=time.time)


@dataclass
class CompressedRule:
    """A compressed explanation rule that covers many instances."""
    id: str
    description: str                 # Human-readable statement of the rule
    condition_pattern: str           # Pattern that triggers this rule
    explanation_template: str        # Template for generating explanations
    instances_explained: List[str]   # IDs of instances this rule covers
    coverage_count: int              # How many instances this rule explains
    accuracy: float                  # Fraction of covered instances correctly explained
    parsimony: float                 # Simplicity score [0-1]
    status: RuleStatus
    first_formed: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    times_applied: int = 0

    @property
    def coverage_ratio(self) -> float:
        """Coverage as fraction of total instances."""
        # Computed externally, stored here for convenience
        return 0.0

    @property
    def compression_score(self) -> float:
        """How good is this rule? Balances coverage, accuracy, and parsimony."""
        return (self.coverage_count * 0.4 +
                self.accuracy * 0.3 +
                self.parsimony * 0.3)


@dataclass
class CompressionMetrics:
    """Overall compression metrics for the explanation store."""
    total_instances: int
    total_rules: int
    compression_ratio: float
    top_rule_coverage: float         # Coverage of the single best rule
    top_3_coverage: float            # Coverage of top 3 rules
    average_accuracy: float
    average_parsimony: float
