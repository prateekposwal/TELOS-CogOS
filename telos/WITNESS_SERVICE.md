# TELOS External Witness Service

A minimal, standalone, deployable process that holds the authoritative
**append-only, monotonic history** for every witnessed scope, and **attests**
each accepted record with its own asymmetric signing key. It is the external
freshness root the durability layer consults when
`TELOS_TRUST_ANCHOR=external`.

* Service: `telos/witness_service.py` (stdlib only; runnable as its own process)
* Attestation primitives: `telos/core/actions/witness_attest.py` (stdlib RSA,
  PKCS#1 v1.5 + SHA-256)
* Provider that reaches it: `ExternalHttpTrustAnchor` in
  `telos/core/actions/trust_anchor.py`

## Run

```bash
# The witness runs under its OWN account/host/container — never the producer's.
python3 -m telos.witness_service \
    --state-dir  "$HOME/.telos-witness" \
    --host       127.0.0.1 \
    --port       8799 \
    --token-file "$HOME/.telos-witness/writer.token" \
    --print-public-key
```

Then point the producer at it (operator env injection only — TELOS never
fetches a credential):

```bash
export TELOS_TRUST_ANCHOR=external
export TELOS_TRUST_ANCHOR_ENDPOINT=http://127.0.0.1:8799
export TELOS_TRUST_ANCHOR_TOKEN="$(cat "$HOME/.telos-witness/writer.token")"
# Optional: PIN the witness public key so a local forgery of an answer fails.
export TELOS_TRUST_ANCHOR_ATTEST_KEY="$HOME/.telos-witness/witness_public_key.json"
```

## Where the key lives

| Secret | Who holds it | Where |
|---|---|---|
| **Private signing key** | the witness only | `--key-file` (default `<state-dir>/witness_signing_key.json`), written `0600` |
| **Public key** | anyone / pinned by the verifier | `<state-dir>/witness_public_key.json` (served at `GET /public_key`) |
| **Writer token** | the producer (attached to requests) | `--token-file` / `TELOS_WITNESS_TOKEN` on the witness; `TELOS_TRUST_ANCHOR_TOKEN` on the producer |
| **Append-only history** | the witness | `<state-dir>/witness_log.jsonl` |

The witness's signing key and history live in the **witness's** state dir and
are read from the `TELOS_WITNESS_*` namespace — deliberately distinct from the
producer's `TELOS_TRUST_ANCHOR_*` namespace. The producer is never given the
private key.

## Wire contract

```
GET  /health
GET  /public_key
POST /establish
POST /witness                                  (Authorization: Bearer <token>)
GET  /latest/<store>/<producer>/<world>/<cap>  (Authorization: Bearer <token>)
```

* `/witness` → `200` on a new higher sequence or a byte-identical duplicate;
  `409` on ANY sequence `<=` the server-side floor that is not that duplicate
  (rollback, replay of an old pair, same-sequence divergence); `401` unauthorized.
* The floor is **server-side**: rebuilt from the append-only log on startup and
  only ever increased in memory. A client cannot lower it.
* A stored log line whose attestation no longer verifies (a tampered witness
  store) makes the service **refuse to start** rather than serve a weak floor.
* Every answer carries `attestation = {alg, key_id, sig}` over the canonical
  record bytes. With a pinned public key the provider verifies it and fails
  closed on a missing/forged signature.

## Independence — the honest statement

Running the service on the **same account** as the producer is still **one
trust domain**: that account can read `witness_signing_key.json`, delete the
log, or replace the process. Genuine independence requires running the service
(and its write credential) **outside the producer's local account** — a
separate OS account, a separate host, or a container the producer's account
cannot read or write. Bind to `127.0.0.1` by default; use a private network or
an account boundary (not a public bind) when separating hosts.

Security wording for this work:

> "External trust-anchor architecture and anti-replay verification are
> implemented and tested; independent trust-anchor deployment remains
> unverified."

After building and exercising the service: a **deployable** witness service now
exists and is exercised as a **real separate process** against the decisive
adversarial test; same-account deployment remains a **single trust domain**, and
a deployment genuinely outside the local account remains unverified. This is a
genuine public-key attestation with stdlib RSA; it is **not** HSM-grade key
custody and is not claimed to be.

## Threat model at a glance

| Attacker holds | Can they force a loaded/authorized state? |
|---|---|
| Local state + checksum + envelope + historical records | **No** (replay → `STALE`, forge → `INVALID`) |
| … plus the producer's writer token | **No** (open of an old/new sequence → `409`/fail closed) |
| … plus all local metadata | **No** (delete → `ROLLBACK`, bump → `UNKNOWN`) |
| … **but not** the witness private key | **No** — cannot forge the attestation, cannot lower the floor |
| The witness host + its private key | Out of scope — that is the witness being compromised |
