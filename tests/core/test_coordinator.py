"""Contract tests for telos/core/coordination/coordinator.py.

Uses the shared QuickSim/QuickAdpt test doubles from test_coordination.py.
"""

import numpy as np

from telos.core.coordination.coordinator import (
    PipelineCoordinator, SubPipelineConfig, SubResult, CoordinationResult,
    _build_subpipeline,
)
from tests.core.test_coordination import QuickSim, QuickAdpt


def test_sub_pipeline_config_defaults():
    cfg = SubPipelineConfig(name='z')
    assert cfg.budget_ms == 30.0
    assert cfg.state_dim == 6
    assert cfg.n_worlds == 5
    assert cfg.horizon == 3
    assert 'reflex' in cfg.streams
    assert cfg.scale == 'micro'


def test_sub_result_defaults():
    sr = SubResult(name='n', success=True, intent=None, action=None,
                   di=1.0, md=0.0, council_validated=True, duration_ms=0.0,
                   world_count=0)
    assert sr.error is None


def test_coordination_result_defaults():
    r = CoordinationResult(success=True)
    assert r.aggregate_di == 1.0
    assert r.aggregate_md == 0.0
    assert r.all_council_validated is True
    assert r.sub_results == []


def test_build_subpipeline_config():
    cfg = SubPipelineConfig(name='test', budget_ms=20.0)
    p = _build_subpipeline(cfg, simulator=QuickSim(), adapter=QuickAdpt())
    assert p is not None
    assert p.config.compute_budget_ms == 20.0


def test_scale_principle_exposed():
    coord = PipelineCoordinator()
    assert coord.scale_principle.name == 'Scale Invariance (Deliberate Recursion)'
    assert 'perceive' in list(coord.scale_principle.canonical_phases)
    assert coord.scale_verifier.__class__.__name__ == 'ScaleVerifier'


def test_verify_scale_invariance_initial():
    coord = PipelineCoordinator()
    v = coord.verify_scale_invariance()
    assert v['invariant_holds'] is True
    assert v['entries'] == 0
    assert v['principle'] == 'Scale Invariance (Deliberate Recursion)'


def test_spawn_registers_pipeline_and_ledger():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    p = coord.spawn(SubPipelineConfig(name='analyst', budget_ms=20.0,
                                      state_dim=2))
    assert p._scale_scope == 'analyst'
    assert p._scale_parent == 'PipelineCoordinator'
    assert coord.stats['sub_pipelines'] == 1
    assert coord.stats['names'] == ['analyst']
    assert coord.recursion_ledger.entries


def test_phase_signature_lists_nine_phases():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    p = coord.spawn(SubPipelineConfig(name='s', budget_ms=10.0, state_dim=2))
    sig = PipelineCoordinator._phase_signature(p)
    assert len(sig) == 9
    assert 'select' in sig
    assert 'act' in sig
    assert 'reflect' in sig


def test_orchestrate_fan_out():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    result = coord.orchestrate(
        state=np.zeros(2),
        subtasks=[SubPipelineConfig(name='a', budget_ms=15.0, state_dim=2),
                  SubPipelineConfig(name='b', budget_ms=15.0, state_dim=2)],
    )
    assert len(result.sub_results) == 2
    assert result.sub_results[0].name == 'a'
    assert result.sub_results[1].name == 'b'
    assert result.aggregate_di >= 0.0
    assert 0.0 <= result.aggregate_md <= 1.0
    assert result.total_duration_ms >= 0.0


def test_orchestrate_sub_result_success_fields():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    result = coord.orchestrate(
        state=np.zeros(2),
        subtasks=[SubPipelineConfig(name='solo', budget_ms=15.0, state_dim=2)],
    )
    sr = result.sub_results[0]
    assert sr.name == 'solo'
    assert sr.success is True
    assert sr.di >= 0.0
    assert sr.council_validated is True
    assert sr.duration_ms >= 0.0


def test_orchestrate_empty_subtasks():
    coord = PipelineCoordinator()
    result = coord.orchestrate(state=np.zeros(2), subtasks=[])
    assert result.sub_results == []
    assert result.success is False
    assert result.aggregate_di == 0.0


def test_chain_runs_sequentially():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    result = coord.chain(
        state=np.zeros(2),
        subtasks=[SubPipelineConfig(name='s1', budget_ms=10.0, state_dim=2),
                  SubPipelineConfig(name='s2', budget_ms=10.0, state_dim=2)],
    )
    assert len(result.sub_results) == 2
    assert result.sub_results[0].name == 's1'
    assert result.sub_results[1].name == 's2'
    assert result.success is True


def test_on_subresult_callback_fires():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    called = []
    coord.on_subresult(lambda r: called.append(r.name))
    coord.orchestrate(
        state=np.zeros(2),
        subtasks=[SubPipelineConfig(name='cb', budget_ms=15.0, state_dim=2)],
    )
    assert called == ['cb']


def test_stats_counts_recursive_invocations():
    coord = PipelineCoordinator(default_simulator=QuickSim(),
                                default_adapter=QuickAdpt())
    coord.spawn(SubPipelineConfig(name='analysis', budget_ms=20.0,
                                  state_dim=2))
    assert coord.stats['sub_pipelines'] == 1
    assert coord.stats['self_similarity'] >= 0.0