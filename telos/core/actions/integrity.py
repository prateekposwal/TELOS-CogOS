"""
TELOS Pluggable Integrity / Trust Anchors — the ONE durability contract's anchor layer.

The durability envelope (``telos/core/actions/durability.py``) historically
detected only ACCIDENTAL corruption: its integrity field is a plain sha256 of
the payload, co-located with the payload, so an attacker who edits the state can
recompute it. Two gaps follow:

  1. TAMPERING that edits the state (and its recomputed checksum) is
     undetectable.
  2. ROLLBACK/REPLAY of an older-but-valid state is undetectable — integrity
     without freshness/monotonicity is insufficient.

This module makes the integrity mechanism PLUGGABLE and selected by explicit
configuration, without creating a rival persistence system. It defines:

  * ``IntegrityMode`` — ``local`` (default) / ``hmac`` / ``witness``.
  * ``IntegrityAnchor`` — the anchor contract (authenticate an envelope's
    canonical core bytes; expose a monotonic freshness floor).
  * ``LocalAnchor`` — the historical behaviour: sha256, no secret. The DEFAULT.
  * ``HmacAnchor`` — the envelope core is authenticated with an HMAC whose key
    lives OUTSIDE the state artifact (env var or a restricted key file).
  * ``WitnessAnchor`` — a separate witness store recording the latest accepted
    sequence + MAC, so a rollback to an older valid state is detectable when
    the witness is not also rolled back.
  * ``UnavailableAnchor`` — a configured-but-unusable anchor. It is NEVER a
    silent downgrade to ``local``: it makes reads/writes fail CLOSED.
  * ``resolve_anchor`` — explicit configuration -> an anchor instance.

TRUST BOUNDARY (honest): no mode defends against a fully compromised OS/user
account (an attacker who can read the HMAC key, edit state AND witness, or
replace the code). ``hmac`` defends tampering that edits only the state file;
``witness`` defends rollback to an older valid state while the witness is
intact. An HSM or signed external service is a further, unbuilt step.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import tempfile
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger("telos_durability")


class IntegrityMode(str, Enum):
    """The selectable integrity/trust anchor modes."""

    LOCAL = "local"
    HMAC = "hmac"
    WITNESS = "witness"
    UNKNOWN = "unknown"


class AnchorError(RuntimeError):
    """An integrity anchor could not authenticate/verify (fail closed)."""


class AnchorUnavailable(AnchorError):
    """A configured anchor is unavailable or misconfigured (fail closed)."""


def _canonical(obj: Any) -> bytes:
    """Canonical, deterministic JSON bytes (sorted keys, compact, no NaN).

    Args:
        obj: the JSON-serializable object.

    Returns:
        UTF-8 encoded canonical JSON bytes.
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def state_core_bytes(kind: str, payload: Any, *,
                     schema_version: int, sequence: Optional[int]) -> bytes:
    """The authenticated region of a durability envelope.

    The core binds the schema, kind, sequence and payload together, so editing
    ANY of them (including the monotonic sequence) invalidates an HMAC tag.

    Args:
        kind: the envelope kind.
        payload: the envelope payload.
        schema_version: the envelope schema version.
        sequence: the monotonic sequence, when one is carried.

    Returns:
        The canonical bytes of the authenticated region.
    """
    core: Dict[str, Any] = {
        "schema_version": int(schema_version),
        "kind": str(kind),
    }
    if sequence is not None:
        core["sequence"] = int(sequence)
    core["payload"] = payload
    return _canonical(core)


#: Environment variable selecting the durability integrity mode.
ENV_MODE = "TELOS_DURABILITY_INTEGRITY"
#: Environment variable holding the raw HMAC key.
ENV_HMAC_KEY = "TELOS_DURABILITY_HMAC_KEY"
#: Environment variable holding a path to a restricted-permission key file.
ENV_HMAC_KEY_FILE = "TELOS_DURABILITY_HMAC_KEY_FILE"
#: The witness store path (required by witness mode).
ENV_WITNESS_PATH = "TELOS_DURABILITY_WITNESS_PATH"

#: The witness store schema version.
WITNESS_SCHEMA_VERSION = 1


class IntegrityAnchor:
    """The anchor contract: authenticate an envelope core + track freshness.

    Concrete anchors MUST be deterministic and MUST fail closed. ``available``
    is False only for a configured-but-unusable anchor.
    """

    mode: IntegrityMode = IntegrityMode.UNKNOWN
    #: Whether this anchor cryptographically signs the envelope core.
    requires_signature: bool = False
    #: Whether a monotonic ``sequence`` MUST be carried by the envelope.
    requires_sequence: bool = False
    #: Whether a separate witness store is mandatory (its absence fails closed).
    witness_required: bool = False

    @property
    def available(self) -> bool:
        """Whether the anchor is configured and usable."""
        return True

    def tag(self, core: bytes) -> str:
        """Compute the authenticity tag over an envelope core.

        Args:
            core: the canonical authenticated-region bytes.

        Returns:
            The tag (hex string) for the configured mode.

        Raises:
            AnchorUnavailable: when the anchor is not usable.
        """
        raise AnchorUnavailable(f"anchor {self.mode.value!r} has no tag")

    def verify_tag(self, core: bytes, tag: str) -> bool:
        """Constant-time verify an envelope core against a tag.

        Args:
            core: the canonical authenticated-region bytes.
            tag: the expected tag.

        Returns:
            True on a valid tag; False otherwise (never raises on mismatch).
        """
        return False

    def freshness_floor(self) -> Optional[int]:
        """The highest sequence already accepted by this anchor, if known.

        Returns:
            The floor, or None when no freshness root is available.
        """
        return self._last_accepted()

    def _last_accepted(self) -> Optional[int]:
        """The in-memory last-accepted sequence.

        Returns:
            The in-memory high-water mark, or None.
        """
        return getattr(self, "_accepted", None)

    def next_sequence(self) -> int:
        """The next monotonic sequence to persist.

        Returns:
            ``(freshness_floor or 0) + 1``.
        """
        floor = self.freshness_floor()
        return (int(floor) if floor is not None else 0) + 1

    def accept(self, sequence: Optional[int], core: bytes = b"",
               tag: str = "") -> None:
        """Record that a state with ``sequence`` was accepted.

        Args:
            sequence: the accepted sequence (None -> no-op for local).
            core: the canonical core of the accepted state.
            tag: the tag of the accepted state.
        """
        if sequence is None:
            return
        current = self._last_accepted()
        if current is None or int(sequence) > int(current):
            self._accepted = int(sequence)

    def describe(self) -> str:
        """A short human-readable description of the anchor.

        Returns:
            The description string.
        """
        return self.mode.value

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{type(self).__name__} mode={self.mode.value}>"


class LocalAnchor(IntegrityAnchor):
    """The historical behaviour: sha256 payload checksum, no secret.

    This is the DEFAULT and remains byte-identical: it neither signs the core
    nor requires a sequence. It detects accidental corruption only and is NOT
    tamper- or rollback-resistant.
    """

    mode = IntegrityMode.LOCAL
    requires_signature = False
    requires_sequence = False

    def tag(self, core: bytes) -> str:
        """The sha256 of the core bytes (informational; unused by default).

        Args:
            core: the canonical core bytes.

        Returns:
            The sha256 hex digest.
        """
        return hashlib.sha256(core).hexdigest()

    def verify_tag(self, core: bytes, tag: str) -> bool:
        """Constant-time compare of a sha256 core digest.

        Args:
            core: the canonical core bytes.
            tag: the expected digest.

        Returns:
            True when the digest matches.
        """
        return hmac.compare_digest(self.tag(core), str(tag))

    def describe(self) -> str:
        """A short description.

        Returns:
            The description string.
        """
        return "local (sha256 payload checksum, no secret; accidental-only)"


class HmacAnchor(IntegrityAnchor):
    """The envelope core is authenticated with a key held OUTSIDE the artifact.

    The key is never serialized into the state file. Editing the state (or its
    co-located checksum) without the key fails verification.
    """

    mode = IntegrityMode.HMAC
    requires_signature = True
    requires_sequence = True

    def __init__(self, key: bytes):
        """Construct an HMAC anchor over an explicit key.

        Args:
            key: the raw HMAC key bytes (>= 1 byte). Never stored in an artifact.

        Raises:
            ValueError: when the key is empty.
        """
        if not key:
            raise ValueError("HmacAnchor requires a non-empty key")
        self._key = bytes(key)

    @property
    def available(self) -> bool:
        """Always True once constructed with a key."""
        return True

    def tag(self, core: bytes) -> str:
        """HMAC-SHA256 of the envelope core.

        Args:
            core: the canonical core bytes.

        Returns:
            The hex MAC.
        """
        return hmac.new(self._key, core, hashlib.sha256).hexdigest()

    def verify_tag(self, core: bytes, tag: str) -> bool:
        """Constant-time verify of an HMAC-SHA256 tag.

        Args:
            core: the canonical core bytes.
            tag: the expected MAC.

        Returns:
            True on a valid MAC.
        """
        if not isinstance(tag, str) or not tag:
            return False
        return hmac.compare_digest(self.tag(core), tag)

    def describe(self) -> str:
        """A short description.

        Returns:
            The description string.
        """
        return "hmac (HMAC-SHA256 over the envelope core; key external)"


class WitnessAnchor(IntegrityAnchor):
    """Records the latest accepted sequence + MAC in a SEPARATE witness store.

    A signed state alone cannot detect rollback (an old valid state replays
    cleanly). The witness raises the accepted freshness floor, so a rollback to
    an older state is rejected while the witness is intact. The witness holds
    its own keyed MAC so an attacker without the key cannot forge a witness
    entry — but replaying an old witness together with the matching old state is
    NOT detectable (the same-disk limitation; documented).
    """

    mode = IntegrityMode.WITNESS
    requires_signature = True
    requires_sequence = True
    witness_required = True

    def __init__(self, delegate: HmacAnchor, witness_path: str):
        """Construct a witness anchor over an HMAC delegate.

        Args:
            delegate: the signing anchor (must be available).
            witness_path: the separate witness store path.

        Raises:
            ValueError: when the witness path is empty.
        """
        if not witness_path:
            raise ValueError("WitnessAnchor requires a witness_path")
        self._delegate = delegate
        self._witness_path = str(witness_path)

    @property
    def available(self) -> bool:
        """True when the delegate and witness path are usable."""
        return bool(self._delegate.available and self._witness_path)

    @property
    def witness_path(self) -> str:
        """The witness store path.

        Returns:
            The configured witness path.
        """
        return self._witness_path

    def tag(self, core: bytes) -> str:
        """Delegate the signature to the HMAC anchor.

        Args:
            core: the canonical core bytes.

        Returns:
            The hex MAC.
        """
        return self._delegate.tag(core)

    def verify_tag(self, core: bytes, tag: str) -> bool:
        """Delegate verification to the HMAC anchor.

        Args:
            core: the canonical core bytes.
            tag: the expected MAC.

        Returns:
            True on a valid MAC.
        """
        return self._delegate.verify_tag(core, tag)

    def _witness_mac(self, sequence: int, mac: str) -> str:
        """The keyed MAC authenticating a witness entry.

        Args:
            sequence: the witnessed sequence.
            mac: the witnessed state MAC.

        Returns:
            The hex MAC over ``sequence:mac``.
        """
        return self._delegate.tag(
            f"witness|{int(sequence)}|{mac}".encode("utf-8"))

    def read_witness(self) -> Optional[Dict[str, Any]]:
        """Read and authenticate the witness store.

        Returns:
            The witness record, or None when the witness file is absent.

        Raises:
            AnchorUnavailable: when the witness exists but is unreadable,
                malformed, or fails its own keyed MAC (fail closed).
        """
        try:
            with open(self._witness_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            raise AnchorUnavailable(
                f"witness store {self._witness_path!r} unreadable: {e}")
        if not isinstance(raw, dict):
            raise AnchorUnavailable("witness store is not a JSON object")
        seq = raw.get("sequence")
        mac = raw.get("mac")
        wmac = raw.get("witness_mac")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0 \
                or not isinstance(mac, str) or not isinstance(wmac, str):
            raise AnchorUnavailable("witness store entry is malformed")
        if not hmac.compare_digest(self._witness_mac(seq, mac), wmac):
            raise AnchorUnavailable(
                "witness store failed its integrity MAC (tampered)")
        return raw

    def freshness_floor(self) -> Optional[int]:
        """The witnessed freshness floor, intersected with the in-memory one.

        Returns:
            The highest accepted sequence, or None when no witness exists yet.

        Raises:
            AnchorUnavailable: when a present witness is untrustworthy.
        """
        rec = self.read_witness()
        floor = None
        if rec is not None:
            floor = int(rec["sequence"])
        mem = self._last_accepted()
        if mem is not None:
            floor = int(mem) if floor is None else max(floor, int(mem))
        return floor

    def accept(self, sequence: Optional[int], core: bytes = b"",
               tag: str = "") -> None:
        """Record an accepted state in the in-memory mark AND the witness.

        Args:
            sequence: the accepted sequence.
            core: the canonical core of the accepted state.
            tag: the tag of the accepted state.

        Raises:
            AnchorUnavailable: when the witness cannot be written.
        """
        super().accept(sequence, core, tag)
        if sequence is None:
            return
        seq = int(sequence)
        try:
            floor = self.freshness_floor()
        except AnchorUnavailable:
            raise
        if floor is not None and seq < int(floor):
            raise AnchorUnavailable(
                f"refusing to witness sequence {seq} below the floor {floor}")
        mac = str(tag) or self.tag(core)
        record = {
            "schema_version": WITNESS_SCHEMA_VERSION,
            "sequence": seq,
            "mac": mac,
        }
        record["witness_mac"] = self._witness_mac(seq, mac)
        _atomic_write_json(self._witness_path, record)

    def describe(self) -> str:
        """A short description.

        Returns:
            The description string.
        """
        return (f"witness (HMAC + witness store {self._witness_path!r}; "
                f"rollback-detecting while the witness is intact)")


class UnavailableAnchor(IntegrityAnchor):
    """A configured-but-unusable anchor — fails CLOSED, never downgrades.

    This exists so that asking for ``hmac``/``witness`` with no key, no witness
    path, or an unknown mode can never silently fall back to ``local``.
    """

    requires_signature = True
    requires_sequence = True

    def __init__(self, requested_mode: str, reason: str):
        """Construct an unavailable anchor.

        Args:
            requested_mode: the mode string the caller asked for.
            reason: why the anchor is unusable.
        """
        self.requested_mode = str(requested_mode)
        self.reason = str(reason)
        self.mode = IntegrityMode.UNKNOWN

    @property
    def available(self) -> bool:
        """Always False — the whole point of this anchor."""
        return False

    def tag(self, core: bytes) -> str:
        """Never computes a tag (fail closed).

        Args:
            core: unused.

        Raises:
            AnchorUnavailable: always.
        """
        raise AnchorUnavailable(
            f"integrity anchor {self.requested_mode!r} unavailable: "
            f"{self.reason}")

    def verify_tag(self, core: bytes, tag: str) -> bool:
        """Never verifies (fail closed).

        Args:
            core: unused.
            tag: unused.

        Returns:
            Always False.
        """
        return False

    def describe(self) -> str:
        """A short description.

        Returns:
            The description string.
        """
        return (f"UNAVAILABLE ({self.requested_mode}: {self.reason}; "
                f"fail-closed, no downgrade)")


def _atomic_write_json(path: str, obj: Any) -> None:
    """Atomically write a JSON object (temp + fsync + rename).

    Args:
        path: the destination path.
        obj: the JSON-serializable object.

    Raises:
        OSError: when the write fails.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".telos_witness_",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=True, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _warn_key_file_permissions(path: str) -> None:
    """Warn when a key file is readable by group/other.

    Args:
        path: the key file path.
    """
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        return
    if mode & 0o077:
        logger.warning(
            "durability HMAC key file %r is group/other-accessible "
            "(mode %o); restrict it to the owner (chmod 600)", path, mode)


def load_hmac_key(*, key: Optional[object] = None,
                  key_file: Optional[str] = None,
                  env: Optional[Dict[str, str]] = None) -> Optional[bytes]:
    """Resolve the HMAC key from an explicit value, the env, or a key file.

    Resolution order: explicit ``key`` -> ``TELOS_DURABILITY_HMAC_KEY`` ->
    ``TELOS_DURABILITY_HMAC_KEY_FILE`` (or ``key_file``).

    TELOS spawns NO subprocess to obtain the key (the durability contract runs
    in ``telos/core``, whose ONLY governed subprocess channel is the
    ActionExecutor). An operator who keeps the key in the macOS Keychain should
    inject it into ``TELOS_DURABILITY_HMAC_KEY`` at launch, e.g.
    ``TELOS_DURABILITY_HMAC_KEY="$(security find-generic-password -w -s SVC -a ACC)"``.

    Args:
        key: an explicit key (str or bytes).
        key_file: an explicit key-file path.
        env: the environment mapping (defaults to ``os.environ``).

    Returns:
        The key bytes, or None when none could be resolved.
    """
    if key is not None:
        if isinstance(key, bytes):
            return key or None
        text = str(key)
        return text.encode("utf-8") if text else None
    env = env if env is not None else os.environ
    raw = env.get(ENV_HMAC_KEY)
    if raw:
        return str(raw).encode("utf-8")
    path = key_file or env.get(ENV_HMAC_KEY_FILE)
    if path:
        try:
            data = open(path, "rb").read().rstrip(b"\n").rstrip(b"\r")
        except OSError:
            return None
        if not data:
            return None
        _warn_key_file_permissions(path)
        return data
    return None


def resolve_anchor(mode: Optional[object] = None, *,
                   key: Optional[object] = None,
                   key_file: Optional[str] = None,
                   witness_path: Optional[str] = None,
                   env: Optional[Dict[str, str]] = None) -> IntegrityAnchor:
    """Resolve the configured integrity anchor (never a silent downgrade).

    Args:
        mode: explicit mode (``local``/``hmac``/``witness``); when None the
            ``TELOS_DURABILITY_INTEGRITY`` env var is used (default ``local``).
        key: an explicit HMAC key.
        key_file: an explicit key-file path.
        witness_path: an explicit witness store path.
        env: the environment mapping (defaults to ``os.environ``).

    Returns:
        A usable anchor, or an :class:`UnavailableAnchor` (fail closed) when a
        non-local mode is requested without its required material.
    """
    env = env if env is not None else os.environ
    raw_mode = mode if mode is not None else env.get(ENV_MODE, "local")
    text = str(raw_mode).strip().lower()
    if text == IntegrityMode.LOCAL.value:
        return LocalAnchor()
    if text == IntegrityMode.HMAC.value:
        resolved_key = load_hmac_key(key=key, key_file=key_file, env=env)
        if not resolved_key:
            return UnavailableAnchor(
                IntegrityMode.HMAC.value,
                "no HMAC key (set TELOS_DURABILITY_HMAC_KEY or "
                "TELOS_DURABILITY_HMAC_KEY_FILE)")
        return HmacAnchor(resolved_key)
    if text == IntegrityMode.WITNESS.value:
        resolved_key = load_hmac_key(key=key, key_file=key_file, env=env)
        path = witness_path or env.get(ENV_WITNESS_PATH)
        if not resolved_key:
            return UnavailableAnchor(
                IntegrityMode.WITNESS.value,
                "witness mode requires an HMAC key")
        if not path:
            return UnavailableAnchor(
                IntegrityMode.WITNESS.value,
                "witness mode requires TELOS_DURABILITY_WITNESS_PATH")
        return WitnessAnchor(HmacAnchor(resolved_key), str(path))
    return UnavailableAnchor(
        text or "?", f"unknown integrity mode {text!r}")


__all__ = [
    "IntegrityMode", "IntegrityAnchor", "LocalAnchor", "HmacAnchor",
    "WitnessAnchor", "UnavailableAnchor", "AnchorError", "AnchorUnavailable",
    "state_core_bytes", "load_hmac_key", "resolve_anchor",
    "ENV_MODE", "ENV_HMAC_KEY", "ENV_HMAC_KEY_FILE", "ENV_WITNESS_PATH",
    "WITNESS_SCHEMA_VERSION",
]
