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

from __future__ import annotations

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


class ExplanationCompression:
    """Compresses many explanation instances into compact, general rules.

    The compression engine:
    1. Receives explanation instances from the pipeline
    2. Clusters instances by similarity (cause + mechanism + context)
    3. Generates candidate rules from clusters
    4. Evaluates rules: coverage, accuracy, parsimony
    5. Selects the best rules (high coverage + high accuracy + simple)
    6. Retires old rules when better ones emerge

    This is the engine of EXPERTISE: the ability to replace
    10,000 special cases with one general principle.
    """

    def __init__(self, min_instances_per_rule: int = 5,
                 max_rules: int = 50,
                 coverage_threshold: float = 0.1,
                 retirement_threshold: float = 0.05):
        self._min_instances = min_instances_per_rule
        self._max_rules = max_rules
        self._coverage_threshold = coverage_threshold  # Min coverage to keep a rule
        self._retirement_threshold = retirement_threshold

        # Storage
        self._instances: Dict[str, ExplanationInstance] = {}
        self._rules: Dict[str, CompressedRule] = {}
        self._instance_to_rule: Dict[str, str] = {}  # instance_id -> rule_id

        # Compression history
        self._compression_log: List[Dict] = []
        self._max_log = 100
        self._total_compressions: int = 0

    def add_instance(self, phenomenon: str, cause: str,
                      mechanism: str,
                      context: Optional[Dict] = None,
                      confidence: float = 0.5,
                      source: str = "pipeline") -> str:
        """Add an explanation instance for compression.

        Args:
            phenomenon: What is being explained
            cause: Why it happened
            mechanism: How cause led to effect
            context: Surrounding state
            confidence: Confidence in this explanation
            source: Origin

        Returns:
            instance_id
        """
        instance_id = f"exp_{int(time.time()*1000)}_{len(self._instances)}"
        instance = ExplanationInstance(
            id=instance_id,
            phenomenon=phenomenon,
            cause=cause,
            mechanism=mechanism,
            context=context or {},
            confidence=confidence,
            source=source,
        )
        self._instances[instance_id] = instance

        # Try to match to existing rule
        matched_rule = self._find_matching_rule(instance)
        if matched_rule:
            matched_rule.instances_explained.append(instance_id)
            matched_rule.coverage_count = len(matched_rule.instances_explained)
            matched_rule.last_used = time.time()
            self._instance_to_rule[instance_id] = matched_rule.id
        else:
            # Check if we have enough similar instances to form a new rule
            self._try_form_rule(instance)

        return instance_id

    def _find_matching_rule(self, instance: ExplanationInstance) -> Optional[CompressedRule]:
        """Find an existing rule that matches this instance."""
        best_match: Optional[CompressedRule] = None
        best_score = 0.0

        for rule in self._rules.values():
            if rule.status == RuleStatus.RETIRED:
                continue

            # Compute match score based on phenomenon and cause similarity
            score = self._compute_match(rule, instance)
            if score > best_score:
                best_score = score
                best_match = rule

        # Only accept if score is high enough
        if best_score >= 0.5:
            return best_match
        return None

    def _compute_match(self, rule: CompressedRule,
                        instance: ExplanationInstance) -> float:
        """Compute how well a rule matches an instance.

        Uses shared keywords between the rule's pattern and the instance.
        In production, this would use embedding similarity.
        """
        rule_words = set(rule.condition_pattern.lower().split())
        instance_words = set(
            f"{instance.phenomenon} {instance.cause} {instance.mechanism}".lower().split()
        )

        if not rule_words or not instance_words:
            return 0.0

        intersection = rule_words & instance_words
        union = rule_words | instance_words
        jaccard = len(intersection) / max(len(union), 1)

        # Boost if this rule has explained similar instances before
        if rule.instances_explained:
            prev_instances = [self._instances.get(iid) for iid in rule.instances_explained[:10]]
            prev_causes = {i.cause for i in prev_instances if i}
            if instance.cause in prev_causes:
                jaccard += 0.2

        return min(1.0, jaccard)

    def _try_form_rule(self, seed_instance: ExplanationInstance) -> None:
        """Check if enough similar instances exist to form a rule."""
        # Find all instances similar to the seed
        similar: List[ExplanationInstance] = []
        for inst in self._instances.values():
            if inst.id == seed_instance.id:
                continue
            if self._instances_similar(seed_instance, inst):
                similar.append(inst)

        # Need at least min_instances
        if len(similar) < self._min_instances - 1:
            return

        # Include the seed
        all_instances = similar + [seed_instance]

        # Extract common pattern
        pattern = self._extract_condition_pattern(all_instances)
        template = self._extract_explanation_template(all_instances)

        if not pattern or not template:
            return

        # Check if this pattern is already covered
        for rule in self._rules.values():
            if rule.status == RuleStatus.RETIRED:
                continue
            if self._pattern_similar(rule.condition_pattern, pattern):
                # Merge into existing rule
                for inst in all_instances:
                    if inst.id not in rule.instances_explained:
                        rule.instances_explained.append(inst.id)
                        self._instance_to_rule[inst.id] = rule.id
                rule.coverage_count = len(rule.instances_explained)
                rule.last_used = time.time()
                # Update accuracy
                rule.accuracy = min(1.0, rule.accuracy + 0.02)
                return

        # Create new rule
        rule_id = f"rule_{int(time.time()*1000)}_{len(self._rules)}"
        instance_ids = [inst.id for inst in all_instances]

        rule = CompressedRule(
            id=rule_id,
            description=f"Rule covering {len(instance_ids)} instances: {pattern[:40]}...",
            condition_pattern=pattern,
            explanation_template=template,
            instances_explained=instance_ids,
            coverage_count=len(instance_ids),
            accuracy=0.7,  # Initial estimate
            parsimony=self._compute_parsimony(pattern),
            status=RuleStatus.FORMING,
        )
        self._rules[rule_id] = rule

        for iid in instance_ids:
            self._instance_to_rule[iid] = rule_id

        # Activate rule if it passes thresholds
        if rule.coverage_count >= self._min_instances:
            rule.status = RuleStatus.ACTIVE

        logger.info(
            f"ExplanationCompression: formed new rule '{rule_id}' "
            f"covering {rule.coverage_count} instances "
            f"(parsimony={rule.parsimony:.2f})"
        )

    def _instances_similar(self, a: ExplanationInstance,
                            b: ExplanationInstance) -> bool:
        """Check if two instances are similar enough to cluster."""
        a_words = set(f"{a.phenomenon} {a.cause}".lower().split())
        b_words = set(f"{b.phenomenon} {b.cause}".lower().split())
        if not a_words or not b_words:
            return False
        jaccard = len(a_words & b_words) / len(a_words | b_words)
        return jaccard > 0.3

    def _pattern_similar(self, pattern_a: str, pattern_b: str) -> bool:
        """Check if two condition patterns are semantically similar."""
        words_a = set(pattern_a.lower().split())
        words_b = set(pattern_b.lower().split())
        if not words_a or not words_b:
            return False
        jaccard = len(words_a & words_b) / len(words_a | words_b)
        return jaccard > 0.3

    def _extract_condition_pattern(self,
                                    instances: List[ExplanationInstance]) -> str:
        """Extract the common condition pattern from a set of instances."""
        if not instances:
            return ""
        # Find common words across phenomena and causes
        all_words = []
        for inst in instances:
            all_words.append(set(f"{inst.phenomenon} {inst.cause}".lower().split()))

        common = all_words[0]
        for ws in all_words[1:]:
            common = common & ws

        return " ".join(sorted(common)) if common else instances[0].phenomenon[:30]

    def _extract_explanation_template(self,
                                       instances: List[ExplanationInstance]) -> str:
        """Extract a generalized explanation template."""
        if not instances:
            return ""
        # Generalize: replace specific values with placeholders
        template = instances[0].mechanism
        # In production: use LLM to generalize
        return f"When pattern matches: {template[:50]}..."

    def _compute_parsimony(self, pattern: str) -> float:
        """Compute parsimony (simplicity) score. Shorter patterns = more parsimonious."""
        if not pattern:
            return 0.5
        word_count = len(pattern.split())
        # Ideal: 3-10 words
        if word_count <= 3:
            return 0.9
        elif word_count <= 10:
            return 1.0 - (word_count - 3) * 0.05
        else:
            return max(0.1, 0.65 - (word_count - 10) * 0.02)

    def compress(self) -> CompressionMetrics:
        """Run a full compression cycle: evaluate rules, retire weak ones.

        Returns:
            CompressionMetrics describing the state of the compression
        """
        # Evaluate rule quality
        active_rules = [r for r in self._rules.values() if r.status != RuleStatus.RETIRED]
        total_instances = len(self._instances)

        for rule in active_rules:
            # Update accuracy: what fraction of covered instances are well-explained?
            covered = [self._instances.get(iid) for iid in rule.instances_explained]
            covered = [i for i in covered if i]
            if covered:
                correct = sum(1 for i in covered if i.confidence > 0.5)
                rule.accuracy = correct / len(covered)

            # Update parsimony
            rule.parsimony = self._compute_parsimony(rule.condition_pattern)

            # Update status
            if rule.coverage_count >= self._min_instances:
                rule.status = RuleStatus.ACTIVE
            elif rule.status == RuleStatus.ACTIVE:
                rule.status = RuleStatus.REFINING

        # Retire low-performing rules
        to_retire = []
        for rule in active_rules:
            coverage_ratio = rule.coverage_count / max(total_instances, 1)
            if coverage_ratio < self._retirement_threshold and rule.coverage_count < self._min_instances * 2:
                to_retire.append(rule.id)

        for rid in to_retire:
            if rid in self._rules:
                self._rules[rid].status = RuleStatus.RETIRED
                logger.info(f"ExplanationCompression: retired rule '{rid}' — coverage too low")

        # Enforce max rules
        if len(self._rules) > self._max_rules:
            active = [(rid, r) for rid, r in self._rules.items() if r.status != RuleStatus.RETIRED]
            active.sort(key=lambda x: x[1].compression_score)
            # Retire lowest-scoring
            to_remove = active[:len(active) - self._max_rules]
            for rid, _ in to_remove:
                self._rules[rid].status = RuleStatus.RETIRED
                logger.info(f"ExplanationCompression: retired rule '{rid}' — max rules exceeded")

        # Compute metrics
        top_rules = sorted(
            [r for r in self._rules.values() if r.status != RuleStatus.RETIRED],
            key=lambda r: r.compression_score,
            reverse=True,
        )
        top_1_coverage = top_rules[0].coverage_count / max(total_instances, 1) if top_rules else 0.0
        top_3_coverage = sum(
            r.coverage_count for r in top_rules[:3]
        ) / max(total_instances, 1) if top_rules else 0.0

        active_accurate = [r for r in top_rules if r.status == RuleStatus.ACTIVE]
        avg_accuracy = np.mean([r.accuracy for r in active_accurate]) if active_accurate else 0.0
        avg_parsimony = np.mean([r.parsimony for r in active_accurate]) if active_accurate else 0.0

        metrics = CompressionMetrics(
            total_instances=total_instances,
            total_rules=len([r for r in self._rules.values() if r.status != RuleStatus.RETIRED]),
            compression_ratio=total_instances / max(len(active_accurate), 1),
            top_rule_coverage=top_1_coverage,
            top_3_coverage=top_3_coverage,
            average_accuracy=avg_accuracy,
            average_parsimony=avg_parsimony,
        )

        self._total_compressions += 1
        self._compression_log.append({
            "cycle": self._total_compressions,
            "total_instances": total_instances,
            "active_rules": metrics.total_rules,
            "compression_ratio": round(metrics.compression_ratio, 1),
            "top_1_coverage": round(top_1_coverage, 3),
            "retired": len(to_retire),
        })
        if len(self._compression_log) > self._max_log:
            self._compression_log.pop(0)

        logger.info(
            f"ExplanationCompression: compress cycle #{self._total_compressions} — "
            f"{total_instances} instances → {metrics.total_rules} active rules "
            f"(ratio={metrics.compression_ratio:.1f}x, top1={top_1_coverage:.1%})"
        )

        return metrics

    def explain(self, phenomenon: str, cause: str,
                 context: Optional[Dict] = None) -> Dict:
        """Try to explain a phenomenon using compressed rules.

        Returns the best matching rule's explanation, or None.
        """
        # Create a temporary instance for matching
        temp = ExplanationInstance(
            id="_temp",
            phenomenon=phenomenon,
            cause=cause,
            mechanism="",
            context=context or {},
            confidence=0.0,
            source="query",
        )

        best_rule = self._find_matching_rule(temp)
        if best_rule:
            return {
                "explained_by_rule": best_rule.id,
                "rule_description": best_rule.description,
                "explanation": best_rule.explanation_template,
                "coverage": best_rule.coverage_count,
                "accuracy": round(best_rule.accuracy, 3),
                "parsimony": round(best_rule.parsimony, 3),
                "compressed": True,
            }
        else:
            return {
                "explained_by_rule": None,
                "compressed": False,
                "message": "No matching rule found. Add as new instance.",
            }

    def get_top_rules(self, top_n: int = 10) -> List[CompressedRule]:
        """Get the highest-scoring active rules."""
        active = [
            r for r in self._rules.values()
            if r.status in (RuleStatus.ACTIVE, RuleStatus.REFINING)
        ]
        active.sort(key=lambda r: r.compression_score, reverse=True)
        return active[:top_n]

    @property
    def compression_ratio(self) -> float:
        total = len(self._instances)
        active = len([r for r in self._rules.values() if r.status in (RuleStatus.ACTIVE, RuleStatus.REFINING)])
        return total / max(active, 1)

    def to_dict(self) -> Dict:
        top_rules = self.get_top_rules(10)
        return {
            "total_instances": len(self._instances),
            "total_rules": {
                "active": len([r for r in self._rules.values() if r.status == RuleStatus.ACTIVE]),
                "forming": len([r for r in self._rules.values() if r.status == RuleStatus.FORMING]),
                "refining": len([r for r in self._rules.values() if r.status == RuleStatus.REFINING]),
                "retired": len([r for r in self._rules.values() if r.status == RuleStatus.RETIRED]),
            },
            "compression_ratio": round(self.compression_ratio, 1),
            "top_rules": [
                {
                    "id": r.id[:16],
                    "description": r.description[:60],
                    "coverage": r.coverage_count,
                    "accuracy": round(r.accuracy, 3),
                    "parsimony": round(r.parsimony, 3),
                    "compression_score": round(r.compression_score, 3),
                    "status": r.status.value,
                }
                for r in top_rules
            ],
            "top_1_coverage": round(
                top_rules[0].coverage_count / max(len(self._instances), 1), 3
            ) if top_rules else 0.0,
            "compression_history": self._compression_log[-10:],
        }
