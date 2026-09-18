"""
Selection instrumentation — WHY an intent won, recorded not guessed.

Phase 1 of the selection experiment: capture, per cycle, the candidates, their
scores, whether each is executable or inquiry, its mission-progress estimate,
and the regime/blend that drove the choice. This module is NON-BEHAVIORAL:
`build_selection_decision` only reads state and returns a record. Enabling or
disabling it changes nothing about which intent is selected.

Mission progress is domain-agnostic: the pipeline may expose an optional
`_mission_progress_fn(state, intent) -> float` hook (higher = closer to the
mission). Absent the hook, mission progress is reported as None, never
invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Intent types that are information-gathering rather than mission-executing.
_INQUIRY_MARKERS = ("inquiry", "curiosity", "blended_inquiry", "perceive",
                    "memory_miss", "unknown_unknown")


@dataclass
class IntentScoreBreakdown:
    """One candidate intent and the numbers behind its selection.

    Attributes:
        intent_type: the candidate's intent type.
        source_stream: the stream that produced it (metadata `stream`), if any.
        select_score: the weighted score it carried into selection.
        j_score: the commitment/J score if computed for it.
        mission_progress: projected progress toward the mission, or None.
        is_inquiry: True for information-gathering intents.
        executable: True when the intent can produce a motion/action.
        selected: True for the intent that was finally chosen.
        rejected_reason: why it lost (regime/score), when known.
    """

    intent_type: str
    source_stream: Optional[str] = None
    select_score: float = 0.0
    j_score: Optional[float] = None
    mission_progress: Optional[float] = None
    is_inquiry: bool = False
    executable: bool = True
    selected: bool = False
    rejected_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "intent_type": self.intent_type,
            "source_stream": self.source_stream,
            "select_score": round(float(self.select_score), 6),
            "j_score": None if self.j_score is None else round(float(self.j_score), 6),
            "mission_progress": (None if self.mission_progress is None
                                 else round(float(self.mission_progress), 6)),
            "is_inquiry": self.is_inquiry,
            "executable": self.executable,
            "selected": self.selected,
            "rejected_reason": self.rejected_reason,
        }


@dataclass
class SelectionDecision:
    """The full selection record for one cycle.

    Attributes:
        cycle: cycle id.
        regime: "action" (blend<0.05), "blended" (0.05-0.95), or "inquiry" (>0.95).
        omega_value: the Ω uncertainty that drove the blend.
        omega_threshold: the (learned) threshold the Ω compared against.
        blend: the RAW sigmoid blend before any policy adjustment.
        blend_effective: the blend actually used (post-policy), or raw.
        curiosity_level: curiosity drive level (0 if absent).
        selection_policy: the active policy label ("control" by default).
        selected_type: the intent type finally selected.
        candidates: the scored candidate breakdowns.
    """

    cycle: int
    regime: str
    omega_value: float
    omega_threshold: float
    blend: float
    blend_effective: float
    curiosity_level: float
    selection_policy: str
    selected_type: Optional[str]
    candidates: List[IntentScoreBreakdown] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "cycle": self.cycle,
            "regime": self.regime,
            "omega_value": round(float(self.omega_value), 6),
            "omega_threshold": round(float(self.omega_threshold), 6),
            "blend": round(float(self.blend), 6),
            "blend_effective": round(float(self.blend_effective), 6),
            "curiosity_level": round(float(self.curiosity_level), 6),
            "selection_policy": self.selection_policy,
            "selected_type": self.selected_type,
            "candidates": [c.to_dict() for c in self.candidates],
        }


def is_inquiry_intent(intent: Any) -> bool:
    """Classify an intent as information-gathering vs mission-executing.

    Args:
        intent: an IntentIR (or any object with intent_type/metadata).

    Returns:
        True when the intent is inquiry-type.
    """
    if intent is None:
        return False
    meta = getattr(intent, "metadata", None) or {}
    if isinstance(meta, dict) and meta.get("stream") == "inquiry":
        return True
    itype = str(getattr(intent, "intent_type", "") or "")
    return any(marker in itype for marker in _INQUIRY_MARKERS)


def mission_progress(pipeline: Any, ctx: Any, intent: Any) -> Optional[float]:
    """Estimate an intent's projected mission progress (domain-agnostic).

    Args:
        pipeline: the pipeline (may expose `_mission_progress_fn`).
        ctx: the phase context (carries the current state).
        intent: the candidate intent.

    Returns:
        The hook's float value, or None when no hook/signal is available.
    """
    fn = getattr(pipeline, "_mission_progress_fn", None)
    if fn is None or intent is None:
        return None
    try:
        return float(fn(getattr(ctx, "state", None), intent))
    except Exception:
        return None


def _regime(blend: float) -> str:
    """Name the regime for a blend value.

    Args:
        blend: effective blend in [0, 1].

    Returns:
        "action", "blended", or "inquiry".
    """
    if blend < 0.05:
        return "action"
    if blend > 0.95:
        return "inquiry"
    return "blended"


def build_selection_decision(ctx: Any, pipeline: Any) -> Dict[str, Any]:
    """Build the non-behavioral selection record for the current cycle.

    Args:
        ctx: the PhaseContext after the select phase.
        pipeline: the pipeline (for config + optional mission hook).

    Returns:
        A JSON-ready dict (SelectionDecision.to_dict()).
    """
    blend = float(getattr(ctx, "inquiry_blend", 0.0) or 0.0)
    blend_eff = float(getattr(ctx, "_inquiry_blend_effective", blend) or blend)
    omega_value = float(getattr(ctx, "inquiry_omega_value", 0.0) or 0.0)
    threshold = 0.5
    learner = getattr(pipeline, "_omega_threshold_learner", None)
    if learner is not None and hasattr(learner, "get_threshold"):
        try:
            threshold = float(learner.get_threshold())
        except Exception:
            threshold = 0.5
    curiosity = 0.0
    cstate = getattr(ctx, "curiosity_state", None)
    if isinstance(cstate, dict):
        curiosity = float(cstate.get("curiosity_level", 0.0) or 0.0)
    policy = getattr(getattr(pipeline, "config", None), "selection_policy", "control")

    selected = getattr(ctx, "selected_intent", None)
    selected_type = getattr(selected, "intent_type", None) if selected else None

    candidates: List[IntentScoreBreakdown] = []
    seen = set()
    for intent, score in (getattr(ctx, "intents", None) or []):
        itype = getattr(intent, "intent_type", None)
        if itype is None or itype in seen:
            continue
        seen.add(itype)
        inquiry = is_inquiry_intent(intent)
        candidates.append(IntentScoreBreakdown(
            intent_type=itype,
            source_stream=(getattr(intent, "metadata", {}) or {}).get("stream"),
            select_score=float(score),
            mission_progress=mission_progress(pipeline, ctx, intent),
            is_inquiry=inquiry,
            executable=not inquiry,
            selected=(itype == selected_type),
        ))
    if selected_type and selected_type not in seen:
        inquiry = is_inquiry_intent(selected)
        candidates.append(IntentScoreBreakdown(
            intent_type=selected_type,
            source_stream=(getattr(selected, "metadata", {}) or {}).get("stream"),
            select_score=1.0,
            mission_progress=mission_progress(pipeline, ctx, selected),
            is_inquiry=inquiry,
            executable=not inquiry,
            selected=True,
            rejected_reason="direct_selection",
        ))

    decision = SelectionDecision(
        cycle=int(getattr(ctx, "cycle_count", 0) or 0),
        regime=_regime(blend_eff),
        omega_value=omega_value,
        omega_threshold=threshold,
        blend=blend,
        blend_effective=blend_eff,
        curiosity_level=curiosity,
        selection_policy=str(policy),
        selected_type=selected_type,
        candidates=candidates,
    )
    return decision.to_dict()


__all__ = [
    "IntentScoreBreakdown", "SelectionDecision", "is_inquiry_intent",
    "mission_progress", "build_selection_decision",
]
