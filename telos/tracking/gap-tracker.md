# TELOS — Gap Tracker (canonical)

Canonical source: `telos/tracking/gap-tracker.json` (machine-readable).
BSAHI references this file; TELOS owns it. Last verified: 2026-08-02.

## Rule (architect mandate)
**DONE means SHIPPED** (committed + pushed + live). Unshipped work goes in LEFT, never DONE.
Every report ends with labeled `DONE (verified)` + `LEFT / TODO (verified)`.

## Gaps — open (8)

| ID | System | Gap | Effort | Impact | Shell |
|----|--------|-----|--------|--------|-------|
| G-01 | TELOS | Gap-scanner pre-commit gate RED on clean tree (750 fails, 4/6 checks) | L | critical | S1 |
| G-02 | BSAHI | Working paper (v2.0.0) not written | L | high | S3 |
| G-03 | BSAHI | M4 gate 3/7 (bridge not flipped) | S | medium | S1 |
| G-05 | BSAHI | Spool staleness: btc-rpc stale 3+ days | S | medium | S1 |
| G-06 | BSAHI | Resource legs deferred (UTXO/bandwidth/validation/node_geo) | L | high | S3 |
| G-08 | TELOS | Uncommitted TELOS work (29 files) | S | high | S0 |
| G-09 | BSAHI | brief-52 (v2.0.0) pending, not published | S | medium | S0 |
| G-12 | process | Bot/skill lifecycle audit — remove unused, redesign better | M | high | S4 |
| G-14 | process | DONE=SHIPPED not yet auto-enforced | S | medium | S5 |

## Gaps — closed (2)

| ID | Gap |
|----|-----|
| G-07 | Canonical gap tracker created (this file) |
| G-11 | SCCR v2.0.0 correction SHIPPED (0.0149 → 0.1719, live) |

## Patterns (5)

- **P-01 Gates red on clean tree** → staged-scope/threshold the scanner, fix legacy dead code, let M4 run, reconnect spool (G-01, G-03, G-05)
- **P-02 Derived artifacts/docs out of sync** → single source of truth + provenance everywhere (G-04, G-10, G-13)
- **P-03 Research written but not consolidated/published** → the working paper consolidates; publish brief-52 (G-02, G-06, G-09)
- **P-04 Work accumulates unshipped / no canonical tracking** → this tracker + auto-check + DONE=SHIPPED (G-07, G-08, G-14)
- **P-05 Bots kept alive past usefulness** → lifecycle audit: remove, then redesign better (G-12)

## Shells (coverage proof — every open gap maps to exactly one shell)

- **S0 SHIP & FREEZE**: G-08, G-09 — *exit:* TELOS committed+pushed; brief-52 published
- **S1 GATES GREEN**: G-01, G-03, G-05 — *exit:* scanner green/thresholded, M4 7/7, spool fresh
- **S2 CORRECTNESS & CONSISTENCY**: G-04, G-10, G-13 — *exit:* provenance, DNS, axiom refs reconciled
- **S3 THE PAPER**: G-02, G-06 — *exit:* working-paper.md + resource legs v1
- **S4 BOT/SKILL LIFECYCLE**: G-12 — *exit:* every bot audited, unused removed, redesigned serve the goal
- **S5 ENFORCEMENT**: G-14 — *exit:* self-audit reads tracker, DONE=SHIPPED hooked

**Zero-omission check:** open gaps G-01,02,03,05,06,08,09,12,14 → S1,G3,S1,S1,S3,S0,S0,S4,S5. All 9 covered.
