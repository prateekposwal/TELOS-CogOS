"""
TELOS v6 — EvidenceProvenanceValidator — falsification-aware council advisor.

Phase 9 (Council). Scores a candidate intent against the FALSIFICATION RECORD
of its intent type (plus the world model's reality-gap state). This is the
decision-provenance-as-evidence rule:

    A decision type that has been repeatedly FALSIFIED by reality (its actions
    never materialize, or its predictions keep contradicting observation) must
    lose the benefit of the doubt. The validator does NOT hard-block on its own
    (it is an advisor with a scalar evidence weight, not a hard gate) — but its
    dissent lowers evidence integrity, which feeds the governor's causal
    confidence / recovery capability gates and the council's DI. Combined with
    the runtime's stagnation-armed force-escape (Lambda 3.1), a falsified loop
    like `blended_inquiry`-with-no-action is caught and forced to escape.

The validator reads the SAME RealityGapTracker the act phase uses, plus a
compact trace-history of intent-type outcomes, so the council's view of a
candidate is grounded in the system's own decision ledger (Lambda 6.5 —
evidence-based belief revision).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from telos.core.council.base import Validator, ValidationSignal
from telos.world.world import World
from telos.intent_ir import IntentIR
from telos.core.governance.recovery_types import STAGNATION_EXEMPT_RECOVERY_TYPES

logger = logging.getLogger('telos_council_validators')

# Intent types that are evidence-gathering by design: they should never be
# penalised for not producing a world-changing action — their purpose IS inquiry.
_INQUIRY_TYPES = {
    "inquiry", "inquiry_explore", "inquiry_recalibrate", "inquiry_resolve",
    "curiosity_explore", "perceive", "memory_miss",
}

# Consecutive falsified selections of the SAME intent type that trigger dissent.
FALSIFICATION_DISSENT_AFTER = 3


class EvidenceProvenanceValidator(Validator):
    """Scores candidate intents against the falsification record.

    - For the world model: uses the RealityGapTracker's per-model list of
      prediction failures (is_falsified + recent mean gap).
    - For the candidate type: uses the runtime's no-action/failure history
      (consecutive no-action cycles on the same type + recent blocked cycles).

    Dissents (passed=False) when the candidate type is demonstrably falsified
    and it is not a legitimate inquiry type — forcing the selector toward a
    differently-typed escape. Genuine inquiry types are never penalised.
    """

    @property
    def name(self) -> str:
        return "EvidenceProvenanceValidator"

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 omega_vector: Optional[dict] = None,
                 context: Optional[Dict] = None) -> ValidationSignal:
        if intent is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no intent to validate", evidence_weight=0.0,
            )

        intent_type = intent.intent_type or "unknown"
        ctx = context or {}

        # Falsification record of the WORLD MODEL (reality gap).
        tracker = ctx.get("reality_gap_tracker")
        now_cycle = ctx.get("cycle_count") or 0
        model_falsified = False
        model_gap = None
        if tracker is not None:
            try:
                m = tracker.model("world")
                # CURRENT falsification only (Λ6.5): a stale gap history is
                # frozen, not fresh — absence of validation is uncertainty,
                # mirroring the act-phase fidelity gate's act-then-learn rule.
                model_falsified = bool(m.currently_falsified(now_cycle=now_cycle or None))
                if m.gap_history:
                    model_gap = float(m.recent_mean_gap)
            except Exception:
                pass

        # Falsification record of THIS INTENT TYPE (decision ledger history).
        history = ctx.get("intent_history") or {}
        type_blocked = history.get("consecutive_no_action", 0)
        total_no_action = history.get("total_no_action", 0)
        recent_blocks = history.get("recent_blocks", 0)

        if intent_type in _INQUIRY_TYPES:
            # Inquiry types exist precisely to resolve uncertainty — never
            # punish the act of asking questions. Their falsification shows up
            # via the model record instead.
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.4,
                reason=f"inquiry type '{intent_type}' is evidence-gathering by design; "
                       "not scored as falsified",
                evidence_weight=0.2,
                metadata={"intent_type": intent_type, "inquiry": True},
            )

        if intent_type in STAGNATION_EXEMPT_RECOVERY_TYPES:
            # Designed escape types are the ANSWER to falsification — never
            # scored falsified by the arming counter their suppressed attempts
            # accumulate (mirrors the stagnation exemption: a vetoed recovery
            # is governance suppression, not a loop pathology; the type must be
            # able to pass the council or the trap is permanent).
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.4,
                reason=f"recovery type '{intent_type}' is the designed escape "
                       "from falsification; never scored as falsified",
                evidence_weight=0.2,
                metadata={"intent_type": intent_type, "recovery": True},
            )

        reasons = []
        dissent = False
        if model_falsified:
            reasons.append(f"world model falsified (recent_gap={model_gap:.2f})")
        if type_blocked >= FALSIFICATION_DISSENT_AFTER:
            dissent = True
            reasons.append(
                f"intent type '{intent_type}' produced no action for "
                f"{type_blocked} consecutive cycles (falsified loop)"
            )
        elif total_no_action >= FALSIFICATION_DISSENT_AFTER + 2:
            dissent = True
            reasons.append(
                f"intent type '{intent_type}' has {total_no_action} total "
                f"no-action outcomes — pattern of non-execution"
            )

        if dissent:
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.7,
                reason=" | ".join(reasons),
                evidence_weight=0.6,
                metadata={
                    "intent_type": intent_type,
                    "model_falsified": model_falsified,
                    "consecutive_no_action": type_blocked,
                    "total_no_action": total_no_action,
                },
            )

        if reasons:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.3,
                reason=" | ".join(reasons) + " (not yet dissenting)",
                evidence_weight=0.2,
                metadata={"intent_type": intent_type},
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.7,
            reason=f"intent type '{intent_type}' has no falsification record",
            evidence_weight=0.3,
            metadata={"intent_type": intent_type},
        )


__all__ = ["EvidenceProvenanceValidator", "FALSIFICATION_DISSENT_AFTER"]
