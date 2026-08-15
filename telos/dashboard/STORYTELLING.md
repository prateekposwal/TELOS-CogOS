# Data Storytelling Playbook — TELOS Live Dashboard

> Written 2026-08-14 as the learning artifact for the "learn these first" assignment.
> Derivation: this playbook is distilled from two Juice Analytics articles by
> Zach Gemignani (fetched this session, links below), then honestly audited
> against the CURRENT dashboard, then applied. It is not a generic summary —
> every principle below is mapped to a concrete TELOS dashboard decision.

## Sources (fetched 2026-08-14, with honesty)

1. **"15 Best Data Storytelling Tools"** — https://www.juiceanalytics.com/writing/best-data-storytelling-solutions
   (primary article; the 5-category taxonomy + the definition of data storytelling)
2. **"Six Essential Features for a Data Storytelling Solution"** — the live URL 404'd twice
   (https://www.juiceanalytics.com/writing/six-essential-features-for-a-data-storytelling-solution and
   an /insights/ variant). Retrieved from the Wayback Machine capture of 2019-11-12
   (https://web.archive.org/web/20191112043646/…same path) — 31 captures exist; the article is by the
   same author, July 14, 2017, and is the exact piece the primary article links to
   ("It emphasizes features such as…").
3. **"20 Best Storytelling Examples"** — https://www.juiceanalytics.com/writing/20-best-data-storytelling-examples
   (the assignment's stated fallback; used for example-driven principles)

### The article's core definition (what we are building toward)

> "Data storytelling is quickly becoming a popular mode for presenting data. It combines text and
> graphics with data visualizations to guide an audience." — 15 Best Data Storytelling Tools

> "Traditional dashboards are good at showing a full-status picture all at once. Visual analytics
> tools are great for flexible exploration. But neither of those solutions were designed to tell
> stories with data. Data storytelling is a new model for communicating information to an audience
> using narrative flow, text, and visuals to engage, educate, and move people to action.
> In this new era where the audience needs to come first, the priorities are different."
> — Six Essential Features (Wayback capture)

The key distinction: **a dashboard shows status; a data story guides.** The audience
needs to come first — not the data's completeness.

---

## (a) The taxonomy — 5 categories, and what each optimizes for

The article evaluated tools that "resemble[d] the description above" — explicitly **leaving out**
"more technical tools, visualization libraries, and old-school dashboard/report tools."
That exclusion is itself a principle: our page must not *feel* like a BI report.

| Category | Tools surveyed | What it optimizes for | The lesson for TELOS |
|---|---|---|---|
| **Guided Analytics** | Juicebox, Toucan Toco, Nugit, Flow Immersive | Exploratory visualization **combined with explanatory text**; "intended as an alternative to traditional dashboards and reports"; easy authoring; automatically connected visualizations | This is our target category. The story strip + live graphs, with captions, guidance, and connected visuals. |
| **Stand-alone Visualization** | Flourish, RAWGraphs, Datawrapper | Beautifully-designed individual charts meant to be **embedded in a webpage/article** | Each graph panel must work as a self-contained piece of evidence with its own caption. |
| **Data Storytelling as a Feature** | Tableau Story Points, ArcGIS StoryMaps, Qlik Sense Stories, PowerBI, Observable | Storytelling bolted onto a big BI/analytics platform; "provides guidance, features, and instruction… **without providing a focused solution**"; Tableau's Story Points "has not achieved wide-adoption" | The warning: a story feature that is a side-tab of a BI platform gets ignored. Our story must lead the page, not hide behind a tab. |
| **Design over Data** | Infogram, Visme, Piktochart | Infographics/templates; "The data is one of many media elements"; charts "show a few data points **rather than to enable analysis**"; for Piktochart, "Data seems to be mostly an afterthought for a solution that focuses on brand, styling, and templates" | The warning: decoration (animated borders, pop animations) must never bury or outshine the numbers. Data first; decoration serves it. |
| **Stories with Words** | SiSense Narratives, ChatGPT, Phrazor, Luminoso | **NLG**: algorithms identify insights and present them "in sentences and bullet points" — words carry the story when charts can't | The opportunity: when the graph is overwhelming (2000+ edges), a computed insight sentence guides the eye. Our insight line is this category, derived from real numbers. |

**Where we sit:** TELOS is a **Guided Analytics** product (live exploratory viz + explanatory
narrative), borrowing the **Stories with Words** trick for its insight line, and must avoid the
**Design over Data** failure mode and the **Feature-in-a-BI-tool** failure mode.

---

## (b) The six essential features — adapted from "report" to "live system dashboard"

The six-features article frames them for report-style apps. Each row re-derives it for a
*continuously-running live system dashboard* (which is what we have: a producer running the real
pipeline every ~2s).

| # | Essential feature (article) | As the article says | Adapted to a LIVE system dashboard |
|---|---|---|---|
| 1 | **Human-friendly visualizations** | "Your audience should be able to easily understand your data presentation **the first time they see it**. Using common language and clear images is key." | Every number uses plain labels (decisions, lessons, domains) — no pipeline jargon in the story. First-time comprehension is the test: a visitor who has never seen TELOS should understand the page in one glance. |
| 2 | **Integration of text and visuals** | "Data stories are a combination of data visuals flowing together with thoughtful prose… **set the stage, then give context and add detail**." | Every stat box gets a one-line caption saying *why it matters*. Every graph panel gets a caption saying *what to look at*. Text first sets the stage (hook), then the graphs add detail (evidence). |
| 3 | **Narrative flow** | "The text and visuals should carry your audience from a starting point (often the **big picture**) to the **insights or outcomes that will influence decisions**. Every user selection helps craft a relevant story." | The page must run hook → context → evidence → insight → action. The insight line must say what the data MEANS (DI trend, dominant domain, growth), not just restate it. |
| 4 | **Connected stories** | "It takes more than one data story to tell the whole story. Think of exploring your data as a **'Choose Your Own Adventure'** book, in which the audience can pick a path at the end of each section." | Domain chips in the story become clickable paths into the knowledge graph (click "identity" → the KG highlights identity nodes). One story, many entry points. |
| 5 | **Saving your place** | "Let the audience save the point they've arrived at… come back to the analysis over time and share it." | For a live system dashboard, place-saving collapses to: the page URL is a stable, shareable snapshot of the *system* (bookmark it, come back any time, the story resumes). Deep-linkable state is out of scope and noted honestly as LEFT. |
| 6 | **Effortless sharing** | "Data stories are often a social exercise… easy way to share their insights, discuss what they've found, and decide on actions together." | The dashboard is already served on a LAN URL (port 8765) — sharing = sending the link. The chat command box is the collaboration surface: the audience doesn't just read TELOS's story, they can act on it. |

---

## (c) Concrete principles for OUR dashboard

### P1 — The narrative arc: hook → context → evidence → insight → action
The article's definition ends with "move people to action." Five beats, one page:

1. **Hook** — what is TELOS doing RIGHT NOW (mood + last intent + position + live badge).
   The examples support this: *We Feel Fine* hooks with a live feed ("searches the internet every
   10 minutes"); Periscopic's gun-deaths piece is "a masterclass in… gradually revealing the data."
2. **Context** — what has it been through (decisions, lessons, world states, domains) — the
   accumulation that makes the current moment meaningful. *Wine & Math* "does an excellent job of
   setting the context… before diving into the results."
3. **Evidence** — the graphs, each captioned so it reads as evidence for the story, not decoration.
4. **Insight** — what the data means: DI trend, most active domain, growth signal. This is the
   "stories with words" feature — *SiSense Narratives* "automatically present[s]… insights in plain,
   easy to understand language based on what the engine recognizes as interesting."
5. **Action** — the invitation: "Direct TELOS" (chat box). The story must end facing forward.

### P2 — Balance explanatory text with exploratory graphics
The primary article: traditional tools "are limited in their ability to balance the **explanatory**
and **exploratory** elements of an effective data story." The strip explains (words, hierarchy,
insight); the graph wall explores (zoom, pan, pause, 3 modes, fullscreen). Each must keep its job:
don't turn the strip into a graph, don't turn the graphs into wallpaper.

### P3 — A story that updates live
The producer pushes a fresh overview every cycle over WebSocket and the page polls `/api/overview`.
The narrative must be a function of *runtime state*, so the story visibly evolves:
- DI dropped → the hook says TELOS is being cautious this cycle (honest: it is).
- lessons/edges grew since the last poll → the insight says "TELOS is learning new domains."
- The hook's "right now" beat changes every cycle (last intent, position, mood).
The same words may repeat across cycles — that's fine; a live story is a continuous broadcast,
not a one-time article. What must never happen is the *opposite*: words that claim things the
numbers don't show.

### P4 — Avoid the dashboard-dump anti-pattern
"Everything visible = nothing explained." The article's own exclusion criterion ("old-school
dashboard/report tools") names the anti-pattern: 8 equal-weight numbers, no hierarchy, no captions,
no guidance. Structural rules that prevent it:
- **One hero number per story section** (not N equal stats). Hierarchy IS explanation.
- **Every metric must carry a caption** that says why it matters in one sentence.
- **The page must open with a narrative hook and end with an action** — never start with stats and
  just stop.

### P5 — Design over Data: decoration must not bury the numbers
The category's critique of Piktochart: "Data seems to be mostly an afterthought for a solution that
focuses on brand, styling, and templates." Rules:
- Animation/glow must be *signal* (live badge breathing, a node appearing), never noise
  (every number flashing on every poll).
- No hard-coded hex in components; the token system stays the single source of color.
- Honest empty states beat pretty placeholders — a blank "no knowledge yet" with a reason.

### P6 — Stories with Words: narrative can carry insight when viz can't
The KG at live runtime holds 2000+ edges — no human reads that as a picture; it reads as noise.
The "stories with words" category exists precisely for this: *a sentence computed from the data*
("identity dominates the graph at 65/76 lessons — TELOS has been learning about itself") guides the
eye to what the viz cannot show alone. Words are not a substitute for honest numbers — they are a
*derived* reading of those numbers, and must be re-derived every poll, never hardcoded.

### P7 — Human-friendly, common language
"Common language and clear images." In the story: "decisions", "lessons", "domains" — not
"cycles", "knowledge nodes", "domain_facts". Jargon belongs in the side panels (the explorer
surface), not the story (the explanatory surface).

---

## AUDIT — the CURRENT dashboard vs the article's lens

Audited against the live dashboard at `main @ d61e7bd` (producer running, 457+ cycles,
76 lessons, 2093 edges, mood "confident" from real SystemSelf).

### What it does WELL (per the article)

| # | Strength | Evidence |
|---|---|---|
| W1 | **It is a genuine text+visual hybrid, not a pure stats page** | A headline sentence + mood sentence + chips sit above the live graph wall. That's the "combination of data visuals flowing together with thoughtful prose" the six-features article asks for — more than most dashboards attempt. |
| W2 | **It already leads with a live-data hook** | The story strip is above the fold, before the graphs, not hidden behind a tab ("Data Storytelling as a Feature" warning avoided). |
| W3 | **Honesty is structural** | Every number is measured runtime data; the anti-fabrication tests are load-bearing. The article's "audience first" ethos aligns with "never invent a number to make the story better." |
| W4 | **Plain labels** | "decisions", "domains", "lessons", "world states" — common language, no pipeline jargon. |
| W5 | **Live badge + WS push** | The ● live · N cycles badge and per-cycle push are a real-time *broadcast* — closer to "We Feel Fine" than to a static report. |

### What it does POORLY (per the article)

| # | Weakness | Pattern name | Evidence (from the live payload) |
|---|---|---|---|
| X1 | **8 equal-weight numbers = dashboard dump** | **stat-dump vs narrative structure** | `story-stats` renders decisions, domains, lessons, world states, worlds simulated, DI, MD, graph nodes/edges — all identical size, no hero, no caption. Exactly the "full-status picture all at once" the article says traditional dashboards do and data stories exist to replace. |
| X2 | **No hook — the headline is a flat recount** | stat-dump vs narrative structure | "TELOS has made 457 decisions across 5 domains, learned 76 lessons, explored 10 world-states." That's a *summary*, not a hook. Nothing says what TELOS is doing RIGHT NOW (last intent, position, mood at a glance) — the live beat that makes the page feel alive. |
| X3 | **No insight layer — numbers displayed, not interpreted** | stat-dump vs narrative structure | DI=100%, MD=0.00, identity=65/76 nodes, identity_affinity=2030/2093 edges — and the page says nothing about what any of it means. The "stories with words" capability (a sentence computed from the data) is unused. The edge-type chips literally dump "identity_affinity 2030" with no gloss. |
| X4 | **Graphs not guided** | un-captioned evidence | Panel titles are bare ("🧠 Cognitive Visualization", "🗺️ GridWorld — 3D Isometric", "🧠 Knowledge Graph") — no caption, no "what to look at". First-time comprehension (feature #1) fails: a visitor sees 3 canvases + 3 KG modes + isometric 3D and no guidance. |
| X5 | **The mood sentence implies a fake time-frame** | honesty-adjacent copy | "Today TELOS feels confident…" — "Today" is false for a live run (457 cycles over the producer's lifetime, not a day). Small, but it violates the article's "common language" (and our own honesty rule): the copy should describe the live *now*, not invent a calendar day. |
| X6 | **The story doesn't know it is identity-heavy** | missing insight | 2030/2093 edges are identity_affinity — the graph is *about TELOS learning about itself* — and the story is silent. The most interesting real fact in the data goes unremarked because nobody computed it. |
| X7 | **No action beat** | missing narrative flow | The strip ends at the mood line. The article's definition ends with "move people to action"; the chat box exists but nothing in the story points to it. |
| X8 | **Mild design-over-data drift** | decoration as noise | `countPop` flashes accent color on *every* number change every 5s poll — animation that says nothing. The animated story-strip gradient border is decoration; acceptable, but the pop-flash is signal-free motion. |

### Root-cause pattern
Everything in X1–X3, X6, X7 is ONE pattern:

> **stat-dump vs narrative structure — data displayed but not explained or guided.**
> The page presents measured truth (good) as an unranked list (bad): no hierarchy, no captions,
> no hook, no interpretation, no action.

### Structural rule that now prevents it (this pass)
> **The page must open with a narrative hook and end with an action; every major metric must
> carry a one-sentence caption explaining why it matters; the story must include one insight
> sentence re-computed from live data every poll; graphs must carry a one-line "what to look at"
> caption; and the story must lead to the chat command box as the action surface.**

---

## What the audit supports — the application plan (this session)

1. **Story strip restructure** (dashboard.html + story.js + dashboard.css):
   hook headline → hero number (decisions) with caption → supporting stats each with a caption →
   insight line (computed from real data) → clickable domain chips → edge chips → recent decisions →
   mood reflection (honest "right now" wording) → action row pointing to chat.
2. **State-aware narrative** (story.js, all derived from the real payload):
   DI-dropped → "TELOS is being cautious this cycle"; graph growth between polls → "TELOS is
   learning new domains"; identity share → insight sentence; most-active domain → named.
3. **Graph captions** (dashboard.html): one-sentence "what to look at" under each graph-wall title.
4. **Connected stories** (knowledge-graph.js + story.js): clicking a domain chip highlights that
   domain in the KG canvases (Choose-Your-Own-Adventure, small scale); click again to clear.
5. **Design discipline**: no new inline styles (existing chip color pattern is grandfathered),
   token system intact, DOM contract preserved (all existing ids stay), honest empty states stay.
6. **Honest fallback** (serve_dashboard.py): the no-producer path derives `worlds_simulated` from
   real trace values and reads mood from the persisted system_self file instead of hardcoding
   "neutral" — every number still measured, none invented.
7. **countPop**: keep the animation (it is a genuine value-change signal for *some* numbers) but
   stop flashing every number on every poll — pop only on actual change, which it already does;
   the deeper fix is hierarchy (hero moves, supporting numbers don't all pop equally).

---

## System Score decision (2026-08-14) — bounded composite replaces the timer

**Pattern fixed:** *cumulative drain metric displayed as an unbounded quality
score* — `score = 100 − cycles + rewards` subtracted an unbounded counter (a
timer) from a fixed constant, so the headline number was monotonically
decreasing forever (-271 after 371 cycles). The breakdown caption made it
*legible*; it was never *good*.

**Structural rule (now enforced):**
> Display metrics that measure QUALITY must be bounded — the range is part of
> the metric's definition and enforced at the API boundary (out-of-range
> values are rejected as invalid format, never displayed) — and derived only
> from measured signals. Endurance facts (cycles elapsed, run length) are
> labeled as endurance readouts and are NEVER folded into a quality score.

**Chosen metric (producer.py `system_score()`):**
```
SystemScore = 100 · clamp01( 0.50·DI + 0.25·(1 − min(1, MD/5))
                           + 0.15·min(1, rewards/20)
                           + 0.10·min(1, cells_visited/25) )
```
- Bounded [0, 100] by construction; every component is a real measured
  signal (DecisionTrace DI/MD, reward pool secured, grid coverage). Perfect
  state = 100; no state can fall below 0.
- Time is NOT a component — cycles elapsed is a separate endurance readout.
- DI dominates (0.50) per Axiom 1.2: process over outcomes.
- The sidebar caption is derived from `score_components` (the exact inputs
  the producer used), so the number is always explainable and never
  invented. Legacy unbounded trace scores are structurally rejected by
  `safe_score()` rather than displayed.

## Episode efficiency decision (2026-08-14, v7-refined 2026-08-15) — real cycles-per-goal + moves-per-goal split, ZERO sim mutation

**Pattern fixed:** *rejected idea justified by a partially-true blocker* — a
LEFT item said "episode-based scoring rejected — would require mutating shared
sim state for a display metric; the composite already captures the efficiency
signal." Re-examination found the blocker real only for the NAIVE design
(restoring sim.rewards at episode reset would make `GridSim.get_facts` /
`evaluate` — which read sim.rewards into decision-relevant DomainFacts — see
respawned rewards TELOS already collected: fake infinite score), while the
conclusion was wrong on both counts: a mutation-free path existed, and the
composite (DI/MD/reward/coverage) never measured pace.

**Chosen metric (producer.py, separate labeled stat cluster — NOT a System
Score component):**
```
episodes.completed            # goal-reaches observed (real events)
episode_steps                 # decision-cycles in the current episode (ALL cycles)
episode_moves                 # position-changing moves only (blocked/no-op/inquiry excluded)
avg_steps_per_goal            # mean of completed episodes (None until ≥1) — hero label: CYCLES per goal
avg_moves_per_goal            # mean of position-changing moves (v7 split) — hero label: MOVES per goal
efficiency_vs_optimal         # clamp01(8 / avg_cycles) — bounded [0,1] when defined
moves_efficiency_vs_optimal   # clamp01(8 / avg_moves)
```
- ZERO sim mutation: pure producer bookkeeping on `terminal()` → reset — the
  event the producer already observes. The reward dict is never touched.
- Separate stat, not a component: cycles-per-goal is cycle-derived (each cycle
  is one decision cycle incl. blocked/inquiry pauses) — endurance-adjacent,
  and the structural rule forbids folding endurance facts into a quality
  score. Also undefined until the first episode completes; a folded phantom
  0/0.5 would be an invented number.
- v7 split (2026-08-15): the hero now shows BOTH — "cycles per goal" (counts
  every decision cycle incl. blocked & inquiry pauses) and "moves per goal"
  (blocked/no-op/inquiry excluded, i.e. real position changes). The split
  answers "how expensive was the episode" vs "how direct was the path" from
  the same real episode events. Honest '—' until the first episode completes.
- Shadow-reward path rejected with evidence: after episode 1 the world is
  exhausted, so per-episode reward vs a shadow pool measures world depletion,
  not agent efficiency; `reward_fraction` already carries the honest depletion
  signal.

**Structural rule (now enforced):**
> Before rejecting a metric, enumerate mutation-free measurement paths on
> events the system already observes. Distinguish "the naive implementation is
> unsafe" from "the metric is impossible". If the metric is a pace readout
> (cycle-derived, undefined until its first event), present it as a separate
> labeled stat with an honest empty state — never fold it into a quality score,
> and never invent a fill-in value.


---

## v3 addendum (2026-08-15) — from "story strip on a BI dashboard" to "the page IS the story"

Owner direction: v2's story strip was a story *feature on a tool*; the ask is BIG DATA
STORYTELLING in the spirit of https://wc26.bogachev.fr and https://meteo.ashwyn.studio.
Full codified spec: `telos/dashboard/BIGDATA_BRIEF.md`. What changed and why it stays honest:

### What the v3 redesign did
1. **The page is now one scroll narrative.** Hero ("Cognitive Data / Portraits") → chapters
   01 The Signal → 02 The World · The Scanned Perimeter → 03 The Memory · The Canopy →
   04 The Memory · Orbital Ecology → 05 The Memory · Nebula Clusters → 06 The Mind ·
   Activation Aurora → 07 The Mind · Synapse Rhizome → 08 The Story So Far
   (v5, 2026-08-15: every mode is an ORIGINAL data-portrait — real edges drawn in all
   three memory modes, stream activations + DI growth rings + real cognition mode in
   the mind modes; the isometric grid renderer, the fake timer-driven active phase,
   and the rainbow palette are gone. All ids + the one-mode-per-section structure are
   unchanged.) → deep-dive. Chapter markers (ghost numerals + hairline)
   replace the tab bar; the sidebar became a slide-in system drawer. The narrative arc of
   P1 (hook → context → evidence → insight → action) now spans the whole page instead of
   one box: hero = hook+context, chapters = evidence (each captioned "what to look at"),
   chapter 08 = insight, chat = action.
   **v4 (2026-08-15): one mode per section.** Each knowledge-graph mode and each mind mode
   is its OWN full-width chapter in the GRIDWORLD pattern (ghost numeral + hairline +
   panel + caption + pull-quote) — the three memory modes and two mind modes never share
   a panel, and the memory timeline in the deep-dive is a compact panel matching the chat
   panel (same 240px scroll footprint), not a tall page section.
   **v4 explicit-structure record (2026-08-15, user-approved):** the five chapter sections remain EXPLICIT hand-written HTML (`kg-panel-tree`/`-solar`/`-bubble`, `brain-panel-orbit`/`-tree`) — a template/factory abstraction is deliberately NOT used, so the DOM-contract tests gate literal, statically readable markup. **v5 record:** the same five explicit sections now host the v5 original modes (Canopy/Orbital Ecology/Nebula Clusters, Activation Aurora/Synapse Rhizome) — same ids, same structure, new honest renderers.
2. **The hero is a data canvas.** `#hero-backdrop` draws the REAL DI/MD history as a glowing
   pulse waveform (the wc26 momentum-pulse idea, honest: it IS the measured series). The
   title's second line is dyed with REAL knowledge-domain colors. The hero lede repeats the
   project's opening claim in the references' spirit: *"Cognitive Data — measured live, never
   invented."*
3. **Pull-quotes are computed evidence.** Chapters 01–04 carry a quote derived every poll from
   real fields: latest decision (cycle/intent/DI/verdict), live position + episode efficiency,
   graph composition + leading domain, top stream activation. These are the "Stories with
   Words" layer (P6) at chapter scale.
4. **P5 (design-over-data) re-checked.** The cinematic layers (backdrop, dye, ghost numerals,
   reveals) are all *mapped to data* — the backdrop is the DI/MD series, the dye is the domain
   palette, the quotes are the decision log. Decoration that carries no data (the old animated
   gradient strip) was removed. The anti-noise rule (P5: animation must be signal) still holds:
   exactly one pulsing endpoint per canvas.
5. **P7 (common language) preserved.** The hero/chapters speak in "decisions, lessons, world
   states, futures" — jargon ("cycles", "stream_activations", "domain_facts") stays in the
   drawer and the code, never the narrative.

### Honesty invariants carried over (unchanged, still enforced)
- Every number renders from `/api/overview`, `/api/checkpoints`, `/api/knowledge` or the
  real series they feed. No Math.random for data, no demo traces, no invented insight.
- Empty states are honest and specific ("awaiting the first decision cycle…").
- The System Score stays a bounded 0–100 composite; endurance facts stay labeled as such.
- The DOM-contract tests now gate the narrative structure itself (chapters, quotes, backdrop)
  plus the overlap/visibility contract in a real browser at 1440×900.

---

## v6/v7 addendum (2026-08-15) — performance & UX pass (Items 6–8) + hero-stat honesty

### Structural changes (frontend brief)
1. **three.js is lazy-loaded** (`dashboard/js/lazy-3d.js`, new). The ~600 KB
   vendor chain (three.min.js → OrbitControls.js → knowledge-3d.js) is no
   longer eager `<script>` tags: an IntersectionObserver on `#kg-panel-bubble`
   (chapter 05) with a 900px preload margin injects the chain in strict order
   when the nebula approaches the viewport. Initial paint never waits on the
   600 KB file. The DOM-contract load-order test was deliberately updated to
   assert the loader's chain order instead of HTML tag order. Vendored-only,
   still no CDN, still the same honest 2D fallback if THREE/WebGL is missing.
2. **gzip + cache headers** (serve_dashboard.py). Static assets are gzipped
   when the client asks (`Content-Encoding: gzip` + `Vary: Accept-Encoding`);
   `/dashboard/vendor/*` is `public, max-age=31536000, immutable`; `/dashboard/*`
   is `public, max-age=3600`; the HTML shell + API stay no-cache. The
   WebSocket endpoint (port 8766) and every `/api/*` endpoint are untouched.
3. **Nebula hint pill** (`#kg3d-hint`, chapter 05). "drag to orbit · scroll to
   zoom · click a star" — bottom-center chip, `pointer-events:none`, 13px mono
   floor, fades on first pointerdown or after 6s (wired before the WebGL gates
   so the 2D fallback dismisses it too).
4. **Chapter scrollspy mini-nav** (`#mini-nav` + `dashboard/js/scrollspy.js`,
   new). Fixed right rail of the nine story stops (01–08 + DD), current chapter
   highlighted via IntersectionObserver band + `aria-current="true"`, native
   anchor click-to-scroll (scroll-margin-top 72px; reduced-motion = instant).
   Visible ≥1280px where it cannot overlap the 1200px narrative column.
5. **Mobile pass.** ≤768px the memory/mind panel zoom/pause/fullscreen buttons
   are ≥44×44px touch targets; the 3D canvas renders at 375px (verified with a
   real-pixel browser probe at 375×812).

### Hero-stat honesty (v7, data-side)
- "futures imagined" → **"worlds simulated"** with a per-decision caption
  (`#story-worlds-sim-caption`): cumulative counterfactual rollout states
  divided by real decisions — both measured totals, never a constant.
- "steps per goal" → **"cycles per goal"** (counts every decision cycle incl.
  blocked & inquiry pauses) + new **"moves per goal"** stat
  (`#story-moves-per-goal`: blocked/no-op/inquiry excluded). Both render '—'
  until the first episode completes — never a fabricated number.
- The DECISIONS caption names the REAL gate that held the latest decision
  back (`firewall_blocked_by` / council `blocking_validator`): "was held back
  by …", measured from the live trace.
- The LESSONS caption names the real knowledge-graph source: "live
  knowledge-graph nodes …", tracked from real KG archival over time.
