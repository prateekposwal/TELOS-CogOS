"""Live-data producer tests: the dashboard PRODUCES the data it serves.

Pattern under test: a dashboard must produce or attach to a live producer —
never read cold files that nothing writes. And everything the producer
exposes must be REAL (measured) data, JSON-clean, and persisted with edges.
"""
import json
import os
import tempfile
import time

import numpy as np
import pytest

import telos.dashboard.producer as prod_mod
from telos.dashboard.producer import DashboardProducer, json_clean


@pytest.fixture()
def isolated_paths(tmp_path, monkeypatch):
    """Point the producer at temp paths so tests never touch /tmp/telos_*.

    Args:
        tmp_path: pytest temp dir.
        monkeypatch: pytest monkeypatch for producer module globals.
    """
    monkeypatch.setattr(prod_mod, "CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    monkeypatch.setattr(prod_mod, "KNOWLEDGE_PATH", str(tmp_path / "knowledge.json"))
    monkeypatch.setattr(prod_mod, "LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(prod_mod, "IDENTITY_PATH", str(tmp_path / "identity.json"))
    monkeypatch.setattr(prod_mod, "PATTERN_PATH", str(tmp_path / "patterns.json"))
    return tmp_path


def test_producer_runs_real_cycles_and_populates_everything(isolated_paths):
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=3)
    p.start()
    try:
        time.sleep(2.5)  # burst + a couple of steady cycles
        snap = p.snapshot()
        assert snap["decisions"] >= 3, "producer must run real cycles"
        assert snap["traces"], "real traces must be recorded"
        assert snap["di"] >= 0.0 and snap["md"] >= 0.0, "measured DI/MD"
        assert snap["mood"] in ("neutral", "confident", "curious", "cautious",
                                "reflective", "engaged", "testing_boundaries",
                                "determined") or isinstance(snap["mood"], str)
        # Knowledge graph: real nodes AND edges
        assert snap["knowledge"]["nodes"] > 0, "knowledge nodes from real runs"
        assert snap["knowledge"]["edges"] > 0, "edges from real runs"
        assert snap["knowledge"]["domains"], "per-domain stats"
        # Position stays inside the 5x5 grid
        pos = snap["position"]
        assert 0 <= pos[0] <= 4 and 0 <= pos[1] <= 4, "agent must stay in bounds"
        # Recent decisions carry real intents
        assert snap["recent_decisions"], "story decisions present"
        assert snap["recent_decisions"][-1]["cycle_id"] == snap["decisions"]
    finally:
        p.stop()
    assert not p.is_running


def test_producer_persists_knowledge_with_edges(isolated_paths):
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=3)
    p.start()
    try:
        time.sleep(2.5)
        assert os.path.exists(prod_mod.KNOWLEDGE_PATH), "knowledge persisted"
        with open(prod_mod.KNOWLEDGE_PATH) as f:
            raw = json.load(f)
        assert len(raw.get("nodes", {})) > 0, "persisted nodes"
        assert len(raw.get("edges", {})) > 0, "persisted edges — the edge layer"
        # Checkpoints written per cycle
        cps = os.listdir(prod_mod.CHECKPOINT_DIR)
        assert any(c.startswith("checkpoint_") for c in cps), "checkpoints written"
    finally:
        p.stop()


def test_producer_checkpoints_are_json_clean_and_serializable(isolated_paths):
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=2)
    p.start()
    try:
        time.sleep(2.0)
        snap = p.snapshot()
        for t in snap["traces"]:
            # json_clean output must round-trip through strict json.dumps
            json.dumps(json_clean(t), allow_nan=False)
        # The API-serialized knowledge payload must be strict-JSON clean too
        json.dumps(snap["knowledge_payload"], allow_nan=False)
    finally:
        p.stop()


def test_producer_no_fabrication_snapshot_counts_match_cycles(isolated_paths):
    """Honesty: snapshot numbers must equal measured cycle counts, never
    invented larger values."""
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=2)
    p.start()
    try:
        time.sleep(2.0)
        snap = p.snapshot()
        assert snap["decisions"] == snap["producer"]["cycles"]
        assert len(snap["traces"]) == snap["decisions"]
        assert len(snap["recent_decisions"]) <= len(snap["traces"])
    finally:
        p.stop()


def test_json_clean_converts_numpy_and_nan():
    assert json_clean(np.float64(1.5)) == 1.5
    assert json_clean(np.bool_(True)) is True
    assert json_clean(np.array([1.0, 2.0])) == [1.0, 2.0]
    assert json_clean(float("nan")) is None
    assert json_clean(float("inf")) is None
    d = json_clean({"a": np.float64(2.0), "b": float("nan"), "c": [np.int64(3)]})
    assert d == {"a": 2.0, "b": None, "c": [3]}


def test_serialize_knowledge_shapes_nodes_and_edges():
    from telos.core.knowledge.graph import KnowledgeGraph
    kg = KnowledgeGraph()
    n1 = kg.record("navigation", "move_to_1_0", 0.9, provenance={"source": "test", "cycle": 1, "caller": "test"})
    n2 = kg.record("gridworld", "terrain_forest", 1.0, provenance={"source": "test", "cycle": 1, "caller": "test"})
    kg.add_edge(n1, n2, edge_type="at_location", weight=0.8)
    payload = prod_mod.serialize_knowledge(kg)
    assert len(payload["nodes"]) == 2
    assert payload["nodes"][0]["id"] and payload["nodes"][0]["label"]
    assert payload["edges"][0]["source"] == n1
    assert payload["edges"][0]["edge_type"] == "at_location"


def test_producer_score_is_bounded_system_score(isolated_paths):
    """The headline metric is a bounded 0-100 composite of measured signals,
    never a timer: after real cycles the score is in range, the components
    are exposed, and the score equals the formula re-evaluated from the
    same components (integrity: no invented number)."""
    from telos.dashboard.producer import system_score

    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=3)
    p.start()
    try:
        time.sleep(2.5)
        snap = p.snapshot()
        assert snap["decisions"] >= 3
        assert snap["score"] is None or (0.0 <= snap["score"] <= 100.0), \
            f"score {snap['score']} outside the defined range"
        assert snap["score_components"] is not None, "components must be exposed"
        c = snap["score_components"]
        assert set(c["weights"]) == {"di", "md", "reward", "coverage"}
        # Re-evaluate the formula from the SAME components the producer used.
        recomputed = system_score(
            di=c["di"], md=c["md"],
            reward_collected=snap["reward_collected"],
            reward_available=snap["reward_available"],
            world_states=snap["world_states"],
            grid_area=c["grid_area"],
        )
        assert abs(snap["score"] - recomputed) < 0.01, \
            f"displayed score {snap['score']} != recomputed {recomputed}"
        # Every trace score is bounded too (old-format scores are rejected).
        for t in snap["traces"]:
            s = t.get("score")
            assert s is None or (0.0 <= s <= 100.0), f"trace score {s} out of range"
    finally:
        p.stop()


def test_producer_score_before_first_cycle_is_none(isolated_paths):
    """Honest empty state: before any cycle there is no score, not a fake
    100 or a fabricated neutral number."""
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=1)
    assert p.snapshot()["score"] is None
    assert p.snapshot()["score_components"] is None
    p.stop()
