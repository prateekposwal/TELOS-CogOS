from telos.core.runtime import TelosV14Pipeline, PipelineConfig


class TestPipeline:
    def test_has_nine_phases(self):
        p = TelosV14Pipeline(PipelineConfig())
        assert len(p._phases) == 9

    def test_v2_module_attributes_exist(self):
        p = TelosV14Pipeline(PipelineConfig())
        assert hasattr(p, '_assumption_auditor')
        assert hasattr(p, '_identity_utility')
        assert hasattr(p, '_council_reflector')
        assert hasattr(p, '_error_attribution')
        assert hasattr(p, '_theory_builder')
        assert hasattr(p, '_interpretation_engine')
        assert hasattr(p, '_axiom_evolution')
        assert hasattr(p, '_regret_memory')
        assert hasattr(p, '_introspection_scheduler')
        assert hasattr(p, '_internal_debate')
        assert hasattr(p, '_cognitive_momentum')

    def test_v25_module_attributes_exist(self):
        p = TelosV14Pipeline(PipelineConfig())
        assert hasattr(p, '_unknown_unknown_detector')
        assert hasattr(p, '_model_competition')
        assert hasattr(p, '_time_horizon')
        assert hasattr(p, '_surprise_budget')
        assert hasattr(p, '_active_forgetting')
        assert hasattr(p, '_cognitive_energy')
        assert hasattr(p, '_dual_confidence')
        assert hasattr(p, '_identity_compression')
        assert hasattr(p, '_explanation_compression')
        assert hasattr(p, '_resource_accounting')

    def test_build_pipeline_components_imports(self):
        from telos.core.pipeline_builder import build_pipeline_components
        config = PipelineConfig()
        from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
        from telos.core.ledger.skill_library import SkillLibrary
        infra = InfrastructureManager()
        skills = SkillLibrary()
        comps = build_pipeline_components(config, infra, skills)
        assert 'attention_engine' in comps
        assert 'assumption_auditor' in comps
        assert 'identity_utility' in comps
        assert 'council_reflector' in comps
        assert 'resource_accounting' in comps


def test_resource_budgets_memory_is_truthful_cycle_count():
    """Defect 3: the `memory` resource-budget field claimed to be
    `trace_history_length` ("number of stored traces") but actually carried
    `ctx.cycle_count` — and core retains NO trace-history list, so the name
    lied (the dashboard's /api/health cycle count is not stored traces). The
    value is now exposed under its correct name and the misleading field is
    gone. Renaming is behaviour-neutral: no consumer read the old key."""
    from types import SimpleNamespace

    p = TelosV14Pipeline(PipelineConfig())
    budgets = p._compute_resource_budgets(SimpleNamespace(cycle_count=163_683))
    mem = budgets["memory"]
    assert mem["cycle_count"] == 163_683
    assert "trace_history_length" not in mem, \
        "the misleading trace-history field must be removed"
