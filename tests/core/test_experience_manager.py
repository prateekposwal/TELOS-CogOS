"""Tests for ExperienceManager — external learning observer that indexes
successful trajectories into the SkillLibrary and records user interactions."""

import json
import numpy as np

from types import SimpleNamespace

from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.experience_manager import (
    ExperienceConfig,
    ExperienceManager,
)
from telos.core.ledger.world_ledger import WorldLedger
from telos.core.types import PipelinePhase, PipelineResult


def make_result(health=0.8, trajectory=True, state=None, worlds=3, cycle=1,
                budget=10.0):
    trace = SimpleNamespace(
        world_state_snapshot=np.array([0.0, 1.0]) if state is None else state,
        cycle_id=cycle,
        budget_consumed_ms=budget,
    ) if trajectory else None
    return PipelineResult(
        selected_trajectory=SimpleNamespace(
            intent_type="explore",
            confidence=0.9,
            params={"k": 1},
        ) if trajectory else None,
        health_score=health,
        pipeline_phase=PipelinePhase.COMPLETE,
        worlds_generated=worlds,
        decision_trace=trace,
    )


class TestConfig:
    def test_defaults(self):
        cfg = ExperienceConfig()
        assert cfg.utility_threshold == 0.1
        assert cfg.index_interval == 1
        assert cfg.max_skills == 100
        assert cfg.log_level == "INFO"


class TestObserve:
    def test_rejects_no_trajectory(self):
        manager = ExperienceManager(SkillLibrary())
        assert manager.observe(make_result(trajectory=False)) is None
        assert manager.stats["total_observations"] == 1
        assert manager._observations[0]["reason"] == "no_trajectory"
        assert manager.stats["skills_indexed"] == 0

    def test_rejects_below_threshold(self):
        manager = ExperienceManager(SkillLibrary())
        assert manager.observe(make_result(health=0.05)) is None
        assert manager._observations[0]["reason"] == "below_threshold"
        assert manager._observations[0]["indexed"] is False

    def test_indexes_successful_result(self):
        lib = SkillLibrary()
        manager = ExperienceManager(lib)
        skill = manager.observe(make_result(health=0.9))
        assert skill is not None
        assert skill.skill_id.startswith("skill_")
        assert lib.skill_count == 1
        assert skill.utility_score == 0.9
        assert skill.trajectory["intent_type"] == "explore"
        assert manager.stats["skills_indexed"] == 1
        assert manager.stats["indexed_rate"] == 1.0

    def test_fingerprint_from_state_snapshot(self):
        state = np.array([3.0, 4.0])
        manager = ExperienceManager(SkillLibrary())
        result = make_result(state=state)
        result.decision_trace.world_state_snapshot = state
        skill = manager.observe(result)
        import hashlib
        expected = hashlib.md5(state.tobytes()).hexdigest()[:12]
        assert skill.fingerprint == expected

    def test_null_state_fingerprint_when_no_trace(self):
        manager = ExperienceManager(SkillLibrary())
        assert manager._compute_fingerprint(None) == "null_state"

    def test_interval_gating(self):
        manager = ExperienceManager(
            SkillLibrary(), config=ExperienceConfig(index_interval=2)
        )
        assert manager.observe(make_result(cycle=1)) is None
        assert manager._observations[-1]["reason"] == "not_interval"
        skill = manager.observe(make_result(cycle=2))
        assert skill is not None
        assert manager.stats["skills_indexed"] == 1

    def test_cycle_count_increments_on_rejections(self):
        manager = ExperienceManager(SkillLibrary())
        manager.observe(make_result(trajectory=False))
        manager.observe(make_result(health=0.05))
        assert manager._cycle_count == 2


class TestObserveUserInteraction:
    def test_writes_to_ledger(self):
        ledger = WorldLedger()
        manager = ExperienceManager(SkillLibrary())
        manager.observe_user_interaction("Prateek", "execute", 0.8, 4, ledger)
        profile = ledger.get_user_profile("Prateek")
        assert profile is not None
        assert profile.last_intent == "execute"
        assert profile.total_interactions == 1


class TestIndexRecent:
    def test_missing_dir_returns_zero(self, tmp_path):
        manager = ExperienceManager(SkillLibrary())
        assert manager.index_recent(str(tmp_path / "nope")) == 0

    def test_indexes_traces_from_checkpoints(self, tmp_path):
        lib = SkillLibrary()
        manager = ExperienceManager(lib)
        good = {"health_score": 0.9, "intent_type": "explore",
                "fp": "abc", "confidence": 0.8, "cycle_id": 7}
        bad = {"health_score": 0.02, "intent_type": "explore"}
        cp_dir = tmp_path / "checkpoints"
        cp_dir.mkdir()
        (cp_dir / "checkpoint_b.json").write_text(json.dumps({"traces": [bad]}) or "")
        (cp_dir / "checkpoint_a.json").write_text(json.dumps({"decision_traces": [good]}))
        (cp_dir / "checkpoint_z.json").write_text(json.dumps({"traces": [good]}))

        n = manager.index_recent(str(cp_dir), cycles=2)
        # two most-recent files (a and z by mtime order) both have good traces
        assert n >= 1
        assert manager.stats["skills_indexed"] >= 1

    def test_index_recent_only_counted_for_high_utility(self, tmp_path):
        lib = SkillLibrary()
        manager = ExperienceManager(lib)
        cp_dir = tmp_path / "checkpoints"
        cp_dir.mkdir()
        (cp_dir / "checkpoint_a.json").write_text(
            json.dumps({"decision_traces": [{"health_score": 0.01}]})
        )
        assert manager.index_recent(str(cp_dir), cycles=1) == 0


class TestStats:
    def test_stats_shape(self):
        manager = ExperienceManager(SkillLibrary())
        s = manager.stats
        assert set(s) == {
            "total_observations", "skills_indexed",
            "skill_library_size", "indexed_rate",
        }
        assert s["skill_library_size"] == 0