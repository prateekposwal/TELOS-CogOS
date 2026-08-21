"""Contract tests for telos/core/debug/guard.py.

DebugLoopGuard detects the three canonical debug-loop pathologies: repeated
non-acting intents (acts-over-intentions), uncited claims restated as if
grounded (one-grounded-truth), and mixing assertions across files in one
thread (single-concern).
"""
import pytest

from telos.core.debug.guard import (
    DebugLoopGuard,
    GuardStatus,
    KNOWN_LOOPS,
    NO_ACTION_REPEAT_THRESHOLD,
    UNSUPPORTED_FALSIFIED_AFTER,
)


def test_module_constants():
    assert NO_ACTION_REPEAT_THRESHOLD == 2
    assert UNSUPPORTED_FALSIFIED_AFTER == 1


def test_guard_status_enum_values():
    assert GuardStatus.HEALTHY.value == "healthy"
    assert GuardStatus.WATCHING.value == "watching"
    assert GuardStatus.TRAPPED.value == "trapped"
    assert GuardStatus.RECOVERED.value == "recovered"


def test_known_loops_has_three_canonical_patterns():
    assert set(KNOWN_LOOPS) == {
        "acts_over_intentions", "one_grounded_truth", "single_concern",
    }
    for loop in KNOWN_LOOPS.values():
        assert loop.name
        assert loop.description
        assert loop.escape


class TestActsOverIntentions:
    def test_acting_intent_stays_healthy(self):
        g = DebugLoopGuard()
        for _ in range(5):
            assert g.record_intent("read the test", acted=True) == GuardStatus.HEALTHY
        assert g.is_trapped("read the test") is False

    def test_no_action_progression_to_trap(self):
        g = DebugLoopGuard()
        intent = "read the test"
        assert g.record_intent(intent, acted=False) == GuardStatus.HEALTHY
        assert g.record_intent(intent, acted=False) == GuardStatus.WATCHING
        assert g.record_intent(intent, acted=False) == GuardStatus.TRAPPED
        assert g.is_trapped(intent) is True
        escape = g.escape_suggestion(intent)
        assert escape is not None
        assert escape == KNOWN_LOOPS["acts_over_intentions"].escape

    def test_acting_after_streak_resets(self):
        g = DebugLoopGuard()
        intent = "read"
        g.record_intent(intent, acted=False)
        g.record_intent(intent, acted=False)
        assert g.record_intent(intent, acted=True) == GuardStatus.HEALTHY
        assert g._streak[intent] == 0
        assert g.is_trapped(intent) is False

    def test_recover_flips_to_recovered_and_clears(self):
        g = DebugLoopGuard()
        intent = "read"
        for _ in range(3):
            g.record_intent(intent, acted=False)
        assert g.is_trapped(intent) is True
        assert g.recover(intent) == GuardStatus.RECOVERED
        assert g.is_trapped(intent) is False
        assert g.escape_suggestion(intent) is None

    def test_custom_threshold(self):
        g = DebugLoopGuard(threshold=1)
        intent = "run"
        assert g.record_intent(intent, acted=False) == GuardStatus.WATCHING
        assert g.record_intent(intent, acted=False) == GuardStatus.TRAPPED


class TestOneGroundedTruth:
    def test_cited_claim_scores_one(self):
        g = DebugLoopGuard()
        assert g.score_claim("test_loop_recovery passes", cited=True) == 1.0
        assert g.claim_supported("test_loop_recovery passes") is True

    def test_uncited_claim_scores_zero_and_unsupported(self):
        g = DebugLoopGuard()
        assert g.score_claim("the build is broken", cited=False) == 0.0
        assert g.claim_supported("the build is broken") is False

    def test_restated_uncited_claim_accumulates(self):
        g = DebugLoopGuard()
        g.score_claim("fixed", cited=False)
        g.score_claim("fixed", cited=False)
        assert g._claims["fixed"] == 2

    def test_uncited_then_cited_becomes_supported(self):
        g = DebugLoopGuard()
        g.score_claim("x passes", cited=False)
        assert g.score_claim("x passes", cited=True) == 1.0
        assert g.claim_supported("x passes") is True


class TestSingleConcern:
    def test_mismatched_files_reconcile(self):
        g = DebugLoopGuard()
        msg = g.check_concern(
            assertion="assert trap_cycles",
            file="tests/core/test_dashboard.py",
            owning_file="tests/core/test_loop_recovery.py",
        )
        assert msg is not None
        assert "single-concern" in msg
        assert "assert trap_cycles" in msg
        assert "test_loop_recovery.py" in msg

    def test_matching_files_are_clean(self):
        g = DebugLoopGuard()
        assert g.check_concern(
            assertion="assert x", file="a.py", owning_file="a.py"
        ) is None

    def test_missing_file_is_clean(self):
        g = DebugLoopGuard()
        assert g.check_concern(assertion="assert x", file=None, owning_file="a.py") is None
        assert g.check_concern(assertion="assert x", file="a.py", owning_file=None) is None


class TestSnapshot:
    def test_snapshot_serializable(self):
        g = DebugLoopGuard()
        g.record_intent("read", acted=False)
        g.record_intent("read", acted=False)
        g.record_intent("read", acted=False)
        g.score_claim("claim", cited=False)
        snap = g.snapshot()
        assert snap["intents"]["read"] == 3
        assert snap["trapped"]["read"] is True
        assert snap["claims"]["claim"] == 1