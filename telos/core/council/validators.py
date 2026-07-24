"""
Concrete Council Validators — Truth-Anchored Advisors

Each validator is a specialized cognitive process that performs one
kind of truth-check. They are NOT agents — they have no goals, no
autonomy, and no ability to act. They only output ValidationSignals.

If any validator returns passed=False, the Council blocks the
Decision Integrator from acting. This is how TELOS ensures
Epistemic Integrity: the system refuses to pursue a mission
when reality contradicts it.
"""

from __future__ import annotations

import numpy as np
import logging
from typing import Optional, Any, List, TYPE_CHECKING

from telos.core.council.base import Validator, ValidationSignal

if TYPE_CHECKING:
    from telos.core.infra_manager.failure_ledger import FailureLedger
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR
from telos.core.ledger.skill_library import SkillLibrary

logger = logging.getLogger('telos_council_validators')


class RealityValidator(Validator):
    """Verifies the planned action aligns with observed physics/data.

    Checks:
    1. Does the intent match what the PerceptionStream observed?
    2. Is the proposed action within plausible physical bounds?
    3. Is there a mismatch between the World state and the intent's
       assumed state (e.g., acting on a hallucinated entity)?

    This is the first line of defense against "wishful reasoning":
    if the system plans to fly but physics says it can't, this
    validator blocks.
    """

    @property
    def name(self) -> str:
        return "RealityValidator"

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 omega_vector: Optional[dict] = None) -> ValidationSignal:
        # If omega_vector has high Ω_O, widen drift tolerance during investigation
        drift_tolerance_mult = 1.0
        if omega_vector and omega_vector.get('other', 0) > 0.3:
            drift_tolerance_mult = 1.0 + 0.2 * omega_vector.get('other', 0.5)
        if intent is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no intent to validate", evidence_weight=0.0,
            )

        issues: List[str] = []
        nans = int(np.isnan(world.state).sum())
        if nans > 0:
            issues.append(f"state contains {nans} NaN values")

        infs = int(np.isinf(world.state).sum())
        if infs > 0:
            issues.append(f"state contains {infs} Inf values")

        action = intent.params.get("action_vector",
                                   intent.target if hasattr(intent, 'target') else None)
        if action is not None and isinstance(action, np.ndarray):
            if np.isnan(action).any():
                issues.append("proposed action contains NaN")
            if np.linalg.norm(action) > 100.0:
                issues.append(f"proposed action norm {np.linalg.norm(action):.1f} exceeds 100")

        if domain_facts is not None and isinstance(domain_facts, DomainFacts):
            if "bounds" in domain_facts.constraints:
                issues.append("domain reports out-of-bounds state")

        if issues:
            evidence_weight = min(1.0, 0.3 + 0.2 * len(issues))
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.8,
                reason=" | ".join(issues),
                evidence_weight=evidence_weight,
                metadata={"issue_count": len(issues), "issues": issues},
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.9,
            reason="state and action are physically plausible",
            evidence_weight=0.3,
        )


class ConstraintValidator(Validator):
    """Verifies the planned action does not violate system constraints.

    Checks:
    1. Are there domain-specific constraints that block this action?
    2. Does the action respect safety thresholds?
    3. Does the action respect ethical boundaries (if defined)?

    This is the system's "conscience" — it enforces the rules
    that cannot be broken even for mission success.
    """

    @property
    def name(self) -> str:
        return "ConstraintValidator"

    def _check_action_against_constraints(
        self, world: World, intent: IntentIR, constraints: List[str]
    ) -> List[str]:
        violations = []
        action = intent.params.get("action_vector") if intent.params else None
        if action is None:
            return violations
        for c in constraints:
            if c.startswith("_"):
                continue
            next_state = world.state + action
            geometry_keywords = ("boundary", "bounds", "world_bounds", "wall")
            if any(kw in c.lower() for kw in geometry_keywords):
                if np.any(next_state < 0):
                    violations.append(f"domain constraint: {c} (action moves out of bounds)")
            elif "speed" in c.lower() or "velocity" in c.lower():
                speed = float(np.linalg.norm(action))
                limit = float(c.split("=")[-1]) if "=" in c else float("inf")
                if speed > limit:
                    violations.append(f"domain constraint: {c} (speed {speed:.2f} > limit {limit})")
            elif "energy" in c.lower() or "resource" in c.lower():
                violations.append(f"domain constraint: {c}")
        return violations

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 omega_vector: Optional[dict] = None) -> ValidationSignal:
        # If omega_vector has high Ω_O, widen drift tolerance during investigation
        drift_tolerance_mult = 1.0
        if omega_vector and omega_vector.get('other', 0) > 0.3:
            drift_tolerance_mult = 1.0 + 0.2 * omega_vector.get('other', 0.5)
        if intent is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no intent to validate", evidence_weight=0.0,
            )

        violations: List[str] = []

        if world.safety_score < 0.3:
            violations.append(f"safety score {world.safety_score:.2f} below 0.3 threshold")

        if domain_facts is not None and isinstance(domain_facts, DomainFacts):
            if domain_facts.constraints:
                violations.extend(
                    self._check_action_against_constraints(world, intent, domain_facts.constraints)
                )

        if violations:
            evidence_weight = min(1.0, 0.4 + 0.2 * len(violations))
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.9,
                reason=" | ".join(violations),
                evidence_weight=evidence_weight,
                metadata={"violations": violations},
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.95,
            reason="all constraints satisfied",
            evidence_weight=0.2,
        )


class MemoryAdvisor(Validator):
    """Checks that the planned action does not contradict historical fact.

    Queries the SkillLibrary for prior outcomes of similar situations,
    the FailureLedger for past structural failures (Kintsugi),
    and the KnowledgeGraph for proven/failed approaches.
    """

    def __init__(self, skill_library: SkillLibrary,
                 failure_ledger: Optional['FailureLedger'] = None,
                 knowledge_graph: Optional[Any] = None):
        self.skill_library = skill_library
        self.failure_ledger = failure_ledger
        self.knowledge_graph = knowledge_graph

    def connect(self, failure_ledger=None, knowledge_graph=None):
        self.failure_ledger = failure_ledger or self.failure_ledger
        self.knowledge_graph = knowledge_graph or self.knowledge_graph
        return self

    @property
    def name(self) -> str:
        return "MemoryAdvisor"

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 omega_vector: Optional[dict] = None) -> ValidationSignal:
        # If omega_vector has high Ω_O (other-uncertainty), lower evidence threshold
        # to be more tolerant during uncertainty investigation
        evidence_tolerance = 1.0
        if omega_vector and omega_vector.get('other', 0) > 0.3:
            evidence_tolerance = 1.0 - 0.3 * omega_vector.get('other', 0.5)
        if intent is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no intent to validate", evidence_weight=0.0,
            )

        relevant = self.skill_library.find_relevant_skills(world.state, threshold=0.3)

        # ── Kintsugi check: query FailureLedger for matching root causes ──
        kintsugi_signals = []
        action_str = None
        if intent is not None and intent.params:
            action_str = str(intent.params.get("action_vector", ""))
        if self.failure_ledger is not None:
            recent = self.failure_ledger.get_recent_failures(n=20)
            for i, f in enumerate(recent):
                if f.root_cause in ("governance_intervention", "simulation_divergence"):
                    continue
                blocked_tokens = set(
                    token.strip().lower()
                    for token in f.blocked_by.replace(",", " ").split()
                ) if f.blocked_by else set()
                if intent.intent_type in blocked_tokens:
                    recency = (i + 1) / max(len(recent), 1)
                    kintsugi_signals.append((f, recency))
                if f.affected_entities:
                    for depth in world.metadata.get("semantic_depths", []):
                        eid = getattr(depth, 'entity_id', None)
                        for ae in f.affected_entities:
                            if isinstance(ae, dict) and ae.get("entity_id") == eid:
                                recency = (i + 1) / max(len(recent), 1)
                                kintsugi_signals.append((f, recency))
                # Check pattern_exploit failures against current move
                if f.failure_type == "pattern_exploit" and action_str is not None:
                    blocked_move = f.blocked_by or ""
                    if blocked_move.lower() in action_str.lower():
                        recency = (i + 1) / max(len(recent), 1)
                        kintsugi_signals.append((f, recency))

        if kintsugi_signals:
            worst_failure, recency = max(kintsugi_signals, key=lambda x: x[0].severity)
            confidence = -0.2 - 0.8 * recency
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=confidence,
                reason=f"Kintsugi: past failure #{worst_failure.failure_id[:8]} "
                       f"(type={worst_failure.failure_type}, severity={worst_failure.severity:.2f}) "
                       f"matches current context — structural barrier prevents action",
                evidence_weight=min(0.9, (worst_failure.severity + 0.2) * evidence_tolerance),
                metadata={
                    "kintsugi_match_count": len(kintsugi_signals),
                    "worst_failure_id": worst_failure.failure_id,
                    "worst_failure_type": worst_failure.failure_type,
                    "recency": round(recency, 3),
                    "kintsugi_confidence": round(confidence, 3),
                },
            )

        # ── Knowledge Graph check: does a proven solution exist? ──
        if self.knowledge_graph is not None:
            domain = getattr(world, 'domain', 'unknown')
            proven = self.knowledge_graph.search(domain, top_k=3, min_outcome=0.51)
            failed = self.knowledge_graph.search_failures(domain, top_k=3)
            if intent is not None and intent.params:
                current_approach = intent.intent_type or "unknown"
                for fnode in failed:
                    if fnode.approach == current_approach:
                        return ValidationSignal(
                            validator_name=self.name,
                            passed=False,
                            confidence=-0.6,
                            reason=f"KnowledgeGraph: approach '{current_approach}' failed "
                                   f"previously in domain '{domain}' (outcome={fnode.outcome:.2f}) "
                                   f"— {fnode.failure_reason or 'no reason recorded'}",
                            evidence_weight=0.7,
                            metadata={
                                "failed_node": fnode.node_id,
                                "proven_alternatives": [n.approach for n in proven],
                            },
                        )
            if proven and intent is not None:
                best = proven[0]
                self.knowledge_graph.activate(best.node_id)
                if best.outcome > 0.85:
                    return ValidationSignal(
                        validator_name=self.name,
                        passed=True,
                        confidence=0.8,
                        reason=f"KnowledgeGraph: proven solution '{best.approach}' "
                               f"scored {best.outcome:.2f} in domain '{domain}'",
                        evidence_weight=0.3,
                        metadata={"proven_approach": best.approach, "proven_outcome": best.outcome},
                    )

        if not relevant:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.5,
                reason="no contradictory historical evidence",
                evidence_weight=0.1 * evidence_tolerance,
            )

        worst = min(relevant, key=lambda s: s.utility_score)
        if worst.utility_score < 0.3:
            evidence_weight = min(0.8, (0.3 + 0.2 * (1.0 - worst.utility_score)) * evidence_tolerance)
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.7,
                reason=f"historical skill {worst.skill_id} had utility {worst.utility_score:.2f} "
                       f"— similar situation previously failed",
                evidence_weight=evidence_weight,
                metadata={
                    "worst_skill_id": worst.skill_id,
                    "worst_utility": worst.utility_score,
                    "match_count": len(relevant),
                },
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.6,
            reason=f"historical precedents are positive (best utility={worst.utility_score:.2f})",
            evidence_weight=0.1,
        )


class MissionDriftDetector(Validator):
    """Checks whether the planned action actually achieves the mission.

    This is NOT a goal-check (does the mission want X?). It is a
    reality-check (will this trajectory actually produce mission-X?).

    If the CounterfactualEngine predicts state Y but the mission
    requires state X, this detector flags the divergence. The system
    may still proceed if it has high confidence, but the drift is
    recorded for the audit trail.

    Unlike other validators, this one tracks cumulative drift over
    time. A single high-drift cycle is a warning; sustained high
    drift triggers a block.

    Cumulative drift is maintained as a sliding window of the last
    100 observations to prevent unbounded growth (P2.6 fix).
    """

    _MAX_DRIFT_WINDOW = 100

    def __init__(self, drift_threshold: float = 5.0,
                 cumulative_threshold: float = 10.0):
        self.drift_threshold = drift_threshold
        self.cumulative_threshold = cumulative_threshold
        self._drift_history: List[float] = []

    @property
    def name(self) -> str:
        return "MissionDriftDetector"

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 omega_vector: Optional[dict] = None) -> ValidationSignal:
        # If omega_vector has high Ω_O, widen drift tolerance during investigation
        drift_tolerance_mult = 1.0
        if omega_vector and omega_vector.get('other', 0) > 0.3:
            drift_tolerance_mult = 1.0 + 0.2 * omega_vector.get('other', 0.5)
        if intent is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no intent to validate", evidence_weight=0.0,
            )

        predicted = None
        if intent.params and "trajectory" in intent.params:
            traj = intent.params["trajectory"]
            predicted = getattr(traj, 'state', None)

        observed = world.state
        if predicted is not None and observed is not None:
            drift = float(np.linalg.norm(predicted - observed))
        else:
            drift = 0.0

        self._drift_history.append(drift)
        if len(self._drift_history) > self._MAX_DRIFT_WINDOW:
            self._drift_history = self._drift_history[-self._MAX_DRIFT_WINDOW:]

        cumulative_drift = sum(self._drift_history)

        evidence_weight = min(0.9, drift / self.drift_threshold)

        if drift > self.drift_threshold * drift_tolerance_mult:
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.8,
                reason=f"instantaneous drift {drift:.2f} exceeds threshold {self.drift_threshold * drift_tolerance_mult:.2f}",
                evidence_weight=evidence_weight,
                metadata={
                    "instantaneous_drift": drift,
                    "cumulative_drift": cumulative_drift,
                    "threshold": self.drift_threshold,
                },
            )

        if cumulative_drift > self.cumulative_threshold * drift_tolerance_mult:
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.6,
                reason=f"cumulative drift {cumulative_drift:.2f} exceeds "
                       f"threshold {self.cumulative_threshold * drift_tolerance_mult:.2f}",
                evidence_weight=min(0.9, cumulative_drift / self.cumulative_threshold),
                metadata={
                    "instantaneous_drift": drift,
                    "cumulative_drift": cumulative_drift,
                    "threshold": self.cumulative_threshold,
                },
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.7,
            reason=f"drift within bounds ({drift:.2f} < {self.drift_threshold * drift_tolerance_mult:.2f})",
            evidence_weight=evidence_weight,
            metadata={"instantaneous_drift": drift, "cumulative_drift": cumulative_drift},
        )

    def reset_drift(self) -> None:
        self._drift_history.clear()


# ═══════════════════════════════════════════════════════════════════
# Domain-Specific Validators for Software Development
# ═══════════════════════════════════════════════════════════════════
# These validators check codebase health using the DevDomainAdapter's
# 11-dim state vector. They replace the GridWorld semantics with
# real software metrics: dependency health, test coverage, code quality.
#
# State indices (from DevDomainAdapter):
#   [0]: dep_count_scaled
#   [1]: dep_outdated_ratio     ← DepHealthValidator
#   [2]: test_count_scaled      ← TestCoverageValidator
#   [3]: test_pass_ratio        ← TestCoverageValidator
#   [4]: ts_error_count_scaled  ← CodeQualityValidator
#   [5]: lint_error_count_scaled ← CodeQualityValidator
#   [6-10]: other metrics
#
# These validators produce meaningful DI/MD values because they
# operate on real metric thresholds, not trivial NaN/Inf checks.
# ═══════════════════════════════════════════════════════════════════


class DepHealthValidator(Validator):
    """Checks dependency health for codebase projects.

    State indices used:
      [1] = dep_outdated_ratio (0-1, fraction of outdated deps)

    Logic:
      - If dep_outdated_ratio > 0.3 → BLOCK with evidence_weight = ratio
      - If any domain_facts.events contain "Missing" → BLOCK
      - Returns confidence proportional to dep health (1.0 - ratio)

    This validator blocks pipelines from proceeding on projects with
    severely outdated dependencies, preventing downstream failures
    from version mismatches or security vulnerabilities.
    """

    @property
    def name(self) -> str:
        return "DepHealthValidator"

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None) -> ValidationSignal:
        state = world.state
        if state is None or len(state) < 2:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="state too small for dep health check", evidence_weight=0.0,
            )

        dep_ratio = float(state[1])

        # Check findings from domain facts (DevDomainSim surfaces them as events)
        findings: List[str] = []
        if domain_facts is not None and hasattr(domain_facts, 'events'):
            findings = domain_facts.events or []

        issues: List[str] = []
        if dep_ratio > 0.3:
            issues.append(f"dependency outdated ratio {dep_ratio:.2f} exceeds 0.3 threshold")

        for f in findings:
            if "Missing" in str(f):
                issues.append(f"dependency issue: {f}")

        if issues:
            evidence_weight = min(1.0, dep_ratio + 0.2 * len(issues))
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.8,
                reason=" | ".join(issues),
                evidence_weight=evidence_weight,
                metadata={
                    "dep_outdated_ratio": dep_ratio,
                    "issue_count": len(issues),
                    "issues": issues,
                },
            )

        confidence = float(np.clip(1.0 - dep_ratio, 0.0, 1.0))
        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=confidence,
            reason=f"dependency health OK (outdated ratio={dep_ratio:.2f})",
            evidence_weight=dep_ratio,
        )


class TestCoverageValidator(Validator):
    """Checks test coverage for codebase projects.

    State indices used:
      [2] = test_count_scaled (0-1, capped at 100 tests)
      [3] = test_pass_ratio (0-1)

    Logic:
      - If test_count_scaled < 0.3 → BLOCK with "Test coverage too low"
      - If test_pass_ratio < 0.8 → BLOCK with "Tests failing"
      - Returns confidence based on coverage level

    This validator prevents deployment to production when the test
    suite is inadequate or actively failing.
    """

    @property
    def name(self) -> str:
        return "TestCoverageValidator"

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None) -> ValidationSignal:
        state = world.state
        if state is None or len(state) < 4:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="state too small for test coverage check", evidence_weight=0.0,
            )

        test_coverage = float(state[2])
        test_pass = float(state[3])

        issues: List[str] = []
        if test_coverage < 0.3:
            issues.append(f"test coverage {test_coverage:.2f} below 0.3 threshold")

        if test_pass < 0.8:
            issues.append(f"test pass ratio {test_pass:.2f} below 0.8 threshold")

        if issues:
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.8,
                reason=" | ".join(issues),
                evidence_weight=0.7,
                metadata={
                    "test_coverage": test_coverage,
                    "test_pass_ratio": test_pass,
                },
            )

        confidence = float(np.clip(0.5 + test_coverage * 0.5, 0.0, 1.0))
        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=confidence,
            reason=f"test coverage OK (coverage={test_coverage:.2f}, pass={test_pass:.2f})",
            evidence_weight=0.3,
        )


class CodeQualityValidator(Validator):
    """Checks code quality for codebase projects.

    State indices used:
      [4] = ts_error_count (0-1 scaled, capped at 100)
      [5] = lint_error_count (0-1 scaled)
      [1] = dep_outdated_ratio (used for combined evidence)

    Logic:
      - If ts_error_count > 0.05 → BLOCK with "TypeScript errors detected"
      - If lint_error_count > 0.05 → BLOCK with "Lint errors detected"
      - Combined evidence_weight = min(1.0, ts_errors + lint_errors + dep_issues)

    This is the gatekeeper for codebase hygiene — it catches TS errors,
    lint violations, and contextual dependency rot.
    """

    @property
    def name(self) -> str:
        return "CodeQualityValidator"

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None) -> ValidationSignal:
        state = world.state
        if state is None or len(state) < 6:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="state too small for code quality check", evidence_weight=0.0,
            )

        ts_errors = float(state[4])
        lint_errors = float(state[5])
        dep_issues = float(state[1]) if len(state) > 1 else 0.0

        issues: List[str] = []
        if ts_errors > 0.05:
            issues.append(f"TypeScript errors {ts_errors:.3f} exceed 0.05 threshold")

        if lint_errors > 0.05:
            issues.append(f"lint errors {lint_errors:.3f} exceed 0.05 threshold")

        if issues:
            evidence_weight = min(1.0, ts_errors + lint_errors + dep_issues)
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.8,
                reason=" | ".join(issues),
                evidence_weight=evidence_weight,
                metadata={
                    "ts_error_count": ts_errors,
                    "lint_error_count": lint_errors,
                    "dep_outdated_ratio": dep_issues,
                },
            )

        confidence = float(np.clip(1.0 - (ts_errors + lint_errors), 0.0, 1.0))
        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=confidence,
            reason=f"code quality OK (ts_errors={ts_errors:.3f}, lint_errors={lint_errors:.3f})",
            evidence_weight=min(0.3, ts_errors + lint_errors + 0.1),
        )
