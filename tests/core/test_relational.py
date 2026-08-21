"""Contract tests for RelationalContext — the five relational dimensions
(trust, authority, collaboration, dependency, responsibility) that govern
how TELOS interacts with users, agents, and itself."""
from telos.core.reasoning.relational import RelationalContext


def test_defaults_are_documented_values():
    rc = RelationalContext()
    assert rc.trust == 0.5
    assert rc.authority == 0.5
    assert rc.collaboration == 0.5
    assert rc.dependency == 0.0
    assert rc.responsibility == 0.5


def test_custom_values_roundtrip_via_to_dict():
    rc = RelationalContext(trust=0.9, dependency=0.4)
    d = rc.to_dict()
    assert d["trust"] == 0.9
    assert d["dependency"] == 0.4


def test_from_dict_restores_and_fills_defaults():
    rc = RelationalContext.from_dict({"trust": 0.1, "responsibility": 0.8})
    assert rc.trust == 0.1
    assert rc.responsibility == 0.8
    assert rc.authority == 0.5  # missing key falls back to default


def test_relational_coherence_placeholder():
    assert RelationalContext().relational_coherence == 1.0