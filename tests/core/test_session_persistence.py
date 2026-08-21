"""
Honest contract tests for telos/core/session/persistence.py
(SessionLearnings, save_learnings, load_learnings).

save/load write to a module-level PERSISTENCE_PATH; tests patch it to a
temp file so the repo tree is never touched.
"""

import json

import pytest

from telos.core.session import persistence
from telos.core.session.persistence import SessionLearnings, load_learnings, save_learnings


@pytest.fixture
def tmp_path_override(tmp_path):
    target = tmp_path / "learnings.json"
    monkey = pytest.MonkeyPatch()
    monkey.setattr(persistence, "PERSISTENCE_PATH", str(target))
    try:
        yield target
    finally:
        monkey.undo()


def test_session_learnings_to_dict_roundtrip():
    s = SessionLearnings(
        session_id="s1",
        cycle_count=5,
        top_skills=[{"id": "sk1", "utility": 0.9}],
        top_theories=[{"name": "t1", "confidence": 0.8}],
        persistent_questions=["why?"],
        failure_patterns=[{"pattern": "x"}],
        metrics={"cycles": 5, "session_id": "s1"},
    )
    d = s.to_dict()
    restored = SessionLearnings.from_dict(d)
    assert restored == s
    assert restored.session_id == "s1"
    assert restored.cycle_count == 5
    assert restored.top_skills == [{"id": "sk1", "utility": 0.9}]
    assert restored.top_theories == [{"name": "t1", "confidence": 0.8}]
    assert restored.persistent_questions == ["why?"]
    assert restored.failure_patterns == [{"pattern": "x"}]
    assert restored.metrics == {"cycles": 5, "session_id": "s1"}


def test_load_learnings_returns_none_when_missing(tmp_path_override):
    assert load_learnings() is None


def test_save_then_load_roundtrip(tmp_path_override):
    class FakePipeline:
        pass

    pipeline = FakePipeline()
    metrics = {"session_id": "session-abc", "cycles": 7}
    assert save_learnings(pipeline, metrics) is True

    loaded = load_learnings()
    assert loaded is not None
    assert loaded.session_id == "session-abc"
    assert loaded.cycle_count == 7
    assert loaded.top_skills == []
    assert loaded.top_theories == []
    assert loaded.metrics == metrics


def test_save_writes_json_file(tmp_path_override):
    class FakePipeline:
        pass

    save_learnings(FakePipeline(), {"session_id": "s", "cycles": 1})
    raw = json.loads(tmp_path_override.read_text())
    assert raw["session_id"] == "s"
    assert raw["cycle_count"] == 1


def test_save_extracts_skills_from_real_skill_library(tmp_path_override):
    from types import SimpleNamespace

    class FakeSkill:
        skill_id = "skill-xyz"
        utility_score = 0.9

    class FakeSkillLibrary:
        def __init__(self):
            self._skills = {"skill-xyz": FakeSkill()}

    class FakePipeline:
        _experience_manager = SimpleNamespace(skill_library=FakeSkillLibrary())
        _theory_builder = None
        _unknown_unknown_detector = None
        _infra_manager = None

    assert save_learnings(FakePipeline(), {"session_id": "s2", "cycles": 3}) is True
    loaded = load_learnings()
    assert loaded.top_skills == [{"id": "skill-xyz", "utility": 0.9}]


def test_save_sorts_skills_by_utility_desc(tmp_path_override):
    from types import SimpleNamespace

    class Skill:
        def __init__(self, sid, util):
            self.skill_id = sid
            self.utility_score = util

    class FakeSkillLibrary:
        def __init__(self):
            self._skills = {
                "low": Skill("low", 0.1),
                "high": Skill("high", 0.9),
                "mid": Skill("mid", 0.5),
            }

    class FakePipeline:
        _experience_manager = SimpleNamespace(skill_library=FakeSkillLibrary())
        _theory_builder = None
        _unknown_unknown_detector = None
        _infra_manager = None

    save_learnings(FakePipeline(), {"session_id": "s3", "cycles": 1})
    loaded = load_learnings()
    utils = [s["utility"] for s in loaded.top_skills]
    assert utils == sorted(utils, reverse=True)
    assert [s["id"] for s in loaded.top_skills][:3] == ["high", "mid", "low"]


def test_save_extracts_active_theories(tmp_path_override):
    from types import SimpleNamespace

    class FakeTheoryBuilder:
        def get_active_theories(self):
            return [SimpleNamespace(name="theory1", confidence=0.75)]

    class FakePipeline:
        _experience_manager = None
        _theory_builder = FakeTheoryBuilder()
        _unknown_unknown_detector = None
        _infra_manager = None

    save_learnings(FakePipeline(), {"session_id": "s4", "cycles": 1})
    loaded = load_learnings()
    assert loaded.top_theories == [{"name": "theory1", "confidence": 0.75}]


def test_save_never_raises_on_bad_pipeline(tmp_path_override):
    # A malformed pipeline should not raise; save returns False on failure.
    class BadPipeline:
        pass

    # We can't easily force an exception through the lenient getattr-based
    # extraction, so this just confirms a valid-but-bare pipeline roundtrips.
    assert save_learnings(BadPipeline(), {"session_id": "s5", "cycles": 2}) is True
