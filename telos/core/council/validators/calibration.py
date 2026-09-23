"""
CalibrationValidator — the honest-confidence gate.

Borrowed from the System One model discipline (TypeSafe / Jev): the automation
deal-breaker is not a wrong answer, it is a *confidently wrong* one. A system
that can be 95% right but cannot say when it is in the 5% cannot be trusted to
act unsupervised.

TELOS already claims confidence (``intent.confidence``) on every decision. This
validator consults the :class:`CalibrationTracker` — which measures how well
those claims have matched realized outcomes — and objects when the system is
both **miscalibrated** (ECE above tolerance) and **overconfident** on the
current claim (claim materially above its empirical accuracy).

Two modes (default is the safe, behavior-neutral one):
  * ``enforce=False`` (default, ADVISORY) — always returns a zero-weight PASS
    abstention. The calibration verdict is carried in ``metadata`` for the
    audit trail, but the validator does not alter DI, voting, or escalation.
    This keeps the canonical pipeline byte-for-byte unchanged.
  * ``enforce=True`` — an overconfident + miscalibrated claim is BLOCKED
    (Axiom 1.3: refuse to act on unsupported certainty).

Λ1.2 (Process over Outcomes): this is a process-honesty check, not an
outcome check — it never reads the current cycle's result.
"""

from __future__ import annotations

import logging
from typing import Optional, Any, TYPE_CHECKING

from telos.core.council.base import Validator, ValidationSignal
from telos.world.world import World
from telos.intent_ir import IntentIR

if TYPE_CHECKING:
    from telos.core.calibration.tracker import CalibrationTracker

logger = logging.getLogger('telos_council_validators')


class CalibrationValidator(Validator):
    """Blocks overconfident claims when recent confidence is miscalibrated.

    Args:
        tracker: the pipeline's CalibrationTracker (source of ECE / the
            recalibration map). None disables the check (PASS abstention).
        ece_threshold: ECE above which confidence is considered miscalibrated.
        overconfidence_threshold: claimed confidence above which a claim is
            scrutinised for overconfidence.
        max_gap: how far (claimed − calibrated) may drift before the claim is
            treated as overconfident.
        enforce: False (default) = advisory only; True = may BLOCK.
    """

    def __init__(self, tracker: Optional["CalibrationTracker"] = None,
                 ece_threshold: float = 0.25,
                 overconfidence_threshold: float = 0.7,
                 max_gap: float = 0.2,
                 enforce: bool = False):
        self._tracker = tracker
        self.ece_threshold = float(ece_threshold)
        self.overconfidence_threshold = float(overconfidence_threshold)
        self.max_gap = float(max_gap)
        self.enforce = bool(enforce)

    @property
    def name(self) -> str:
        return "CalibrationValidator"

    def _abstain(self, reason: str, metadata: Optional[dict] = None) -> ValidationSignal:
        """Zero-weight PASS — an honest abstention that cannot affect the vote.

        Args:
            reason: human-readable explanation.
            metadata: optional audit payload.

        Returns:
            A PASS signal with zero confidence and zero evidence weight.
        """
        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.0,
            reason=reason, evidence_weight=0.0, metadata=metadata or {},
        )

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 context: Optional[dict] = None) -> ValidationSignal:
        """Judge whether the current claim's confidence is honest.

        Args:
            world: the world model (unused — calibration is context-free).
            intent: the candidate intent carrying the claimed confidence.
            domain_facts: objective facts (unused).
            context: shared per-cycle council context (unused).

        Returns:
            A ValidationSignal: zero-weight PASS (advisory / insufficient data),
            a recalibrated PASS (enforce, well-calibrated), or a BLOCK
            (enforce, overconfident + miscalibrated).
        """
        if intent is None:
            return self._abstain("no intent to validate")

        tracker = self._tracker
        if tracker is None:
            return self._abstain("calibration tracker not wired")

        if not tracker.has_signal:
            return self._abstain(
                f"insufficient calibration samples "
                f"({tracker.sample_count} < {tracker.min_samples})",
                metadata={"sample_count": tracker.sample_count,
                          "enforce": self.enforce},
            )

        claimed = float(getattr(intent, "confidence", 0.0) or 0.0)
        calibrated = tracker.calibrated_confidence(claimed)
        ece = tracker.ece()
        ece = float(ece) if ece is not None else 0.0
        gap = claimed - calibrated

        miscalibrated = ece > self.ece_threshold
        overconfident = (claimed >= self.overconfidence_threshold
                         and gap > self.max_gap)

        metadata = {
            "ece": round(ece, 4),
            "claimed_confidence": round(claimed, 4),
            "calibrated_confidence": round(calibrated, 4),
            "gap": round(gap, 4),
            "sample_count": tracker.sample_count,
            "miscalibrated": miscalibrated,
            "overconfident": overconfident,
            "enforce": self.enforce,
        }

        if miscalibrated and overconfident:
            reason = (
                f"overconfident claim {claimed:.2f} vs calibrated "
                f"{calibrated:.2f} (gap {gap:+.2f}) with ECE {ece:.2f} > "
                f"{self.ece_threshold:.2f}"
            )
            if self.enforce:
                return ValidationSignal(
                    validator_name=self.name, passed=False, confidence=-0.7,
                    reason=reason, evidence_weight=min(0.9, ece + max(0.0, gap)),
                    metadata=metadata,
                )
            return self._abstain(f"ADVISORY: {reason}", metadata=metadata)

        # Well-calibrated (or the claim is not overconfident): in enforce mode
        # surface the recalibrated confidence; advisory mode stays a no-op.
        if self.enforce:
            return ValidationSignal(
                validator_name=self.name, passed=True,
                confidence=float(min(0.95, max(0.0, calibrated))),
                reason=(f"calibrated: claim {claimed:.2f} → {calibrated:.2f} "
                        f"(ECE {ece:.2f})"),
                evidence_weight=0.1, metadata=metadata,
            )
        return self._abstain(
            f"calibrated: claim {claimed:.2f} → {calibrated:.2f} (ECE {ece:.2f})",
            metadata=metadata,
        )
