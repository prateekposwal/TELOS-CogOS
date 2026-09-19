"""
TELOS External Trust Anchor — the independent freshness/authenticity boundary.

THE HONEST GAP THIS CLOSES:
    The local integrity envelope (``telos/core/actions/durability.py`` +
    ``integrity.py``) detects accidental corruption and, when ``hmac``/``witness``
    are configured, tampering by an attacker who can edit only the state file and
    rollback to an older valid state while a separate LOCAL witness is intact.
    None of that escapes the local account: an attacker who controls the filesystem
    can rewrite state + checksum/envelope as a CONSISTENT historical pair, and can
    replay a previously valid state + local witness pair. Local cryptography cannot
    fix this because the freshness root lives on the same disk as the thing it is
    supposed to defend.

    This module introduces an OPTIONAL, operator-configured EXTERNAL trust anchor.
    When configured, the local filesystem ceases to be the ultimate authority: the
    externally witnessed monotonic record decides whether a locally-persisted
    authority state may claim to be CURRENT.

ARCHITECTURE (the enforced separation):
    Local state -> Local integrity envelope -> External witness/trust anchor
                 -> Authority decision

    * ``WitnessRecord`` is the minimum witnessed material (monotonic sequence,
      state_hash, evidence_hash, capability identity, producer/world identity,
      schema/version, a useful-but-not-relied-upon timestamp, previous-state
      linkage, witness identity/version).
    * ``TrustAnchor`` is the PROVIDER INTERFACE: ``establish`` / ``witness`` /
      ``verify`` / ``get_latest`` / ``health``. A provider stores and returns
      records; it makes NO authority decision.
    * ``TrustVerdict`` / ``TrustVerification`` are provider-neutral contracts.
      The fail-closed authority mapping lives in ``durability.py`` (the consumer),
      never in a provider — so no vendor/HSM is hard-coded here.

FRESHNESS IS SEQUENCE-BASED, NOT CLOCK-BASED:
    The witnessed ``timestamp`` is informational only. Freshness is the monotonic
    ``sequence`` plus the witness's stored history. A wall-clock rollback cannot
    move the freshness floor backward.

FAIL-CLOSED, NO INVENTED GRACE:
    When an external anchor is configured, ``INVALID | STALE | ROLLBACK |
    CONFLICT | UNKNOWN (safety-critical) | UNAVAILABLE`` all mean NO AUTHORITY.
    There is no silent fallback to local state and no fail-open grace period.

PROVIDERS (honest about what exists):
    * ``DisabledTrustAnchor`` — the DEFAULT: no external anchor is configured, so
      the trusted local disk remains the security boundary and existing behaviour
      is byte-identical. Nothing external is contacted.
    * ``ExternalHttpTrustAnchor`` — talks to an operator-configured HTTP witness
      endpoint (env ``TELOS_TRUST_ANCHOR_ENDPOINT``) through the governed
      ``NetworkSandbox`` egress channel. DEFAULT-OFF. When a witness public key
      is pinned (``TELOS_TRUST_ANCHOR_ATTEST_KEY``) every answer must carry a
      valid witness attestation; a missing or forged signature fails closed
      (UNAVAILABLE), never an accepted unverified answer.
    * ``UnavailableTrustAnchor`` — configured but unusable: never downgrades.

SINGLE-USER MACHINE, STATED PLAINLY:
    On one machine with no genuine external service there is NO true
    independence. This interface makes real externality POSSIBLE, and a
    deployable witness service now exists (``telos/witness_service.py``; see
    ``telos/WITNESS_SERVICE.md``) that holds an append-only monotonic history
    and signs every accepted record with its own RSA key
    (``witness_attest.py``). The adversarial test runs it as a REAL separate
    process; the in-repo reference server still stands in for speed. Running
    the service on the SAME account is still one trust domain — genuine
    independence requires it outside the local account, which remains
    unverified. No HSM-grade custody is claimed.

CREDENTIAL vs TRUST (do not conflate three different things):
    * OBTAINING a credential — outside TELOS: the operator injects it into the
      environment at launch (e.g. a Keychain lookup in the shell that starts the
      process). TELOS deliberately spawns NO ``security``/Keychain subprocess: the
      durability/trust code lives in ``telos/core``, whose ONLY governed
      subprocess channel is the ActionExecutor. An in-process CLI call would be an
      ungoverned channel and is forbidden here.
    * USING a credential — the provider may attach it to a request to authenticate
      the WRITER to the anchor (``TELOS_TRUST_ANCHOR_TOKEN``).
    * TRUSTING the external witness — a separate decision: the anchor is trusted
      only when it is genuinely outside the local account's control. Holding a
      write token is NOT the same as the anchor being independent.

RESIDUAL PATH (stated, not hidden):
    A LIVE compromised process that can read the provider's write credential (or
    that shares the anchor's trust domain) can publish a forged-but-newer record
    and the anchor will witness it. True independence requires the anchor's write
    credential to be unavailable to the local account (another host/account/HSM)
    and the anchor itself to be uncompromised. Protection against compromise of
    the external trust anchor itself is explicitly NOT claimed.

SECURITY BOUNDARY:
    Without external trust anchor: trusted local disk is the security boundary.
    With external trust anchor: local disk is storage, not the ultimate authority.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from telos.core.actions.sandbox import EgressRule, NetworkSandbox
from telos.core.actions.witness_attest import key_id as _attest_key_id
from telos.core.actions.witness_attest import load_public_key as _load_public_key
from telos.core.actions.witness_attest import (
    verify_attestation as _verify_attestation,
)

#: Environment variable selecting the external trust-anchor provider.
ENV_TRUST_ANCHOR = "TELOS_TRUST_ANCHOR"
#: Environment variable holding the operator-configured witness endpoint URL.
ENV_TRUST_ENDPOINT = "TELOS_TRUST_ANCHOR_ENDPOINT"
#: Optional environment variable holding the anchor's writer credential/token.
ENV_TRUST_TOKEN = "TELOS_TRUST_ANCHOR_TOKEN"
#: Environment variable overriding the witness identity string.
ENV_TRUST_WITNESS_ID = "TELOS_TRUST_ANCHOR_WITNESS_ID"
#: Optional env var: path to the witness's PUBLIC attestation key (JSON). When
#: set, every witness answer must carry a valid signature from that key, so a
#: local attacker holding only the writer token cannot forge a witness answer.
ENV_TRUST_ATTEST_KEY = "TELOS_TRUST_ANCHOR_ATTEST_KEY"

#: The witnessed-record schema version.
WITNESS_RECORD_SCHEMA_VERSION = 1
#: The default witness identity/version reported by a provider.
DEFAULT_WITNESS_ID = "external-http-witness"
DEFAULT_WITNESS_VERSION = 1

#: The modes the external trust anchor supports.
MODE_OFF = "off"
MODE_EXTERNAL = "external"

class TrustVerdict(str, Enum):
    """The provider-neutral result of comparing local state to the witness."""

    #: The local state is the anchor's latest witnessed record.
    CURRENT = "CURRENT"
    #: The local state is OLDER than the anchor's latest (replayed/rolled back).
    STALE = "STALE"
    #: The local state is ABSENT while the anchor holds a record (deletion).
    ROLLBACK = "ROLLBACK"
    #: The anchor holds no record, but a local record exists (safety-critical).
    UNKNOWN = "UNKNOWN"
    #: The local record diverges from the anchor's record (forged/tampered).
    INVALID = "INVALID"
    #: The anchor is configured but unreachable/misconfigured (fail closed).
    UNAVAILABLE = "UNAVAILABLE"
    #: The anchor holds conflicting entries for the same sequence.
    CONFLICT = "CONFLICT"
    #: No external anchor is configured; the local boundary applies.
    DISABLED = "DISABLED"


#: Verdicts that revoke authority when the external anchor is enabled.
FAIL_CLOSED_VERDICTS = frozenset({
    TrustVerdict.STALE,
    TrustVerdict.ROLLBACK,
    TrustVerdict.UNKNOWN,
    TrustVerdict.INVALID,
    TrustVerdict.UNAVAILABLE,
    TrustVerdict.CONFLICT,
})


class TrustAnchorError(RuntimeError):
    """Base class for external trust-anchor failures (fail closed)."""


class TrustAnchorUnavailable(TrustAnchorError):
    """The configured external anchor is unreachable or misconfigured."""


class TrustAnchorConflict(TrustAnchorError):
    """The anchor rejected a record as conflicting with its stored history."""


def canonical_witness_bytes(obj: Any) -> bytes:
    """Canonical, deterministic JSON bytes for a witnessed record.

    Args:
        obj: the JSON-serializable object.

    Returns:
        UTF-8 encoded canonical JSON bytes (sorted keys, compact, no NaN).
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class WitnessScope:
    """The identity of the witnessed subject (what a record is about).

    Attributes:
        store_id: the logical authority store identity (e.g. ``reality_gap``).
        producer_id: the producer identity that wrote the state.
        world_id: the world/domain identity the state describes.
        capability_id: the capability identity, or ``*`` for a multi-capability
            store.
    """

    store_id: str
    producer_id: str = "telos"
    world_id: str = "default"
    capability_id: str = "*"

    def to_dict(self) -> Dict[str, Any]:
        """Serializable scope mapping.

        Returns:
            Dict with the four scope fields.
        """
        return {
            "store_id": self.store_id,
            "producer_id": self.producer_id,
            "world_id": self.world_id,
            "capability_id": self.capability_id,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "WitnessScope":
        """Rebuild a scope from a mapping.

        Args:
            raw: a mapping carrying the scope fields.

        Returns:
            The reconstructed :class:`WitnessScope`.
        """
        return cls(
            store_id=str(raw.get("store_id", "")),
            producer_id=str(raw.get("producer_id", "telos")),
            world_id=str(raw.get("world_id", "default")),
            capability_id=str(raw.get("capability_id", "*")),
        )


@dataclass(frozen=True)
class WitnessRecord:
    """The minimum material the external anchor witnesses.

    Attributes:
        sequence: the monotonic sequence (freshness root).
        state_hash: sha256 of the canonical local envelope core.
        evidence_hash: sha256 of the canonical evidence payload.
        scope: the witnessed subject identity.
        envelope_schema_version: the local envelope schema version.
        kind: the local envelope kind.
        timestamp: informational wall-clock stamp (NEVER used for freshness).
        prev_state_hash: the previous witnessed state hash (linkage).
        prev_sequence: the previous witnessed sequence (linkage).
        witness_id: the anchor/witness identity.
        witness_version: the anchor/witness implementation version.
    """

    sequence: int
    state_hash: str
    evidence_hash: str
    scope: WitnessScope
    envelope_schema_version: int
    kind: str
    timestamp: float = 0.0
    prev_state_hash: str = ""
    prev_sequence: int = 0
    witness_id: str = DEFAULT_WITNESS_ID
    witness_version: int = DEFAULT_WITNESS_VERSION
    record_schema_version: int = WITNESS_RECORD_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Serializable witnessed record.

        Returns:
            Dict with every witnessed field (scope flattened under ``scope``).
        """
        return {
            "record_schema_version": int(self.record_schema_version),
            "sequence": int(self.sequence),
            "state_hash": str(self.state_hash),
            "evidence_hash": str(self.evidence_hash),
            "scope": self.scope.to_dict(),
            "envelope_schema_version": int(self.envelope_schema_version),
            "kind": str(self.kind),
            "timestamp": float(self.timestamp),
            "prev_state_hash": str(self.prev_state_hash),
            "prev_sequence": int(self.prev_sequence),
            "witness_id": str(self.witness_id),
            "witness_version": int(self.witness_version),
        }

    def canonical_bytes(self) -> bytes:
        """Canonical bytes used for any hash/commitment over the record.

        Returns:
            The canonical JSON bytes of :meth:`to_dict`.
        """
        return canonical_witness_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "WitnessRecord":
        """Rebuild a record from a mapping (validating required fields).

        Args:
            raw: a mapping carrying the witnessed fields.

        Returns:
            The reconstructed :class:`WitnessRecord`.

        Raises:
            TrustAnchorError: when a required field is missing or malformed.
        """
        if not isinstance(raw, dict):
            raise TrustAnchorError("witness record is not a JSON object")
        try:
            sequence = raw["sequence"]
            state_hash = raw["state_hash"]
            evidence_hash = raw["evidence_hash"]
            scope_raw = raw["scope"]
        except KeyError as e:
            raise TrustAnchorError(f"witness record missing field {e}")
        if isinstance(sequence, bool) or not isinstance(sequence, int) \
                or sequence < 0:
            raise TrustAnchorError(f"witness sequence is invalid: {sequence!r}")
        if not isinstance(state_hash, str) or not isinstance(evidence_hash, str):
            raise TrustAnchorError("witness hashes must be strings")
        if not isinstance(scope_raw, dict):
            raise TrustAnchorError("witness scope is not an object")
        return cls(
            sequence=int(sequence),
            state_hash=state_hash,
            evidence_hash=evidence_hash,
            scope=WitnessScope.from_dict(scope_raw),
            envelope_schema_version=int(
                raw.get("envelope_schema_version", 0) or 0),
            kind=str(raw.get("kind", "")),
            timestamp=float(raw.get("timestamp", 0.0) or 0.0),
            prev_state_hash=str(raw.get("prev_state_hash", "")),
            prev_sequence=int(raw.get("prev_sequence", 0) or 0),
            witness_id=str(raw.get("witness_id", DEFAULT_WITNESS_ID)),
            witness_version=int(
                raw.get("witness_version", DEFAULT_WITNESS_VERSION) or 0),
            record_schema_version=int(
                raw.get("record_schema_version",
                        WITNESS_RECORD_SCHEMA_VERSION) or 0),
        )


@dataclass(frozen=True)
class AnchorIdentity:
    """The established identity of an external trust anchor.

    Attributes:
        witness_id: the witness identity.
        witness_version: the witness implementation version.
        externally_independent: whether the anchor is genuinely outside the local
            account's control (honest provider claim).
        endpoint: the anchor endpoint (redacted where necessary).
    """

    witness_id: str
    witness_version: int
    externally_independent: bool
    endpoint: str = ""


@dataclass(frozen=True)
class AnchorHealth:
    """A provider reachability/health report.

    Attributes:
        reachable: whether the anchor answered.
        detail: a short human-readable detail.
    """

    reachable: bool
    detail: str = ""


@dataclass(frozen=True)
class TrustVerification:
    """A provider-neutral verification result.

    Attributes:
        verdict: the :class:`TrustVerdict`.
        reason: a human-readable explanation.
        anchor_record: the anchor's latest record, when one was read.
        anchor_id: the anchor identity, when known.
    """

    verdict: TrustVerdict
    reason: str = ""
    anchor_record: Optional[WitnessRecord] = None
    anchor_id: str = ""

    @property
    def grants_authority(self) -> bool:
        """Whether this verdict permits the local state to claim CURRENT.

        Returns:
            True only for ``CURRENT`` and ``DISABLED``.
        """
        return self.verdict in (TrustVerdict.CURRENT, TrustVerdict.DISABLED)

def hash_envelope_core(core: bytes) -> str:
    """The stable state hash of a canonical envelope core.

    Args:
        core: the canonical authenticated-region bytes of the envelope.

    Returns:
        The sha256 hex digest.
    """
    return hashlib.sha256(core).hexdigest()


class TrustAnchor:
    """The external trust-anchor PROVIDER INTERFACE (no authority semantics).

    A provider answers, for a witnessed record, whether the external anchor's
    stored history agrees that the record is the CURRENT one. It never decides
    whether authority is granted — the consumer (``durability.py``) maps the
    verdict to a fail-closed authority decision.
    """

    #: A short provider name.
    name: str = "trust-anchor"
    #: Whether this provider is genuinely outside the local account's control.
    externally_independent: bool = False
    #: Whether an external anchor is configured (and therefore must be consulted).
    enabled: bool = False
    #: Whether the provider is usable. False => fail closed.
    available: bool = True

    def establish(self, scope: WitnessScope) -> Optional[AnchorIdentity]:
        """Bind a scope to the anchor and return its identity.

        Args:
            scope: the witnessed subject identity.

        Returns:
            The anchor identity, or None when the provider does not establish.
        """
        return None

    def witness(self, record: WitnessRecord) -> WitnessRecord:
        """Publish a record to the external anchor.

        Args:
            record: the local record to witness.

        Returns:
            The anchor's accepted record (may equal ``record``).

        Raises:
            TrustAnchorUnavailable: when the anchor cannot be reached/used.
            TrustAnchorConflict: when the anchor rejects the record as conflicting.
        """
        raise TrustAnchorUnavailable(f"{self.name} does not witness records")

    def verify(self, record: WitnessRecord) -> TrustVerification:
        """Compare a local record against the anchor's stored history.

        Args:
            record: the local record to verify.

        Returns:
            A :class:`TrustVerification` (never raises for a disagreement).
        """
        return TrustVerification(TrustVerdict.UNAVAILABLE,
                                 reason=f"{self.name} cannot verify")

    def get_latest(self, scope: WitnessScope) -> Optional[WitnessRecord]:
        """Read the anchor's latest witnessed record for a scope.

        Args:
            scope: the witnessed subject identity.

        Returns:
            The latest record, or None when the anchor holds none.

        Raises:
            TrustAnchorUnavailable: when the anchor cannot be reached.
        """
        raise TrustAnchorUnavailable(f"{self.name} has no latest record")

    def health(self) -> AnchorHealth:
        """Probe the anchor's reachability.

        Returns:
            An :class:`AnchorHealth` report.
        """
        return AnchorHealth(reachable=False, detail=f"{self.name} has no health")

    def next_sequence(self, scope: WitnessScope) -> int:
        """The next monotonic sequence to witness for a scope.

        Args:
            scope: the witnessed subject identity.

        Returns:
            ``latest.sequence + 1`` when the anchor holds a record, else 1.

        Raises:
            TrustAnchorUnavailable: when the anchor cannot be reached.
        """
        latest = self.get_latest(scope)
        return 1 if latest is None else int(latest.sequence) + 1


class DisabledTrustAnchor(TrustAnchor):
    """The DEFAULT: no external anchor — trusted local disk is the boundary.

    Nothing external is contacted and the durability layer applies its existing
    behaviour byte-identically. ``verify`` returns ``DISABLED``, which the
    consumer treats as "apply the local decision only".
    """

    name = "disabled"
    externally_independent = False
    enabled = False
    available = True

    def witness(self, record: WitnessRecord) -> WitnessRecord:
        """A disabled anchor never witnesses (the caller must check ``enabled``).

        Args:
            record: unused.

        Returns:
            The record unchanged (no external contact).

        Raises:
            TrustAnchorUnavailable: always — a disabled anchor must not be used.
        """
        raise TrustAnchorUnavailable("external trust anchor is not configured")

    def verify(self, record: WitnessRecord) -> TrustVerification:
        """Report that no external verification applies.

        Args:
            record: the local record (unused).

        Returns:
            A ``DISABLED`` verification.
        """
        return TrustVerification(
            TrustVerdict.DISABLED,
            reason="no external trust anchor configured; local boundary applies")

    def health(self) -> AnchorHealth:
        """Report that the (absent) anchor is not configured.

        Returns:
            An :class:`AnchorHealth` with ``reachable=False`` and an honest detail.
        """
        return AnchorHealth(reachable=False, detail="not configured")

    def next_sequence(self, scope: WitnessScope) -> int:
        """The first sequence for a store with no external anchor.

        Args:
            scope: unused.

        Returns:
            1.
        """
        return 1


class UnavailableTrustAnchor(TrustAnchor):
    """A configured-but-unusable external anchor — fails CLOSED, never downgrades.

    This exists so selecting the external mode without a usable endpoint can never
    silently fall back to the local boundary.
    """

    name = "unavailable"
    externally_independent = True
    enabled = True
    available = False

    def __init__(self, requested_mode: str, reason: str):
        """Construct an unavailable anchor.

        Args:
            requested_mode: the mode the caller asked for.
            reason: why the anchor is unusable.
        """
        self.requested_mode = str(requested_mode)
        self.reason = str(reason)

    def _fail(self):
        """Raise the fail-closed error.

        Returns:
            Never returns.

        Raises:
            TrustAnchorUnavailable: always.
        """
        raise TrustAnchorUnavailable(
            f"external trust anchor {self.requested_mode!r} unavailable: "
            f"{self.reason}")

    def witness(self, record: WitnessRecord) -> WitnessRecord:
        """Fail closed — the anchor cannot be written.

        Args:
            record: unused.

        Returns:
            Never returns.

        Raises:
            TrustAnchorUnavailable: always.
        """
        self._fail()

    def verify(self, record: WitnessRecord) -> TrustVerification:
        """Fail closed with an ``UNAVAILABLE`` verdict.

        Args:
            record: unused.

        Returns:
            An ``UNAVAILABLE`` verification.
        """
        return TrustVerification(
            TrustVerdict.UNAVAILABLE,
            reason=f"external trust anchor unavailable: {self.reason}")

    def get_latest(self, scope: WitnessScope) -> Optional[WitnessRecord]:
        """Fail closed — the anchor cannot be read.

        Args:
            scope: unused.

        Returns:
            Never returns.

        Raises:
            TrustAnchorUnavailable: always.
        """
        self._fail()

    def health(self) -> AnchorHealth:
        """Report the anchor as unreachable.

        Returns:
            An :class:`AnchorHealth` with ``reachable=False``.
        """
        return AnchorHealth(reachable=False, detail=self.reason)

    def next_sequence(self, scope: WitnessScope) -> int:
        """Fail closed — no sequence can be assigned.

        Args:
            scope: unused.

        Returns:
            Never returns.

        Raises:
            TrustAnchorUnavailable: always.
        """
        self._fail()


def _endpoint_egress_rule(endpoint: str) -> EgressRule:
    """Build the egress rule an operator-configured endpoint implies.

    The operator SET this endpoint, so its host/port/path prefix are, by
    construction, the intended egress. Everything else stays denied.

    Args:
        endpoint: the absolute endpoint URL.

    Returns:
        An :class:`EgressRule` authorizing GET/POST on the endpoint's origin.

    Raises:
        TrustAnchorUnavailable: when the endpoint is not a usable URL.
    """
    from urllib.parse import urlparse
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()
    if not host or scheme not in ("http", "https"):
        raise TrustAnchorUnavailable(
            f"trust-anchor endpoint {endpoint!r} is not an absolute URL")
    port = parsed.port or (443 if scheme == "https" else 80)
    path = parsed.path or "/"
    route = path if path.endswith("/") else path + "/"
    routes = tuple({route, path})
    return EgressRule(host=host, ports=(port,), routes=routes,
                      methods=("GET", "POST"))


class ExternalHttpTrustAnchor(TrustAnchor):
    """An external witness service reached over the governed egress channel.

    The provider performs no direct network call: every request leaves through the
    ``NetworkSandbox`` (the ONE governed egress channel), so this file is not an
    ungoverned network site. The endpoint is operator-configured; the optional
    writer token authenticates the WRITER, it does not make the anchor trusted.
    """

    name = "external-http"
    externally_independent = True
    enabled = True
    available = True

    def __init__(self, endpoint: str, *,
                 sandbox: Optional[NetworkSandbox] = None,
                 witness_id: str = DEFAULT_WITNESS_ID,
                 witness_version: int = DEFAULT_WITNESS_VERSION,
                 token: Optional[str] = None,
                 timeout: float = 10.0,
                 attestation_public_key: Optional[Dict[str, Any]] = None):
        """Construct an HTTP witness client.

        Args:
            endpoint: the operator-configured witness base URL.
            sandbox: the governed egress sandbox; when omitted one is built with
                an allowlist derived from ``endpoint``.
            witness_id: the witness identity to report/expect.
            witness_version: the witness implementation version.
            token: an optional writer credential (obtained by the operator and
                injected into the environment; TELOS never fetches it).
            timeout: the sandbox request timeout in seconds.
            attestation_public_key: an optional PINNED public key. When set,
                every witness answer must carry a valid witness signature over
                the returned record; a missing/invalid signature fails closed.
                Default None preserves the pre-attestation behaviour exactly.
        """
        if not endpoint:
            raise TrustAnchorUnavailable("external trust anchor requires an endpoint")
        self.endpoint = str(endpoint).rstrip("/")
        self._witness_id = str(witness_id)
        self._witness_version = int(witness_version)
        self._token = str(token) if token else None
        self._attest_key = (
            dict(attestation_public_key)
            if attestation_public_key else None)
        self._sandbox = (sandbox if sandbox is not None
                         else NetworkSandbox(
                             rules=[_endpoint_egress_rule(self.endpoint)],
                             timeout=timeout))

    def _headers(self) -> Dict[str, str]:
        """The request headers (including the optional writer credential).

        Returns:
            Header mapping.
        """
        headers = {"X-Telos-Witness": self._witness_id,
                   "Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _call(self, method: str, path: str,
              body: Optional[Any] = None) -> Dict[str, Any]:
        """Perform one governed request and decode the JSON response.

        Args:
            method: HTTP method (GET/POST).
            path: the endpoint-relative path.
            body: an optional request body: a mapping (encoded canonically) or an
                already-canonical JSON string.

        Returns:
            The decoded response mapping.

        Raises:
            TrustAnchorUnavailable: on egress denial, network error, a non-2xx
                status, or undecodable JSON.
            TrustAnchorConflict: on a 409 conflict response.
        """
        url = self.endpoint + path
        if body is None:
            payload = None
        elif isinstance(body, str):
            payload = body
        else:
            payload = json.dumps(body, sort_keys=True)
        res = self._sandbox.request(method, url, body=payload,
                                   headers=self._headers())
        if not res.allowed:
            raise TrustAnchorUnavailable(
                f"external witness request failed: {res.blocked_reason}")
        if res.status == 409:
            raise TrustAnchorConflict(
                f"external witness rejected a conflicting record: {res.body[:200]}")
        if res.status is None or not (200 <= int(res.status) < 300):
            raise TrustAnchorUnavailable(
                f"external witness returned status {res.status}")
        try:
            decoded = json.loads(res.body)
        except Exception as e:
            raise TrustAnchorUnavailable(
                f"external witness returned undecodable JSON: {e}")
        if not isinstance(decoded, dict):
            raise TrustAnchorUnavailable(
                "external witness returned a non-object JSON body")
        return decoded

    def _require_attestation(self, record: Optional[Dict[str, Any]],
                             body: Dict[str, Any]) -> None:
        """Verify a witness answer's attestation when a public key is pinned.

        A no-op when no public key was configured (byte-identical legacy
        behaviour). When one IS configured, a missing/invalid signature means
        the answer cannot be attributed to this witness, so the call fails
        closed as unavailable (the consumer maps it to UNAVAILABLE).

        Args:
            record: the record carried by the answer.
            body: the decoded answer mapping (must carry ``attestation``).

        Raises:
            TrustAnchorUnavailable: when the answer is not validly attested.
        """
        if self._attest_key is None:
            return
        attestation = body.get("attestation") if isinstance(body, dict) else None
        if record is None or not _verify_attestation(
                self._attest_key, record, attestation):
            raise TrustAnchorUnavailable(
                "external witness answer is not validly attested by the pinned "
                "public key; failing closed")

    def establish(self, scope: WitnessScope) -> Optional[AnchorIdentity]:
        """Handshake with the witness for a scope.

        Args:
            scope: the witnessed subject identity.

        Returns:
            The witness identity, or None when the witness does not report one.

        Raises:
            TrustAnchorUnavailable: when the witness cannot be reached.
        """
        body = self._call("POST", "/establish", {
            "scope": scope.to_dict(),
            "witness_id": self._witness_id,
            "witness_version": self._witness_version,
        })
        identity = body.get("identity")
        if not isinstance(identity, dict):
            return None
        if self._attest_key is not None:
            reported = identity.get("public_key")
            if (not isinstance(reported, dict)
                    or _attest_key_id(reported) != _attest_key_id(self._attest_key)):
                raise TrustAnchorUnavailable(
                    "external witness identity does not match the pinned "
                    "public key; failing closed")
        return AnchorIdentity(
            witness_id=str(identity.get("witness_id", self._witness_id)),
            witness_version=int(identity.get("witness_version",
                                             self._witness_version) or 0),
            externally_independent=bool(
                identity.get("externally_independent", True)),
            endpoint=self.endpoint,
        )

    def witness(self, record: WitnessRecord) -> WitnessRecord:
        """Publish a record and return the anchor's stored record.

        Args:
            record: the local record to witness.

        Returns:
            The record as stored by the anchor.

        Raises:
            TrustAnchorUnavailable: when the witness cannot be reached.
            TrustAnchorConflict: when the anchor rejects the record.
        """
        # Send the CANONICAL bytes so a duplicate is byte-identical regardless of
        # dict ordering (the anchor's idempotence then depends on content, not
        # serialization noise).
        body = self._call("POST", "/witness",
                          record.canonical_bytes().decode("utf-8"))
        stored = body.get("record")
        self._require_attestation(
            stored if isinstance(stored, dict) else None, body)
        if isinstance(stored, dict):
            return WitnessRecord.from_dict(stored)
        return record

    def get_latest(self, scope: WitnessScope) -> Optional[WitnessRecord]:
        """Read the anchor's latest record for a scope.

        Args:
            scope: the witnessed subject identity.

        Returns:
            The latest record, or None when the anchor holds none (404).

        Raises:
            TrustAnchorUnavailable: when the witness cannot be reached.
        """
        from urllib.parse import quote
        fields = scope.to_dict()
        segments = "/".join(
            quote(str(fields[k]), safe="")
            for k in ("store_id", "producer_id", "world_id", "capability_id"))
        url_path = f"/latest/{segments}"
        try:
            body = self._call("GET", url_path)
        except TrustAnchorUnavailable as e:
            if "status 404" in str(e):
                return None
            raise
        record = body.get("record")
        if record is None:
            return None
        self._require_attestation(record, body)
        return WitnessRecord.from_dict(record)

    def verify(self, record: WitnessRecord) -> TrustVerification:
        """Compare a local record to the anchor's stored history.

        Args:
            record: the local record to verify.

        Returns:
            A :class:`TrustVerification`:
              * no anchor record -> UNKNOWN (safety-critical, fail closed);
              * local behind -> STALE (a replayed/rolled-back state);
              * local ahead -> UNKNOWN (an unwitnessed forward transition);
              * equal sequence + equal hashes -> CURRENT;
              * equal sequence + differing hashes -> INVALID (forged/tampered);
              * unreachable -> UNAVAILABLE.

        Raises:
            TrustAnchorUnavailable: never; unreachability is returned as a verdict.
        """
        try:
            latest = self.get_latest(record.scope)
        except TrustAnchorUnavailable as e:
            return TrustVerification(TrustVerdict.UNAVAILABLE, reason=str(e),
                                     anchor_id=self._witness_id)
        if latest is None:
            return TrustVerification(
                TrustVerdict.UNKNOWN,
                reason=("external witness holds no record for this scope while "
                        "a local record exists (rollback/deletion or unwitnessed "
                        "state); failing closed"),
                anchor_id=self._witness_id)
        if int(record.sequence) < int(latest.sequence):
            return TrustVerification(
                TrustVerdict.STALE,
                reason=(f"stale/replayed state: local sequence {record.sequence} "
                        f"is older than the witnessed sequence "
                        f"{latest.sequence}"),
                anchor_record=latest, anchor_id=self._witness_id)
        if int(record.sequence) > int(latest.sequence):
            return TrustVerification(
                TrustVerdict.UNKNOWN,
                reason=(f"unwitnessed forward state: local sequence "
                        f"{record.sequence} is AHEAD of the witnessed sequence "
                        f"{latest.sequence} (the anchor is the authority)"),
                anchor_record=latest, anchor_id=self._witness_id)
        if (str(record.state_hash) != str(latest.state_hash)
                or str(record.evidence_hash) != str(latest.evidence_hash)):
            return TrustVerification(
                TrustVerdict.INVALID,
                reason=("local state diverges from the witnessed record at the "
                        "same sequence (forged/tampered state or integrity "
                        "metadata)"),
                anchor_record=latest, anchor_id=self._witness_id)
        return TrustVerification(
            TrustVerdict.CURRENT,
            reason="local state matches the external witness",
            anchor_record=latest, anchor_id=self._witness_id)

    def health(self) -> AnchorHealth:
        """Probe the witness endpoint's health.

        Returns:
            An :class:`AnchorHealth` report.
        """
        try:
            body = self._call("GET", "/health")
        except TrustAnchorError as e:
            return AnchorHealth(reachable=False, detail=str(e))
        return AnchorHealth(reachable=bool(body.get("ok", True)),
                            detail=str(body.get("detail", "ok")))


def resolve_trust_anchor(mode: Optional[object] = None, *,
                         endpoint: Optional[str] = None,
                         token: Optional[str] = None,
                         sandbox: Optional[NetworkSandbox] = None,
                         witness_id: Optional[str] = None,
                         attestation_public_key: Optional[Dict[str, Any]] = None,
                         env: Optional[Dict[str, str]] = None) -> TrustAnchor:
    """Resolve the configured external trust anchor (default OFF).

    Resolution order for the mode: explicit ``mode`` ->
    ``TELOS_TRUST_ANCHOR`` (default ``off``). Only ``external`` enables an
    external anchor; an unknown mode resolves to a fail-closed
    :class:`UnavailableTrustAnchor`, never a silent downgrade.

    Args:
        mode: explicit mode (``off``/``external``).
        endpoint: an explicit endpoint (wins over the environment).
        token: an explicit writer credential (wins over the environment).
        sandbox: an explicit governed egress sandbox.
        witness_id: an explicit witness identity.
        attestation_public_key: an explicit pinned witness public key.
        env: the environment mapping (defaults to ``os.environ``).

    Returns:
        A :class:`TrustAnchor`. ``off`` (the default) yields
        :class:`DisabledTrustAnchor` and contact nothing external.
    """
    env = env if env is not None else os.environ
    raw_mode = mode if mode is not None else env.get(ENV_TRUST_ANCHOR, MODE_OFF)
    text = str(raw_mode).strip().lower()
    if text in ("", MODE_OFF, "none", "disabled"):
        return DisabledTrustAnchor()
    if text == MODE_EXTERNAL:
        resolved_endpoint = endpoint or env.get(ENV_TRUST_ENDPOINT)
        if not resolved_endpoint:
            return UnavailableTrustAnchor(
                MODE_EXTERNAL,
                "external mode requires TELOS_TRUST_ANCHOR_ENDPOINT (the "
                "operator-configured witness URL)")
        resolved_token = token if token is not None else env.get(ENV_TRUST_TOKEN)
        resolved_witness = witness_id or env.get(ENV_TRUST_WITNESS_ID)
        resolved_attest = attestation_public_key
        if resolved_attest is None:
            attest_path = env.get(ENV_TRUST_ATTEST_KEY)
            if attest_path:
                try:
                    resolved_attest = _load_public_key(str(attest_path))
                except Exception as e:
                    return UnavailableTrustAnchor(
                        MODE_EXTERNAL,
                        f"cannot load pinned attestation public key "
                        f"{attest_path!r}: {e}")
        try:
            return ExternalHttpTrustAnchor(
                str(resolved_endpoint),
                sandbox=sandbox,
                witness_id=(resolved_witness or DEFAULT_WITNESS_ID),
                token=resolved_token,
                attestation_public_key=resolved_attest)
        except TrustAnchorUnavailable as e:
            return UnavailableTrustAnchor(MODE_EXTERNAL, str(e))
    return UnavailableTrustAnchor(
        text or "?", f"unknown external trust-anchor mode {text!r}")


__all__ = [
    "TrustVerdict", "TrustVerification", "WitnessScope", "WitnessRecord",
    "AnchorIdentity", "AnchorHealth", "TrustAnchor", "DisabledTrustAnchor",
    "UnavailableTrustAnchor", "ExternalHttpTrustAnchor",
    "TrustAnchorError", "TrustAnchorUnavailable", "TrustAnchorConflict",
    "resolve_trust_anchor", "canonical_witness_bytes", "hash_envelope_core",
    "FAIL_CLOSED_VERDICTS", "WITNESS_RECORD_SCHEMA_VERSION",
    "ENV_TRUST_ANCHOR", "ENV_TRUST_ENDPOINT", "ENV_TRUST_TOKEN",
    "ENV_TRUST_WITNESS_ID", "ENV_TRUST_ATTEST_KEY", "MODE_OFF", "MODE_EXTERNAL",
    "DEFAULT_WITNESS_ID", "DEFAULT_WITNESS_VERSION",
]
