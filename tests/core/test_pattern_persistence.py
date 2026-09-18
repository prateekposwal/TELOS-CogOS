"""
PatternLibrary persistence — sets/numpy in metadata must not break save(), and
the reloaded indices must match the in-memory list contract.

Two latent bugs lived here: (1) `save()` raised "Object of type set is not JSON
serializable" and silently lost the checkpoint; (2) `load()` rebuilt the domain
/type indices as `set`s while every other code path calls `.append()` on them,
so a reloaded library raised "AttributeError: 'set' object has no attribute
'append'" on the next index. Both are locked here.
"""

import json
import os

import numpy as np

from telos.core.pattern.core import PatternLibrary, Pattern, PatternSignature, PatternType


def _make_library(tmp_path) -> PatternLibrary:
    lib = PatternLibrary()
    sig = PatternSignature(
        state_hash="h1", intent_type="navigate",
        drift_bucket=0, integrity_bucket=1, action_signature="move",
    )
    lib.record(
        domain="gridworld", pattern_type=PatternType.SUCCESS, signature=sig,
        action_taken="move", outcome_score=0.9,
        metadata={"blocked": {(1, 2), (3, 4)}, "np_val": np.float64(1.5)},
    )
    return lib


def _only_pattern_id(lib: PatternLibrary) -> str:
    return next(iter(lib._patterns))


def test_save_with_set_metadata_does_not_raise(tmp_path):
    """A set/numpy value in metadata is coerced, not fatal."""
    lib = _make_library(tmp_path)
    path = str(tmp_path / "patterns.json")
    lib.save(path)  # must not raise
    assert os.path.isfile(path)
    with open(path) as f:
        data = json.load(f)
    pid = _only_pattern_id(lib)
    assert data["patterns"][pid]["metadata"]["blocked"]


def test_reloaded_indices_support_append(tmp_path):
    """After load(), the domain/type indices accept .append (list contract)."""
    lib = _make_library(tmp_path)
    path = str(tmp_path / "patterns.json")
    lib.save(path)

    reloaded = PatternLibrary()
    reloaded.load(path)
    # This is the operation that used to raise on a set-backed index.
    sig2 = PatternSignature(state_hash="h2", intent_type="collect",
                            drift_bucket=0, integrity_bucket=1)
    new_id = reloaded.record(
        domain="gridworld", pattern_type=PatternType.SUCCESS, signature=sig2,
        action_taken="collect", outcome_score=0.5,
    )
    assert new_id in reloaded._domain_index["gridworld"]


def test_reload_roundtrip_preserves_patterns(tmp_path):
    """Every saved pattern survives a save/load round trip."""
    lib = _make_library(tmp_path)
    path = str(tmp_path / "patterns.json")
    lib.save(path)
    reloaded = PatternLibrary()
    reloaded.load(path)
    pid = _only_pattern_id(lib)
    assert pid in reloaded._patterns
    assert reloaded._patterns[pid].domain == "gridworld"


def test_json_safe_handles_nested_containers():
    """_json_safe recurses through sets, dicts, lists, and numpy scalars."""
    from telos.core.pattern.core import _json_safe
    value = {
        "s": {3, 1, 2},
        "n": np.int64(7),
        "l": [np.float64(2.5), {"t": (1, 2)}],
    }
    safe = _json_safe(value)
    json.dumps(safe)  # must be serializable
    assert safe["s"] == [1, 2, 3]
    assert safe["n"] == 7
    assert safe["l"][1]["t"] == [1, 2]
