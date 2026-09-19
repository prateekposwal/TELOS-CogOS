# TELOS Durability Contract

> Safety-critical authority and the evidence required to justify that authority
> must have an explicit, durable, integrity-verifiable state boundary.
> **There is exactly ONE runtime persistence mechanism — never a second
> competing store.**

Implementation: `telos/core/actions/durability.py` (the envelope + atomic
read/write), with the **pluggable integrity anchors** in
`telos/core/actions/integrity.py` (owned by, and re-exported from, the
durability module). Consumed by `telos/core/actions/reality_loop.py`
(`CapabilityAuthority`) and `telos/core/runtime.py` (the pipeline's per-model
Reality Gap evidence). Construction audit:
`telos/tools/durability_audit.py`.

## What is covered

| State | Where it lives | Durability |
|---|---|---|
| Capability-authority evidence (per-capability measured Reality Gaps) | the configured `CapabilityAuthority(state_path=…)` store | DURABLE when a path is configured |
| Reality Gap state (per-model prediction-vs-observation evidence) | `PipelineConfig.reality_gap_state_path` (loaded/persisted by the runtime) | DURABLE when a path is configured |
| Certification / revocation state | the canonical operator-reviewed JSON registry (`telos/audit/capability_certification.json`), written only by an explicit operator act | Reviewed artifact, operator-gated |
| Evidence provenance | the envelope `kind` + the store path + the audit trail | In-band |
| Atomic persistence / consistency | one `RealityGapTracker.to_state()` payload per file, written temp→fsync→rename | Atomic per store |

Capability authority is a **projection** of the Reality Gap tracker state and is
never persisted separately — so "authority says X, evidence says Y" cannot
happen within a store. The canonical certification registry is deliberately
separate and operator-gated: the runtime may *withhold* authority
automatically, but only an operator may *grant* canonical certification.

## Envelope (integrity-verifiable)

```json
{
  "schema_version": 1,
  "kind": "telos_authority_evidence",
  "checksum": "<sha256 of the canonical payload>",
  "sequence": 7,
  "anchor": "hmac",
  "mac": "<HMAC over the envelope core>",
  "payload": { "models": { "<model_id>": { … tracker state … } } }
}
```

`checksum` is `sha256(canonical_json(payload))` (sorted keys, compact
separators, `allow_nan=False`). Writes are atomic: a crash or a concurrent
reader never observes a half-written record.

`sequence`, `anchor` and `mac` are **present only when a trust anchor requires
them**. In the default `local` mode the envelope is the historical four-key
form (`schema_version`, `kind`, `checksum`, `payload`) — **byte-identical** to
the pre-anchor contract.

## Integrity / trust anchors (pluggable, selected by explicit configuration)

Selected by `TELOS_DURABILITY_INTEGRITY` (`local` default; `hmac`; `witness`).

| Mode | What it defends against | What it does **NOT** defend against |
|---|---|---|
| **`local`** (default) | Accidental corruption; deletion made explicit. | Tampering (the sha256 is co-located and recomputable); rollback/replay. **Not tamper- or rollback-resistant.** |
| **`hmac`** | Tampering that edits the state file (and/or its co-located checksum) without the key. The key is held **outside** the artifact (env `TELOS_DURABILITY_HMAC_KEY`, or a restricted-permission key file `TELOS_DURABILITY_HMAC_KEY_FILE`). A Keychain-held key is injected into the env at launch (`TELOS_DURABILITY_HMAC_KEY="$(security find-generic-password -w -s SVC -a ACC)"`) — TELOS spawns **no** subprocess (the core's only governed subprocess channel is the ActionExecutor). | An attacker who can **read the key** (i.e. who already has the user account/OS); rollback/replay of an older correctly-signed state. |
| **`witness`** | Rollback/replay to an older **valid** state, while the witness store (a separate file recording the latest accepted `sequence` + MAC) is intact. | An attacker who can also edit/roll back the witness; anyone with the key; full OS compromise. |
| **unavailable / misconfigured** | — (fails **closed**: no authority, no write) | Never silently downgrades to `local`. |

**Anti-rollback / freshness.** When an anchor requires freshness the envelope
carries a monotonic `sequence` (bound inside the authenticated HMAC core).
On load, a `sequence` **older than the anchor's accepted freshness floor** is
classified `CORRUPTED` (stale/replayed) and fails closed. For `witness` the
floor is durable across restarts (the witness store); for `hmac`/`local` it is
in-process only (a same-file sequence cannot defend against an attacker who
rewrites the whole file).

**No silent downgrade.** A configured anchor that is unusable (missing key,
keychain locked/unavailable, missing witness path, unknown mode) resolves to an
`UnavailableAnchor` that makes reads/writes **fail closed**. A `local`/default
reader refuses a stronger-anchored (`hmac`/`witness`) envelope, and an
`hmac`/`witness` reader refuses an unsigned envelope. There is **no** fallback
from `hmac`/`witness` to `local`.

## Read classification

* **FIRST_RUN** — the configured store does not exist. Honest cold start;
  initialization is safe (bootstrap).
* **LOADED** — exists, correct `kind`, supported `schema_version`, integrity
  verifies (checksum and/or the configured anchor's MAC), and the `sequence` is
  not older than the anchor's freshness floor. The payload is trusted.
* **CORRUPTED / TAMPERED / STALE** — exists but unreadable, not a JSON object,
  missing the envelope, wrong `kind`, newer/unknown `schema_version`, integrity
  mismatch, anchored in a mode the reader is not configured for, anchored
  without a MAC, or carrying a `sequence` older than the accepted floor.
  **Fails closed**: no authority is granted and no automatic reconstruction
  from stale positive state occurs. Corrupt/deleted/replayed safety-critical
  state is **never** silently treated as a clean first run.

## DURABLE vs EPHEMERAL

* **DURABLE (production)** — a path is configured. Evidence is loaded on
  construction and rewritten atomically on every mutation.
* **EPHEMERAL (tests / in-memory)** — no path. Nothing is read or written.
  Supported for tests and one-shot harnesses; never acceptable for a
  safety-critical production authority.

`CapabilityAuthority()` (no path) stays supported for tests. Production
construction must be explicit: `CapabilityAuthority.durable(path)` or
`state_path=…`. `durability=DURABLE` without a path raises. The producer's
`LiveCanary` passes a durable authority path; a PRODUCER-origin canary without
one refuses with `authority_durability_unconfigured`.

## Persistence location

Paths are supplied by the caller (e.g. the producer's
`/tmp/telos_capability_authority.json`, or the pipeline's
`reality_gap_state_path`). **No default path is invented** — a silent default
could make separate instances or tests share state unexpectedly. The witness
store path (`TELOS_DURABILITY_WITNESS_PATH`) is likewise caller-supplied and
must be a **different** file from the state store.

## Trust boundary (honest statement)

**`local` keeps trusted-local-disk as the boundary**: it detects accidental
corruption and makes deletion explicit, but an attacker who can modify both the
state **and its co-located checksum** is undetected. **`hmac`** raises the
boundary to possession of the key: it stops an attacker who can edit only the
state file, but not one who can read the key (i.e. who has the user
account/OS). **`witness`** additionally detects rollback to an older valid
state while the witness is intact.

**No mode defends against a fully compromised OS/user account** — an attacker
who can read the key, edit the state **and** the witness, or replace the code
itself. An **HSM or signed external service** is a further, **unbuilt** step and
is not claimed.

## Fail-closed invariants (pinned by tests)

A. Missing safety-critical state never grants authority.
B. Corrupt/tampered/stale state never grants authority.
C. Restart cannot resurrect falsified authority.
D. Reality Gap state survives restart when durability is configured.
E. Stale positive evidence cannot outrank newer falsification.
F. Canonical revocation remains operator-gated.
G. Certification never activates execution.
H. Explicit ephemeral/test mode remains possible.
I. Production authority cannot accidentally be ephemeral.
J. Deleting persistence cannot manufacture a clean certification state.
K. A configured-but-unusable anchor fails closed (never downgrades to `local`).
L. An older valid state cannot be replayed past the freshness floor.
