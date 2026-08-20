"""DebugLoopGuard tests — lock the three canonical anti-loop patterns from
the "stuttering debugger" pathology:

  PATTERN 01 — acts over intentions: a repeated non-acting intent is trapped
    (Λ3.1 + firewall) and an escape is injected.
  PATTERN 02 — one grounded truth: an uncited claim scores 0 (Λ2.3 × Λ6.5).
  PATTERN 03 — single concern: assertion/file mismatch fires reconciliation.

These are the patterns the GridWorld pipeline already enforces (Decision
Firewall loop-trap, EvidenceProvenanceValidator) re-stated for the agent /
debugger layer, so they must stay green just like the loop-recovery tests.
"""

from telos.core.debug import (
    DebugLoopGuard,
    GuardStatus,
    NO_ACTION_REPEAT_THRESHOLD,
    UNSUPPORTED_FALSIFIED_AFTER,
)


def test_acting_intent_stays_healthy_and_resets_streak():
    g = DebugLoopGuard()
    # Acting intent repeatedly is never a loop.
    for _ in range(5):
        assert g.record_intent("read_test", acted=True) == GuardStatus.HEALTHY
        assert g.is_trapped("read_test") is False


def test_non_acting_intent_is_trapped_after_threshold_and_injects_escape():
    g = DebugLoopGuard(threshold=2)
    # First repeat: healthy. Second: watching. Third: trapped.
    assert g.record_intent("read_test", acted=False) == GuardStatus.HEALTHY
    assert g.record_intent("read_test", acted=False) == GuardStatus.WATCHING
    status = g.record_intent("read_test", acted=False)
    assert status == GuardStatus.TRAPPED
    assert g.is_trapped("read_test") is True
    assert "inject the missing act" in (g.escape_suggestion("read_test") or "").lower()


def test_escape_when_trapped_is_by_construction():
    """Threshold of N traps the intent on the (N+1)-th non-acting repeat.

    A single non-acting intent is a genuine candidate (not yet a loop); the
    trap forms only once the streak exceeds the threshold — mirroring the
    firewall's RECOVERY_AFTER_LOOP_BLOCKS discipline where the ko block never
    waives a single attempt, only a pattern.
    """
    g = DebugLoopGuard(threshold=1)
    assert g.record_intent("plan", acted=False) == GuardStatus.WATCHING
    assert g.record_intent("plan", acted=False) == GuardStatus.TRAPPED
    assert g.is_trapped("plan") is True


def test_recover_clears_trap():
    g = DebugLoopGuard(threshold=1)
    g.record_intent("plan", acted=False)
    g.record_intent("plan", acted=False)
    assert g.is_trapped("plan") is True
    assert g.recover("plan") == GuardStatus.RECOVERED
    assert g.is_trapped("plan") is False
    assert g.escape_suggestion("plan") is None


def test_intents_are_tracked_independently():
    """Two distinct intents never share a trap — single concern, not shared."""
    g = DebugLoopGuard(threshold=1)
    g.record_intent("read_test", acted=False)
    g.record_intent("read_test", acted=False)
    assert g.is_trapped("read_test") is True
    assert g.is_trapped("edit_line") is False


def test_uncited_claim_scores_zero_and_repeats_are_loop_signals():
    g = DebugLoopGuard()
    assert g.score_claim("trap_cycles empty", cited=False) == 0.0
    assert g.score_claim("trap_cycles empty", cited=False) == 0.0
    # Unsupportable, and restated twice — deprioritised.
    assert g.claim_supported("trap_cycles empty") is False
    assert UNSUPPORTED_FALSIFIED_AFTER >= 1


def test_cited_claim_scores_one_and_resets():
    g = DebugLoopGuard()
    # Same claim, but now cited — supported and the false streak resets.
    assert g.score_claim("trap_cycles empty", cited=True) == 1.0
    assert g.claim_supported("trap_cycles empty") is True


def test_concern_mismatch_fires_reconciliation():
    g = DebugLoopGuard()
    msg = g.check_concern(
        assertion="assert trap_cycles",
        file="test_dashboard_api.py",
        owning_file="test_loop_recovery.py",
    )
    assert msg is not None
    assert "test_loop_recovery.py" in msg and "test_dashboard_api.py" in msg


def test_matching_concern_is_clean():
    g = DebugLoopGuard()
    assert g.check_concern(
        assertion="assert trap_cycles",
        file="test_loop_recovery.py",
        owning_file="test_loop_recovery.py",
    ) is None


def test_snapshot_is_serialisable():
    g = DebugLoopGuard(threshold=1)
    g.record_intent("read_test", acted=False)
    g.record_intent("read_test", acted=False)
    g.score_claim("uncited", cited=False)
    snap = g.snapshot()
    assert snap["trapped"]["read_test"] is True
    assert snap["intents"]["read_test"] >= 1
    assert snap["claims"]["uncited"] == 1
    import json
    json.dumps(snap)


def test_threshold_and_constant_are_exposed():
    assert isinstance(NO_ACTION_REPEAT_THRESHOLD, int)
    assert NO_ACTION_REPEAT_THRESHOLD == 2
    assert isinstance(UNSUPPORTED_FALSIFIED_AFTER, int)
