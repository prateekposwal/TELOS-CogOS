# TELOS — Gap Tracker (canonical)

Canonical source: `telos/tracking/gap-tracker.json` (machine-readable).
BSAHI references this file; TELOS owns it. Last verified: 2026-08-04 (G-06 legs shipped v1).

## Rule (architect mandate)
**DONE means SHIPPED** (committed + pushed + live). Unshipped work goes in LEFT, never DONE.
Every report ends with labeled `DONE (verified)` + `LEFT / TODO (verified)`.

## Gaps — open (1)

| ID | System | Gap | Effort | Impact | Shell |
|----|--------|-----|--------|--------|-------|
| G-18 | BSAHI | node_geo per-region cost distributions not expanded (G-06 remainder) | M | low | S3 |

## Gaps — closed (17)

| ID | Gap |
|----|-----|
| G-01 | Gap-scanner pre-commit gate RED on clean tree |
| G-02 | Working paper |
| G-03 | M4 gate not flipped |
| G-04 | backtest.py lacks provenance/version markers |
| G-05 | Spool staleness: btc-rpc source stale 3+ days |
| G-06 | Resource legs deferred: UTXO, bandwidth, validation, node_geo |
| G-07 | No canonical gap tracker existed |
| G-08 | Uncommitted TELOS work |
| G-09 | brief-52 |
| G-10 | DNS registrar parking nameservers |
| G-11 | SCCR v2.0.0 correction — 10x bug + reconciliation |
| G-12 | Bot/skill usefulness audit — remove unused, redesign better |
| G-13 | AXIOMS.md consistency — 42 axioms confirmed, but latent_cognition.md referenced 20 |
| G-14 | DONE=SHIPPED enforcement not yet automatic |
| G-15 | Real node census |
| G-16 | brief-52 publish: content-briefs never consumed for posting — FIXED |
| G-17 | BSAHI stuck mid-rebase |

## Patterns (5)
- **P-01 Gates red on clean tree / health not self-certifying** → Make gap-scanner staged-scope or thresholded; fix or archive legacy dead code (meal_library, dev_domain_adapter); let M4
- **P-02 Derived artifacts / docs out of sync** → model-spec.json single source (done); extend provenance to backtest.py; reconcile axiom-count references; DNS cleanup
- **P-03 Research written but not consolidated/published** → Write the working paper; publish brief-52; then resource legs extend the same paper
- **P-04 Work accumulates unshipped / no canonical tracking** → This tracker (done); commit TELOS work; auto-check tracker in self-audit; DONE=SHIPPED gate
- **P-05 Bots/skills kept alive past usefulness** → Audit every bot/skill: if not useful now → remove, then redesign better to the goal (architect mandate). Retire, don't a

## Shells (coverage proof — every open gap maps to exactly one shell)
- **S0 SHIP & FREEZE**: G-08, G-09 — *exit:* TELOS repo committed+pushed; brief-52 published; no unshipped work in either repo
- **S1 GATES GREEN**: G-01, G-03, G-05 — *exit:* Gap scanner green (or staged-scope/thresholded + exception documented); M4 7/7 flipped; spool fresh
- **S2 CORRECTNESS & CONSISTENCY**: G-04, G-10, G-13 — *exit:* backtest.py provenance added; DNS cleaned; axiom references reconciled
- **S3 THE PAPER**: G-02, G-18 — *exit:* research/working-paper.md written + regenerated HTML + resource legs scoped with v1 measurements
- **S4 BOT/SKILL LIFECYCLE**: G-12 — *exit:* Every bot/skill audited; unused removed; redesigned ones serve the goal
- **S5 ENFORCEMENT**: G-14 — *exit:* Self-audit reads tracker; DONE=SHIPPED enforced by hook; tracker auto-updated

**Zero-omission check:** open gaps G-18 → all covered above.
