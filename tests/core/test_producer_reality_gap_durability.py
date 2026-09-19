"""
Producer-level Reality Gap durability — the live producer is NOT accidentally ephemeral.

FALSIFIER UNDER TEST: the live producer's world-model Reality Gap state must
survive a process restart (model_fidelity cannot silently reset to an untested
cold start), and the live producer must never be a production path where
capability authority is durable while Reality Gap is accidentally ephemeral.
Tool execution stays OFF (no ``TELOS_TOOL_WORKSPACE``) and no live canary runs
(no ``TELOS_CANARY_ENABLED``).

The mechanism is the ONE canonical durability envelope
(``telos/core/actions/durability.py``); this suite only pins the producer's
explicit configuration + restart wiring, never a second persistence store.
"""

import inspect
import json
import os
import time

import numpy as np
import pytest

import telos.dashboard.producer as prod_mod
from telos.core.actions.durability import (
    KIND_AUTHORITY_EVIDENCE, SCHEMA_VERSION, StateOutcome, build_envelope,
    read_state,
)
from telos.dashboard.producer import DashboardProducer


@pytest.fixture()
def isolated_producer_paths(tmp_path, monkeypatch):
    """Point every producer state path at tmp and force the tool channel OFF.

    Args:
        tmp_path: pytest temp dir.
        monkeypatch: used to rebind the producer module globals per test.

    Returns:
        The isolated tmp_path root.
    """
    monkeypatch.setattr(prod_mod, "CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    monkeypatch.setattr(prod_mod, "PRODUCER_STATE_PATH",
                        str(tmp_path / "producer_state.json"))
    monkeypatch.setattr(prod_mod, "KNOWLEDGE_PATH", str(tmp_path / "knowledge.json"))
    monkeypatch.setattr(prod_mod, "LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(prod_mod, "IDENTITY_PATH", str(tmp_path / "identity.json"))
    monkeypatch.setattr(prod_mod, "PATTERN_PATH", str(tmp_path / "patterns.json"))
    monkeypatch.setattr(prod_mod, "DECISION_LOG_PATH",
                        str(tmp_path / "decision_log.json"))
    monkeypatch.setattr(prod_mod, "MEMORY_PATH", str(tmp_path / "memory.json"))
    monkeypatch.setattr(prod_mod, "REALITY_GAP_STATE_PATH",
                        str(tmp_path / "reality_gap.json"))
    # Default-off safety posture: no governed tool channel, no canary.
    monkeypatch.delenv("TELOS_TOOL_WORKSPACE", raising=False)
    monkeypatch.delenv("TELOS_CANARY_ENABLED", raising=False)
    return tmp_path


def _built_producer():
    """Build a real producer pipeline without starting the background loop.

    Returns:
        A DashboardProducer whose real pipeline is constructed.
    """
    p = DashboardProducer(cycle_interval_s=0.2, burst_cycles=1)
    p._build()
    return p


# ── configuration: explicit, deterministic, not accidentally ephemeral ──────

def test_live_producer_configures_durable_reality_gap_state(
        isolated_producer_paths):
    """The producer passes its explicit Reality Gap store path into the pipeline."""
    p = _built_producer()
    cfg = p._pipeline.config
    assert prod_mod.REALITY_GAP_STATE_PATH, "an explicit path must be configured"
    assert cfg.reality_gap_state_path == prod_mod.REALITY_GAP_STATE_PATH
    assert cfg.reality_gap_state_path is not None
    # The capability-authority evidence is durable too; the invariant is that
    # Reality Gap is not left ephemeral beside it.
    assert prod_mod.CAPABILITY_AUTHORITY_STATE_PATH
    # Default-off: this construction grants no tool execution.
    assert getattr(cfg, "action_executor", None) is None


def test_producer_source_pins_reality_gap_state_path():
    """Regression: the producer must not silently DROP the kwarg in a refactor."""
    src = inspect.getsource(DashboardProducer._build)
    assert "reality_gap_state_path=REALITY_GAP_STATE_PATH" in src


# ── restart: real producer cycles generate + persist + reload ───────────────

def test_producer_reality_gap_survives_restart(isolated_producer_paths):
    """start -> real cycles persist evidence -> stop -> restart -> load."""
    path = prod_mod.REALITY_GAP_STATE_PATH
    p1 = DashboardProducer(cycle_interval_s=0.2, burst_cycles=15)
    p1.start()
    try:
        deadline = time.time() + 30.0
        while time.time() < deadline and not os.path.exists(path):
            time.sleep(0.1)
    finally:
        p1.stop()
    assert os.path.exists(path), "live cycles must persist Reality Gap evidence"

    result = read_state(path, expected_kind=KIND_AUTHORITY_EVIDENCE)
    assert result.outcome is StateOutcome.LOADED
    stored = (result.payload or {}).get("models", {})
    assert "world" in stored, "the world-model evidence was persisted"

    # Restart over the SAME configured path.
    p2 = _built_producer()
    assert p2._pipeline._reality_gap_evidence_corrupt is False
    post = p2._pipeline._reality_gap_tracker.model("world")
    assert post.validation_count == stored["world"]["validation_count"]
    assert post.last_validation_cycle == stored["world"]["last_validation_cycle"]
    assert post.ever_falsified == stored["world"]["ever_falsified"]


def test_producer_reality_gap_restart_is_deterministic(isolated_producer_paths):
    """A measured gap recorded on the producer's ONE tracker survives restart."""
    p1 = _built_producer()
    p1._pipeline._reality_gap_tracker.record(
        "world", np.array([1.0, 0.0]), np.array([0.0, 0.0]), cycle=7)
    p1._pipeline._persist_reality_gap_state()

    p2 = _built_producer()
    m = p2._pipeline._reality_gap_tracker.model("world")
    assert m.validation_count == 1
    assert m.last_validation_cycle == 7
    assert m.ever_falsified is True


# ── failure semantics: the existing contract, at the producer boundary ──────

def test_producer_missing_reality_gap_store_is_first_run(isolated_producer_paths):
    """An absent store is an honest cold start, not corruption."""
    p = _built_producer()
    assert p._pipeline._reality_gap_state_path == prod_mod.REALITY_GAP_STATE_PATH
    assert p._pipeline._reality_gap_evidence_corrupt is False
    assert p._pipeline._reality_gap_tracker.model("world").validation_count == 0


@pytest.mark.parametrize("mutate", ["corrupt", "schema_mismatch", "wrong_kind"])
def test_producer_reality_gap_bad_store_fails_closed(
        isolated_producer_paths, mutate):
    """Corrupt / newer-schema / wrong-kind stores are CORRUPTED -> gate fails closed.

    Args:
        isolated_producer_paths: isolated producer state paths fixture.
        mutate: which bad-store shape to write (corrupt / schema_mismatch /
            wrong_kind).
    """
    path = prod_mod.REALITY_GAP_STATE_PATH
    if mutate == "corrupt":
        open(path, "w", encoding="utf-8").write("{not-json")
    elif mutate == "schema_mismatch":
        env = build_envelope(KIND_AUTHORITY_EVIDENCE, {"models": {}},
                             schema_version=SCHEMA_VERSION + 1)
        open(path, "w", encoding="utf-8").write(json.dumps(env))
    else:
        env = build_envelope("some_other_state", {"models": {}})
        open(path, "w", encoding="utf-8").write(json.dumps(env))

    p = _built_producer()
    assert p._pipeline._reality_gap_evidence_corrupt is True


def test_producer_persistence_failure_grants_no_authority(
        isolated_producer_paths):
    """A failed persist is logged, never fatal, and never adds authority."""
    p = _built_producer()
    assert p._pipeline._reality_gap_tracker.model("world").validation_count == 0
    # Aim the store at a directory so the atomic replace cannot succeed.
    p._pipeline._reality_gap_state_path = str(isolated_producer_paths)
    p._pipeline._persist_reality_gap_state()  # must not raise
    # No false authority is manufactured by the failed write.
    assert p._pipeline._reality_gap_evidence_corrupt is False
    assert p._pipeline._reality_gap_tracker.model("world").validation_count == 0
