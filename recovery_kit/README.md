# recovery_kit

Client-owned wallet recovery toolkit. **Legal gate first**: no attempt plan
is generated until `recovery_kit.intake` reports `GATE: CLEARED`
(ownership-proof checklist + zero red flags + signed engagement terms).

## Commands

```bash
python3 -m recovery_kit.cli intake CASE-001            # guided gate checklist
python3 -m recovery_kit.cli estimate-space \
  --slot abandon --slot ? --slot prefix:elep --slot alt:snow|salt \
  --slot '?' x8 --value-usd 20000                      # feasibility math
python3 -m recovery_kit.cli triage cases/CASE-001/intake.json
python3 -m recovery_kit.cli benchmark --json-out benchmarks/local.json  # measure BEFORE quoting
python3 -m recovery_kit.cli gen-command CASE-001 partial-seed \
  --params '{"slots":["abandon","?"],"address_hint":"bc1q.."}'
```

## Local web UI

Run the whole toolkit from a browser (localhost only, Python stdlib only):

```bash
PYTHONPATH=. python3 -m recovery_kit.server --port 8766
# then open http://127.0.0.1:8766/
```

- Binds **127.0.0.1 ONLY** (never the network). Default port **8766** — 8765 is
  the TELOS dashboard. Note: the TELOS dashboard's WebSocket feed can also use
  8766; if it is running, start this UI on another port (`--port 8799`).
- Endpoints:
  | Route | What it does |
  |---|---|
  | `GET /` | single-page UI (embedded HTML/JS/CSS, zero external assets) |
  | `GET /api/health` | `{"ok": true}` |
  | `POST /api/estimate-space` | `space.estimate` + `verdict` (+ `fee_viability` when `value_usd` given); mirrors cli.py defaults |
  | `POST /api/benchmark` | `benchmark.benchmark`; samples clamped to <=4000 gen / <=24 PBKDF2 so requests stay fast; returns clamped-vs-requested honestly |
  | `POST /api/intake-gate` | checklist runner mirroring `intake.run_intake`'s record schema + gate rule (non-interactive form) |
  | `POST /api/triage` | pasted intake JSON -> `triage.triage_case`; refuses any record without `gate_cleared: true` |
- The server is transport only: every endpoint delegates to the existing
  modules (`space`, `benchmark`, `triage`) — no new math, no key material.
- Tests (ephemeral-port server in-process):
  `PYTHONPATH=. python3 -m pytest tests/test_recovery_kit_server.py -q`

## Local web UI

```bash
PYTHONPATH=. python3 -m recovery_kit.server --port 8766   # 127.0.0.1 ONLY
# then open http://127.0.0.1:8766/
```

Pages:
- `/` — tools: estimate-space, benchmark, intake gate, triage
- `/wallet` — **wallet file inspection** (Class C): upload an ENCRYPTED artifact
  (wallet.dat / Multibit / Electrum / Android backup). Bytes analyzed in memory
  only, never persisted, discarded after response. `POST /api/wallet-inspect`.

Endpoints: `GET /api/health` · `POST /api/estimate-space` · `POST /api/benchmark` ·
`POST /api/intake-gate` · `POST /api/triage` · `POST /api/wallet-inspect` (raw body).

Safety contract: **never** upload/paste seed words, passphrases, or private keys —
the server must never see plaintext key material. Wallet *files* are only
acceptable because they are encrypted artifacts; even so they are handled in
memory and deleted.

## Honesty rules (non-negotiable)
1. Throughput presets in `space.py` are conservative placeholders — benchmark
   `hashcat -m 9645` / btcrecover on YOUR rented GPU before quoting timelines.
2. The checksum divisor is an expected-value filter; treat big spaces as
   order-of-magnitude only.
3. btcrecover command templates carry TODO(verify) markers — check the docs
   for your pinned version.
4. No income guarantees, ever. The estimator's job is to REJECT unwinnable
   cases early; that refusal is the product.

Wordlist: official BIP-39 English list from github.com/bitcoin/bips.
