"""
Scorecard <-> memory-eval schema linkage (Fix 1 regression guard).

The scorecard's `_memory_eval_beats_naive` reads the artifact `memory_eval.py`
writes. Those two drifted once: the reader still looked for `beats_naive` /
`controller.recall@1` after the eval switched to `beats_baselines` /
`semantic.recall@1`, so the memory retrieval evidence silently stopped counting.
These tests lock the WRITER and the READER together so that drift fails loudly.
"""

import json

from telos.core.verifier.capability_scorecard import _memory_eval_beats_naive
from telos.tools.memory_eval import evaluate


def _write_artifact(tmp_path, beats_baselines, recall_at_1):
    """Write a minimal memory_eval.json under a temp repo root."""
    audit = tmp_path / "telos" / "audit"
    audit.mkdir(parents=True)
    (audit / "memory_eval.json").write_text(
        json.dumps({
            "beats_baselines": beats_baselines,
            "semantic": {"recall@1": recall_at_1},
        }),
        encoding="utf-8",
    )
    return str(tmp_path)


def test_evaluate_emits_the_keys_the_reader_reads():
    """The writer emits `beats_baselines` (bool) and `semantic.recall@1`."""
    result = evaluate()
    assert "beats_baselines" in result
    assert isinstance(result["beats_baselines"], bool)
    assert isinstance(result["semantic"], dict)
    assert isinstance(result["semantic"].get("recall@1"), float)
    # The reader's OLD key path must not be what the writer emits.
    assert "beats_naive" not in result
    assert "controller" not in result


def test_reader_true_when_artifact_matches_the_schema(tmp_path):
    """A matching artifact (beats_baselines + semantic recall@1 >= 0.9) passes."""
    root = _write_artifact(tmp_path, True, 1.0)
    assert _memory_eval_beats_naive(root) is True


def test_reader_is_a_real_gate_when_beats_baselines_is_false(tmp_path):
    """beats_baselines false must return false, whatever the recall."""
    root = _write_artifact(tmp_path, False, 1.0)
    assert _memory_eval_beats_naive(root) is False


def test_reader_requires_the_recall_floor(tmp_path):
    """A true verdict with recall@1 below 0.9 does not count the evidence."""
    root = _write_artifact(tmp_path, True, 0.5)
    assert _memory_eval_beats_naive(root) is False


def test_reader_false_without_the_artifact(tmp_path):
    """No artifact -> no credit (never a silent pass)."""
    assert _memory_eval_beats_naive(str(tmp_path)) is False
