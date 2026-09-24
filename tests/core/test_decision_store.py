"""
File-backed decision exchange tests.

Proves the exchange loop: a record written by one context is found,
reconstructed, queried, and revalidated by ANOTHER (a fresh store instance,
standing in for a different process/agent) — no human ferrying the JSON.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from telos.core.handoff import (
    DecisionStore, DecisionRecord, DecisionRecorder, RecordStatus,
    RevalidationCondition,
)
from telos.world.evidence import ValidationStatus
from telos.world.epistemic import RealityGapTracker
from telos.tools import decision_records as dr_cli


def _record(decision_id="cycle-1-reflex", *, intent="reflex", objective="reach goal",
            domain="gridworld", cycle=1, status=RecordStatus.OPEN, ts=1.0):
    """A minimal record for store tests."""
    r = DecisionRecord(
        decision_id=decision_id, objective=objective, owner="Prateek",
        timestamp=ts, decision={"intent_type": intent}, confidence=0.8,
        provenance={"schema_version": "1.0", "cycle": cycle, "domain": domain},
        status=status,
    )
    r.revalidation_conditions.append(
        RevalidationCondition(condition="prediction holds", watches="world_model"))
    return r


def _falsified_gap():
    tr = RealityGapTracker()
    for _ in range(5):
        tr.record("m", np.array([0.0, 0.0]), np.array([10.0, 10.0]))
    return tr.model("m")


# ── Write / read across contexts ─────────────────────────────────────────────

def test_write_then_read_from_a_fresh_store(tmp_path):
    DecisionStore(str(tmp_path)).write(_record())
    # A DIFFERENT store instance (another process/agent) reads it.
    other = DecisionStore(str(tmp_path))
    loaded = other.load("cycle-1-reflex")
    assert loaded is not None
    assert loaded.decision["intent_type"] == "reflex"
    assert loaded.objective == "reach goal"


def test_all_and_index(tmp_path):
    store = DecisionStore(str(tmp_path))
    store.write(_record("a", intent="reflex", ts=1.0))
    store.write(_record("b", intent="explore", ts=2.0))
    assert [r.decision_id for r in store.all()] == ["a", "b"]
    idx = store.index()
    assert {row["decision_id"] for row in idx} == {"a", "b"}
    assert idx[0]["intent_type"] == "reflex"


def test_find_filters(tmp_path):
    store = DecisionStore(str(tmp_path))
    store.write(_record("a", intent="reflex", domain="gridworld", ts=1.0))
    store.write(_record("b", intent="explore", domain="gridworld", ts=2.0))
    store.write(_record("c", intent="reflex", domain="devdomain", ts=3.0))
    assert [r.decision_id for r in store.find(intent_type="reflex")] == ["a", "c"]
    assert [r.decision_id for r in store.find(domain="devdomain")] == ["c"]
    assert [r.decision_id for r in store.find(intent_type="reflex", limit=1)] == ["a"]


def test_id_is_sanitized(tmp_path):
    store = DecisionStore(str(tmp_path))
    store.write(_record("weird/id with spaces"))
    assert store.count() == 1
    assert store.load("weird/id with spaces") is not None


# ── Revalidation keeps the exchange current ──────────────────────────────────

def test_revalidate_persists_falsification(tmp_path):
    store = DecisionStore(str(tmp_path))
    store.write(_record("a"))
    changed = store.revalidate(_falsified_gap(), cycle=42)
    assert changed == ["a"]
    # A fresh reader sees the updated status on disk.
    reloaded = DecisionStore(str(tmp_path)).load("a")
    assert reloaded.status == RecordStatus.FALSIFIED
    assert reloaded.revalidation_conditions[0].status == ValidationStatus.FALSIFIED
    assert reloaded.revalidation_conditions[0].last_checked_cycle == 42


def test_revalidate_no_change_returns_empty(tmp_path):
    store = DecisionStore(str(tmp_path))
    r = _record("a")
    r.revalidation_conditions[0].status = ValidationStatus.FALSIFIED  # already there
    r.status = RecordStatus.FALSIFIED
    store.write(r)
    assert store.revalidate(_falsified_gap(), cycle=9) == []


def test_revalidate_only_marks_selected_condition(tmp_path):
    store = DecisionStore(str(tmp_path))
    r = _record("a")
    r.revalidation_conditions.append(
        RevalidationCondition(condition="multi-region writes required", watches="roadmap"))
    store.write(r)
    changed = store.revalidate(_falsified_gap(), cycle=7,
                               only=lambda c: "prediction" in c.condition)
    assert changed == ["a"]
    reloaded = store.load("a")
    assert reloaded.revalidation_conditions[0].status == ValidationStatus.FALSIFIED
    assert reloaded.revalidation_conditions[1].status == ValidationStatus.UNVALIDATED


# ── Lifecycle ────────────────────────────────────────────────────────────────

def test_supersede_links_replacement(tmp_path):
    store = DecisionStore(str(tmp_path))
    store.write(_record("old"))
    assert store.supersede("old", "new") is True
    reloaded = store.load("old")
    assert reloaded.status == RecordStatus.SUPERSEDED
    assert reloaded.provenance["superseded_by"] == "new"
    assert store.supersede("missing", "new") is False


# ── Recorder integration ─────────────────────────────────────────────────────

def _ctx(intent_type="reflex", cycle=1):
    verdict = SimpleNamespace(validated=True, escalation_requested=False,
                              decision_integrity=1.0, mission_drift=0.1,
                              blocking_validator=None)
    return SimpleNamespace(
        cycle_count=cycle, state=np.array([1.0, 2.0]), user_name="Prateek",
        selected_intent=SimpleNamespace(intent_type=intent_type, confidence=0.8, params={}),
        selected_action=np.array([0.0, 1.0]),
        strategic_options_data=[], verdict=verdict, firewall_blocked=False,
        representation="spatial",
        domain_facts=SimpleNamespace(constraints=[], domain="gridworld"),
    )


def test_recorder_persists_to_store(tmp_path):
    store = DecisionStore(str(tmp_path))
    rec = DecisionRecorder(store=store)
    pl = SimpleNamespace(config=SimpleNamespace(mission_name="nav"))
    assert rec.observe(pl, _ctx("reflex")) is not None
    assert store.count() == 1
    assert DecisionStore(str(tmp_path)).load("cycle-1-reflex") is not None


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_list_and_show(tmp_path, capsys):
    store = DecisionStore(str(tmp_path))
    store.write(_record("a", intent="reflex"))
    root = str(tmp_path)

    assert dr_cli.main(["--root", root, "list"]) == 0
    out = capsys.readouterr().out
    assert "reflex" in out and "1 record(s)" in out

    assert dr_cli.main(["--root", root, "show", "a"]) == 0
    md = capsys.readouterr().out
    assert "## Decision" in md and "## Revalidation conditions" in md

    assert dr_cli.main(["--root", root, "show", "missing"]) == 1
