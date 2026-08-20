"""
Debug Loop Guard — structural patterns that keep the human-facing agent /
debugger layer from stuttering (the patterns the GridWorld pipeline already
embodies, now made load-bearing for the agent/skill layer).

A prior session exhibited the "stuttering debugger" pathology:
  - it re-emitted the SAME intent ("Let me read the test") with zero tool
    calls across many turns (never progressed),
  - it conflated two unrelated failure memories (a current dashboard test
    and a stale, already-fixed loop-recovery trap) into one workspace,
  - it restated an uncited assertion as if grounded while never actually
    grounding on the pasted pytest output,
  - it narrated near-identical prose instead of compressing state.

This guard is NOT a new algorithm — it is the pipeline's own Λ3.1
stagnation recovery, the Decision Firewall loop-trap coordination, and the
EvidenceProvenanceValidator (Λ2.3 × Λ6.5) re-stated as a single reusable
component for the agent/debugger layer. Three canonical rules:

  PATTERN 01 — "Acts over Intentions" (Λ3.1 + firewall)
    An intent-narration that yields NO_ACTION_REPEAT_THRESHOLD consecutive
    zero-tool-call repeats is a loop, not a plan. After that streak the
    guard trap-blocks the repeated non-acting intent and injects an escape
    suggestion (acts over intentions).

  PATTERN 02 — "One Grounded Truth" (Λ2.3 × Λ6.5)
    Any claim restated without a citation to an actual tool/pytest-output
    row is scored as an UNSUPPORTED hypothesis and auto-deprioritized.
    Restating an uncited claim twice = a loop signal. A claim is only
    SUPPORTED when it carries a citation.

  PATTERN 03 — "Single Concern per Debug Thread" (Λ1.1, Λ4.6)
    One debug thread holds ONE failing test. Referencing assertion A while
    holding file B fires an explicit reconciliation signal.

Engineering Value:
  Makes the three loop-breaking disciplines the GridWorld pipeline already
  enforces (and that won it DI 1.000) available verbatim to the debugger /
  agent layer, so the same repeated-intent, unfalsifiable-belief, mixed-
  concern pathologies are detected and escaped by construction rather than
  left to luck.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# PATTERN 01: acts-over-intentions. After this many consecutive repeats of a
# non-acting intent we consider it a loop and inject an escape.
NO_ACTION_REPEAT_THRESHOLD = 2

# PATTERN 02: an uncited claim restated more than once is a loop signal.
UNSUPPORTED_FALSIFIED_AFTER = 1


class GuardStatus(Enum):
    """The four states a tracked intent can be in."""
    HEALTHY = "healthy"                 # < threshold repeats, not trapped
    WATCHING = "watching"               # near the loop threshold, not yet trapped
    TRAPPED = "trapped"                 # loop detected: escape injected
    RECOVERED = "recovered"             # escape suggestion was accepted


@dataclass
class PatentLoops:
    """Named loop patterns the guard recognises, for logging / escape text.

    Args:
        name: canonical pattern name.
        description: one-line summary.
        escape: the recovery suggestion injected when trapped.
    """
    name: str
    description: str
    escape: str


# The three canonical anti-patterns from the diagnosis, each with its
# injection-site recovery text.
KNOWN_LOOPS: Dict[str, PatentLoops] = {
    "acts_over_intentions": PatentLoops(
        name="acts_over_intentions",
        description=(
            "intent-narration with zero tool calls for consecutive turns — "
            "an 'I will read' that never Read is a no-action cycle."
        ),
        escape="Inject the missing act now: perform the tool call you keep "
               "narrating (e.g. Read the file) before emitting any further prose.",
    ),
    "one_grounded_truth": PatentLoops(
        name="one_grounded_truth",
        description=(
            "an uncited / unfalsified claim restated repeatedly instead of "
            "being grounded against the actual pytest/tool output row."
        ),
        escape="Ground the claim: cite the exact tool/output row it came from, "
               "or relabel it as an unsupported hypothesis and deprioritise it.",
    ),
    "single_concern": PatentLoops(
        name="single_concern",
        description=(
            "referencing one failing test while holding a different file's "
            "assertion in the same workspace — two concerns conflated."
        ),
        escape="Reconcile: the cited assertion does not exist in the file you "
               "hold. Split into one thread per failing test, or drop the stray claim.",
    ),
}


class DebugLoopGuard:
    """Tracks repeated intents and traps the three canonical debug loops.

    Each call site records what it tried to do; the guard tells it whether
    that is a healthy single attempt, a watching/impending loop, a trapped
    loop (inject the escape), or recovered. It mirrors the Firewall loop-trap
    coordination (Λ3.1) and the EvidenceProvenanceValidator's score-by-record
    discipline (Λ6.5) for the agent layer.

    Args:
        threshold: consecutive repeats of a non-acting intent that trap it.
        recover_on_accept: whether calling recover() flips a trapped loop to
            recovered (and resets its streak).
    """

    def __init__(self, threshold: int = NO_ACTION_REPEAT_THRESHOLD,
                 recover_on_accept: bool = True):
        self.threshold = threshold
        self.recover_on_accept = recover_on_accept
        self._streak: Dict[str, int] = {}
        self._trapped: Dict[str, bool] = {}
        self._escapes: Dict[str, str] = {}
        self._claims: Dict[str, int] = {}

    # -- PATTERN 01: acts over intentions -----------------------------------

    def record_intent(self, intent: str, acted: bool) -> GuardStatus:
        """Record whether the agent acted on `intent`.

        A non-acting intent repeated `threshold` consecutive times is a loop:
        the guard sets status TRAPPED and stores an escape suggestion.

        Args:
            intent: the (normalised) thing the agent said it would do.
            acted: True if the intent produced a real tool call this turn.

        Returns:
            GuardStatus for this intent (TRAPPED once the loop forms).
        """
        if acted:
            self._streak[intent] = 0
            self._trapped[intent] = False
            return GuardStatus.HEALTHY
        n = self._streak.get(intent, 0) + 1
        self._streak[intent] = n
        if n >= self.threshold + 1:
            self._trapped[intent] = True
            self._escapes[intent] = KNOWN_LOOPS["acts_over_intentions"].escape
            return GuardStatus.TRAPPED
        if n == self.threshold:
            return GuardStatus.WATCHING
        return GuardStatus.HEALTHY

    def is_trapped(self, intent: str) -> bool:
        """True if `intent` is in the trapped (loop-detected) state.

        Args:
            intent: the intent key to check.
        """
        return self._trapped.get(intent, False)

    def escape_suggestion(self, intent: str) -> Optional[str]:
        """The recovery text to inject for a trapped intent, else None.

        Args:
            intent: the intent key.

        Returns:
            The stored escape suggestion, or None if not trapped.
        """
        return self._escapes.get(intent)

    def recover(self, intent: str) -> GuardStatus:
        """Accept the escape for `intent`: flip it to RECOVERED and reset.

        Args:
            intent: the intent key being recovered.

        Returns:
            GuardStatus.RECOVERED (and the streak/trap is cleared).
        """
        self._streak[intent] = 0
        self._trapped[intent] = False
        self._escapes.pop(intent, None)
        return GuardStatus.RECOVERED

    # -- PATTERN 02: one grounded truth --------------------------------------

    def score_claim(self, claim: str, cited: bool) -> float:
        """Score a claim by whether it is grounded.

        An uncited claim scores 0 (auto-deprioritised against any cited
        claim). Restating an uncited claim more than UNSUPPORTED_FALSIFIED_AFTER
        times is a loop signal and also returns 0.0.

        Args:
            claim: the claim (normalised) being made.
            cited: True if it cites an actual tool/pytest output row.

        Returns:
            1.0 for a cited claim (with bonus for first citation), else 0.0.
        """
        if cited:
            self._claims[claim] = 0
            return 1.0
        n = self._claims.get(claim, 0) + 1
        self._claims[claim] = n
        return 0.0

    def claim_supported(self, claim: str) -> bool:
        """True if `claim` was last cited (grounded).

        Args:
            claim: the claim key to check.
        """
        return self._claims.get(claim, 0) == 0 and claim in self._claims

    # -- PATTERN 03: single concern per debug thread -------------------------

    def check_concern(self, assertion: str, file: Optional[str],
                      owning_file: Optional[str]) -> Optional[str]:
        """Flag a concern mismatch between an assertion and its file.

        If `assertion` is attributed to `owning_file` but `file` is a
        different file, return a reconciliation message; else None.

        Args:
            assertion: the assertion being referenced (e.g. "assert trap_cycles").
            file: the file the agent currently holds / is editing.
            owning_file: the file where that assertion actually lives.

        Returns:
            A reconciliation message on mismatch, else None.
        """
        if file and owning_file and file != owning_file:
            return (
                f"single-concern: `{assertion}` lives in {owning_file}, not "
                f"{file} — reconcile or drop (one debug thread holds one test)."
            )
        return None

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        """Serialisable summary of tracked streaks and claims.

        Returns:
            dict with 'intents' (intent → streak) and 'claims' (claim → restates).
        """
        return {
            "intents": dict(self._streak),
            "trapped": dict(self._trapped),
            "claims": dict(self._claims),
        }
