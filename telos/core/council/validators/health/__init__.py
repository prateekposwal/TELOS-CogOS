import numpy as np
import logging
from enum import Enum
from typing import Optional, Any, List
from telos.core.council.base import Validator, ValidationSignal
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR

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
