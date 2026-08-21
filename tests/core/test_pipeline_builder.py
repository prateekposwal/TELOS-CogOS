"""Tests for PipelineBuilder — component construction wiring."""

from types import SimpleNamespace

from telos.core.pipeline_builder import build_pipeline_components


class TestBuildComponents:
    def test_returns_expected_component_keys(self):
        config = SimpleNamespace(compute_budget_ms=123.0)
        components = build_pipeline_components(config)
        expected = {
            "omega_threshold_learner", "commitment_optimizer",
            "resource_gradient_tracker", "curiosity_drive", "identity_entropy",
            "attention_engine", "pattern_library", "planner",
            "representation_selector", "axiom_prover", "tripartite_u",
            "relational_context", "meta_cognition", "theory_builder",
            "interpretation_engine", "axiom_evolution", "council_reflector",
            "internal_debate", "error_attribution", "assumption_auditor",
            "unknown_unknown_detector", "identity_utility",
            "introspection_scheduler", "regret_memory", "model_competition",
            "time_horizon", "surprise_budget", "active_forgetting",
            "cognitive_energy", "dual_confidence", "identity_compression",
            "explanation_compression", "cognitive_momentum",
            "resource_accounting", "ecosystem",
        }
        assert set(components) == expected

    def test_config_compute_budget_feeds_surprise_budget(self):
        config = SimpleNamespace(compute_budget_ms=456.0)
        components = build_pipeline_components(config)
        assert components["surprise_budget"]._base_budget_ms == 456.0

    def test_curiosity_drive_wired_to_assumption_auditor(self):
        config = SimpleNamespace(compute_budget_ms=100.0)
        components = build_pipeline_components(config)
        assert components["curiosity_drive"]._assumption_auditor is components["assumption_auditor"]

    def test_axiom_prover_receives_infra_and_skills(self):
        config = SimpleNamespace(compute_budget_ms=100.0)
        infra = object()
        skills = object()
        components = build_pipeline_components(config, infra_manager=infra,
                                               skill_library=skills)
        assert components["axiom_prover"]._infra_manager is infra
        assert components["axiom_prover"]._skill_library is skills

    def test_default_infra_and_skills_are_none(self):
        config = SimpleNamespace(compute_budget_ms=100.0)
        components = build_pipeline_components(config)
        assert components["axiom_prover"]._infra_manager is None
        assert components["axiom_prover"]._skill_library is None