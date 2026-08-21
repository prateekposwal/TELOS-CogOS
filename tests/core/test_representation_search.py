"""Tests for RepresentationSearch — register, record_discovery, productivity,
should_switch, switch_to, and to_dict contract."""

from telos.core.reasoning.representation_search import (
    RepresentationType,
    RepresentationCandidate,
    RepresentationSearch,
)


class TestRepresentationType:
    def test_all_types(self):
        values = {t.value for t in RepresentationType}
        assert values == {
            "symbolic", "spatial", "temporal", "graph", "statistical", "analogical",
        }


class TestRepresentationCandidate:
    def test_defaults(self):
        c = RepresentationCandidate(rep_type=RepresentationType.GRAPH)
        assert c.age == 0
        assert c.discoveries_produced == 0
        assert c.total_effort == 0.0
        assert c.bridge_count == 0
        assert c.productivity == 0.0

    def test_productivity_is_discoveries_per_effort(self):
        c = RepresentationCandidate(rep_type=RepresentationType.GRAPH,
                                    discoveries_produced=3, total_effort=2.0)
        assert c.productivity == 1.5

    def test_productivity_never_divides_by_zero(self):
        c = RepresentationCandidate(rep_type=RepresentationType.SYMBOLIC,
                                    discoveries_produced=0, total_effort=0.0)
        assert c.productivity == 0.0


class TestRegister:
    def test_register_first_candidate_becomes_current(self):
        rs = RepresentationSearch()
        rid = rs.register(RepresentationType.SYMBOLIC)
        assert rid == "rep_symbolic"
        assert rs._current == rid

    def test_register_keeps_existing_current(self):
        rs = RepresentationSearch()
        rid1 = rs.register(RepresentationType.SYMBOLIC)
        rs.register(RepresentationType.SPATIAL)
        assert rs._current == rid1


class TestRecordDiscovery:
    def test_accumulates_discoveries_and_effort(self):
        rs = RepresentationSearch()
        rid = rs.register(RepresentationType.ANALOGICAL)
        rs.record_discovery(rid, effort=1.0)
        rs.record_discovery(rid, effort=1.0)
        c = rs._candidates[rid]
        assert c.discoveries_produced == 2
        assert c.total_effort == 2.0
        assert c.productivity == 1.0

    def test_unknown_rid_is_silently_ignored(self):
        rs = RepresentationSearch()
        rs.record_discovery("rep_nope", effort=1.0)
        assert len(rs._candidates) == 0


class TestShouldSwitch:
    def test_no_candidates_returns_none(self):
        rs = RepresentationSearch()
        assert rs.should_switch() is None

    def test_high_productivity_current_does_not_switch(self):
        rs = RepresentationSearch()
        rid = rs.register(RepresentationType.SYMBOLIC)
        rs.record_discovery(rid, effort=1.0)
        rs.record_discovery(rid, effort=1.0)
        assert rs.should_switch(min_productivity=0.1) is None

    def test_switches_when_other_representation_dominates(self):
        rs = RepresentationSearch()
        rs.register(RepresentationType.SYMBOLIC)  # current, productivity 0
        rs.register(RepresentationType.SPATIAL)
        rs.record_discovery("rep_spatial", effort=1.0)  # productivity 1.0
        assert rs.should_switch(min_productivity=0.1) == "spatial"

    def test_best_must_more_than_double_current(self):
        rs = RepresentationSearch()
        rs.register(RepresentationType.SYMBOLIC)  # current, productivity 0
        rs.register(RepresentationType.SPATIAL)   # also productivity 0
        assert rs.should_switch(min_productivity=0.1) is None


class TestSwitchTo:
    def test_switching_updates_current_and_count(self):
        rs = RepresentationSearch()
        rs.register(RepresentationType.SYMBOLIC)
        rs.register(RepresentationType.TEMPORAL)
        assert rs.switch_to("rep_temporal") is True
        assert rs._current == "rep_temporal"
        assert rs._switch_count == 1

    def test_unknown_target_does_not_switch(self):
        rs = RepresentationSearch()
        rs.register(RepresentationType.SYMBOLIC)
        assert rs.switch_to("rep_nope") is False
        assert rs._switch_count == 0
        assert rs._current == "rep_symbolic"


class TestToDict:
    def test_to_dict_contract(self):
        rs = RepresentationSearch()
        rs.register(RepresentationType.SYMBOLIC)
        rs.register(RepresentationType.SPATIAL)
        rs.record_discovery("rep_symbolic", effort=1.0)
        d = rs.to_dict()
        assert d["current"] == "rep_symbolic"
        assert d["switches"] == 0
        assert set(d["candidates"].keys()) == {"rep_symbolic", "rep_spatial"}
        assert d["candidates"]["rep_symbolic"]["type"] == "symbolic"
        assert d["candidates"]["rep_symbolic"]["productivity"] == 1.0
        assert d["candidates"]["rep_symbolic"]["discoveries"] == 1
        assert d["candidates"]["rep_spatial"]["productivity"] == 0.0