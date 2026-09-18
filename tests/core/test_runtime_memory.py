"""
Runtime memory wiring (Phase 2) — memory is consumed, not just written.

The pipeline must insert decision outcomes into its ONE MemoryController and
consult it during perception, so real cycles consume memory. The
governance-suppression rule holds on the runtime path too.
"""

import numpy as np
import pytest

from telos.core.memory.controller import MemoryController


def _build_pipeline(tmp_path):
    from telos_task import GridSim, GridAdpt, DEFAULT_BLOCKED, DEFAULT_REWARDS
    from telos.core.runtime import PipelineConfig, TelosV14Pipeline
    from telos.core.streams.implementations import (
        ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
    )
    from telos.core.ledger.skill_library import SkillLibrary

    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=5, horizon=3,
        checkpoint_path=str(tmp_path / "cp"),
        memory_path=str(tmp_path / "memory.json"),
        deterministic_seed=7,
    ))
    sl = SkillLibrary()
    for stream in (ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
                   PlanningStream(sl)):
        pipe.register_stream(stream)
    return pipe


def test_pipeline_has_one_memory_controller(tmp_path):
    """The pipeline owns exactly one MemoryController."""
    pipe = _build_pipeline(tmp_path)
    assert isinstance(pipe._memory_controller, MemoryController)


def test_cycles_consume_memory(tmp_path):
    """Running real cycles stores outcomes AND recalls them."""
    pipe = _build_pipeline(tmp_path)
    state = np.array([0.0, 0.0])
    for _ in range(6):
        pipe.execute(state, user_name="mem")
    stats = pipe.memory_report()
    assert stats["inserted"] > 0
    assert stats["memory_consumed"] > 0


def test_memory_persists_across_restart(tmp_path):
    """Memory survives a pipeline shutdown + rebuild at the same path."""
    pipe = _build_pipeline(tmp_path)
    state = np.array([0.0, 0.0])
    for _ in range(4):
        pipe.execute(state, user_name="mem")
    pipe.shutdown()
    pipe2 = _build_pipeline(tmp_path)
    assert pipe2.memory_report()["total"] > 0


def test_governance_suppressed_cycle_not_recorded(tmp_path):
    """A governance-blocked cycle must not enter decision memory."""
    pipe = _build_pipeline(tmp_path)
    controller = pipe._memory_controller
    before = controller.stats()["inserted"]
    recorded = controller.record_outcome(
        cycle=1, intent_type="navigate", outcome_success=False,
        governance_blocked=True,
    )
    assert recorded is False
    assert controller.stats()["inserted"] == before
    assert controller.rejected_governance_suppression >= 1


def test_memory_consumption_artifact_written(tmp_path, monkeypatch):
    """shutdown() writes the consumption artifact with its real provenance.

    A SHORT run must NOT claim sustained consumption: the artifact declares the
    cycle span and requires min_cycles_required before
    consumed_in_real_cycles is True. This is the honesty guard — a 5-cycle test
    records 5 cycles, not a pass.

    The test runs the pipeline in an isolated cwd so it never clobbers the
    repo's real measured artifact (telos/audit/memory_consumption.json).
    """
    import json
    import os
    # Isolate the artifact path: the runtime writes repo-relative, so run from
    # a temp cwd and create the expected directory structure there. The write
    # itself is opt-in, so the repo's real measured artifact is never touched.
    os.makedirs(os.path.join(str(tmp_path), "telos", "audit"), exist_ok=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELOS_WRITE_MEMORY_ARTIFACT", "1")
    pipe = _build_pipeline(tmp_path)
    state = np.array([0.0, 0.0])
    for _ in range(5):
        pipe.execute(state, user_name="mem")
    pipe.shutdown()
    path = os.path.join(str(tmp_path), "telos", "audit", "memory_consumption.json")
    assert os.path.isfile(path)
    with open(path) as f:
        data = json.load(f)
    assert data["memory_consumed"] > 0
    assert data["source"] == "runtime_pipeline"
    assert data["cycles_observed"] == 5
    assert data["min_cycles_required"] >= 50
    assert data["consumed_in_real_cycles"] is False, \
        "a 5-cycle test run must not claim sustained consumption"


