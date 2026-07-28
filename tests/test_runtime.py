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
