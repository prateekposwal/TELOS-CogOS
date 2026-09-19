"""
TELOS Durability Contract — ONE integrity-verifiable authority/evidence boundary.

PRINCIPLE (adopted):
    Safety-critical authority and the evidence required to justify that authority
    must have an explicit, durable, integrity-verifiable state boundary.
    There is exactly ONE persistence mechanism for runtime authority evidence —
    never a second competing store.

This module is the single implementation of that mechanism. Every runtime
authority/evidence store (the capability-authority ledger's measured Reality
Gaps, and the pipeline's own per-model Reality Gap evidence) is written and read
through the SAME envelope:

    {
      "schema_version": 1,                 # contract version
      "kind": "telos_authority_evidence",   # what state this is
      "checksum": "<sha256 of payload>",    # integrity of the evidence
      "sequence": 7,                        # monotonic (only when configured)
      "anchor": "hmac",                     # trust anchor (only when non-local)
      "mac": "<hmac of the core>",          # anchor authentication (non-local)
      "payload": { ... }                    # a RealityGapTracker.to_state()
    }

The envelope is written ATOMICALLY (temp file + fsync + os.replace). There is
one state boundary per configured path; a reader therefore never observes a
torn mixture of an old authority record and a new evidence record.

PLUGGABLE INTEGRITY ANCHOR (see ``telos/core/actions/integrity.py``):
    The integrity field is pluggable and selected by EXPLICIT configuration
    (``TELOS_DURABILITY_INTEGRITY``):

      * ``local`` (DEFAULT) — the historical sha256 payload checksum, no secret.
        Byte-identical to the pre-anchor contract. Detects ACCIDENTAL corruption
        only; NOT tamper- or rollback-resistant.
      * ``hmac`` — the envelope core (schema + kind + sequence + payload) is
        authenticated with an HMAC whose key lives OUTSIDE the artifact
        (``TELOS_DURABILITY_HMAC_KEY`` or a restricted key file; a Keychain-held
        key is injected into the env at launch). Editing the state (or its
        checksum) without the key fails verification.
      * ``witness`` — ``hmac`` PLUS a separate witness store recording the
        latest accepted ``sequence`` + MAC, so a rollback to an older valid
        state is rejected while the witness is intact.

    A configured-but-unusable anchor resolves FAIL CLOSED and NEVER silently
    downgrades to ``local`` (see ``UnavailableAnchor``). A ``sequence`` is
    carried (and enforced against the anchor's freshness floor) whenever an
    anchor requires freshness — the anti-rollback property.

EXTERNAL TRUST ANCHOR (see ``telos/core/actions/trust_anchor.py``):
    Local cryptography cannot detect an attacker who controls the filesystem and
    rewrites state + integrity metadata as a consistent historical pair, nor a
    replay of a previously valid state + local witness pair: the freshness root
    lives on the same disk. An OPTIONAL, operator-configured EXTERNAL trust anchor
    closes that gap. When enabled, after local integrity verifies the state is
    also checked against the anchor's stored witnessed record (a monotonic
    ``sequence`` + ``state_hash`` + ``evidence_hash``), and only a ``CURRENT``
    verdict permits the state to claim authority. The provider lives in
    ``trust_anchor.py`` and makes no authority decision; this module maps the
    provider's verdict fail-closed. It is DEFAULT-OFF (``TELOS_TRUST_ANCHOR=off``),
    so existing behaviour is byte-identical.

    When the external anchor is enabled, the local filesystem is STORAGE, not the
    ultimate authority: ``STALE``/``ROLLBACK``/``INVALID``/``CONFLICT``/``UNKNOWN``
    (safety-critical) and ``UNAVAILABLE`` all revoke authority with no silent
    fallback and no fail-open grace period.

DURABLE vs EPHEMERAL (the load-bearing distinction):

  * DURABLE (production) — a path IS configured. State is loaded on
    construction and rewritten atomically on every evidence mutation, so a
    process restart cannot resurrect falsified authority. Production
    construction MUST make durability explicit (see ``DurabilityMode`` and
    ``telos/tools/durability_audit.py``).
  * EPHEMERAL (tests / in-memory) — no path is configured. Nothing is read or
    written; the ledger lives only in memory. Supported and lightweight by
    design, but NEVER acceptable for a safety-critical production authority.

READ CLASSIFICATION (failure modes are first-class, never collapsed):

  * FIRST_RUN  — the configured store does NOT exist. This is an honest cold
    start: there is no prior evidence. Initialization is safe.
  * LOADED     — the store exists, is a well-formed envelope of the expected
    kind + supported schema, and its integrity verifies (checksum and/or the
    configured anchor's MAC, plus the freshness floor). The payload is trusted.
  * CORRUPTED  — the store exists but is unreadable, not a JSON object, missing
    the envelope, of the wrong kind, of an unsupported (newer) schema version,
    fails its integrity check, is anchored in a mode the reader is not
    configured for (a downgrade attempt), or carries a sequence OLDER than the
    accepted freshness floor (a rollback/replay). TAMPERING, truncation and
    REPLAY are all in this class: a corrupted/tampered/stale safety-critical
    store FAILS CLOSED (no authority is granted, and no automatic reconstruction
    from stale positive state occurs). It is NEVER silently treated as
    FIRST_RUN.

SECURITY BOUNDARY (honest statement):
    Without an external trust anchor: trusted local disk is the security
    boundary. ``local`` detects accidental corruption and makes deletion
    explicit, and is NOT tamper- or rollback-resistant. ``hmac`` lifts the
    boundary to possession of the key — it stops an attacker who can edit ONLY
    the state file, but NOT an attacker who can read the key (i.e. who has the
    user account/OS). ``witness`` additionally detects rollback to an older
    valid state while the LOCAL witness is intact; replaying an old state + the
    matching old local witness is NOT detectable (the same-disk limitation).
    With an external trust anchor: local disk is storage, not the ultimate
    authority. A fully compromised local FILESYSTEM (state + checksums/envelopes
    + local metadata + historical valid state) can no longer silently make an old
    or forged state appear current, because the freshness/authenticity record
    lives outside that filesystem.

    NOT claimed: protection against compromise of the external trust anchor
    itself, nor against a LIVE compromised process that can read the anchor's
    write credential and publish forged-but-newer records. True independence
    requires the anchor (and its write credential) to be outside the local
    account's control.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from telos.core.actions.integrity import (
    AnchorUnavailable, HmacAnchor, IntegrityAnchor, IntegrityMode, LocalAnchor,
    UnavailableAnchor, WitnessAnchor, load_hmac_key, resolve_anchor,
    state_core_bytes,
)
from telos.core.actions.trust_anchor import (
    AnchorIdentity, DisabledTrustAnchor, TrustAnchor, TrustAnchorError,
    TrustVerdict, TrustVerification, WitnessRecord, WitnessScope,
    hash_envelope_core, resolve_trust_anchor,
)

logger = logging.getLogger("telos_durability")

#: The durability envelope schema version. Bump on an incompatible change.
SCHEMA_VERSION = 1

#: The single kind for runtime authority/evidence state (a RealityGapTracker
#: ``to_state()`` mapping). Capability authority is a PROJECTION of this state
#: and is never persisted separately — so authority and evidence cannot
#: disagree.
KIND_AUTHORITY_EVIDENCE = "telos_authority_evidence"


class StateOutcome(str, Enum):
    """How a configured durable store resolved on read."""

    FIRST_RUN = "FIRST_RUN"
    LOADED = "LOADED"
    CORRUPTED = "CORRUPTED"


class DurabilityMode(str, Enum):
    """Whether an authority/evidence ledger is durable or intentionally ephemeral."""

    DURABLE = "DURABLE"
    EPHEMERAL = "EPHEMERAL"


@dataclass(frozen=True)
class StateLoadResult:
    """The classified outcome of reading a configured durable store.

    Attributes:
        outcome: FIRST_RUN / LOADED / CORRUPTED.
        payload: the envelope payload when LOADED, else None.
        reason: a human-readable explanation of the classification.
        path: the store path inspected.
        sequence: the monotonic sequence carried by the envelope, if any.
        anchor_mode: the trust anchor the envelope declares (``local`` when
            unanchored), if it could be determined.
    """

    outcome: StateOutcome
    payload: Optional[Dict[str, Any]] = None
    reason: str = ""
    path: str = ""
    sequence: Optional[int] = None
    anchor_mode: Optional[str] = None
    trust_verdict: Optional[str] = None
    trust_reason: str = ""

    @property
    def first_run(self) -> bool:
        """Whether the store was absent (an honest cold start)."""
        return self.outcome is StateOutcome.FIRST_RUN

    @property
    def corrupted(self) -> bool:
        """Whether the store exists but could not be trusted (fail closed)."""
        return self.outcome is StateOutcome.CORRUPTED


def canonical_payload_bytes(payload: Any) -> bytes:
    """Canonical, deterministic bytes for an evidence payload.

    Sorting keys and using the most compact separators makes the checksum
    stable across processes and Python versions; ``allow_nan=False`` rejects
    non-finite floats (which are never valid evidence).

    Args:
        payload: the JSON-serializable evidence payload.

    Returns:
        UTF-8 encoded canonical JSON bytes.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def payload_checksum(payload: Any) -> str:
    """The sha256 integrity digest of an evidence payload.

    Args:
        payload: the JSON-serializable evidence payload.

    Returns:
        The sha256 hex digest of :func:`canonical_payload_bytes`.
    """
    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def build_envelope(kind: str, payload: Any, *,
                   schema_version: int = SCHEMA_VERSION,
                   sequence: Optional[int] = None,
                   anchor: Optional[IntegrityAnchor] = None
                   ) -> Dict[str, Any]:
    """Wrap a payload in the canonical durability envelope.

    With neither ``sequence`` nor a signing ``anchor`` this returns EXACTLY the
    historical four-key envelope (byte-identical default). A ``sequence`` is
    added only when supplied; a signing anchor adds an ``anchor`` mode and a
    ``mac`` over the envelope core.

    Args:
        kind: the state kind (the expected producer/consumer contract).
        payload: the evidence payload.
        schema_version: the envelope schema version.
        sequence: an optional monotonic sequence to carry in the envelope.
        anchor: an optional integrity anchor; only a signing anchor (hmac /
            witness) changes the envelope shape.

    Returns:
        The envelope dict (schema_version, kind, checksum[, sequence]
        [, anchor, mac], payload).
    """
    envelope: Dict[str, Any] = {
        "schema_version": int(schema_version),
        "kind": str(kind),
        "checksum": payload_checksum(payload),
        "payload": payload,
    }
    if sequence is not None:
        envelope["sequence"] = int(sequence)
    if anchor is not None and anchor.requires_signature:
        core = state_core_bytes(kind, payload, schema_version=schema_version,
                                sequence=sequence)
        envelope["anchor"] = anchor.mode.value
        envelope["mac"] = anchor.tag(core)
    return envelope


def default_witness_scope(kind: str, *, producer_id: str = "telos",
                          world_id: str = "default",
                          capability_id: str = "*") -> WitnessScope:
    """The default witnessed scope for a store kind.

    Args:
        kind: the envelope kind (used as the store identity).
        producer_id: the producer identity that writes the state.
        world_id: the world/domain identity the state describes.
        capability_id: the capability identity, or ``*`` for a multi-capability
            store.

    Returns:
        The :class:`WitnessScope`.
    """
    return WitnessScope(store_id=str(kind), producer_id=producer_id,
                        world_id=world_id, capability_id=capability_id)


def build_witness_record(*, kind: str, payload: Any, schema_version: int,
                         sequence: int, scope: WitnessScope,
                         prev: Optional["tuple[str, int]"] = None,
                         witness_id: str = "", witness_version: int = 0,
                         timestamp: float = 0.0) -> WitnessRecord:
    """Build the witnessed record for a local envelope.

    The ``state_hash`` binds the canonical envelope core (schema + kind +
    sequence + payload), so editing ANY of them diverges from the witness. The
    ``evidence_hash`` binds the canonical payload alone.

    Args:
        kind: the envelope kind.
        payload: the evidence payload.
        schema_version: the envelope schema version.
        sequence: the monotonic sequence carried by the envelope.
        scope: the witnessed subject identity.
        prev: optional ``(prev_state_hash, prev_sequence)`` linkage.
        witness_id: the witness identity that will store the record.
        witness_version: the witness implementation version.
        timestamp: an informational wall-clock stamp (never used for freshness).

    Returns:
        The :class:`WitnessRecord` for this envelope.
    """
    core = state_core_bytes(kind, payload, schema_version=schema_version,
                            sequence=sequence)
    prev_hash, prev_seq = (prev if prev is not None else ("", 0))
    return WitnessRecord(
        sequence=int(sequence),
        state_hash=hash_envelope_core(core),
        evidence_hash=payload_checksum(payload),
        scope=scope,
        envelope_schema_version=int(schema_version),
        kind=str(kind),
        timestamp=float(timestamp),
        prev_state_hash=str(prev_hash),
        prev_sequence=int(prev_seq),
        witness_id=str(witness_id),
        witness_version=int(witness_version),
    )


def atomic_write_state(path: str, kind: str, payload: Any, *,
                       schema_version: int = SCHEMA_VERSION,
                       sequence: Optional[int] = None,
                       anchor: Optional[IntegrityAnchor] = None,
                       trust_anchor: Optional[TrustAnchor] = None,
                       witness_scope: Optional[WitnessScope] = None) -> None:
    """Atomically persist an enveloped evidence payload.

    The write is temp-file + fsync + ``os.replace`` so a crash or a concurrent
    reader can never observe a half-written authority/evidence record. When an
    anchor requires freshness a sequence is auto-assigned from the anchor's
    accepted floor; after the state lands, the anchor's witness (if any) is
    raised.

    Args:
        path: the destination store path.
        kind: the state kind to stamp into the envelope.
        payload: the evidence payload.
        schema_version: the envelope schema version.
        sequence: an optional explicit sequence (overrides auto-assignment).
        anchor: an optional integrity anchor. A configured-but-unusable anchor
            raises :class:`AnchorUnavailable` (fail closed, no downgrade).
        trust_anchor: an optional EXTERNAL trust anchor. When configured and
            enabled it is the authority: the witnessed record is published
            BEFORE the local write, so the local file can never run ahead of the
            external freshness root. Disabled (default) -> no external contact.
        witness_scope: the witnessed subject identity; defaults to a scope
            derived from ``kind``.

    Raises:
        AnchorUnavailable: when a configured anchor is unusable or cannot be
            authenticated, or the external trust anchor rejects/cannot witness
            (fail closed).
        OSError/ValueError: when the payload cannot be serialized or the write
            fails; callers decide whether that is fatal.
    """
    trust_enabled = bool(trust_anchor is not None
                         and getattr(trust_anchor, "enabled", False))
    if trust_anchor is not None and trust_enabled and not trust_anchor.available:
        raise AnchorUnavailable(
            f"refusing to persist state with an unusable external trust anchor: "
            f"{trust_anchor.name}")
    scope = witness_scope or default_witness_scope(kind)
    if trust_enabled:
        # The external anchor is the authority: publish the witnessed record
        # BEFORE writing local state so the local file is never ahead of the
        # freshness root. A failure here writes NOTHING (fail closed). The
        # provider's own error class is normalized to the durability contract's
        # AnchorUnavailable (the ONE fail-closed error callers already handle).
        try:
            latest = trust_anchor.get_latest(scope)
        except TrustAnchorError as e:
            raise AnchorUnavailable(str(e))
        if sequence is None:
            sequence = 1 if latest is None else int(latest.sequence) + 1
        elif latest is not None and int(sequence) <= int(latest.sequence):
            raise AnchorUnavailable(
                f"refusing to witness sequence {sequence} at or below the "
                f"external freshness floor {latest.sequence}")
        record = build_witness_record(
            kind=kind, payload=payload, schema_version=schema_version,
            sequence=int(sequence), scope=scope,
            prev=(latest.state_hash, latest.sequence) if latest else None,
            witness_id=getattr(trust_anchor, "_witness_id", "") or "",
            witness_version=getattr(trust_anchor, "_witness_version", 0) or 0)
        try:
            trust_anchor.witness(record)  # raises -> no local write
        except TrustAnchorError as e:
            raise AnchorUnavailable(str(e))
    if anchor is not None and not anchor.available:
        raise AnchorUnavailable(
            f"refusing to persist state with an unusable integrity anchor: "
            f"{anchor.describe()}")
    if anchor is not None and anchor.requires_sequence and sequence is None:
        sequence = anchor.next_sequence()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    envelope = build_envelope(kind, payload, schema_version=schema_version,
                              sequence=sequence, anchor=anchor)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".telos_state_",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2, sort_keys=True, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if anchor is not None and sequence is not None:
        core = state_core_bytes(kind, payload, schema_version=schema_version,
                                sequence=sequence)
        anchor.accept(sequence, core, envelope.get("mac", ""))


def _classify_sequence(raw: Dict[str, Any]) -> "tuple[Optional[int], str]":
    """Validate the optional monotonic sequence field.

    Args:
        raw: the parsed envelope mapping.

    Returns:
        ``(sequence, "")`` when valid/absent, else ``(None, reason)``.
    """
    sequence = raw.get("sequence")
    if sequence is None:
        return None, ""
    if isinstance(sequence, bool) or not isinstance(sequence, int) \
            or sequence < 0:
        return None, f"durable store sequence is invalid: {sequence!r}"
    return int(sequence), ""


def read_state(path: Optional[str], *, expected_kind: str,
               supported_schema: int = SCHEMA_VERSION,
               anchor: Optional[IntegrityAnchor] = None,
               trust_anchor: Optional[TrustAnchor] = None,
               witness_scope: Optional[WitnessScope] = None) -> StateLoadResult:
    """Read and classify a configured durable store (fail closed).

    Args:
        path: the store path (None/empty is a configuration error -> CORRUPTED).
        expected_kind: the required envelope kind.
        supported_schema: the highest schema version this code understands; a
            newer (unknown) version is CORRUPTED, never guessed.
        anchor: the configured integrity anchor. When it requires a signature
            the envelope must be anchored and its MAC must verify; when it
            requires freshness the sequence must be >= the anchor's floor. A
            configured-but-unusable anchor -> CORRUPTED (no silent downgrade).
        trust_anchor: an optional EXTERNAL trust anchor. When configured and
            enabled the state is additionally checked against the anchor's
            witnessed record; any verdict other than CURRENT -> CORRUPTED
            (fail closed, no silent fallback, no grace period).
        witness_scope: the witnessed subject identity; defaults to a scope
            derived from ``expected_kind``.

    Returns:
        A :class:`StateLoadResult` classifying the store as FIRST_RUN, LOADED,
        or CORRUPTED. CORRUPTED carries a reason and NEVER a payload.
    """

    def _corrupt(reason: str, *,
                 sequence: Optional[int] = None,
                 anchor_mode: Optional[str] = None,
                 trust_verdict: Optional[str] = None,
                 trust_reason: str = "") -> StateLoadResult:
        return StateLoadResult(StateOutcome.CORRUPTED, reason=reason,
                               path=str(path or ""), sequence=sequence,
                               anchor_mode=anchor_mode,
                               trust_verdict=trust_verdict,
                               trust_reason=trust_reason)

    trust_enabled = bool(trust_anchor is not None
                         and getattr(trust_anchor, "enabled", False))
    scope = witness_scope or default_witness_scope(expected_kind)
    if trust_enabled and not trust_anchor.available:
        return _corrupt(
            f"external trust anchor unavailable ({trust_anchor.name}); failing "
            f"closed", trust_verdict=TrustVerdict.UNAVAILABLE.value)
    if anchor is not None and not anchor.available:
        return _corrupt(
            f"integrity anchor unavailable ({anchor.describe()}); failing "
            f"closed — refusing to fall back to the 'local' checksum")
    if not path:
        return _corrupt("no durable store path configured")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        if trust_enabled:
            try:
                latest = trust_anchor.get_latest(scope)
            except (AnchorUnavailable, TrustAnchorError) as e:
                return _corrupt(
                    f"external trust anchor unavailable: {e}",
                    trust_verdict=TrustVerdict.UNAVAILABLE.value)
            if latest is not None:
                return _corrupt(
                    f"local state is absent while the external witness holds "
                    f"sequence {latest.sequence} (rollback/deletion); failing "
                    f"closed",
                    sequence=int(latest.sequence),
                    trust_verdict=TrustVerdict.ROLLBACK.value)
        return StateLoadResult(
            StateOutcome.FIRST_RUN,
            reason="durable store absent (honest first run)",
            path=str(path))
    except Exception as e:
        return _corrupt(f"durable store unreadable/malformed: {e}")
    if not isinstance(raw, dict):
        return _corrupt("durable store is not a JSON object")
    for key in ("schema_version", "kind", "checksum", "payload"):
        if key not in raw:
            return _corrupt(
                f"durable store is missing the integrity envelope (no {key!r})")
    if raw.get("kind") != expected_kind:
        return _corrupt(
            f"durable store kind mismatch: expected {expected_kind!r}, "
            f"found {raw.get('kind')!r}")
    version = raw.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) \
            or version <= 0:
        return _corrupt(f"durable store schema_version is invalid: {version!r}")
    if version > supported_schema:
        return _corrupt(
            f"durable store schema_version {version} is newer than supported "
            f"{supported_schema}; refusing to guess")
    payload = raw.get("payload")
    sequence, seq_reason = _classify_sequence(raw)
    if seq_reason:
        return _corrupt(seq_reason)

    declared = raw.get("anchor")
    declared_mode = (str(declared) if declared is not None
                     else IntegrityMode.LOCAL.value)
    if declared is not None and str(declared) != IntegrityMode.LOCAL.value:
        # A stronger-anchor envelope: only the matching configured anchor may
        # read it. Anything else is a downgrade attempt and fails closed.
        if anchor is None or anchor.mode.value != str(declared):
            return _corrupt(
                f"durable store is {declared}-anchored but the reader is not "
                f"configured for it; refusing a silent downgrade",
                sequence=sequence, anchor_mode=declared_mode)
        if "mac" not in raw or not isinstance(raw.get("mac"), str):
            return _corrupt(
                f"durable store declares the {declared} anchor but carries no "
                f"MAC", sequence=sequence, anchor_mode=declared_mode)
        core = state_core_bytes(expected_kind, payload, schema_version=version,
                                sequence=sequence)
        if not anchor.verify_tag(core, raw.get("mac")):
            return _corrupt(
                f"durable store {declared} MAC verification failed "
                f"(tampered or wrong key)",
                sequence=sequence, anchor_mode=declared_mode)
    else:
        # Unanchored/legacy envelope: only a non-signing anchor may read it.
        if anchor is not None and anchor.requires_signature:
            return _corrupt(
                f"durable store lacks the required {anchor.mode.value} anchor; "
                f"refusing to accept an unsigned store")
        try:
            actual = payload_checksum(payload)
        except Exception as e:
            return _corrupt(f"durable store payload is not serializable: {e}")
        if actual != raw.get("checksum"):
            return _corrupt("durable store integrity checksum mismatch "
                            "(corrupted or tampered)")

    # External trust-anchor verification (the independent freshness root). Any
    # verdict other than CURRENT revokes authority (fail closed, no fallback).
    if trust_enabled:
        if sequence is None:
            return _corrupt(
                "durable store lacks the sequence required by the external "
                "trust anchor", anchor_mode=declared_mode,
                trust_verdict=TrustVerdict.INVALID.value)
        local_record = build_witness_record(
            kind=expected_kind, payload=payload, schema_version=version,
            sequence=int(sequence), scope=scope, prev=None,
            witness_id=getattr(trust_anchor, "_witness_id", "") or "",
            witness_version=getattr(trust_anchor, "_witness_version", 0) or 0)
        try:
            verification = trust_anchor.verify(local_record)
        except (AnchorUnavailable, TrustAnchorError) as e:
            return _corrupt(f"external trust anchor error: {e}",
                            sequence=sequence, anchor_mode=declared_mode,
                            trust_verdict=TrustVerdict.UNAVAILABLE.value)
        if not verification.grants_authority:
            return _corrupt(
                f"external witness rejected the state: {verification.reason}",
                sequence=sequence, anchor_mode=declared_mode,
                trust_verdict=verification.verdict.value,
                trust_reason=verification.reason)

    # Freshness / anti-rollback.
    if anchor is not None:
        if anchor.requires_sequence and sequence is None:
            return _corrupt(
                f"durable store lacks the sequence required by the "
                f"{anchor.mode.value} anchor", anchor_mode=declared_mode)
        try:
            floor = anchor.freshness_floor()
        except AnchorUnavailable as e:
            return _corrupt(str(e), sequence=sequence,
                            anchor_mode=declared_mode)
        if anchor.witness_required and floor is None:
            return _corrupt(
                "witness store absent for a sequenced state (rolled back or "
                "deleted); failing closed", sequence=sequence,
                anchor_mode=declared_mode)
        if sequence is not None and floor is not None and sequence < int(floor):
            return _corrupt(
                f"stale/replayed state: sequence {sequence} is older than the "
                f"accepted floor {floor} (rollback rejected)",
                sequence=sequence, anchor_mode=declared_mode)
        if sequence is not None:
            core = state_core_bytes(expected_kind, payload,
                                    schema_version=version, sequence=sequence)
            anchor.accept(sequence, core, raw.get("mac", ""))

    return StateLoadResult(StateOutcome.LOADED, payload=payload,
                           reason="integrity verified", path=str(path),
                           sequence=sequence, anchor_mode=declared_mode)


__all__ = [
    "SCHEMA_VERSION", "KIND_AUTHORITY_EVIDENCE",
    "StateOutcome", "DurabilityMode", "StateLoadResult",
    "canonical_payload_bytes", "payload_checksum", "build_envelope",
    "atomic_write_state", "read_state",
    "default_witness_scope", "build_witness_record",
    # Pluggable integrity / trust anchor surface (owned here; implemented in
    # telos/core/actions/integrity.py).
    "IntegrityAnchor", "IntegrityMode", "LocalAnchor", "HmacAnchor",
    "WitnessAnchor", "UnavailableAnchor", "AnchorUnavailable", "resolve_anchor",
    "load_hmac_key",
    # External trust-anchor surface (implemented in
    # telos/core/actions/trust_anchor.py) re-exported for the ONE durability API.
    "TrustAnchor", "DisabledTrustAnchor", "TrustAnchorError", "TrustVerdict",
    "TrustVerification", "WitnessRecord", "WitnessScope", "AnchorIdentity",
    "resolve_trust_anchor", "hash_envelope_core",
]
