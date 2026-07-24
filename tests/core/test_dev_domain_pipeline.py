"""
DevDomain Full-Pipeline Integration Test.

Tests the complete TELOS pipeline with DevDomainSim + DevDomainAdpt
and all 7 validators (4 original + 3 dev-domain) registered.

Verifies:
  - Pipeline runs without error on realistic codebase state vectors
  - DI < 1.0 when state has issues (deps outdated, tests failing)
  - DI == 1.0 when state is clean and all validators pass
  - Domain-specific thresholds are applied correctly
"""

import numpy as np
import pytest

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
    DepHealthValidator, TestCoverageValidator, CodeQualityValidator,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.adapters.dev_domain_adapter import DevDomainSim, DevDomainAdpt

from tests.core.conftest import MockSimulator


# ═══════════════════════════════════════════════════════════════════
# Helper: build a DevDomain pipeline with all 7 validators
# ═══════════════════════════════════════════════════════════════════

def build_dev_domain_pipeline(project_path: str = "/tmp/test_project") -> TelosV14Pipeline:
    """Build a TelosV14Pipeline configured for DevDomain with all validators."""
    sim = DevDomainSim(project_path)
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=DevDomainAdpt(),
        simulator=sim,
        compute_budget_ms=200.0,
        state_dim=11,
        n_worlds=5,
        horizon=3,
    ))
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim)

    # Register all 4 original (GridWorld) validators
    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=3.0))

    # Register all 3 dev-domain validators
    pipeline.register_validator(DepHealthValidator())
    pipeline.register_validator(TestCoverageValidator())
    pipeline.register_validator(CodeQualityValidator())

    return pipeline


# ═══════════════════════════════════════════════════════════════════
# DevDomain state vectors
# ═══════════════════════════════════════════════════════════════════
# State indices (from DevDomainAdapter):
#   [0]: dep_count_scaled
#   [1]: dep_outdated_ratio     ← DepHealthValidator
#   [2]: test_count_scaled      ← TestCoverageValidator
#   [3]: test_pass_ratio        ← TestCoverageValidator
#   [4]: ts_error_count_scaled  ← CodeQualityValidator
#   [5]: lint_error_count_scaled ← CodeQualityValidator
#   [6]: file_count_scaled
#   [7]: bundle_size_mb_scaled
#   [8]: has_readme
#   [9]: has_ci_config
#   [10]: missing_peer_deps

CLEAN_STATE = np.array([
    0.5,   # [0]  reasonable dep count
    0.0,   # [1]  no outdated deps
    0.8,   # [2]  good test coverage
    1.0,   # [3]  all tests pass
    0.0,   # [4]  no TS errors
    0.0,   # [5]  no lint errors
    0.5,   # [6]  moderate files
    0.2,   # [7]  small bundle
    1.0,   # [8]  has README
    1.0,   # [9]  has CI
    0.0,   # [10] no missing peer deps
])

DIRTY_STATE = np.array([
    1.0,   # [0]  many deps
    0.6,   # [1]  many outdated deps (>0.3 → DepHealth blocks)
    0.15,  # [2]  low test coverage (<0.3 → TestCoverage blocks)
    0.5,   # [3]  tests failing (<0.8 → TestCoverage blocks)
    0.12,  # [4]  TS errors (>0.05 → CodeQuality blocks)
    0.15,  # [5]  lint errors (>0.05 → CodeQuality blocks)
    0.5,   # [6]
    0.5,   # [7]
    0.0,   # [8]  no README
    0.0,   # [9]  no CI
    0.3,   # [10] some missing peer deps
])


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════

class TestDevDomainPipeline:
    """Full-pipeline integration tests with DevDomain."""

    def test_pipeline_runs_without_error(self):
        """The pipeline should execute a clean state without raising."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(CLEAN_STATE, user_name="test-devdomain")
        # The pipeline completes — no exception is the primary assertion
        assert result is not None

    def test_pipeline_returns_result_with_trace(self):
        """Result should contain a full DecisionTrace."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(CLEAN_STATE, user_name="test-devdomain")
        assert result.decision_trace is not None
        assert result.decision_trace.cycle_id > 0
        assert result.decision_trace.decision_integrity >= 0.0
        assert result.decision_trace.mission_drift >= 0.0

    def test_clean_state_produces_di_equals_1(self):
        """A perfectly clean codebase state should yield DI == 1.0 (all validators pass)."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(CLEAN_STATE, user_name="test-devdomain")
        # All validators pass on clean state → no evidence ignored → DI=1.0
        assert result.decision_integrity == 1.0, \
            f"Expected DI=1.0 for clean state, got {result.decision_integrity}"

    def test_dirty_state_produces_di_less_than_1(self):
        """A dirty codebase state should yield DI < 1.0 (some validators block)."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(DIRTY_STATE, user_name="test-devdomain")
        # Multiple validators block on dirty state → evidence ignored → DI drops
        assert result.decision_integrity < 1.0, \
            f"Expected DI < 1.0 for dirty state, got {result.decision_integrity}"

    def test_dirty_state_is_council_blocked(self):
        """Dirty state should be blocked by the Council."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(DIRTY_STATE, user_name="test-devdomain")
        assert result.council_blocked is True, \
            "Dirty state should be council-blocked"

    def test_dirty_state_has_blocking_validator(self):
        """Dirty state should have a named blocking validator."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(DIRTY_STATE, user_name="test-devdomain")
        trace = result.decision_trace
        assert trace is not None
        assert trace.blocking_validator is not None, \
            "Dirty state should have a blocking validator"
        # At least one of the dev-domain validators should have blocked
        assert trace.blocking_validator in (
            "DepHealthValidator", "TestCoverageValidator", "CodeQualityValidator"
        ), f"Expected dev-domain blocker, got {trace.blocking_validator}"

    def test_clean_state_not_council_blocked(self):
        """Clean state should pass through the Council without block."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(CLEAN_STATE, user_name="test-devdomain")
        assert result.council_blocked is False, \
            "Clean state should not be council-blocked"

    def test_clean_state_has_no_blocking_validator(self):
        """Clean state should have no blocking validator."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(CLEAN_STATE, user_name="test-devdomain")
        trace = result.decision_trace
        assert trace is not None
        assert trace.blocking_validator is None, \
            f"Clean state should have no blocking validator, got {trace.blocking_validator}"

    def test_council_signals_populated_on_dirty(self):
        """Council signals should contain detailed per-validator output on dirty state."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(DIRTY_STATE, user_name="test-devdomain")
        trace = result.decision_trace
        assert trace is not None
        signals = trace.council_signals
        assert len(signals) == 7, f"Expected 7 council signals, got {len(signals)}"
        # At least 3 should be blocked
        blocked = [s for s in signals if not s["passed"]]
        assert len(blocked) >= 3, \
            f"Expected >=3 blocked signals on dirty state, got {len(blocked)}"

    def test_all_seven_validators_registered(self):
        """The pipeline should have all 7 validators registered."""
        pipeline = build_dev_domain_pipeline()
        assert len(pipeline.council._validators) == 7, \
            f"Expected 7 validators, got {len(pipeline.council._validators)}"
        names = sorted(v.name for v in pipeline.council._validators)
        expected_names = sorted([
            "RealityValidator", "ConstraintValidator", "MemoryAdvisor",
            "MissionDriftDetector", "DepHealthValidator",
            "TestCoverageValidator", "CodeQualityValidator",
        ])
        assert names == expected_names, \
            f"Validator names mismatch:\n  got:      {names}\n  expected: {expected_names}"

    def test_mission_drift_computed_on_dirty_state(self):
        """Mission drift should be computed even on dirty blocked state."""
        pipeline = build_dev_domain_pipeline()
        result = pipeline.execute(DIRTY_STATE, user_name="test-devdomain")
        trace = result.decision_trace
        assert trace is not None
        # Mission drift is computed from predicted vs observed state
        assert trace.mission_drift >= 0.0

    def test_edge_case_partially_healthy(self):
        """Partially healthy state — only dep health bad, rest good."""
        pipeline = build_dev_domain_pipeline()
        # Only dep_outdated_ratio is high
        partial_state = CLEAN_STATE.copy()
        partial_state[1] = 0.6  # outdated deps
        result = pipeline.execute(partial_state, user_name="test-devdomain")
        assert result.decision_integrity < 1.0, \
            "Partially healthy state should have DI < 1.0"
        trace = result.decision_trace
        assert trace is not None
        # Should be blocked by DepHealthValidator
        if result.council_blocked:
            assert trace.blocking_validator == "DepHealthValidator", \
                f"Expected DepHealthValidator, got {trace.blocking_validator}"

    def test_dev_domain_pipeline_many_cycles(self):
        """Run multiple cycles to ensure stability."""
        pipeline = build_dev_domain_pipeline()
        for i in range(5):
            state = CLEAN_STATE if i % 2 == 0 else DIRTY_STATE
            result = pipeline.execute(state, user_name="test-devdomain")
            assert result is not None
            if i % 2 == 0:
                assert result.decision_integrity == 1.0, \
                    f"Cycle {i}: clean state should have DI=1.0"
            else:
                assert result.decision_integrity < 1.0, \
                    f"Cycle {i}: dirty state should have DI<1.0"

    def test_dev_domain_adapter_name_is_devdomain(self):
        """DevDomainAdpt.name should be 'devdomain'."""
        adapter = DevDomainAdpt()
        assert adapter.name == "devdomain"


# ═══════════════════════════════════════════════════════════════════
# Domain-specific Firewall threshold tests
# ═══════════════════════════════════════════════════════════════════

class TestDevDomainFirewallThreshold:
    """Tests that the firewall applies domain-specific DI thresholds."""

    def test_devdomain_threshold_is_higher(self):
        """DevDomain should have a higher DI threshold (0.6) than GridWorld (0.3)."""
        from telos.core.governance.firewall import DOMAIN_THRESHOLDS
        assert DOMAIN_THRESHOLDS["devdomain"] == 0.6
        assert DOMAIN_THRESHOLDS["gridworld"] == 0.3

    def test_firewall_inspect_uses_domain_threshold(self):
        """Firewall inspect should use domain-specific threshold when domain arg is passed."""
        from telos.core.governance.firewall import DecisionFirewall, FirewallConfig
        from telos.world.world import World
        from telos.intent_ir import IntentIR

        fw = DecisionFirewall()
        # DI=0.5 should pass for gridworld (threshold=0.3) but fail for devdomain (threshold=0.6)
        world = World(state=np.array([1.0, 2.0]))
        intent = IntentIR("test")

        # GridWorld: DI=0.5 >= max(0.3, 0.3) = 0.3 → pass
        verdict_gw = fw.inspect(world, intent, council_validated=True,
                                 decision_integrity=0.5, domain="gridworld")
        assert verdict_gw.passed is True, \
            f"GridWorld should pass DI=0.5 (threshold=0.3), got {verdict_gw.reason}"

        # DevDomain: DI=0.5 < max(0.3, 0.6) = 0.6 → block
        verdict_dd = fw.inspect(world, intent, council_validated=True,
                                 decision_integrity=0.5, domain="devdomain")
        assert verdict_dd.passed is False, \
            f"DevDomain should block DI=0.5 (threshold=0.6), got {verdict_dd.reason}"
        assert verdict_dd.blocked_by == "low_integrity"


# ═══════════════════════════════════════════════════════════════════
# Health Manager Domain-Specific Configuration Tests
# ═══════════════════════════════════════════════════════════════════

class TestHealthManagerDomainConfig:
    """Tests that SystemHealthManager uses domain-specific config values."""

    def test_domain_configs_exist(self):
        """DOMAIN_CONFIGS should contain expected keys."""
        from telos.core.infra_manager.health_manager import DOMAIN_CONFIGS
        for domain in ("gridworld", "devdomain", "default"):
            assert domain in DOMAIN_CONFIGS, f"Missing domain config for '{domain}'"
            cfg = DOMAIN_CONFIGS[domain]
            for key in ("failure_threshold", "window", "clean_cycles", "base_horizon"):
                assert key in cfg, f"Missing key '{key}' in {domain} config"

    def test_devdomain_has_higher_tolerance(self):
        """DevDomain should have higher failure thresholds than GridWorld."""
        from telos.core.infra_manager.health_manager import DOMAIN_CONFIGS
        gw = DOMAIN_CONFIGS["gridworld"]
        dd = DOMAIN_CONFIGS["devdomain"]
        assert dd["failure_threshold"] > gw["failure_threshold"]
        assert dd["window"] > gw["window"]
        assert dd["base_horizon"] > gw["base_horizon"]


# ═══════════════════════════════════════════════════════════════════
# Knowledge Manager Domain-Specific Adjustment Tests
# ═══════════════════════════════════════════════════════════════════

class TestKnowledgeManagerDomainAdjustments:
    """Tests that KnowledgeManager uses domain-specific adjustment scales."""

    def test_domain_adjustments_exist(self):
        """DOMAIN_ADJUSTMENTS should contain expected keys with risk and exploration."""
        from telos.core.infra_manager.knowledge_manager import KnowledgeManager
        for domain in ("gridworld", "devdomain", "default"):
            assert domain in KnowledgeManager.DOMAIN_ADJUSTMENTS, \
                f"Missing domain adjustment for '{domain}'"
            adj = KnowledgeManager.DOMAIN_ADJUSTMENTS[domain]
            for key in ("risk", "exploration"):
                assert key in adj, f"Missing key '{key}' in {domain} adjustments"

    def test_devdomain_adjustment_is_smaller(self):
        """DevDomain adjustments should be smaller (more conservative) than GridWorld."""
        from telos.core.infra_manager.knowledge_manager import KnowledgeManager
        gw = KnowledgeManager.DOMAIN_ADJUSTMENTS["gridworld"]
        dd = KnowledgeManager.DOMAIN_ADJUSTMENTS["devdomain"]
        assert dd["risk"] < gw["risk"], \
            f"Expected devdomain risk ({dd['risk']}) < gridworld risk ({gw['risk']})"
        assert dd["exploration"] < gw["exploration"], \
            f"Expected devdomain exploration ({dd['exploration']}) < gridworld exploration ({gw['exploration']})"


# ═══════════════════════════════════════════════════════════════════
# InfrastructureManager Domain Propagation Tests
# ═══════════════════════════════════════════════════════════════════

class TestInfrastructureManagerDomain:
    """Tests that InfrastructureManager propagates domain to sub-managers."""

    def test_infra_manager_creates_sub_managers_with_domain(self):
        """InfrastructureManager should pass domain to KnowledgeManager and HealthManager."""
        from telos.core.infra_manager.infrastructure_manager import InfrastructureManager

        infra_dd = InfrastructureManager(domain="devdomain")
        assert infra_dd.knowledge_mgr.domain == "devdomain"
        assert infra_dd.health.domain == "devdomain"

        infra_gw = InfrastructureManager(domain="gridworld")
        assert infra_gw.knowledge_mgr.domain == "gridworld"
        assert infra_gw.health.domain == "gridworld"

    def test_default_domain_is_gridworld(self):
        """Default domain for InfrastructureManager should be gridworld."""
        from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
        infra = InfrastructureManager()
        assert infra._domain == "gridworld"
        assert infra.knowledge_mgr.domain == "gridworld"
        assert infra.health.domain == "gridworld"
