"""Contract tests for the representation Ecosystem — niches with ecological
roles, their relations, and competition dynamics (representational ecology)."""
import pytest

from telos.core.ecology.ecosystem import (
    Ecosystem, Niche, EcosystemRelation, NicheRelation, EcologicalRole,
)


class TestNicheContract:
    def test_exhaustion_criteria(self):
        n = Niche(id="n1", name="x", marginal_discovery_rate=0.0,
                  exploration_depth=0.8)
        assert n.is_exhausted is True
        n2 = Niche(id="n2", name="y", marginal_discovery_rate=0.5,
                   exploration_depth=0.8)
        assert n2.is_exhausted is False


class TestEcosystem:
    def test_register_creates_niche(self):
        e = Ecosystem()
        n = e.register("symbolic", role=EcologicalRole.PIONEER, cycle=1)
        assert n.name == "symbolic"
        assert n.birth_cycle == 1
        assert e._niches[n.id] is n

    def test_register_links_parent_child(self):
        e = Ecosystem()
        parent = e.register("parent", cycle=1)
        child = e.register("child", parent_id=parent.id, cycle=2)
        assert child.parent_id == parent.id
        assert child.id in e._niches[parent.id].children_ids

    def test_relate_adds_relation(self):
        e = Ecosystem()
        a = e.register("a")
        b = e.register("b")
        e.relate(a.id, b.id, NicheRelation.SYMBIOTIC, strength=0.7)
        assert len(e._relations) == 1
        assert e._relations[0].relation == NicheRelation.SYMBIOTIC

    def test_apply_competition_reduces_rate(self):
        e = Ecosystem()
        a = e.register("a")
        b = e.register("b")
        a.marginal_discovery_rate = 0.1
        b.marginal_discovery_rate = 1.0
        e.relate(a.id, b.id, NicheRelation.COMPETING)
        before = a.marginal_discovery_rate
        e.apply_competition(a.id)
        assert a.marginal_discovery_rate < before

    def test_apply_competition_unknown_niche_noop(self):
        e = Ecosystem()
        e.apply_competition("does_not_exist")  # no crash

    def test_niche_fitness(self):
        e = Ecosystem()
        n = e.register("a")
        fitness = e.niche_fitness(n.id)
        assert 0.0 <= fitness <= 1.0