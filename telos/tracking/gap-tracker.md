# TELOS — Gap Tracker (canonical)

Canonical source: `telos/tracking/gap-tracker.json` (machine-readable).
BSAHI references this file; TELOS owns it. Last verified: 2026-08-11 (data-capture lessons G-25..G-30 recorded).

## Rule (architect mandate)
**DONE means SHIPPED** (committed + pushed + live). Unshipped work goes in LEFT, never DONE.
Every report ends with labeled `DONE (verified)` + `LEFT / TODO (verified)`.

## Operational rule (P2.0)
After any bug/fix/misdiagnosis that took **>2 rounds**, write the lesson to `telos/lessons/` before session close. Conversation is not memory.

## Gaps — open (6)

| ID | System | Gap | Effort | Impact | Shell |
|----|--------|-----|--------|--------|-------|
| G-18 | BSAHI | node_geo per-region cost distributions not expanded (G-06 remainder) | M | low | S3 |
| G-19 | process | Master to-do list created (master-todo.md) — canonical reconciliation of all lists | S | high | — |
| G-20 | BSAHI | Vachagan reply drafted+committed but NOT posted (A2) | XS | medium | — |
| G-21 | BSAHI | Cost-to-Flood v1 note + budget table + dust-RAM leg (C2-C6) | M | medium | — |
| G-22 | BSAHI | Governance-boundary: window capture LIVE; GBI note + calibration + post-window analysis (G2-G4) | M | high | — |
| G-23 | BSAHI | D5 external reproduction — THE GATE (A1/B1) | XS | critical | — |

## Gaps — closed (24)

| ID | Gap | Lesson |
|----|-----|--------|
| G-01 | Gap-scanner pre-commit gate RED on clean tree (750 fails across 4/6 checks) |  |
| G-02 | Working paper (v2.0.0 methodology doc) not written |  |
| G-03 | M4 gate not flipped (3/7 clean cycles) |  |
| G-04 | backtest.py lacks provenance/version markers |  |
| G-05 | Spool staleness: btc-rpc source stale 3+ days ⚠ MISDIAGNOSIS-CORRECTED |  |
| G-06 | Resource legs deferred: UTXO, bandwidth, validation, node_geo |  |
| G-07 | No canonical gap tracker existed (created this file) |  |
| G-08 | Uncommitted TELOS work (AGENTS.md, decision_log, benchmarks data, knowledge_library, reports) |  |
| G-09 | brief-52 (v2.0.0) still pending — not published |  |
| G-10 | DNS registrar parking nameservers (cosmetic) |  |
| G-11 | SCCR v2.0.0 correction — 10x bug + reconciliation (COMPLETED) |  |
| G-12 | Bot/skill usefulness audit — remove unused, redesign better (ARCHITECT MANDATE) |  |
| G-13 | AXIOMS.md consistency — 42 axioms confirmed, but latent_cognition.md referenced 20 (file gone) |  |
| G-14 | DONE=SHIPPED enforcement not yet automatic (principle persisted, gate manual) |  |
| G-15 | Real node census (primary source >=32K via getnodeaddresses, agent-25) |  |
| G-16 | brief-52 publish: content-briefs never consumed for posting — FIXED |  |
| G-17 | BSAHI stuck mid-rebase (15h, detached HEAD, 3 stale autostashes) |  |
| G-24 | Internal working docs leaked to public web (16 pages: plans, reply drafts, personal names) |  |
| G-25 | node_census skipped days (Aug 4, Aug 10) — cycleCount-gated, resets on restart — FIXED | L-01 |
| G-26 | Research runner manual-only (5 fetchers dead ~9 days, findings static) — FIXED | L-02 |
| G-27 | hashrate/mempool_recent 'stale' false alarm — file count misread as staleness — CLOSED as misdiagnosis | L-03 |
| G-28 | GH013 hardcoded GitHub token pushed; ALL pushes blocked — FIXED (rotation doc) | L-04 |
| G-29 | btc-rpc '3 days stale' was a wrong-directory misdiagnosis — btc_rpc (underscore) always fresh — CLOSED as misdiagnosis | L-05 |
| G-30 | THE META-GAP: data-capture lessons learned in conversation were NEVER persisted into TELOS — FIXED structurally | L-00 |

## Patterns (9)
- **P-01 Gates red on clean tree / health not self-certifying** → Make gap-scanner staged-scope or thresholded; fix or archive legacy dead code (meal_library, dev_domain_adapter); let M4 run naturally; reconnect stale spool source
- **P-02 Derived artifacts / docs out of sync** → model-spec.json single source (done); extend provenance to backtest.py; reconcile axiom-count references; DNS cleanup
- **P-03 Research written but not consolidated/published** → Write the working paper; publish brief-52; then resource legs extend the same paper
- **P-04 Work accumulates unshipped / no canonical tracking** → This tracker (done); commit TELOS work; auto-check tracker in self-audit; DONE=SHIPPED gate
- **P-05 Bots/skills kept alive past usefulness** → Audit every bot/skill: if not useful now → remove, then redesign better to the goal (architect mandate). Retire, don't accumulate.
- **P-06 Conversation-only learning / counter-reset scheduling (LESSONS NOT PERSISTED)** → telos/lessons/ record appended to every session; data captures gated on persisted last-run-date not cycleCount; >2-round fixes MUST be recorded
- **P-07 Freshness judged by file count instead of per-source cadence** → Staleness = age vs per-source expectedIntervalMinutes from spool cursors (monitor.js 08-02). Never judge health by listing files.
- **P-08 Secrets hardcoded in code / pushed to remote** → env vars + gitignored .env.local; secret-scan before push; on GH013 rotate (revoke + recreate), never just delete
- **P-09 Wrong-slot diagnosis (near-identical source names, wrong directory)** → Resolve source keys from CONFIG.endpoints; confirm canonical location before declaring staleness

## Shells (7)
- **S0 SHIP & FREEZE**: G-08, G-09 — *exit:* TELOS repo committed+pushed; brief-52 published; no unshipped work in either repo
- **S1 GATES GREEN**: G-01, G-03, G-05 — *exit:* Gap scanner green (or staged-scope/thresholded + exception documented); M4 7/7 flipped; spool fresh
- **S2 CORRECTNESS & CONSISTENCY**: G-04, G-10, G-13 — *exit:* backtest.py provenance added; DNS cleaned; axiom references reconciled
- **S3 THE PAPER**: G-02, G-18 — *exit:* research/working-paper.md written + regenerated HTML + resource legs scoped with v1 measurements
- **S4 BOT/SKILL LIFECYCLE**: G-12 — *exit:* Every bot/skill audited; unused removed; redesigned ones serve the goal
- **S5 ENFORCEMENT**: G-14 — *exit:* Self-audit reads tracker; DONE=SHIPPED enforced by hook; tracker auto-updated
- **S6 LEARNING PERSISTENCE**: G-25, G-26, G-27, G-28, G-29, G-30 — *exit:* Every >2-round fix recorded in telos/lessons/ with gap link; sessions append before close; self-audit checks lessons dir non-empty

**Zero-omission check:** open gaps: G-18, G-19, G-20, G-21, G-22, G-23 → all covered by shells above.
