"""
Items 6-8: post-action observation -> Reality Gap -> capability authority.

PATTERN (a closed feedback loop, measured not asserted): after a LIVE action
the adapter takes a GENUINE post-action read of the real world (item 6). That
observation is compared against the prediction to produce a bounded, comparable
Reality Gap (item 7). The gap is fed into the existing ``RealityGapTracker`` and
mapped onto the capability's AUTHORITY (item 8): a low gap reinforces fidelity,
a persistent/large gap reduces it — and a capability whose measured authority
falls below the FAIL threshold can no longer ACT.

One canonical metric and one canonical authority derivation live here so no
consumer invents its own (Λ6.7). The metric is deliberately simple, bounded, and
deterministic:

    gap(p, o) = 0.0                         when p == o (exact match)
              = 1.0                         when either side is absent
              = clamp(1 - similarity)       otherwise, similarity in [0, 1]

``similarity`` is ``difflib.SequenceMatcher(None, p, o).ratio()`` — a normalized,
language-agnostic character-overlap ratio. A completely disjoint pair maps to a
gap near 1.0; a near-miss maps to a small positive gap. The metric never returns
NaN, is bounded to [0, 1], and is symmetric.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np

from telos.core.governance.capability_authorization import (
    CapabilityAuthorization, CapabilityStatus,
)
from telos.world.epistemic import RealityGapTracker

logger = logging.getLogger("telos_capability_authority")

#: The canonical metric name recorded alongside every measured gap.
GAP_METRIC = "normalized_text_divergence"
#: An exact match.
GAP_EXACT = 0.0
#: An absent/unreadable observation is a total miss.
GAP_MISSING = 1.0

#: Fidelity at or above this -> PASS (authority reinforced).
AUTHORITY_PASS_FIDELITY = 0.7
#: Fidelity strictly below this -> FAIL (authority lost; ACT blocked).
AUTHORITY_FAIL_FIDELITY = 0.5


def text_reality_gap(predicted: Any, observed: Any) -> float:
    """Compute the bounded Reality Gap between a prediction and an observation.

    Args:
        predicted: the predicted result (coerced to str for comparison).
        observed: the post-action observation (coerced to str).

    Returns:
        0.0 on an exact match; 1.0 when either side is None; otherwise
        ``clamp(1 - SequenceMatcher ratio)`` in (0, 1]. Always finite.
    """
    if predicted is None or observed is None:
        return GAP_MISSING
    p = str(predicted)
    o = str(observed)
    if p == o:
        return GAP_EXACT
    ratio = difflib.SequenceMatcher(None, p, o).ratio()
    gap = 1.0 - float(ratio)
    return float(min(1.0, max(0.0, gap)))


def observation_fingerprint(content: Any) -> str:
    """A stable content fingerprint for an observation (item 6).

    Args:
        content: the observed content (coerced to str).

    Returns:
        The sha256 hex digest of the UTF-8 content (empty input -> digest of b"").
    """
    data = b"" if content is None else str(content).encode("utf-8", "replace")
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class AuthorityState:
    """The measured authority of ONE capability at a point in time.

    Attributes:
        capability: the capability name.
        model_id: the RealityGapTracker model id backing the capability.
        status: the derived ``CapabilityStatus`` for the model_fidelity gate.
        fidelity: 0..1 recent-window fidelity, or None (untested/stale).
        validations: how many verified outcomes have been recorded.
        recent_mean_gap: mean gap over the recent window, or None.
        last_gap: the most recent measured gap, or None.
        ever_falsified: whether any recorded gap exceeded the falsification
            threshold.
        reason: a human-readable explanation of the status.
    """

    capability: str
    model_id: str
    status: CapabilityStatus
    fidelity: Optional[float]
    validations: int
    recent_mean_gap: Optional[float]
    last_gap: Optional[float]
    ever_falsified: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Serializable authority record.

        Returns:
            Dict of the authority fields (status as its string value).
        """
        return {
            "capability": self.capability,
            "model_id": self.model_id,
            "status": self.status.value,
            "fidelity": self.fidelity,
            "validations": self.validations,
            "recent_mean_gap": self.recent_mean_gap,
            "last_gap": self.last_gap,
            "ever_falsified": self.ever_falsified,
            "reason": self.reason,
        }


class CapabilityAuthority:
    """Per-capability authority derived from measured Reality Gaps.

    This is a THIN derivation over the existing ``RealityGapTracker`` — it owns
    no parallel history. ``record`` feeds each measured gap into the tracker
    (encoded so the tracker's own MD equals the gap) and ``state`` reads the
    tracker's ``model_fidelity`` back out, mapping it onto the
    ``CapabilityAuthorization`` model_fidelity dimension. There is exactly one
    authority source (Λ6.7).
    """

    #: Fidelity at/above which the model_fidelity gate PASSes.
    PASS_FIDELITY: float = AUTHORITY_PASS_FIDELITY
    #: Fidelity strictly below which the model_fidelity gate FAILs.
    FAIL_FIDELITY: float = AUTHORITY_FAIL_FIDELITY
    #: Model-id namespace for world-action capabilities.
    MODEL_PREFIX: str = "world_action"

    def __init__(self, tracker: Optional[RealityGapTracker] = None, *,
                 state_path: Optional[str] = None):
        """Construct the authority ledger over a RealityGapTracker.

        DURABLE AUTHORITY (restart safety): when ``state_path`` is configured the
        ledger PERSISTS its measured evidence (per-model gap history, sticky
        falsification, recency stamp) after every recording and RELOADS it on
        construction. The measured falsification state of a capability is thus
        not erased by a process restart — a falsified capability stays FAILed
        even though the canonical certification registry still says
        LIVE-CERTIFIED. This store is runtime EVIDENCE, deliberately separate
        from the operator-gated canonical certification registry (Λ6.7): the
        runtime may withhold authority automatically; only canonical registry
        mutation requires an explicit operator.

        Fails CLOSED: if the configured store exists but is unreadable or
        malformed, :meth:`state` withholds authority for every capability
        (FAIL) rather than silently reverting to the act-then-learn bootstrap.
        An ABSENT store is a genuine first run (bootstrap, UNKNOWN) — not
        recovery.

        Args:
            tracker: the existing tracker to reuse (defaults to a fresh one).
            state_path: optional durable evidence path. None (default) keeps
                the ledger purely in-memory (byte-identical default behavior).
        """
        self.tracker = tracker if tracker is not None else RealityGapTracker()
        self.state_path: Optional[str] = (
            str(state_path) if state_path else None)
        #: True when a configured evidence store existed but could not be
        #: trusted; every authority query then fails closed.
        self._evidence_unreadable: bool = False
        if self.state_path:
            self._load_state()

    # ── durable evidence store ────────────────────────────────────────────

    def _load_state(self) -> None:
        """Load the persisted evidence store, failing closed when unreadable.

        An absent file is a first run (no prior evidence -> bootstrap). A file
        that exists but is unreadable or malformed sets ``_evidence_unreadable``
        so authority is withheld rather than silently restored.
        """
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except Exception as e:  # unreadable safety record -> FAIL CLOSED
            self._evidence_unreadable = True
            logger.error(
                "capability authority evidence %r unreadable (%s); authority "
                "fails closed (no capability is authorized from an unreadable "
                "store)", self.state_path, e)
            return
        if not isinstance(data, dict):
            self._evidence_unreadable = True
            logger.error(
                "capability authority evidence %r is not a JSON object; "
                "authority fails closed", self.state_path)
            return
        payload = data.get("models", data)
        try:
            self.tracker.load_state(payload)
        except Exception as e:  # malformed record -> FAIL CLOSED
            self._evidence_unreadable = True
            logger.error(
                "capability authority evidence %r malformed (%s); authority "
                "fails closed", self.state_path, e)

    def _persist_state(self) -> None:
        """Atomically persist the measured evidence (best-effort, audited).

        A persistence failure is logged loudly (never silently swallowed): if
        the falsification record cannot be written, restart safety for this
        process cannot be guaranteed.
        """
        if not self.state_path:
            return
        try:
            directory = os.path.dirname(self.state_path) or "."
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=directory, prefix=".authority_ev_", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"models": self.tracker.to_state()}, f, indent=2)
                os.replace(tmp, self.state_path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error(
                "capability authority evidence persist to %r FAILED (%s); "
                "restart safety for this authority is not guaranteed",
                self.state_path, e)

    def model_id(self, capability: str) -> str:
        """The tracker model id for a capability.

        Args:
            capability: the capability name.

        Returns:
            The canonical ``world_action:<capability>`` model id.
        """
        return f"{self.MODEL_PREFIX}:{capability}"

    def record(self, capability: str, gap: float, *, cycle: Optional[int] = None
               ) -> AuthorityState:
        """Record one measured gap and return the recalibrated authority.

        The gap is encoded as ``predicted=[1.0]``, ``observed=[1 - gap]`` so the
        tracker's own norm-based MD reproduces the measured gap exactly.

        Args:
            capability: the capability the gap was measured for.
            gap: the bounded Reality Gap (clamped to [0, 1]).
            cycle: pipeline cycle of the measurement (recency stamp).

        Returns:
            The AuthorityState AFTER the recalibration.
        """
        g = float(min(1.0, max(0.0, float(gap))))
        self.tracker.record(
            self.model_id(capability),
            np.array([1.0]),
            np.array([1.0 - g]),
            cycle=cycle,
        )
        state = self.state(capability, now_cycle=cycle)
        # Durable authority: persist the measured evidence so a process restart
        # cannot resurrect a falsified capability's authority.
        self._persist_state()
        return state

    def state(self, capability: str, *,
              now_cycle: Optional[int] = None) -> AuthorityState:
        """Read the current authority of a capability.

        Args:
            capability: the capability name.
            now_cycle: current pipeline cycle (makes stale evidence explicit).

        Returns:
            The AuthorityState. A never-validated capability is UNKNOWN
            (act-then-learn must be able to collect its first evidence). A
            capability whose last validated window was FALSIFIED stays FAIL
            even once its evidence goes stale — time alone must never restore
            authority (the safe direction is durable); only fresh verified
            evidence can. A stale, never-falsified model is UNKNOWN.
        """
        mid = self.model_id(capability)
        if self._evidence_unreadable:
            # The configured evidence store could not be trusted: withhold
            # authority (FAIL) rather than silently reverting to the permissive
            # act-then-learn bootstrap (fail-closed).
            return AuthorityState(
                capability=capability, model_id=mid, status=CapabilityStatus.FAIL,
                fidelity=None, validations=0, recent_mean_gap=None,
                last_gap=None, ever_falsified=False,
                reason=("authority evidence store is unreadable/malformed — "
                        "failing closed (an operator-reviewed store is "
                        "required); no capability is authorized"))
        model = self.tracker.model(mid)
        fidelity = self.tracker.model_fidelity(mid, now_cycle=now_cycle)
        recent = model.recent_mean_gap if model.gap_history else None
        last = model.gap_history[-1] if model.gap_history else None
        if model.validation_count == 0:
            status = CapabilityStatus.UNKNOWN
            reason = "no verified action has been recorded for this capability"
        elif fidelity is None:
            # Stale (no REAL validation within the truth window). Staleness is
            # absence of CURRENT evidence, not recovery: for a model whose last
            # validated window was already falsified, withhold authority (FAIL)
            # rather than silently re-authorize on the clock. This is the
            # "losing authority incorrectly" fix — a stale falsified record must
            # never pass a gate that only vetoes FAIL. A stale model that was
            # never falsified falls through to UNKNOWN (act-then-learn).
            stale_fidelity = (None if recent is None
                              else float(min(1.0, max(0.0, 1.0 - float(recent)))))
            if stale_fidelity is not None \
                    and stale_fidelity < self.FAIL_FIDELITY:
                status = CapabilityStatus.FAIL
                reason = (f"authority evidence is stale after a falsified "
                          f"window (recent mean gap {recent:.3f}); fresh "
                          f"verified evidence is required — time alone does "
                          f"not restore authority")
            else:
                status = CapabilityStatus.UNKNOWN
                reason = "authority evidence is stale (not refreshed recently)"
        elif fidelity >= self.PASS_FIDELITY:
            status = CapabilityStatus.PASS
            reason = (f"recent mean gap {recent:.3f} -> fidelity "
                      f"{fidelity:.3f} (>= {self.PASS_FIDELITY})")
        elif fidelity < self.FAIL_FIDELITY:
            status = CapabilityStatus.FAIL
            reason = (f"recent mean gap {recent:.3f} -> fidelity "
                      f"{fidelity:.3f} (< {self.FAIL_FIDELITY}); ACT revoked")
        else:
            status = CapabilityStatus.LIMITED
            reason = (f"recent mean gap {recent:.3f} -> fidelity "
                      f"{fidelity:.3f} (degraded, between "
                      f"{self.FAIL_FIDELITY} and {self.PASS_FIDELITY})")
        return AuthorityState(
            capability=capability, model_id=mid, status=status,
            fidelity=(None if fidelity is None else float(fidelity)),
            validations=model.validation_count,
            recent_mean_gap=(None if recent is None else float(recent)),
            last_gap=(None if last is None else float(last)),
            ever_falsified=bool(model.ever_falsified),
            reason=reason,
        )

    def status(self, capability: str, *,
               now_cycle: Optional[int] = None) -> CapabilityStatus:
        """The derived model_fidelity gate status for a capability.

        Args:
            capability: the capability name.
            now_cycle: current pipeline cycle.

        Returns:
            The CapabilityStatus (PASS / LIMITED / FAIL / UNKNOWN).
        """
        return self.state(capability, now_cycle=now_cycle).status

    def capability_authorization(
            self, capability: str, *, now_cycle: Optional[int] = None,
            overrides: Optional[Dict[str, CapabilityStatus]] = None
    ) -> CapabilityAuthorization:
        """Build a full CapabilityAuthorization with derived model_fidelity.

        Every dimension defaults to PASS EXCEPT ``model_fidelity``, which is the
        capability's MEASURED authority. This object is directly consumable by
        ``WorldActionRunner`` / ``ActionExecutor`` — the existing hard-gate
        machinery — so a fidelity FAIL vetoes ACT with no new gate type.

        Args:
            capability: the capability name.
            now_cycle: current pipeline cycle.
            overrides: optional per-dimension statuses that win over defaults.

        Returns:
            The conjunctive CapabilityAuthorization for this capability.
        """
        dims = {d.name: CapabilityStatus.PASS
                for d in CapabilityAuthorization().dimensions}
        dims["model_fidelity"] = self.status(capability, now_cycle=now_cycle)
        if overrides:
            dims.update(overrides)
        return CapabilityAuthorization(**dims)


__all__ = [
    "GAP_METRIC", "GAP_EXACT", "GAP_MISSING",
    "AUTHORITY_PASS_FIDELITY", "AUTHORITY_FAIL_FIDELITY",
    "text_reality_gap", "observation_fingerprint",
    "AuthorityState", "CapabilityAuthority",
]
