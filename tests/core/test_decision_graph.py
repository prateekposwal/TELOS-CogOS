"""
DecisionGraph tests — the executable layer (typed assumptions + propagation).

Verifies `affected_decisions(G)` traverses assumption→decision and propagating
decision→decision edges, excludes guarded (non-propagating) edges, round-trips
through the store, and is queryable from the CLI.
"""

import numpy as np
import pytest

from telos.core.handoff import (
    DecisionRecord, DecisionStore, AssumptionRegistry, DecisionGraph,
)
from telos.tools import decision_records as dr_cli


def _rec(decision_id, *, refs=None, depends_on=None, guarded=None):
    return DecisionRecord(
        decision_id=decision_id,
        assumption_refs=list(refs or []),
        depends_on=list(depends_on or []),
        guarded_deps=list(guarded or []),
        decision={"intent_type": "x"},
    )


def _graph():
    """D1,D2 depend on G1; D1->D2 propagates; D1->D3 is GUARDED; D2->D4 propagates."""
    registry = AssumptionRegistry({"G1": "peak writes stay under 10k/s", "G2": "EU latency < 200ms"})
    records = [
        _rec("D1", refs=["G1"]),
        _rec("D2", refs=["G1"], depends_on=["D1"]),
        _rec("D3", refs=["G2"], depends_on=["D1"], guarded=["D1"]),
        _rec("D4", depends_on=["D2"]),
        _rec("D5", depends_on=["D3"]),
    ]
    return DecisionGraph(records, registry)


def test_registry_round_trip(tmp_path):
    reg = AssumptionRegistry()
    reg.add("G1", "a")
    reg.add("G2", "b")
    assert reg.get("G1") == "a" and "G1" in reg and len(reg) == 2
    path = str(tmp_path / "assumptions.json")
    reg.save(path)
    assert AssumptionRegistry.load(path).to_dict() == {"G1": "a", "G2": "b"}


def test_affected_decisions_direct_and_transitive():
    g = _graph()
    assert g.direct_dependents("G1") == ["D1", "D2"]
    # D1->D2->D4 propagate; D1->D3 is guarded (excluded); D5 (via D3) not reached.
    assert g.affected_decisions("G1") == ["D1", "D2", "D4"]


def test_guarded_edge_does_not_propagate():
    g = _graph()
    assert "D3" not in g.affected_decisions("G1")   # guarded
    assert "D5" not in g.affected_decisions("G1")   # downstream of a guarded edge
    # D3 IS directly affected by G2, and D3->D5 propagates.
    assert g.affected_decisions("G2") == ["D3", "D5"]


def test_explain_shape():
    info = _graph().explain("G1")
    assert info["assumption"] == "G1"
    assert info["direct"] == ["D1", "D2"]
    assert info["transitive"] == ["D4"]
    assert info["affected"] == ["D1", "D2", "D4"]


def test_record_round_trips_graph_fields():
    r = _rec("D1", refs=["G1"], depends_on=["D0"], guarded=["D0"])
    back = DecisionRecord.from_dict(r.to_dict())
    assert back.assumption_refs == ["G1"]
    assert back.depends_on == ["D0"]
    assert back.guarded_deps == ["D0"]


def test_store_graph_integration(tmp_path):
    store = DecisionStore(str(tmp_path))
    reg = AssumptionRegistry({"G1": "peak writes under 10k/s"})
    store.write_registry(reg)
    store.write(_rec("D1", refs=["G1"]))
    store.write(_rec("D2", refs=["G1"], depends_on=["D1"]))
    store.write(_rec("D3", refs=["G2"]))                 # unrelated
    # Registry file must not be mistaken for a decision.
    assert store.count() == 3
    g = store.graph()
    assert g.affected_decisions("G1") == ["D1", "D2"]
    assert g.registry.get("G1") == "peak writes under 10k/s"


def test_cli_affected(tmp_path, capsys):
    store = DecisionStore(str(tmp_path))
    store.write_registry(AssumptionRegistry({"G1": "peak writes under 10k/s"}))
    store.write(_rec("D1", refs=["G1"]))
    store.write(_rec("D2", refs=["G1"], depends_on=["D1"]))
    rc = dr_cli.main(["--root", str(tmp_path), "affected", "G1", "--explain"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "affected_decisions -> ['D1', 'D2']" in out
    assert "direct     : ['D1', 'D2']" in out
    assert dr_cli.main(["--root", str(tmp_path), "affected", "GX"]) == 1
