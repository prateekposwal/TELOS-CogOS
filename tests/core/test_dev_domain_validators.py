"""
Tests for development-domain-specific Council validators.

These validators use the DevDomainAdapter's 11-dim state vector to
check real software metrics (dependency health, test coverage, code quality)
instead of the GridWorld coordinate checks used by the base validators.

Running these tests verifies that DI/MD metrics are now grounded in
meaningful evidence rather than trivially passing.
"""

import numpy as np
import pytest

from telos.core.council.base import Council, CouncilVerdict, ValidationSignal, Validator
from telos.core.council.validators import (
    DepHealthValidator, TestCoverageValidator, CodeQualityValidator,
)
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR


# ═══════════════════════════════════════════════════════════════════
# DepHealthValidator Tests
# ═══════════════════════════════════════════════════════════════════

class TestDepHealthValidator:
    """Tests for DepHealthValidator — dependency health checking."""

    def test_passes_on_healthy_deps(self):
        """A state with low dep_outdated_ratio should pass."""
        state = np.array([1.0, 0.05, 0.5, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("fix_bug")
        validator = DepHealthValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is True, f"Should pass with healthy deps: {signal.reason}"
        assert signal.confidence > 0.9, f"Confidence should be high: {signal.confidence}"
        assert "dependency health OK" in signal.reason

    def test_blocks_on_outdated_deps(self):
        """A state with dep_outdated_ratio > 0.3 should block."""
        state = np.array([1.0, 0.45, 0.5, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("fix_bug")
        validator = DepHealthValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is False, f"Should block with outdated deps: {signal.reason}"
        assert "exceeds 0.3 threshold" in signal.reason
        assert signal.evidence_weight >= 0.45
        assert "dep_outdated_ratio" in signal.metadata
        assert signal.metadata["dep_outdated_ratio"] == 0.45

    def test_blocks_on_missing_peer_deps(self):
        """Findings containing 'Missing' should trigger block regardless of ratio."""
        state = np.array([1.0, 0.1, 0.5, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("fix_bug")
        facts = DomainFacts(
            state=state,
            resources={"dep_health": 0.9},
            constraints=[],
            events=["⚠️  Missing expo-font (peer dep of @expo/vector-icons)"],
            metrics={"code_quality": 0.9},
        )
        validator = DepHealthValidator()
        signal = validator.validate(world, intent, domain_facts=facts)

        assert signal.passed is False, f"Should block on missing deps: {signal.reason}"
        assert "Missing" in signal.reason
        assert "dependency issue" in signal.reason

    def test_abstains_on_too_small_state(self):
        """If state is too small to check, it should pass trivially."""
        state = np.array([1.0])
        world = World(state=state)
        intent = IntentIR("fix_bug")
        validator = DepHealthValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is True
        assert signal.confidence == 0.0
        assert signal.evidence_weight == 0.0

    def test_confidence_is_proportional_to_health(self):
        """Confidence = 1.0 - dep_ratio for healthy states."""
        state = np.array([1.0, 0.0, 0.5, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("fix_bug")
        validator = DepHealthValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is True
        assert signal.confidence == 1.0  # 1.0 - 0.0

    def test_in_council_blocks_deps(self):
        """When registered in Council, DepHealthValidator should block bad dep state."""
        council = Council()
        council.register(DepHealthValidator())

        state = np.array([1.0, 0.6, 0.5, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")

        verdict = council.evaluate(world, intent)
        assert verdict.validated is False
        assert verdict.blocking_validator == "DepHealthValidator"
        assert verdict.decision_integrity < 1.0  # Evidence was ignored → DI drops


# ═══════════════════════════════════════════════════════════════════
# TestCoverageValidator Tests
# ═══════════════════════════════════════════════════════════════════

class TestTestCoverageValidator:
    """Tests for TestCoverageValidator — test suite health checking."""

    def test_passes_on_good_coverage(self):
        """High test count and pass ratio should pass."""
        state = np.array([1.0, 0.0, 0.8, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")
        validator = TestCoverageValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is True
        assert "test coverage OK" in signal.reason
        assert signal.confidence >= 0.9  # 0.5 + 0.8*0.5 = 0.9

    def test_blocks_on_low_coverage(self):
        """test_count_scaled < 0.3 should block."""
        state = np.array([1.0, 0.0, 0.15, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")
        validator = TestCoverageValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is False
        assert "below 0.3 threshold" in signal.reason

    def test_blocks_on_failing_tests(self):
        """test_pass_ratio < 0.8 should block."""
        state = np.array([1.0, 0.0, 0.7, 0.5, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")
        validator = TestCoverageValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is False
        assert "below 0.8 threshold" in signal.reason

    def test_blocks_on_both_issues(self):
        """Both low coverage AND failing tests should report both."""
        state = np.array([1.0, 0.0, 0.2, 0.4, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")
        validator = TestCoverageValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is False
        assert "below 0.3 threshold" in signal.reason
        assert "below 0.8 threshold" in signal.reason
        assert signal.metadata["test_coverage"] == 0.2
        assert signal.metadata["test_pass_ratio"] == 0.4

    def test_abstains_on_too_small_state(self):
        """State too small should pass trivially."""
        state = np.array([1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")
        validator = TestCoverageValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is True
        assert signal.confidence == 0.0
        assert signal.evidence_weight == 0.0

    def test_in_council_blocks_low_coverage(self):
        """Council with TestCoverageValidator blocks on low test coverage."""
        council = Council()
        council.register(TestCoverageValidator())

        state = np.array([1.0, 0.0, 0.1, 0.9, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")

        verdict = council.evaluate(world, intent)
        assert verdict.validated is False
        assert verdict.blocking_validator == "TestCoverageValidator"

    def test_evidence_weight_is_high_on_block(self):
        """Blocking signal should have high evidence_weight."""
        state = np.array([1.0, 0.0, 0.1, 0.5, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")
        validator = TestCoverageValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is False
        assert signal.evidence_weight == 0.7  # Hardcoded for test coverage blocks
        assert signal.confidence <= -0.8


# ═══════════════════════════════════════════════════════════════════
# CodeQualityValidator Tests
# ═══════════════════════════════════════════════════════════════════

class TestCodeQualityValidator:
    """Tests for CodeQualityValidator — codebase hygiene checking."""

    def test_passes_on_clean_code(self):
        """Zero TS and lint errors should pass."""
        state = np.array([1.0, 0.0, 0.5, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("refactor")
        validator = CodeQualityValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is True
        assert "code quality OK" in signal.reason
        assert signal.confidence == 1.0

    def test_blocks_on_ts_errors(self):
        """ts_error_count > 0.05 should block."""
        state = np.array([1.0, 0.0, 0.5, 1.0, 0.12, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("refactor")
        validator = CodeQualityValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is False
        assert "TypeScript errors" in signal.reason
        assert "exceed 0.05 threshold" in signal.reason

    def test_blocks_on_lint_errors(self):
        """lint_error_count > 0.05 should block."""
        state = np.array([1.0, 0.0, 0.5, 1.0, 0.0, 0.15, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("refactor")
        validator = CodeQualityValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is False
        assert "lint errors" in signal.reason
        assert "exceed 0.05 threshold" in signal.reason

    def test_blocks_on_both_errors(self):
        """Both TS and lint errors should report both issues."""
        state = np.array([1.0, 0.0, 0.5, 1.0, 0.2, 0.3, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("refactor")
        validator = CodeQualityValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is False
        assert "TypeScript errors" in signal.reason
        assert "lint errors" in signal.reason

    def test_combined_evidence_weight(self):
        """evidence_weight = min(1.0, ts_errors + lint_errors + dep_issues)."""
        state = np.array([1.0, 0.1, 0.5, 1.0, 0.2, 0.3, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("refactor")
        validator = CodeQualityValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is False
        expected_weight = min(1.0, 0.2 + 0.3 + 0.1)
        assert signal.evidence_weight == expected_weight, \
            f"Expected {expected_weight}, got {signal.evidence_weight}"
        assert signal.metadata["ts_error_count"] == 0.2
        assert signal.metadata["lint_error_count"] == 0.3
        assert signal.metadata["dep_outdated_ratio"] == 0.1

    def test_abstains_on_too_small_state(self):
        """State too small should pass trivially."""
        state = np.array([1.0, 0.0, 0.0])
        world = World(state=state)
        intent = IntentIR("refactor")
        validator = CodeQualityValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is True
        assert signal.confidence == 0.0
        assert signal.evidence_weight == 0.0

    def test_passes_with_minor_errors_below_threshold(self):
        """Errors at exactly 0.05 should pass (threshold is > 0.05)."""
        state = np.array([1.0, 0.0, 0.5, 1.0, 0.05, 0.05, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("refactor")
        validator = CodeQualityValidator()
        signal = validator.validate(world, intent)

        assert signal.passed is True, f"Should pass at threshold: {signal.reason}"

    def test_in_council_blocks_code_quality(self):
        """Council with CodeQualityValidator blocks on TS errors."""
        council = Council()
        council.register(CodeQualityValidator())

        state = np.array([1.0, 0.0, 0.5, 1.0, 0.3, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")

        verdict = council.evaluate(world, intent)
        assert verdict.validated is False
        assert verdict.blocking_validator == "CodeQualityValidator"
        assert verdict.decision_integrity < 1.0


# ═══════════════════════════════════════════════════════════════════
# Integration Tests — All three validators together
# ═══════════════════════════════════════════════════════════════════

class TestDomainValidatorsIntegration:
    """Integration tests with all three dev-domain validators registered."""

    def test_all_pass_on_green_codebase(self):
        """A perfectly healthy codebase passes all three validators."""
        council = Council()
        council.register(DepHealthValidator())
        council.register(TestCoverageValidator())
        council.register(CodeQualityValidator())

        # A near-perfect state vector
        state = np.array([1.0, 0.0, 0.8, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")

        verdict = council.evaluate(world, intent)
        assert verdict.validated is True
        assert verdict.blocking_validator is None
        assert verdict.decision_integrity == 1.0  # No evidence ignored
        assert verdict.mission_drift == 0.0  # No drift
        assert verdict.summary.startswith("Council: 3/3 passed")
        assert "DI=1.000" in verdict.summary

    def test_dep_block_lowers_di(self):
        """When DepHealth blocks, DI drops proportionally."""
        council = Council()
        council.register(DepHealthValidator())
        council.register(TestCoverageValidator())
        council.register(CodeQualityValidator())

        # Bad deps but everything else fine
        state = np.array([1.0, 0.6, 0.8, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")

        verdict = council.evaluate(world, intent)
        assert verdict.validated is False
        assert verdict.blocking_validator == "DepHealthValidator"
        # DI should be < 1.0 because evidence was ignored (blocked)
        assert verdict.decision_integrity < 1.0
        # The summary should contain "BLOCKED"
        assert "BLOCKED" in verdict.summary

    def test_multiple_blocks_increase_evidence_ignored(self):
        """When multiple validators block, DI drops further."""
        council = Council()
        council.register(DepHealthValidator())
        council.register(TestCoverageValidator())
        council.register(CodeQualityValidator())

        # Everything bad
        state = np.array([1.0, 0.6, 0.1, 0.4, 0.3, 0.2, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")

        verdict = council.evaluate(world, intent)
        assert verdict.validated is False
        # At least one validator blocked
        assert verdict.blocking_validator is not None
        # DI much lower because multiple high-weight evidences were ignored
        assert verdict.decision_integrity < 0.5

    def test_mission_drift_calculated_from_predicted_vs_observed(self):
        """MD is computed from predicted vs observed state, not from validators."""
        council = Council()
        council.register(DepHealthValidator())
        council.register(TestCoverageValidator())
        council.register(CodeQualityValidator())

        state = np.array([1.0, 0.0, 0.8, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")

        predicted = np.array([1.0, 0.0, 0.9, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        observed = np.array([1.0, 0.0, 0.7, 0.9, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])

        verdict = council.evaluate(world, intent, predicted_state=predicted, observed_state=observed)
        assert verdict.mission_drift > 0.0
        expected_md = float(np.linalg.norm(predicted - observed))
        assert verdict.mission_drift == expected_md

    def test_individual_validator_output_in_council_trace(self):
        """Council trace captures each validator's output for audit."""
        council = Council()
        council.register(DepHealthValidator())

        state = np.array([1.0, 0.5, 0.8, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])
        world = World(state=state)
        intent = IntentIR("deploy")

        verdict = council.evaluate(world, intent)
        assert len(verdict.signals) == 1
        signal = verdict.signals[0]
        assert signal.validator_name == "DepHealthValidator"
        assert signal.passed is False
        assert signal.verdict == "BLOCK"
        assert signal.evidence_weight == 0.7  # min(1.0, 0.5 + 0.2*1)
