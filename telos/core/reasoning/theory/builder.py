"""TheoryBuilder — abstraction from experience."""
from __future__ import annotations
import time
import hashlib
import numpy as np
from typing import Dict, List, Optional, Any
from telos.core.reasoning.theory.dataclasses import *

class TheoryBuilder:
    """Builds abstract theories from concrete experiences.

    The pipeline:
    1. EXPERIENCE → Add new experience
    2. CLUSTER → Find similar experiences, form patterns
    3. HYPOTHESIZE → Generate hypotheses from patterns
    4. TEST → Test hypotheses against new experiences
    5. PROMOTE → Promote strong hypotheses to theories

    This is called periodically (every N cycles) and on-demand
    when the IntrospectionScheduler triggers reflection.
    """

    def __init__(self, min_experiences_for_pattern: int = 5,
                 min_patterns_for_hypothesis: int = 2,
                 min_tests_for_theory: int = 5,
                 theory_confidence_threshold: float = 0.8):
        self._experiences: Dict[str, Experience] = {}
        self._patterns: Dict[str, Pattern] = {}
        self._hypotheses: Dict[str, Hypothesis] = {}
        self._theories: Dict[str, Theory] = {}
        self._max_history = 1000

        self._min_experiences_for_pattern = min_experiences_for_pattern
        self._min_patterns_for_hypothesis = min_patterns_for_hypothesis
        self._min_tests_for_theory = min_tests_for_theory
        self._theory_confidence_threshold = theory_confidence_threshold

        # Tracks which experiences have been clustered
        self._indexed_experiences: Set[str] = set()

    def add_experience(self, context: Dict[str, Any],
                       action: str, outcome: float,
                       confidence: float = 0.8,
                       domain: str = "unknown") -> str:
        """Add a new experience to the builder."""
        eid = f"exp_{hashlib.md5(f'{context}{action}{time.time()}'.encode()).hexdigest()[:12]}"
        experience = Experience(
            id=eid,
            context=context,
            action=action,
            outcome=outcome,
            confidence=confidence,
            timestamp=time.time(),
            domain=domain,
        )
        self._experiences[eid] = experience
        if len(self._experiences) > self._max_history:
            # Remove oldest
            oldest = min(self._experiences.keys(),
                         key=lambda k: self._experiences[k].timestamp)
            del self._experiences[oldest]
            self._indexed_experiences.discard(oldest)

        logger.debug(f"TheoryBuilder: added experience {eid} ({domain}: {action} → {outcome:.2f})")
        return eid

    def cluster(self) -> List[Pattern]:
        """Cluster unindexed experiences into patterns.

        Uses simple feature similarity:
          - Same action + similar context + similar outcome
          - Groups of min_experiences_for_pattern or more form a pattern
        """
        unindexed = [
            e for eid, e in self._experiences.items()
            if eid not in self._indexed_experiences
        ]
        if len(unindexed) < self._min_experiences_for_pattern:
            return []

        new_patterns: List[Pattern] = []

        # Group by action
        by_action: Dict[str, List[Experience]] = defaultdict(list)
        for exp in unindexed:
            by_action[exp.action].append(exp)

        for action, exps in by_action.items():
            if len(exps) < self._min_experiences_for_pattern:
                continue

            # Compute average outcome
            avg_outcome = sum(e.outcome for e in exps) / len(exps)

            # Find common context features
            common: Dict[str, Any] = {}
            if exps:
                first_context = exps[0].context
                for key, val in first_context.items():
                    if all(e.context.get(key) == val for e in exps):
                        common[key] = val

            # Group by outcome similarity
            outcome_groups: Dict[str, List[Experience]] = defaultdict(list)
            for exp in exps:
                bucket = "high" if exp.outcome > 0.7 else ("low" if exp.outcome < 0.3 else "medium")
                outcome_groups[bucket].append(exp)

            for bucket, group in outcome_groups.items():
                if len(group) < self._min_experiences_for_pattern:
                    continue

                pid = f"pat_{hashlib.md5(f'{action}{bucket}{time.time()}'.encode()).hexdigest()[:10]}"
                pattern = Pattern(
                    id=pid,
                    name=f"{action}_{bucket}",
                    experiences=[e.id for e in group],
                    common_context=common,
                    avg_outcome=sum(e.outcome for e in group) / len(group),
                    confidence=min(0.5 + 0.05 * len(group), 0.95),
                    created=time.time(),
                    last_updated=time.time(),
                    support_count=len(group),
                )
                self._patterns[pid] = pattern
                new_patterns.append(pattern)

                for e in group:
                    self._indexed_experiences.add(e.id)

        if new_patterns:
            logger.info(
                f"TheoryBuilder: formed {len(new_patterns)} new patterns "
                f"(from {len(unindexed)} experiences)"
            )

        return new_patterns

    def hypothesize(self) -> List[Hypothesis]:
        """Generate hypotheses from patterns.

        For each pattern, generate a hypothesis:
        "In context C, action A leads to outcome O with probability P"
        """
        new_hypotheses: List[Hypothesis] = []

        for pid, pattern in self._patterns.items():
            # Check if this pattern already has a hypothesis
            already_covered = any(
                pid in h.supporting_patterns
                for h in self._hypotheses.values()
                if not h.falsified
            )
            if already_covered:
                continue

            # Only hypothesize from well-supported patterns
            if pattern.support_count < self._min_patterns_for_hypothesis:
                continue

            hid = f"hyp_{hashlib.md5(f'{pid}{time.time()}'.encode()).hexdigest()[:10]}"
            action = pattern.name.rsplit('_', 1)[0] if '_' in pattern.name else pattern.name

            hypothesis = Hypothesis(
                id=hid,
                description=f"In context matching {len(pattern.common_context)} features, "
                           f"action '{action}' leads to outcome {pattern.avg_outcome:.2f}",
                context_signature=pattern.common_context,
                action=action,
                predicted_outcome=pattern.avg_outcome,
                confidence=pattern.confidence * 0.8,
                supporting_patterns=[pid],
                created=time.time(),
            )
            self._hypotheses[hid] = hypothesis
            new_hypotheses.append(hypothesis)

        if new_hypotheses:
            logger.info(
                f"TheoryBuilder: generated {len(new_hypotheses)} new hypotheses"
            )

        return new_hypotheses

    def test_hypotheses(self, context: Dict[str, Any],
                        action: str, actual_outcome: float) -> List[Tuple[str, bool]]:
        """Test all active hypotheses against a new experience.

        Returns list of (hypothesis_id, survived) tuples.
        """
        results: List[Tuple[str, bool]] = []

        for hid, hypothesis in self._hypotheses.items():
            if hypothesis.falsified:
                continue

            # Check if context matches this hypothesis
            if not self._context_matches(hypothesis.context_signature, context):
                continue

            if hypothesis.action != action:
                continue

            survived = hypothesis.test(actual_outcome)
            results.append((hid, survived))

            log_msg = (
                f"TheoryBuilder: hypothesis '{hypothesis.description[:30]}...' "
                f"tested: survived={survived} "
                f"(confidence {hypothesis.confidence:.2f}, "
                f"passed={hypothesis.tests_passed}, failed={hypothesis.tests_failed})"
            )
            if survived:
                logger.debug(log_msg)
            else:
                logger.info(log_msg)

        return results

    def promote(self) -> List[Theory]:
        """Promote strong hypotheses to theories.

        A hypothesis is promoted when:
          - Confidence > theory_confidence_threshold
          - tests_passed >= min_tests_for_theory
          - Not falsified
        """
        new_theories: List[Theory] = []

        for hid, hypothesis in self._hypotheses.items():
            if hypothesis.falsified:
                continue
            if hypothesis.confidence < self._theory_confidence_threshold:
                continue
            if hypothesis.tests_passed < self._min_tests_for_theory:
                continue

            # Check if already promoted
            already_theory = any(
                t.hypothesis_id == hid for t in self._theories.values()
            )
            if already_theory:
                continue

            tid = f"thr_{hashlib.md5(hid.encode()).hexdigest()[:10]}"

            # Collect domains from supporting experiences
            domains: Set[str] = set()
            for pid in hypothesis.supporting_patterns:
                pattern = self._patterns.get(pid)
                if pattern:
                    for eid in pattern.experiences:
                        exp = self._experiences.get(eid)
                        if exp:
                            domains.add(exp.domain)

            theory = Theory(
                id=tid,
                name=f"Theory: {hypothesis.action} → {hypothesis.predicted_outcome:.2f}",
                description=hypothesis.description,
                hypothesis_id=hid,
                context_signature=hypothesis.context_signature,
                action=hypothesis.action,
                predicted_outcome=hypothesis.predicted_outcome,
                confidence=hypothesis.confidence,
                tests_passed=hypothesis.tests_passed,
                tests_failed=hypothesis.tests_failed,
                domains=list(domains),
                created=time.time(),
            )
            self._theories[tid] = theory
            new_theories.append(theory)

            logger.warning(
                f"TheoryBuilder: PROMOTED theory '{theory.name}' "
                f"(confidence={theory.confidence:.2f}, "
                f"tests={theory.tests_passed}/{theory.tests_passed + theory.tests_failed})"
            )

        return new_theories

    def build(self, context: Dict[str, Any], action: str,
              outcome: float, confidence: float = 0.8,
              domain: str = "unknown") -> Dict[str, Any]:
        """Full pipeline: add experience → cluster → hypothesize → test → promote.

        Returns a summary of what was built.
        """
        # 1. Add experience
        eid = self.add_experience(context, action, outcome, confidence, domain)

        # 2. Test active hypotheses (before clustering)
        test_results = self.test_hypotheses(context, action, outcome)

        # 3. Cluster into patterns
        new_patterns = self.cluster()

        # 4. Generate new hypotheses from patterns
        new_hypotheses = self.hypothesize()

        # 5. Promote strong hypotheses
        new_theories = self.promote()

        return {
            "experience_id": eid,
            "hypotheses_tested": len(test_results),
            "hypotheses_survived": sum(1 for _, s in test_results if s),
            "new_patterns": len(new_patterns),
            "new_hypotheses": len(new_hypotheses),
            "new_theories": len(new_theories),
        }

    def _context_matches(self, signature: Dict[str, Any],
                          context: Dict[str, Any]) -> bool:
        """Check if a context matches a pattern signature."""
        if not signature:
            return True
        for key, val in signature.items():
            if key not in context:
                return False
            if isinstance(val, (int, float)) and isinstance(context[key], (int, float)):
                if abs(val - context[key]) > 0.2 * abs(val + 1e-6):
                    return False
            elif context[key] != val:
                return False
        return True

    def estimate_theory_gain(self, context: Dict[str, Any],
                              action: str) -> float:
        """Estimate expected theory gain from taking an action.

        TG is high when:
        - There's no matching theory yet (novel context)
        - There are active hypotheses that could be confirmed
        - The system has many uncategorized patterns

        Returns float [0, 1].
        """
        n_theories = len(self._theories)
        n_hypotheses = len([h for h in self._hypotheses.values() if not h.falsified])
        n_patterns = len(self._patterns)

        # No abstraction yet → high potential gain
        if n_theories == 0 and n_hypotheses == 0 and n_patterns < 3:
            return 0.8  # fertile ground for new theories

        # Active hypotheses that could be tested
        hypothesis_ratio = n_hypotheses / max(n_hypotheses + n_theories, 1)

        # Unclustered patterns ready for abstraction
        pattern_potential = min(1.0, n_patterns / 10.0) if n_patterns > 2 else 0.0

        gain = hypothesis_ratio * 0.6 + pattern_potential * 0.4
        return min(1.0, gain)

    def get_active_theories(self) -> List[Theory]:
        return list(self._theories.values())

    def get_active_hypotheses(self) -> List[Hypothesis]:
        return [h for h in self._hypotheses.values() if not h.falsified]

    @property
    def total_experiences(self) -> int:
        return len(self._experiences)

    @property
    def total_patterns(self) -> int:
        return len(self._patterns)

    @property
    def total_hypotheses(self) -> int:
        return len(self._hypotheses)

    @property
    def total_theories(self) -> int:
        return len(self._theories)

    def to_dict(self) -> Dict:
        return {
            "total_experiences": self.total_experiences,
            "total_patterns": self.total_patterns,
            "total_hypotheses": self.total_hypotheses,
            "active_hypotheses": len(self.get_active_hypotheses()),
            "total_theories": self.total_theories,
            "theories": [
                {
                    "name": t.name,
                    "confidence": t.confidence,
                    "tests": f"{t.tests_passed}/{t.tests_passed + t.tests_failed}",
                    "domains": t.domains,
                }
                for t in self._theories.values()
            ],
        }
