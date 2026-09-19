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
      "payload": { ... }                    # a RealityGapTracker.to_state()
    }

The envelope is written ATOMICALLY (temp file + fsync + os.replace). There is
one state boundary per configured path; a reader therefore never observes a
torn mixture of an old authority record and a new evidence record.

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
    kind + supported schema, and its checksum verifies. The payload is trusted
    as the evidence it claims to be.
  * CORRUPTED  — the store exists but is unreadable, not a JSON object, missing
    the envelope, of the wrong kind, of an unsupported (newer) schema version,
    or fails its integrity checksum. TAMPERING and truncation are both in this
    class: a corrupted/tampered safety-critical store FAILS CLOSED (no
    authority is granted, and no automatic reconstruction from stale positive
    state occurs). It is NEVER silently treated as FIRST_RUN.

TRUST BOUNDARY (honest statement):
    Trusted-local-disk remains the security boundary. This envelope detects
    accidental corruption and casual tampering, and makes deletion explicit —
    it does NOT protect against an attacker who can modify BOTH the state and
    its integrity metadata. A stronger trust anchor (HSM, signed external
    witness, append-only remote log) would be required for that, and is not
    claimed here.
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
    """

    outcome: StateOutcome
    payload: Optional[Dict[str, Any]] = None
    reason: str = ""
    path: str = ""

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
                   schema_version: int = SCHEMA_VERSION) -> Dict[str, Any]:
    """Wrap a payload in the canonical durability envelope.

    Args:
        kind: the state kind (the expected producer/consumer contract).
        payload: the evidence payload.
        schema_version: the envelope schema version.

    Returns:
        The envelope dict (schema_version, kind, checksum, payload).
    """
    return {
        "schema_version": int(schema_version),
        "kind": str(kind),
        "checksum": payload_checksum(payload),
        "payload": payload,
    }


def atomic_write_state(path: str, kind: str, payload: Any, *,
                       schema_version: int = SCHEMA_VERSION) -> None:
    """Atomically persist an enveloped evidence payload.

    The write is temp-file + fsync + ``os.replace`` so a crash or a concurrent
    reader can never observe a half-written authority/evidence record.

    Args:
        path: the destination store path.
        kind: the state kind to stamp into the envelope.
        payload: the evidence payload.
        schema_version: the envelope schema version.

    Raises:
        OSError/ValueError: when the payload cannot be serialized or the write
            fails; callers decide whether that is fatal.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    envelope = build_envelope(kind, payload, schema_version=schema_version)
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


def read_state(path: Optional[str], *, expected_kind: str,
               supported_schema: int = SCHEMA_VERSION) -> StateLoadResult:
    """Read and classify a configured durable store (fail closed).

    Args:
        path: the store path (None/empty is a configuration error → CORRUPTED).
        expected_kind: the required envelope kind.
        supported_schema: the highest schema version this code understands; a
            newer (unknown) version is CORRUPTED, never guessed.

    Returns:
        A :class:`StateLoadResult` classifying the store as FIRST_RUN, LOADED,
        or CORRUPTED. CORRUPTED carries a reason and NEVER a payload.
    """

    def _corrupt(reason: str) -> StateLoadResult:
        return StateLoadResult(StateOutcome.CORRUPTED, reason=reason,
                               path=str(path or ""))

    if not path:
        return _corrupt("no durable store path configured")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
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
    try:
        actual = payload_checksum(payload)
    except Exception as e:
        return _corrupt(f"durable store payload is not serializable: {e}")
    if actual != raw.get("checksum"):
        return _corrupt("durable store integrity checksum mismatch "
                        "(corrupted or tampered)")
    return StateLoadResult(StateOutcome.LOADED, payload=payload,
                           reason="integrity verified", path=str(path))


__all__ = [
    "SCHEMA_VERSION", "KIND_AUTHORITY_EVIDENCE",
    "StateOutcome", "DurabilityMode", "StateLoadResult",
    "canonical_payload_bytes", "payload_checksum", "build_envelope",
    "atomic_write_state", "read_state",
]
