"""serve_dashboard API tests — the HTTP surface serves LIVE runtime data
when the producer is running, persisted history when it isn't, and never
fabricated data."""
import json
import os
import tempfile

import pytest

import telos.serve_dashboard as sd
from telos.dashboard.producer import DashboardProducer


@pytest.fixture()
def handler(tmp_path, monkeypatch):
    """A bare DashboardHandler with temp paths (no socket needed — the
    _load_* methods only touch module globals).

    Args:
        tmp_path: pytest temp dir for checkpoint/knowledge paths.
        monkeypatch: pytest monkeypatch for module globals.
    """
    monkeypatch.setattr(sd, "CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    monkeypatch.setattr(sd, "KNOWLEDGE_PATH", str(tmp_path / "knowledge.json"))
    monkeypatch.setattr(sd, "_producer", None)
    return sd.DashboardHandler.__new__(sd.DashboardHandler), tmp_path


def test_knowledge_empty_when_no_producer_no_files(handler):
    h, _ = handler
    payload = h._load_knowledge()
    # The honest empty set now also carries a `stats` block (live/archived/
    # total) from the single _finalize_knowledge canonical source — nodes and
    # edges stay [] (nothing fabricated), and the counts are exactly zero.
    assert payload["nodes"] == []
    assert payload["edges"] == []
    assert payload["stats"] == {"live": 0, "archived": 0, "total": 0}
    assert h._load_checkpoints() == []
    assert h._load_overview()["decisions"] == 0
    assert h._load_overview()["producer"]["running"] is False


def test_knowledge_from_persisted_file_with_edges(handler):
    h, tmp = handler
    kp = tmp / "knowledge.json"
    kp.write_text(json.dumps({
        "nodes": {"n1": {"node_id": "n1", "domain": "navigation",
                         "approach": "move_to_1_0", "outcome": 0.9}},
        "edges": {"e1": {"edge_id": "e1", "src": "n1", "dst": "n2",
                         "edge_type": "follows", "weight": 0.8}},
    }))
    sd.KNOWLEDGE_PATH = str(kp)
    payload = h._load_knowledge()
    assert len(payload["nodes"]) == 1
    assert payload["nodes"][0]["id"] == "n1"
    assert payload["edges"] == [{
        "source": "n1", "target": "n2", "weight": 0.8, "edge_type": "follows",
    }]


def test_checkpoints_merge_producer_and_disk(handler, tmp_path, monkeypatch):
    h, tmp = handler
    # Producer with 2 real cycles
    import telos.dashboard.producer as prod_mod
    monkeypatch.setattr(prod_mod, "CHECKPOINT_DIR", str(tmp / "checkpoints"))
    monkeypatch.setattr(prod_mod, "PRODUCER_STATE_PATH", str(tmp / "producer_state.json"))
    monkeypatch.setattr(prod_mod, "KNOWLEDGE_PATH", str(tmp / "knowledge.json"))
    monkeypatch.setattr(prod_mod, "LEDGER_PATH", str(tmp / "ledger.json"))
    monkeypatch.setattr(prod_mod, "IDENTITY_PATH", str(tmp / "identity.json"))
    monkeypatch.setattr(prod_mod, "PATTERN_PATH", str(tmp / "patterns.json"))
    p = DashboardProducer(cycle_interval_s=0.3, burst_cycles=2)
    p.start()
    try:
        import time
        time.sleep(1.6)
        snap = p.snapshot()
        assert snap["decisions"] >= 2
        monkeypatch.setattr(sd, "_producer", p)
        # The producer is LIVE: cycles advance between reads, so each API
        # read must be compared against a FRESH snapshot (a window, not an
        # exact tick). This was a latent timing race: health["cycles"] ==
        # snap["decisions"] failed when a cycle landed between the two reads
        # (6 vs 5) under full-suite load. The assertions below keep the
        # original intent — every API reflects the LIVE producer — without
        # demanding the producer pause between our reads.
        def fresh():
            return p.snapshot()["decisions"]

        traces = h._load_checkpoints()
        assert len(traces) >= 2, "full traces from the live producer"
        assert abs(traces[-1]["cycle_id"] - fresh()) <= 1, (
            "checkpoints tail must track the live producer"
        )
        # Health reflects the live producer
        health = h._load_health_summary()
        assert health["producer_running"] is True
        assert health["cycles"] >= 2
        assert abs(health["cycles"] - fresh()) <= 1, (
            "health cycles drifted from the live producer"
        )
        assert health["mood"] == snap["mood"]
        # Overview reflects the live producer
        ov = h._load_overview()
        assert abs(ov["decisions"] - fresh()) <= 1
        assert ov["lessons"] == snap["knowledge"]["nodes"]
        assert ov["edges"] == snap["knowledge"]["edges"]
    finally:
        p.stop()


def test_checkpoints_are_strict_json_serializable(handler, tmp_path, monkeypatch):
    """Every trace the API serves must survive json.dumps(allow_nan=False)
    — the browser rejects bare NaN/Infinity.

    Args:
        handler: the bare DashboardHandler fixture.
        tmp_path: pytest temp dir.
        monkeypatch: pytest monkeypatch for module globals.
    """
    h, tmp = handler
    import telos.dashboard.producer as prod_mod
    monkeypatch.setattr(prod_mod, "CHECKPOINT_DIR", str(tmp / "checkpoints"))
    monkeypatch.setattr(prod_mod, "PRODUCER_STATE_PATH", str(tmp / "producer_state.json"))
    monkeypatch.setattr(prod_mod, "KNOWLEDGE_PATH", str(tmp / "knowledge.json"))
    monkeypatch.setattr(prod_mod, "LEDGER_PATH", str(tmp / "ledger.json"))
    monkeypatch.setattr(prod_mod, "IDENTITY_PATH", str(tmp / "identity.json"))
    monkeypatch.setattr(prod_mod, "PATTERN_PATH", str(tmp / "patterns.json"))
    p = DashboardProducer(cycle_interval_s=0.3, burst_cycles=2)
    p.start()
    try:
        import time
        time.sleep(1.6)
        monkeypatch.setattr(sd, "_producer", p)
        traces = h._load_checkpoints()
        json.dumps(traces, allow_nan=False)  # must not raise
        json.dumps(h._load_knowledge(), allow_nan=False)
        json.dumps(h._load_overview(), allow_nan=False)
    finally:
        p.stop()
