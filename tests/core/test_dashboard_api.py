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


def test_overview_history_path_exposes_honest_knowledge_nodes(handler, tmp_path):
    """LEFT ITEM 2: in the no-producer (persisted history) path, /api/overview
    must expose the live KG node count under the honest name `knowledge_nodes`
    (never the misnomer `lessons`), plus archived + total so the number is not
    misleading. `lessons` survives only as a deprecated alias equal to it —
    schema-drift guard mirroring test_trace_schema.py.

    Args:
        handler: the bare DashboardHandler fixture.
        tmp_path: is injected by pytest via the handler fixture's tmp_path,
            and stays for API symmetry / future persistence asserts.
    """
    h, tmp = handler
    kp = tmp / "knowledge.json"
    kp.write_text(json.dumps({
        "nodes": {
            "n1": {"node_id": "n1", "domain": "navigation",
                   "approach": "move_to_1_0", "outcome": 0.9},
            "n2": {"node_id": "n2", "domain": "navigation",
                   "approach": "move_to_2_0", "outcome": 0.8},
        },
    }))
    sd.KNOWLEDGE_PATH = str(kp)
    ov = h._load_overview()
    assert ov["knowledge_nodes"] == 2, "honest name must expose live node count"
    assert ov["lessons"] == 2, "deprecated alias must equal the honest name"
    assert ov["archived_nodes"] == 0
    assert ov["knowledge_nodes_total"] == 2
    # The nested producer `knowledge` payload already uses honest keys
    # (nodes / archived_nodes / total_nodes), never `lessons`.
    assert "knowledge_nodes" not in ov["knowledge"]
    assert ov["knowledge"]["nodes"] == 2
    assert ov["knowledge"]["total_nodes"] == 2


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
        # Honest naming contract: the overview's KG-node count is exposed as
        # `knowledge_nodes` (live KnowledgeGraph nodes), NOT `lessons` (which
        # would collide with ExperienceManager lessons). `lessons` is kept
        # only as a deprecated alias with the SAME value — never a different,
        # misleading number. See LEFT ITEM 2.
        assert ov["knowledge_nodes"] == snap["knowledge"]["nodes"], \
            "overview must expose live KG nodes under the honest name"
        assert ov["lessons"] == snap["knowledge"]["nodes"], \
            "deprecated `lessons` alias must equal the honest knowledge_nodes"
        assert ov["archived_nodes"] == snap["knowledge"].get("archived_nodes", 0)
        assert ov["knowledge_nodes_total"] == snap["knowledge"].get("total_nodes", 0)
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


def test_checkpoints_cached_until_files_change(handler, tmp_path):
    """The persisted-file portion of /api/checkpoints is cached on the file
    set's (dir, name, mtime, size): an in-place content change that preserves
    stat fields must NOT be re-read; a real mtime change must invalidate."""
    import os as _os
    h, _ = handler
    cp = tmp_path / "checkpoints"
    cp.mkdir()
    f = cp / "checkpoint_0001.json"
    f.write_text(json.dumps(
        {"cycle": 1, "decision_trace": {"cycle_id": 1, "decision_integrity": 0.9}}))
    first = h._load_checkpoints()
    assert [t["cycle_id"] for t in first] == [1]
    assert first[0]["decision_integrity"] == 0.9
    # Corrupt content in place, preserving the ORIGINAL mtime+size (same
    # digit count): key unchanged -> cache must serve the first read, not
    # re-parse.
    st_before = _os.stat(f)
    f.write_text(json.dumps(
        {"cycle": 1, "decision_trace": {"cycle_id": 1, "decision_integrity": 0.1}}))
    _os.utime(f, ns=(st_before.st_atime_ns, st_before.st_mtime_ns))
    second = h._load_checkpoints()
    assert second[0]["decision_integrity"] == 0.9, (
        "cache must serve the key-unchanged read (no re-parse)"
    )
    # A real mtime change (new write) invalidates and re-reads.
    f.write_text(json.dumps(
        {"cycle": 2, "decision_trace": {"cycle_id": 2, "decision_integrity": 0.5}}))
    third = h._load_checkpoints()
    assert third[0]["cycle_id"] == 2 and third[0]["decision_integrity"] == 0.5, (
        "file-set change must invalidate the cache"
    )
