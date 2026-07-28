from dataclasses import FrozenInstanceError
import pytest
from telos.core.identity.system_self import IdentityCore, IdentityNarrative
from telos.core.genesis import ANCHOR


class TestIdentityCore:
    def test_axioms_count(self):
        core = IdentityCore()
        assert core.axioms_count == 42

    def test_core_is_frozen(self):
        core = IdentityCore()
        with pytest.raises(FrozenInstanceError):
            core.axioms_count = 0

    def test_core_recognizes_values(self):
        core = IdentityCore()
        assert core.recognizes("curiosity")
        assert core.recognizes("integrity")
        assert core.recognizes("truth_seeking")
        assert not core.recognizes("greed")

    def test_genesis_anchor_has_creator(self):
        assert ANCHOR.creator == "Prateek"
        assert ANCHOR.axioms_count == 42

    def test_birth_timestamp_set(self):
        core = IdentityCore()
        assert core.birth_timestamp > 0

    def test_genesis_mood_default(self):
        core = IdentityCore()
        assert core.genesis_mood == "curious"


class TestIdentityNarrative:
    def test_default_markers(self):
        n = IdentityNarrative()
        assert "nascent" in n.markers
        assert "exploring" in n.markers

    def test_add_marker(self):
        n = IdentityNarrative()
        n.add_marker("test_marker")
        assert "test_marker" in n.markers

    def test_record_completed_mission(self):
        n = IdentityNarrative()
        n.record_completed_mission("m1")
        assert "m1" in n.completed_missions
        assert "m1" in n.mission_history

    def test_to_dict(self):
        n = IdentityNarrative()
        n.add_marker("resilient")
        d = n.to_dict()
        assert "role" in d
        assert "markers" in d
        assert "resilient" in d["markers"]
