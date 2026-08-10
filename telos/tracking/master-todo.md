# TELOS — THE ONE CANONICAL MASTER LIST (both repos)

**Owner:** TELOS | **Created:** 2026-08-10 | **Status:** LIVE — updated after every action
**Scope:** BSAHI (`../block-space-economics`) + TELOS (this repo) + process.
**Rule (architect mandate):** DONE means SHIPPED (committed + pushed + live).
Unshipped work goes in LEFT, never DONE. Every action updates this file.

---

## WAVE A — Immediate / now (hard deadlines or blocking everything else)

- [ ] **A1. D5 external reproduction — send the recruit message.** THE submission
      gate (advisor: "worth far more than another 100 commits"). Prateek sends
      `research/reproduce/recruit-message.md` to ONE uninvolved person (~15 min),
      records result in `research/reproduce/external-reproduction.md`. Kit is
      already verified reproducible-by-stranger (fresh-clone PASS, 0.2186).
      **WHY:** only submission blocker. **Effort:** 15 min. **Dep:** none.
      **BLOCKS: entire Wave B.**
- [ ] **A2. Post the reply to Vachagan.** `research/reply-vachagan.md` is DRAFT,
      committed (`bf93f89`, on origin) but NOT posted anywhere. **WHY:** the
      hostile comment becomes the program's next deliverable; reply verified.
      **Effort:** 5 min (Prateek posts, or approves Nostr key use). **Dep:** none.
- [x] **A3. Commit + push TELOS uncommitted work **DONE 2026-08-10**.** AGENTS.md handoffs,
      `TRADING_PROJECT_STATE.md` (new, parked-trading state), regenerated
      decision_log.json / transparency_report.md / gap-tracker.md.
      **WHY:** DONE=SHIPPED; uncommitted work is the confusion pattern itself.
      **Effort:** S. **Dep:** none.
- [x] **A4. Update gap-tracker.json **DONE 2026-08-10** (stale since 2026-08-04).** It does not
      reflect D3-D7, cost-to-flood, governance-boundary, or reply items; point it
      at this file. **WHY:** the canonical tracker went stale — the root cause.
      **Effort:** S. **Dep:** none.
- [x] **A5. Resolve the 1 queued marketing post **DONE 2026-08-10** (LinkedIn item marked superseded — retired by policy)** (BSAHI-MSMFC5QX-UH8K,
      linkedin/fee, scheduled 2026-08-09, never posted). **WHY:** pending
      scheduled work. **Effort:** XS. **Dep:** none.
- [ ] **A6. Commit or deliberately gitignore BSAHI untracked reports**
      (architect DE-2026-08-02..09, daily DE reports, reddit digests, research
      dailies) + `arxiv-abstract-draft.html` + `.pre-fix.bak.json`.
      **WHY:** unshipped-work hygiene. **Effort:** S. **Dep:** none.

## WAVE B — Paper submission (the D-gate)

**DONE:** D1 author ✅ | D2 ORCID ✅ (`0009-0005-2139-1877`) | D4 license ✅
(MIT LICENSE committed `8b3fd0e`) | D6 LaTeX source ✅ (complete, 592 lines) |
D7 companion sign-off ✅ | abstract drafts ✅ (A ~1160 / B ~700, banded) |
falsifiability §7.1 ✅ | evidence/hypothesis separation ✅ | reproduction kit
stranger-verified ✅ | moderator pitch ✅ (§2a).

- [ ] **B1. D5 external reproduction = A1** (the gate — no external reply yet).
- [ ] **B2. D3 arXiv account + endorsement.** Create account (real identity),
      link ORCID, start submission, request endorsement from Daniel Aronoff
      (cleanest path, doubles as tier-2 reproducer). Preflight ready
      (`research/arxiv-d3-preflight.md`). **Effort:** 15 min + waiting.
- [ ] **B3. LaTeX compile pass** on any pdflatex machine; verify PDF renders;
      diff content vs working-paper.md. **Effort:** S. **Dep:** pdflatex.
- [ ] **B4. Final abstract selection** (A vs B) + verify banded claims only.
      **Effort:** XS. **Dep:** B2.
- [ ] **B5. Units & notation consistency pass.** **Effort:** M.
- [ ] **B6. Claims-within-evidence pass** (banded ~22–29% / ~99–100%; ≥32K; T=10).
      **Effort:** S.
- [ ] **B7. Reproducibility line intact** (model-spec v2.0.1 + 3 implementations).
      **Effort:** XS.
- [ ] **B8. Prior-work honesty intact** (Liu et al. 2021, arXiv:2103.05866).
      **Effort:** XS.
- [ ] **B9. Dead-claims audit** (no v1/v2 oracle framing; BIP-110 only as
      documented DOA). **Effort:** S.
- [ ] **B10. Freeze repo → tag v1.0.0 → push tag → Zenodo DOI.**
      **Trigger:** A1/B1 reply lands. **Effort:** S.
- [ ] **B11. arXiv upload** (econ.GN primary / cs.CR cross-list; CC BY 4.0;
      moderator pitch as cover letter). **Effort:** S. **Dep:** B1–B10.
- [ ] **B12. Delving Bitcoin link-first announcement.** **Effort:** XS. **Dep:** B11.
- [ ] **B13. Optech 2–4 sentence summary + submission.** **Effort:** XS. **Dep:** B11.
- [ ] **B14. Post-publication: register preprint URL** (TODO R5 + site surfaces).
      **Effort:** S. **Dep:** B11.

## WAVE C — Research program

### Cost-to-Flood (attacker-side externality; steps 1–3 DONE + committed `bf93f89`)
- [ ] **C1. Complete boundedness theorem** (step 4 — 52.6 GB/yr vbytes cap
      verified; formal proof sketch partial). **Effort:** S–M.
- [ ] **C2. Build the budget scenario table** (step 5: state budgets → node
      impact). **Effort:** S.
- [x] **C3. Draft **DONE 2026-08-10** (cost-to-flood.md + HTML live) `research/cost-to-flood.md` + HTML** (step 6 — the v1 note).
      **Effort:** M.
- [ ] **C4. Consistency review vs SCCR §7 knife-edge** (step 7). **Effort:** S.
- [ ] **C5. Dust-RAM/validation leg** (0.9× is storage-only; dust's real threat
      is RAM). **Effort:** M.
- [ ] **C6. DECISION: standalone note first, or fold into working-paper §5.8
      before submission.** **Effort:** decision. **Dep:** B-wave timing.
- [ ] **C7. Update gap tracker + commit/push cost-to-flood artifacts** (step 8).
      **Effort:** S.

### Governance-Boundary (BIP-110 window — the one-time natural experiment)
- [x] **G1. Window capture — DONE + LIVE** (verified 2026-08-10: spool healthy,
      missedCycles 0, seq 323, height 961792, inWindow=true, 1856 blocks to
      lock-in ≤ 963648 ≈ Aug 23).
- [x] **G2. GBI note **DONE 2026-08-10** (governance-boundary.md + HTML live) — NOT STARTED** (no artifact in either repo). The window is
      the experiment; the note is the framing deliverable. **Effort:** M.
- [ ] **G3. Calibration — NOT STARTED** (no calibration doc found in either repo).
      **Effort:** S–M.
- [ ] **G4. Post-window analysis** — by nature after lock-in (~Aug 23). Analyze
      the signaling record once the window closes. **Effort:** M. **Dep:** G1.

## WAVE D — Backlog / optional (no deadline)

- [ ] **D1. G-18: node_geo per-region cost distributions** (only open gap-tracker
      item; refines C decomposition). **Effort:** M. **Impact:** low.
- [ ] **D2. Interactive paper** (publication-plan §6.2 — SPEC only; build only
      after publication). **Effort:** L. **Dep:** B11.
- [ ] **D3. Backend decision / `/sccr/block/{height}`** (R5-gated). **Effort:** M.
      **Dep:** post-publication.
- [ ] **D4. Trading project — PARKED** (resume conditions in
      `TRADING_PROJECT_STATE.md`, which is itself uncommitted → A3).
- [ ] **D5. TELOS ops health:** block_interval spool stale; DB error ratio
      28% > 20%; M4 cleanCycles 1/7. **Effort:** S.
- [ ] **D6. Archive/ignore the 214 untracked marketing queue files**
      (183 skipped / 30 posted / 1 queued). **Effort:** S.

## WAVE E — Data-capture reliability (lessons persisted 2026-08-11)

**Origin:** 5 data-gap lessons from 2026-08-10 were learned in conversation and fixed in BSAHI but NEVER persisted into TELOS — the architect caught the meta-gap. Now structurally recorded: `telos/lessons/2026-08-11-data-capture-reliability.json` (L-00..L-05), gap-tracker G-25..G-30, AXIOMS.md P2.0.

- [x] **E1. Lessons record created** — `telos/lessons/` with L-01..L-05 (node_census gating, research runner wiring, file-count freshness misjudgment, GH013 token, btc-rpc wrong-dir) + L-00 (the meta-gap) **DONE 2026-08-11**
- [x] **E2. Gap-tracker entries** — G-25..G-30 added (closed), G-05 corrected as misdiagnosis, patterns P-06..P-09, shell S6 **DONE 2026-08-11**
- [x] **E3. Operational rule** — "after any >2-round fix, write the lesson" added to lessons README + AXIOMS.md P2.0 **DONE 2026-08-11**
- [ ] **E4. Self-audit integration** — add a self-audit check: lessons/ dir must be non-empty and latest lesson within N days of last session (future work)
- [ ] **E5. BSAHI side** — node_census Aug 4 historical gap is permanent; monitor for no new gaps (cadence: files daily through Aug 12+)


---

## Coverage table (zero-omission proof)

| Source list | Open items | Covered by |
|---|---|---|
| gap-tracker.json (G-18) | node_geo | D1 |
| gap-tracker staleness | tracker not updated since 08-04 | A4 |
| D2–D7 batch | D3 account, D5 repro, D6 compile, abstract, units, claims, repro-line, prior-work, dead-claims, freeze, submit, Delving, Optech, R5-URL | B2, B1/A1, B3, B4, B5, B6, B7, B8, B9, B10, B11, B12, B13, B14 |
| Cost-to-Flood plan | steps 4–8, reply post, dust-RAM, decision | C1, C2, C3, C4, C7, A2, C5, C6 |
| Governance plan | capture (done), GBI note, calibration, post-window | G1, G2, G3, G4 |
| Reply status | reply not posted | A2 |
| Capture status | capture live; post-window analysis | G1, G4 |
| Wave 0–3 plan | NO ARTIFACT FOUND on disk in either repo — conversational only; verifiable items folded into A/B/C above | A/B/C |
| TELOS uncommitted | AGENTS.md, TRADING state, runtime logs | A3 |
| BSAHI untracked | reports, queue files (1 queued post) | A6, A5 |

**Every open item from every prior list appears exactly once above.**

## Website storytelling (2026-08-10)
- [x] **Data Story page** (story.html) — BIP-110 timeline, SCCR trend, leverage, 4-resource heatmap — LIVE
- [x] **agent-26 public snapshot** data/bip110.json — LIVE
- [x] **nav wired** across all pages — DONE
- [ ] Mobile visual QA (responsive layout verified in CSS; final check on device)
