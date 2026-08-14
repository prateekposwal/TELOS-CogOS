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
