"""
RelationalContext — five-dimensional relational reasoning state.

Honest contract coverage (telos/core/reasoning/relational.py):
  - Dataclass defaults: trust/authority/collaboration/responsibility 0.5,
    dependency 0.0; custom construction.
  - relational_coherence property (placeholder contract = 1.0).
  - to_dict serializes all five dimensions; from_dict round-trips and falls
    back to defaults for missing keys (forward/backward compatibility).
"""
from telos.core.reasoning.relational import RelationalContext


class TestDefaults:
    def test_default_construction(self):
        rc = RelationalContext()
        assert rc.trust == 0.5
        assert rc.authority == 0.5
        assert rc.collaboration == 0.5
        assert rc.dependency == 0.0
        assert rc.responsibility == 0.5

    def test_custom_construction(self):
        rc = RelationalContext(trust=0.9, authority=0.1, collaboration=0.7,
                               dependency=0.3, responsibility=0.8)
        assert (rc.trust, rc.authority, rc.collaboration,
                rc.dependency, rc.responsibility) == (0.9, 0.1, 0.7, 0.3, 0.8)


class TestCoherence:
    def test_relational_coherence_placeholder(self):
        rc = RelationalContext()
        assert rc.relational_coherence == 1.0

    def test_coherence_constant_across_states(self):
        assert RelationalContext(trust=0.0, dependency=1.0).relational_coherence == 1.0


class TestSerialization:
    def test_to_dict_exact_keys(self):
        rc = RelationalContext(trust=0.9, authority=0.1, collaboration=0.7,
                               dependency=0.3, responsibility=0.8)
        d = rc.to_dict()
        assert set(d) == {"trust", "authority", "collaboration",
                          "dependency", "responsibility"}
        assert d == {
            "trust": 0.9, "authority": 0.1, "collaboration": 0.7,
            "dependency": 0.3, "responsibility": 0.8,
        }

    def test_from_dict_roundtrip(self):
        rc = RelationalContext(trust=0.4, authority=0.6, collaboration=0.2,
                               dependency=0.1, responsibility=0.9)
        assert RelationalContext.from_dict(rc.to_dict()) == rc

    def test_from_dict_missing_keys_fall_back_to_defaults(self):
        rc = RelationalContext.from_dict({"trust": 0.9})
        assert rc.trust == 0.9
        assert rc.authority == 0.5
        assert rc.collaboration == 0.5
        assert rc.dependency == 0.0
        assert rc.responsibility == 0.5

    def test_from_dict_empty_returns_defaults(self):
        rc = RelationalContext.from_dict({})
        assert rc == RelationalContext()

    def test_from_dict_coerces_types(self):
        rc = RelationalContext.from_dict({"trust": "0.7"})
        assert rc.trust == 0.7
