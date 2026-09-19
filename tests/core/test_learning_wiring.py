"""Live-loop wiring: verified SkillAcquisition + Curriculum are exercised by
the real pipeline, not only by the learning_curve harness.

These tests are the regression lock for the wiring itself (Λ6.7): the
mechanism must have a live construction site and a live consumption site.
They assert MEASURED counters (proposals/verifications/attached tasks),
never an import.
"""

import numpy as np

from telos.core.ledger.experience_manager import (
    ExperienceConfig, ExperienceManager,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.learning.acquisition import SkillAcquisition
from telos.core.types import PipelineConfig, PipelineResult, PipelinePhase


def _result(health, state, intent="explore"):
    from types import SimpleNamespace
    trace = SimpleNamespace(
        world_state_snapshot=np.asarray(state, dtype=float),
        cycle_id=1, budget_consumed_ms=1.0,
    )
    return PipelineResult(
        selected_trajectory=SimpleNamespace(
            intent_type=intent, confidence=0.9, params={}),
        health_score=health,
        pipeline_phase=PipelinePhase.COMPLETE,
        worlds_generated=2,
        decision_trace=trace,
    )


class TestVerifiedAcquisition:
    def test_default_off_is_direct_index(self):
        em = ExperienceManager(SkillLibrary())
        assert em.acquisition is None
        skill = em.observe(_result(0.9, [0.0, 0.0]))
        assert skill is not None and em.skill_library.skill_count == 1

    def test_proposes_then_verifies_on_later_match(self):
        lib = SkillLibrary()
        em = ExperienceManager(
            lib, ExperienceConfig(verified_acquisition=True,
                                  acquisition_min_outcome=0.6))
        assert isinstance(em.acquisition, SkillAcquisition)
        # Cycle 1: promising -> candidate only, NOT admitted.
        assert em.observe(_result(0.9, [1.0, 1.0])) is None
        assert lib.skill_count == 0
        assert em.acquisition.stats()["proposed"] == 1
        # Cycle 2: SAME situation confirms -> admitted.
        skill = em.observe(_result(0.8, [1.0, 1.0]))
        assert skill is not None
        assert lib.skill_count == 1
        assert em.acquisition.stats()["acquired"] == 1

    def test_unverified_candidate_never_admitted(self):
        lib = SkillLibrary()
        em = ExperienceManager(
            lib, ExperienceConfig(verified_acquisition=True,
                                  acquisition_min_outcome=0.6))
        em.observe(_result(0.9, [2.0, 2.0]))       # propose
        # A DIFFERENT situation / weak outcome never verifies the candidate.
        em.observe(_result(0.2, [3.0, 3.0]))
        assert lib.skill_count == 0
        assert em.acquisition.stats()["acquired"] == 0


class TestLivePipelineWiring:
    def _build(self, tmp_path, **overrides):
        from telos_task import (GridAdpt, GridSim, DEFAULT_BLOCKED,
                                DEFAULT_REWARDS, MISSION_NAME,
                                MISSION_DESCRIPTION)
        from telos.core.runtime import TelosV14Pipeline
        from telos.core.streams.implementations import (
            ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
            TheoryStream)
        from telos.core.streams.inquiry_stream import InquiryStream
        from telos.core.simulation import CounterfactualEngine
        sim = GridSim(blocked=set(DEFAULT_BLOCKED),
                      rewards=dict(DEFAULT_REWARDS))
        cfg = dict(adapter=GridAdpt(), simulator=sim, compute_budget_ms=100.0,
                   state_dim=2, n_worlds=10, horizon=5,
                   mission_name=MISSION_NAME,
                   mission_description=MISSION_DESCRIPTION,
                   checkpoint_path=str(tmp_path), checkpoint_every_n=100000,
                   deterministic_seed=42)
        cfg.update(overrides)
        pipe = TelosV14Pipeline(PipelineConfig(**cfg))
        lib = SkillLibrary()
        em = ExperienceManager(
            lib, ExperienceConfig(
                utility_threshold=0.1, index_interval=1,
                verified_acquisition=bool(overrides.get("verified_learning", False))))
        eng = CounterfactualEngine(sim)
        ts = TheoryStream(lib, theory_builder=getattr(pipe, '_theory_builder', None),
                          curriculum=getattr(pipe, 'curriculum', None))
        for st in (ReflexStream(lib), PerceptionStream(lib), MemoryStream(lib),
                   PlanningStream(lib, sim_engine=eng), InquiryStream(lib), ts):
            pipe.register_stream(st)
        return pipe, em, ts

    def test_live_pipeline_exercises_verified_acquisition(self, tmp_path):
        pipe, em, ts = self._build(tmp_path, verified_learning=True)
        for _ in range(40):
            em.observe(pipe.execute(np.array([0.0, 0.0]), user_name="t"))
        stats = em.acquisition.stats()
        assert stats["proposed"] > 0, "SkillAcquisition was never exercised"
        assert stats["acquired"] > 0, "no skill was ever verified+admitted"
        assert em.skill_library.skill_count > 0

    def test_live_pipeline_exercises_curriculum(self, tmp_path):
        pipe, em, ts = self._build(tmp_path, learning_curriculum=True)
        for _ in range(40):
            em.observe(pipe.execute(np.array([0.0, 0.0]), user_name="t"))
        assert pipe.curriculum is not None
        assert len(pipe.curriculum._tasks) > 0, "curriculum never populated"
        assert ts.curriculum_tasks_attached > 0, (
            "TheoryStream never consumed the curriculum frontier")

    def test_defaults_are_inert(self, tmp_path):
        pipe, em, ts = self._build(tmp_path)  # both flags default False
        assert pipe.curriculum is None
        assert em.acquisition is None
        for _ in range(5):
            em.observe(pipe.execute(np.array([0.0, 0.0]), user_name="t"))
        assert ts.curriculum_tasks_attached == 0
