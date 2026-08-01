# knowledge_library/books — Acquisition Manifest

Status: **NOT DOWNLOADED (acquisition declined)** — see TELOS report below the table.
Facts below verified 2026-08-01 from OpenLibrary bibliographic records (legitimate catalog data).
Covers the 4 priority books (rows 1–4) and the remaining curriculum set (rows 5–27, Tiers 1–3).

| # | Title | Author | Publisher / Year | Verified pages | ISBN-13 | OpenLibrary record |
|---|-------|--------|------------------|----------------|---------|--------------------|
| 1 | Trading Risk (Enhanced Profitability through Risk Control) | Kenneth L. Grant | Wiley, 2004 (1st ed. on record; 2011 2nd ed. ISBN 978-0-470-64334-9 unverified) | 272 (median, 1st ed.) | 978-0-470-25196-6 | /works/OL5758266W |
| 2 | Trading and Exchanges: Market Microstructure for Practitioners | Larry Harris | Oxford University Press, 2003 | xii, 643 (= 655 total) | 978-0-19-514470-3 | /books/OL18178856M |
| 3 | Cryptoassets: The Innovative Investor's Guide to Bitcoin and Beyond | Chris Burniske & Jack Tatar | McGraw-Hill Education, 2018 | xxvii, 325 (= 352 total) | 978-1-26-002667-2 | /books/OL26939457M |
| 4 | The Mathematics of Money Management: Risk Analysis Techniques for Traders | Ralph Vince | Wiley, 1992 (orig.) | 376 (median) | 978-0-471-54738-9 | /works/OL3503409W |

One-line factual note (as agreed): pdfdrive hosts unauthorized scans of in-copyright books, so this channel was not used and legit editions are what we should source.

## Legit acquisition channels (per title)
1. **Grant — Trading Risk**: Wiley store / bookseller (2nd ed. 2011, ISBN 978-0-470-64334-9).
2. **Harris — Trading and Exchanges**: OUP Academic product page; O'Reilly Learning; Internet Archive controlled digital lending: https://archive.org/details/tradingexchanges0000harr (restricted/borrowable).
3. **Burniske & Tatar — Cryptoassets**: McGraw-Hill store / bookseller.
4. **Vince — Mathematics of Money Management**: Wiley / bookseller (orig. 1992; 2nd ed. ISBN 978-0-471-54538-7 per some catalogs — verify before ordering).

## SkillLibrary seed mapping (what consumes these first, once legit copies are in hand)
- `capital_guardian` ← Grant (Trading Risk) + Elder (position sizing/risk mgmt framing)
- `microstructure` ← Harris (Trading and Exchanges)
- `crypto_framing` ← Burniske & Tatar (Cryptoassets)
- `position_sizing` ← Vince (Mathematics of Money Management)

Seed scaffolds ARE BUILT (2026-08-01) in `telos/core/ledger/skill_seeds.py` — see `tests/core/test_skill_seeds.py` (12/12 passing, full suite 566/566). Each scaffold has TOC-derived concept maps, knowledge fields, decision rules, failure modes, and chapter ingestion hooks flagged `verified: False`. Next step (tracked in AGENTS.md Next To-Dos): acquire legit copies, then fill chapter-level content and flip `toc_verified: True`.

---

# Remaining curriculum set — Tiers 1–3 (23 books, rows 5–27)

Same provenance rules as rows 1–4; verified 2026-08-01 from OpenLibrary bibliographic records.
⚠ flags a thin/ambiguous record — verify before ordering. Priority keys:
**[acquire-now]** = next purchase after Grant + Vince · **[acquire-later]** = sequenced after the capital-guardian core · **[reference-only]** = keep as reference, don't read cover-to-cover.

| # | Title | Author | Publisher / Year | Verified pages | ISBN-13 | OpenLibrary record | Tier | Level | Priority |
|---|-------|--------|------------------|----------------|---------|--------------------|------|-------|----------|
| 5 | Economics in One Lesson | Henry Hazlitt | Three Rivers Press, 1946 (orig.; 2008 reprint) | 205 (median) | 978-0-307-76062-3 (2008) | /works/OL541970W | T1 | Beginner | [acquire-later] |
| 6 | Stock Investing For Dummies (5th ed.) | Paul Mladjenovic | Wiley, 2002 (orig.; 5th ed. 2018) | 392 (median) | 978-1-118-46119-3 (5th ed.) | /works/OL278197W | T1 | Beginner | [acquire-later] |
| 7 | How to Day Trade for a Living | Andrew Aziz | CreateSpace / self-published, 2016 | ⚠ 136 (OL median; print ed. ~330 — verify) | 978-1-535-58595-8 | /works/OL19730523W | T1 | Beginner | [acquire-now] |
| 8 | Cryptocurrency Investing Bible | Alan T. Norman | CreateSpace / self-published, 2017 | 162 | 978-1-979-68836-9 | /works/OL34595618W | T1 | Beginner | [acquire-later] |
| 9 | Blockchain Technology: The Ultimate Guide (⚠ title normalized) | Alan T. Norman | CreateSpace / self-published, 2017 | 126 | 978-1-981-52202-6 | /works/OL29231784W | T1 | Beginner | [acquire-later] |
| 10 | Finance: Capital Markets, Financial Management, and Investment Management | Frank J. Fabozzi & Pamela P. Drake | Wiley, 2009 | ⚠ n/a in OL (~800 est.) | 978-0-470-48615-3 | /works/OL29014906W | T1 | Intermediate | [reference-only] |
| 11 | The Economics of Money, Banking, and Financial Markets (13th ed.) | Frederic S. Mishkin | Pearson, 1986 (orig.; 13th ed. 2022) | 731 (median) | 978-1-292-26896-5 (13th ed.) | /works/OL452451W | T1 | Intermediate | [reference-only] |
| 12 | Trading for a Living | Alexander Elder | Wiley, 1993 (2nd ed. "The New Trading for a Living" 2014) | 289 (median) | 978-0-471-59224-2 (1993) | /works/OL1940236W ⚠ seed cites /works/OL1392204W | T2 | Intermediate | [acquire-now] |
| 13 | Technical Analysis of the Financial Markets | John J. Murphy | New York Institute of Finance / Penguin, 1999 | 559 | 978-0-735-20066-1 | /works/OL1957750W | T2 | Intermediate | [acquire-later] |
| 14 | Python for Finance: Mastering Data-Driven Finance (2nd ed.) | Yves Hilpisch | O'Reilly, 2018 (1st ed. 2014) | 720 | 978-1-492-02433-0 (2nd ed.) | /works/OL19541900W | T2 | Intermediate | [acquire-later] |
| 15 | Foundations of Financial Risk | Richard Apostolik / GARP | Wiley, 2015 | 368 | 978-1-119-09805-8 | /works/OL20000877W | T2 | Intermediate | [acquire-later] |
| 16 | Quantitative Financial Risk Management (⚠ 3 candidates; Miller chosen) | Michael B. Miller | Wiley, 2018 | 320 | 978-1-119-52220-1 | /works/OL21640051W | T2 | Intermediate | [acquire-later] |
| 17 | Mastering Bitcoin (2nd ed.) — REPLACES the unverifiable "Cryptocurrency Master" | Andreas M. Antonopoulos | O'Reilly, 2014 (1st ed.; 2nd ed. 2017) | 298 (1st ed. median) | ⚠ 978-1-491-95479-9 (2nd ed., unverified in OL; 1st ed. 978-1-449-37404-4) | /works/OL19547324W | T2 | Intermediate | [acquire-later] |
| 18 | The Secrets of Economic Indicators (3rd ed.) | Bernard Baumohl | FT Press, 2012 (1st ed. Wharton School Pub., 2004) | 468 | 978-0-132-93207-3 (3rd ed.) | /works/OL16637489W | T2 | Beginner | [acquire-later] |
| 19 | Japanese Candlestick Charting Techniques (2nd ed.) | Steve Nison | New York Institute of Finance, 2001 (1st ed. 1991) | 307 (1st ed. median) | 978-0-735-20181-1 (2nd ed.) | /works/OL3459605W | T2 | Intermediate | [acquire-later] |
| 20 | Trading Price Action Trends (⚠ OL record merged w/ "Reading Price Charts Bar by Bar") | Al Brooks | Wiley, 2012 | 576 (merged OL record) | 978-1-118-06651-5 | /works/OL28304682W | T2 | Intermediate | [reference-only] |
| 21 | The Mathematics of Financial Modeling and Investment Management | Sergio M. Focardi & Frank J. Fabozzi | Wiley, 2004 | ⚠ n/a in OL (~800 est.) | 978-0-471-67423-8 | /works/OL29014693W | T3 | Advanced | [reference-only] |
| 22 | Financial Risk Management: A Practitioner's Guide to Managing Market and Credit Risk (2nd ed.) | Steven Allen | Wiley, 2013 (1st ed. 2003) | 608 (OL record of 2009 reprint) | 978-1-118-17545-3 (2nd ed.) | /works/OL16714842W | T3 | Advanced | [acquire-later] |
| 23 | Practical Methods of Financial Engineering and Risk Management | Rupak Chatterjee | Apress, 2014 | 412 | 978-1-430-26133-9 | /works/OL20737315W | T3 | Advanced | [reference-only] |
| 24 | Quantitative Investment Analysis (3rd ed.) | Richard A. DeFusco, Dennis W. McLeavey et al. / CFA Institute | Wiley / CFA Institute, 2015 (2nd ed. 2007) | 640 | 978-1-119-10459-9 (3rd ed.) | /works/OL20771782W | T3 | Intermediate | [reference-only] |
| 25 | Artificial Intelligence in Finance | Yves Hilpisch | O'Reilly, 2020 | 475 | 978-1-492-05543-3 | /works/OL21690356W | T3 | Advanced | [reference-only] |
| 26 | Intermarket Analysis: Profiting from Global Market Relationships (⚠ tier-list title was a paraphrase) | John J. Murphy | Wiley, 2004 | 288 | 978-0-471-02329-6 | /works/OL8081177W | T3 | Intermediate | [acquire-later] |
| 27 | Introductory Econometrics: A Modern Approach (7th ed.) | Jeffrey M. Wooldridge | Cengage, 2019 (6th ed. 2015) | 864 | 978-1-337-55886-0 (7th ed.) | /works/OL21108634W | T3 | Intermediate | [reference-only] |

## Provenance flags (⚠) — how each was resolved
- **Row 7 (Aziz)**: OL page median (136) is far below the print edition's ~330 pp — thin record; verify page count on receipt.
- **Row 9 (Norman blockchain)**: OL record found under the title "Blockchain Technology Explained"; the tier list's "Blockchain: Ultimate Guide" is this book or a same-series variant — verify exact title on order.
- **Rows 10, 21 (Fabozzi & Drake; Fabozzi/Focardi)**: OL has no page count; ~800 is a format-based estimate.
- **Row 12 (Elder)**: OpenLibrary search returns /works/OL1940236W for the 1993 ISBN; the seed scaffold cites /works/OL1392204W for the same ISBN (work-level split). Both resolve to Wiley 1993, ISBN 978-0-471-59224-2.
- **Row 16 (QFRM)**: three distinct books share this title — Miller (Wiley 2018, chosen: newest, practitioner-oriented), Zopounidis & Galariotis (Wiley 2015, textbook), Desheng Dash Wu (Springer 2011). Verify which edition the curriculum intends before ordering.
- **Row 17 (Mastering Bitcoin)**: OL record is the 1st ed. (2014); the 2nd ed. ISBN 978-1-491-95479-9 (2017) is not in OL — verify before ordering. "Cryptocurrency Master" from the tier list has no reliable bibliographic record; Mastering Bitcoin is the sanctioned technical replacement (also legitimately free — the author releases it on GitHub).
- **Row 20 (Brooks)**: OL record for ISBN 978-1-118-06651-5 carries the title "Reading Price Charts Bar by Bar" (merged/sloppy record); the ISBN is the Trading Price Action Trends edition — verify on order.
- **Row 26 (Murphy intermarket)**: actual title is "Intermarket Analysis: Profiting from Global Market Relationships" — the tier list's "Trading with Intermarket Analysis" is a paraphrase.

## No-piracy gate — Internet Archive caution (extends the note above row 1)
IA also hosts **unauthorized scans** of several of these titles (e.g., Murphy row 13, Brooks row 20, a Wooldridge 2016 scan, alternate Nison scans). Those items are NOT channels — same category as pdfdrive. Only the **restricted/borrowable lending records** cited below are legitimate controlled-digital-lending channels.

## Legit acquisition channels (remaining set)
5. **Hazlitt** — FREE authorized edition: Ludwig von Mises Institute distributes it legitimately (ISBN 978-1-933550-21-3); IA lending: https://archive.org/details/economicsinonele00henr
6. **Mladjenovic** — Wiley bookseller; IA lending: https://archive.org/details/stockinvestingfo0000mlad_v0e4 (2016) and https://archive.org/details/stockinvestingfo0000mlad_o0z0 (2009)
7. **Aziz** — Amazon/CreateSpace (self-pub, ~$25); IA lending: https://archive.org/details/howtodaytradefor0000aziz (2016)
8. **Norman — Crypto Bible** — Amazon/CreateSpace (self-pub, ~$15); no IA record
9. **Norman — Blockchain** — Amazon/CreateSpace (self-pub, ~$15); no IA record
10. **Fabozzi & Drake** — Wiley bookseller; no IA record
11. **Mishkin** — Pearson bookseller; IA lending: https://archive.org/details/economicsofmoney00mish_0 (1989) — prefer current 13th ed. if buying
12. **Elder** — Wiley bookseller; IA lending: https://archive.org/details/tradingforliving00elde (1993) and https://archive.org/details/newtradingforliv0000elde (2014 ed.)
13. **Murphy — Technical Analysis** — NYIF/Penguin bookseller or library ILL (no legit IA lending record)
14. **Hilpisch — Python for Finance** — O'Reilly Learning subscription (includes it); O'Reilly bookseller
15. **GARP — Foundations of Financial Risk** — Wiley bookseller; GARP's own FRM Part 1 bookstore
16. **Miller — QFRM** — Wiley bookseller; no IA record
17. **Antonopoulos — Mastering Bitcoin** — FREE legit: author's GitHub (github.com/bitcoinbook/bitcoinbook, 2nd ed.); IA lending: https://archive.org/details/masteringbitcoin0002anto (2017)
18. **Baumohl** — FT Press bookseller; IA lending: https://archive.org/details/secretsofeconomi03edbaum (2013) and https://archive.org/details/secretsofeconomi0000baum (2008)
19. **Nison** — NYIF bookseller; IA lending: https://archive.org/details/japanesecandlest0000niso (2001 2nd ed.)
20. **Brooks** — Wiley bookseller or library ILL (no legit IA lending record)
21. **Fabozzi/Focardi** — Wiley bookseller; IA lending: https://archive.org/details/mathematicsoffin0000foca (2004)
22. **Allen** — Wiley bookseller or library ILL; no IA record
23. **Chatterjee** — Apress/Springer bookseller; no IA record
24. **CFA — Quantitative Investment Analysis** — Wiley/CFA Institute (member discount); IA lending: https://archive.org/details/quantitativeinve0000unse (2015) and https://archive.org/details/quantitativeinve0002unse (2007)
25. **Hilpisch — AI in Finance** — O'Reilly Learning subscription; O'Reilly bookseller
26. **Murphy — Intermarket Analysis** — Wiley bookseller or library ILL; no IA record
27. **Wooldridge** — Cengage bookseller; IA lending: https://archive.org/details/introductoryecon0000wool_c3l8 (2013)

## Priority re-rank — given Grant → Vince → exam sequencing
**[acquire-now] — buy next (feeds the exam directly):**
- **Elder, Trading for a Living (#12)** — the seed's default `max_risk_per_trade = 0.02` IS Elder's 2% rule; the 2%/6% rules are an open ingestion hook on `capital_guardian`. Exam Lesson 1 (drawdown under 1%/2%/5% sizing) needs the doctrinal statements. ~$25–30, and free via IA lending meanwhile.
- **Aziz, How to Day Trade for a Living (#7)** — second open hook on `capital_guardian` (sizing formula, stop placement, discipline). Self-published, ~$25; IA lending record exists.

**[acquire-later] — sequenced after the capital-guardian core:**
Hazlitt (#5, free channel — zero-cost anytime), Mladjenovic (#6), Norman ×2 (#8, #9, cheap), Murphy Technical Analysis (#13 — charting layer of the Strategy Lab), Hilpisch Python for Finance (#14 — implementation layer for the risk/backtest engine), GARP Foundations (#15 — institutional risk taxonomy for validators), Miller QFRM (#16 — quant risk math for simulation), Antonopoulos (#17, free channel; ties to the Bitcoin block-space research thread), Baumohl (#18 — macro regime inputs for `crypto_framing`), Nison (#19 — candlestick layer), Allen (#22 — risk-engine spec), Murphy Intermarket (#26 — cross-asset regime for `crypto_framing`).

**[reference-only] — do not buy / do not read cover-to-cover:**
Fabozzi & Drake (#10), Mishkin (#11), Brooks (#20), Fabozzi/Focardi (#21), Chatterjee (#23), CFA Quantitative Investment Analysis (#24), Hilpisch AI in Finance (#25), Wooldridge (#27). Textbook-sized reference anchors; the specific content each contributes is better acquired via the [acquire-later] practitioner titles first.

## TELOS machinery feed (what consumes each book, once read)
- `capital_guardian` (SkillLibrary seed) ← **#7 Aziz, #12 Elder** (ingestion hooks already declared: 2%/6% rules, sizing formula, stop protocol, kill-switch)
- `crypto_framing` (seed) ← **#5 Hazlitt** (economics literacy for macro framing), **#8/#9 Norman** (custody/exchange/regulatory risk → `regulatory_risk_register`), **#18 Baumohl + #26 Murphy** (macro regime → adoption-curve phase & correlation knowledge fields)
- `microstructure` (seed) ← **#7 Aziz** (execution-side color), none other remaining directly
- `position_sizing` (seed) ← **#16 Miller** (VaR/ES math), **#22 Allen** (risk measures in practice)
- `simulation` (CounterfactualEngine) ← **#16 Miller**, **#21 Fabozzi/Focardi** (stochastic models for counterfactuals), **#25 Hilpisch AI** (ML scenario generators)
- `validators` (Council: Reality / Constraint) ← **#15 GARP** (risk taxonomy), **#24 CFA QIA + #27 Wooldridge** (statistical rigor for backtests), **#10 Fabozzi & Drake** (asset-pricing reality checks)
- `failure-ledger` (Kintsugi, Axiom 2.3) ← **#7 Aziz** (overtrading / revenge-trading patterns), **#8/#9 Norman** (custody/exchange/ICO failure modes), **#22 Allen** (credit & derivative failure modes), **#17 Antonopoulos** (consensus/orphan/protocol failure modes)
- `InfrastructureManager` (Calibrator / MissionPolicy) ← **#14 Hilpisch PyFin + #23 Chatterjee** (quant implementation patterns), **#17 Antonopoulos** (blockchain as infrastructure)
- `Strategy Lab` (future) ← **#13 Murphy TA, #19 Nison** (charting), **#20 Brooks** (price-action discipline counterpoint)

## Footprint estimate (if all 23 remaining books were acquired)
- Tier 1 (7 books): ≈ 2,550 pages
- Tier 2 (9 books): ≈ 3,900 pages
- Tier 3 (7 books): ≈ 4,090 pages
- **Total: ≈ 10,500 pages across 23 books** (two page counts are estimates — flagged above).
- Reading-time context: ~10.5K pages ≈ 260–350 hrs of deliberate technical reading (a size check, not a plan).
- Rough cost: ≈ $700–$1,100 if all bought new at list; the [acquire-now] pair is ~$50; most [acquire-later] titles are <$60; several have free or lending channels noted above.
