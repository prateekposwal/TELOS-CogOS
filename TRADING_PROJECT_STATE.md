# Trading Project — STATE FILE

> **Status: INACTIVE / PARKED** (2026-08-02)
> Parked by Prateek's order while active work focuses on **TELOS core + Bitcoin block-space**.
> **Nothing was deleted.** All scaffolds, tests, manifests, and notes below remain on disk and in the repo history.
> Resume condition is stated at the bottom — do not treat this project as abandoned; treat it as paused.

---

## What this project is

A crypto/equity **trading curriculum + risk doctrine + Strategy Lab** for TELOS:
TELOS learns to trade (risk-first) by ingesting a curated book curriculum into its SkillLibrary,
and eventually operates a live Strategy Lab (sizing, execution, kill-switches) — gated by a risk doctrine.

## Current state (everything that exists, nothing lost)

### 1. The 4 skill scaffolds — BUILT, on disk, tested ✅
Location: `telos/core/ledger/skill_seeds.py` (builder functions) · registry wiring in `telos/core/ledger/__init__.py`
Tests: `tests/core/test_skill_seeds.py` — 12/12 passing (was part of 566/566 suite; suite has since grown to 629/629)

| Scaffold | Skill ID | Consumes (books) | Notes |
|---|---|---|---|
| 1 | `capital_guardian` | Grant *Trading Risk*, Elder (2%/6% rules) | Risk-first gatekeeper; `max_risk_per_trade` default 0.02 = Elder's 2% rule |
| 2 | `microstructure` | Harris *Trading and Exchanges* | Execution mechanics, order types, market structure |
| 3 | `crypto_framing` | Burniske & Tatar *Cryptoassets*, Hazlitt, Norman ×2, Baumohl, Murphy | Macro/regime framing, custody/exchange/regulatory risk register |
| 4 | `position_sizing` | Vince *Mathematics of Money Management*, Miller QFRM, Allen | Sizing math, VaR/ES, risk measures |

Each scaffold contains: TOC-derived concept maps, knowledge fields, decision rules, failure modes,
chapter ingestion hooks — all flagged `verified: False` until legit copies are read and content filled.

### 2. The $100 risk doctrine — DISCUSSED, NOT YET CODIFIED ⚠️
An agreed risk doctrine around a **$100 working capital** envelope was discussed in prior sessions
but **never written down as a formal doctrine**. Reconstruct from the thread before resuming.
Recovery hook: search session/decision logs for "$100", "risk doctrine", "capital envelope".
TODO: codify as a `RiskDoctrine` doc (max per-trade risk $, daily loss limit, kill-switch thresholds,
disallowed products until exam passed).

### 3. The pending exam — PENDING, sequencing drives the book order ⏳
A trading exam is pending; book acquisition order was re-ranked to feed it directly:
[acquire-now] = Elder *Trading for a Living* (#12) + Aziz *How to Day Trade for a Living* (#7).
Exam Lesson 1 (drawdown under 1%/2%/5% sizing) needs the doctrinal statements from Elder.

### 4. The Coldcard custody SOP — DISCUSSED, NEVER CODIFIED ⚠️
A Coldcard (hardware wallet) custody standard operating procedure was discussed but
**never written down**. TODO on resume: codify a Coldcard SOP (setup, seed backup, passphrase,
spending flow, verify-address, recovery test cadence) before any real funds move.

### 5. The 4 priority books — verified metadata, NOT yet acquired 📚
Full manifest (with legit acquisition channels, page counts, ISBNs, OpenLibrary records, no-piracy gate):
`knowledge_library/books/README.md`
- **#1** Grant — *Trading Risk* (Wiley 2004) → `capital_guardian`
- **#2** Harris — *Trading and Exchanges* (OUP 2003) → `microstructure`
- **#3** Burniske & Tatar — *Cryptoassets* (McGraw-Hill 2018) → `crypto_framing`
- **#4** Vince — *Mathematics of Money Management* (Wiley 1992) → `position_sizing`

Plus 23 further curriculum titles (Tiers 1–3) with priorities in the same README (~$700–$1,100 if all bought new;
the [acquire-now] pair is ~$50; several have free/lending channels).

### 6. To-dos (carried, unabridged)
- [ ] Codify the **$100 risk doctrine** (discussed, never written)
- [ ] Codify the **Coldcard custody SOP** (discussed, never written)
- [ ] Pass the **pending exam** (sequencing driver — Elder + Aziz first)
- [ ] Acquire legit copies of the 4 priority books (channels in `knowledge_library/books/README.md`)
- [ ] Read + ingest: fill chapter-level content, flip `verified: True` / `toc_verified: True` in scaffolds
- [ ] Flip the 2%/6% rules ingestion hook on `capital_guardian` (Elder doctrine)
- [ ] Build the **Strategy Lab** (sizing formulas, stop protocol, kill-switch) — gated on risk doctrine
- [ ] Feed `simulation` (CounterfactualEngine) from Miller #16, Fabozzi/Focardi #21, Hilpisch #25
- [ ] Feed `validators` (Reality/Constraint) from GARP #15, CFA #24, Wooldridge #27, Fabozzi/Drake #10
- [ ] Feed `failure-ledger` (Kintsugi) from Aziz #7, Norman #8/#9, Allen #22, Antonopoulos #17
- [ ] Strategy Lab charting layer from Murphy #13, Nison #19, Brooks #20 (reference-only counterpoint)

## Resume conditions
Resume this project when ANY of these is true:
1. Prateek explicitly says "resume trading" / "unpark trading", OR
2. The Bitcoin block-space project reaches a stable state (quality ≥ 90/100 for 7 consecutive cycles), OR
3. Prateek flags the exam date / wants the Coldcard SOP or $100 doctrine codified first.

## How to resume (exact entry points)
1. `git log --oneline -20` in this workspace to find the 2026-08-01 trading session commits.
2. `python3 -m pytest tests/core/test_skill_seeds.py` — confirm scaffolds still pass.
3. Read this file, then `knowledge_library/books/README.md` (acquisition channels).
4. Codify risk doctrine + Coldcard SOP before any real-money work (per the doctrine-first rule).
5. Do NOT delete any of the above files — they are the resumable state.

---
*Last updated: 2026-08-02 by session_start primer fix (Order 1/2 of Prateek's 3 orders).*
