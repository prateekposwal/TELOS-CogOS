# TELOS Durability Contract

> Safety-critical authority and the evidence required to justify that authority
> must have an explicit, durable, integrity-verifiable state boundary.
> **There is exactly ONE runtime persistence mechanism — never a second
> competing store.**

Implementation: `telos/core/actions/durability.py` (the envelope + atomic
read/write), consumed by `telos/core/actions/reality_loop.py`
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
  "payload": { "models": { "<model_id>": { … tracker state … } } }
}
```

`checksum` is `sha256(canonical_json(payload))` (sorted keys, compact
separators, `allow_nan=False`). Writes are atomic: a crash or a concurrent
reader never observes a half-written record.

## Read classification

* **FIRST_RUN** — the configured store does not exist. Honest cold start;
  initialization is safe (bootstrap).
* **LOADED** — exists, correct `kind`, supported `schema_version`, checksum
  verifies. The payload is trusted.
* **CORRUPTED / TAMPERED** — exists but unreadable, not a JSON object, missing
  the envelope, wrong `kind`, newer/unknown `schema_version`, or checksum
  mismatch. **Fails closed**: no authority is granted and no automatic
  reconstruction from stale positive state occurs. Corrupt/deleted
  safety-critical state is **never** silently treated as a clean first run.

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
could make separate instances or tests share state unexpectedly.

## Trust boundary (honest statement)

**Trusted-local-disk remains the security boundary.** The envelope detects
accidental corruption and casual tampering and makes deletion explicit, but it
does **not** protect against an attacker who can modify both the state **and
its integrity metadata**. A stronger trust anchor (HSM, signed external
witness, append-only remote log) would be required for that and is not claimed.

## Fail-closed invariants (pinned by tests)

A. Missing safety-critical state never grants authority.
B. Corrupt/tampered state never grants authority.
C. Restart cannot resurrect falsified authority.
D. Reality Gap state survives restart when durability is configured.
E. Stale positive evidence cannot outrank newer falsification.
F. Canonical revocation remains operator-gated.
G. Certification never activates execution.
H. Explicit ephemeral/test mode remains possible.
I. Production authority cannot accidentally be ephemeral.
J. Deleting persistence cannot manufacture a clean certification state.
