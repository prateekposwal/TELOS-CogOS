# TELOS — Big Data Storytelling Dashboard · Design Brief (v3, 2026-08-15)

> Direction from the owner: the v2 redesign was "better and more visible than the old
> fashion, but not what I'm looking for." References: **https://meteo.ashwyn.studio** and
> **https://wc26.bogachev.fr/m/spa-arg/** (main index: https://wc26.bogachev.fr/index.html).
> Ask: BIG DATA STORYTELLING — more advanced, more visualization.

---

## 1 · What the references teach (studied 2026-08-15)

### 1.1 meteo.ashwyn.studio — what was captured, honestly
- **Captured:** raw HTML (minified, JS-injected React/Three.js shell), the declared fonts
  (`Cormorant Garamond` 600/700 display serif + `Nunito` 400–800 sans from Google Fonts),
  the brand gradient palette embedded in the favicon SVG: teal→cyan→gold
  (`#70d0d0 → #328898 → #70c8c8 → #e7d878 → #b89850`, plus `#00bba3/#14a59e/#14b8a6/#41c0c1/#a67c52/#ffc05f`),
  and a 3rem/0.85rem/0.9rem type scale in the tiny inline CSS.
- **Could NOT capture:** the layout, hero, section flow, or motion — the page is a JS app
  shell (354 DOM tags are the React mount + inline loader); all real styling is injected at
  runtime. Conclusion drawn from what IS visible: a full-viewport 3D WebGL visualization of
  meteo history where **the data is the artwork** — no chrome, no cards, no toolbars.
- **Lesson taken:** immersive full-viewport data-canvas; serif/grotesk editorial pairing;
  a narrow data-derived color language (teal = temperature, gold = pressure) instead of a
  rainbow.

### 1.2 wc26.bogachev.fr — what was captured
The index page and the SPA–ARG match portrait both returned full HTML + inline CSS (self-hosted
fonts, vendored three.js, real data in `matches.json`). This is the *primary* reference for the
TELOS redesign — it is literally a "living data-portrait" built from real recorded events.

**Codified spec:**

| Axis | wc26 rule | Concrete values observed |
|---|---|---|
| **Typography** | Space Grotesk (UI/labels) + Space Mono (every number, tabular-nums); uppercase micro-labels with wide tracking; big display with tight `letter-spacing:-.02em` | title `clamp(32px,7.4vw,108px)` weight 600 `ls:-.028em`; hero stat numbers `clamp(34px,4vw,52px)` mono 700 `ls:-.02em`; stat labels 11px mono `ls:.24em` uppercase; section index numerals `clamp(30px,4.2vw,58px)` mono; score 116px mono 700; HUD labels 10.5px `ls:.16em` uppercase |
| **Color** | deep indigo-violet night, one periwinkle accent, color = data meaning | `--bg:#17102e`, `--ink:#f1eff8`, `--ink-2:#cfcbe4`, `--dim:#8f89ad`, `--faint:#5b5686`, `--fainter:#2b2550`, `--accent:#6f8cff`, `--accent-2:#a9b8ff`; team rails carry real kit colors |
| **Hero** | full-viewport generative WebGL "quilt" — one patch per real match, colored by real team kits, lifted by real shots+goals; radial+linear masks dissolve edges; scrim keeps type crisp; editorial eyebrow (tick + mono uppercase + letter-spacing .28em); two-line title: solid line + data-dyed line | `.hero-bg { position:absolute; width:100vw; mask-image: radial+linear }`; `.hero-scrim` radial gradients; title `.l1` solid white + `.l2 .ch` per-letter REAL team colors |
| **Layout** | centered ~1340px content column; full-bleed backdrop; sections opened by editorial markers (ghost index numeral + phase name + count + hairline); NO plates — cards float "in the air" (no bg/border/radius/shadow); hover lifts `translateY(-6px)` | `.phase { grid-template-columns:auto 1fr auto; border-bottom:1px solid var(--fainter) }`; `.card:hover{ transform:translateY(-6px) }` |
| **Data viz** | 3D isometric pitch with territory blankets; bottom momentum pulse (seismograph strip); score tinting the whole sky dome; xG peak labels; post-match split mini-bar comparisons | `#stage` full-viewport WebGL; `#pulse` bottom strip `width:78%;height:120px`; `.mstats .mbar` 5px split bars |
| **Motion** | restrained: load reveal (fade + 16px rise, .6s), hover lifts, WebGL cloth "breathing", timeline scrub; `prefers-reduced-motion` kills all of it | `.reveal{opacity:0;transform:translateY(16px)} .reveal.in{...transition:.6s cubic-bezier(.2,.7,.2,1)}`; `@media (prefers-reduced-motion:reduce){ transition:none !important }` |
| **Storytelling** | the hero page literally says it: *"Nothing is staged: each match is reconstructed from roughly 1,500 recorded events"* — the claim of honesty is the opening move; every color/peak/title-letter maps to real data; one big number (matches) + lede + legend on one restrained line | `.lede b{font-weight:600}` bolded claim; `.hero-meta .stat .n` big mono; `.legend` mono 11.5px one line |

### 1.3 The principles → TELOS rules
1. **Data IS the artwork** — the canvas layer is the first thing you see, and every pixel of it
   is derived from real series (DI/MD history), not decoration.
2. **Numbers are heroes** — huge mono numerals (tabular), not 28px cards.
3. **Editorial scroll narrative** — numbered chapters with ghost numerals + hairlines; a page
   you read, not a grid you scan.
4. **No plates** — content floats on the night; hairlines and type do the separating.
5. **Color carries meaning** — periwinkle accent + semantic data colors, nothing rainbow.
6. **Restrained motion** — reveals, breathing canvas, endpoint pulses; reduced-motion kills all.
7. **Honesty is the aesthetic** — the hero says "measured live, never invented"; empty states
   are honest, never padded (inherits v2's anti-fabrication contract).

---

## 2 · Audit — current v2 state vs this spec

**Current design (v2):** 280px BI sidebar (metric cards) + sticky toolbar + tab bar
(All/Brain/Grid/Chart/Knowledge/Memory/Chat) + `story-strip` hero card (headline, one hero
number, 4 stat boxes, insight line, chips, mood, action) + `graph-wall` of boxed panels
(brain 2-canvas, grid isometric, DI/MD line chart, KG 3-canvas) + memory/log/chat panels.

**Why it fails the brief:**
- **Reads as a tool, not a story.** Sidebar-of-cards + tabs + boxed panels = BI console
  (STORYTELLING.md's own "Feature-in-a-BI-tool" failure mode). References have zero chrome.
- **Charts are conventional.** Small 300px line chart, boxed panels, uppercase 14px titles.
- **No cinematic hero.** The "hero" is a bordered card with a gradient bar; the references open
  with a full-viewport data canvas + editorial type.
- **No scroll narrative.** Everything sits on one screen; sections don't flow, reveal, or quote.
- **Plain grid, no chapter markers, no pull-quotes, no ghost numerals, no big mono numerics.**

**Data inventory — everything a narrative may truthfully use (Part 2):**
From `/api/overview` (+ WS `overview` pushes): `producer{running,cycles,last_cycle_at,last_error}`,
`decisions`, `domains{name:count}`, `lessons`, `edges`, `edge_types{type:count}`,
`world_states`, `worlds_simulated`, `di`, `md`, `mood`, `score` (0–100 bounded), `score_components{di,md,reward_fraction,world_coverage,weights,drift_threshold,grid_area}`,
`reward_collected`, `reward_available`, `position[x,y]`, `episodes{completed,current_steps,last_steps,avg_steps_per_goal,efficiency_vs_optimal,optimal_steps}`,
`recent_decisions[{cycle_id,intent,di,md,status,worlds,position,blocking_validator}]`, `knowledge{nodes,edges,domains,edge_types}`.
From `/api/checkpoints` (full traces, capped 100): `cycle_id, timestamp, decision_integrity,
mission_drift, council_validated, firewall_blocked, blocking_validator, world_state,
selected_intent, selected_action, strategic_options, stream_activations, council_signals,
domain_facts, worlds_simulated, inquiry_omega_vector, inquiry_blend, agent2_pos, agent2_reward,
score, terrain_changes, health_score, representation, escalation_requested, resource_budgets,
phase_durations_ms` — these feed the **real time-series** `diHistory/mdHistory/cycleLabels`
already maintained in `dashboard.js state`.
From `/api/knowledge`: `nodes[{id,label,domain,importance}]`, `edges[{source,target,weight,edge_type}]`.
From `/api/health`: `health, system_score, mission, cycles, decision_integrity, mission_drift,
mood, resources{c_compute,c_memory,c_bandwidth}`.
**No fabricated data anywhere: the design below maps every visual to one of these fields.**

---

## 3 · Information architecture (scroll narrative)

```
┌ HERO  #story-strip  (100vh)  — "Cognitive Data / Portraits"
│   eyebrow (TELOS · COGOS · live badge #story-live)
│   editorial two-line title — line 2 dyed with REAL domain colors
│   lede (#story-headline hook sentence) + subhead (#story-subhead)
│   hero-meta: giant decisions (#story-decisions) + 4 captioned stats
│     (#story-lessons / #story-worlds / #story-worlds-sim / #story-efficiency)
│   #hero-backdrop canvas: the REAL DI/MD history as a glowing pulse waveform
│   scroll cue
├ CHAPTER 01  "The Signal"      — decision quality
│   big mono DI% (#story-di) / MD (#story-md) beside the LARGE animated
│   time-series (#chart-canvas) · pull-quote from the real latest decision
├ CHAPTER 02  "The World"       — GridWorld terrain
│   #grid-canvas isometric + real position trail + terrain/reward readouts
│   pull-quote: real position/terrain/step
├ CHAPTER 03  "The Memory · Knowledge Tree" — #kg-tree (full-width section)
│   + real domain chips (#story-domain-chips, clickable → highlight) + edge chips
│   (#story-edge-chips) + nodes/edges counts · pull-quote: graph composition
├ CHAPTER 04  "The Memory · Solar System"  — #kg-solar (full-width section)
│   pull-quote: real domain composition (orbiting domains, densest ring)
├ CHAPTER 05  "The Memory · Bubble Map"    — #kg-bubble (full-width section)
│   pull-quote: real edge composition (strongest connection)
├ CHAPTER 06  "The Mind · Neural Orbit"    — #brain-orbit (full-width section)
│   real stream activations · pull-quote: top stream
├ CHAPTER 07  "The Mind · Root System"     — #brain-tree (full-width section)
│   real stream activations · pull-quote: top streams as canopy
├ CHAPTER 08  "The Story So Far" — narrative hub
│   insight sentence (#story-insight, computed from live numbers)
│   recent decisions (#story-recent) · mood (#story-mood) · action (#story-action)
└ DEEP-DIVE  — compact memory timeline (#memory-timeline, chat-sized panel) ·
  command chat (#chat-*) · log
```

v4 note (2026-08-15): one mode per section — the three KG modes and the two Mind modes
each occupy their own full-width chapter (GRIDWORLD pattern: ghost numeral + hairline +
panel + caption + pull-quote); no shared/stacked panels. The memory timeline is compact,
matching the chat panel.

Every section maps to a real field; the "pull-quotes" are computed from `recent_decisions`,
`position`, `episodes`, `knowledge`, and the latest `stream_activations` — never invented.

## 4 · Per-section data + viz + motion

| Section | Data (real) | Viz | Motion |
|---|---|---|---|
| Hero backdrop | `state.diHistory` / `state.mdHistory` / cycle count | glowing DI waveform above a mirror-MD waveform, hairline grid, live-head endpoint | waveform progressively reveals as data grows; endpoint pulses (reduced-motion: static frame) |
| 01 Signal | `diHistory`, `mdHistory` | dual-axis area/line chart, large (≥1000×360) | endpoint glow; reveal on scroll |
| 02 World | `world_state` chain, `terrain`, `rewards`, `agent2` | existing isometric 3D gridworld | existing breath/particles; reveal |
| 03–05 Memory modes | `/api/knowledge` nodes+edges, domains, edge types | ONE KG mode per full-width section (tree / solar / bubble) | existing orbit/forces; reveal |
| 06–07 Mind modes | latest `stream_activations` | ONE mode per full-width section (neural orbit / root system) | existing; reveal |
| 05 Story | overview-derived sentences | editorial prose + chips | reveal; live re-derivation every poll |
| Pull-quotes | `recent_decisions`, `position`, `episodes`, `knowledge`, `stream_activations` | large type quote + mono citation | reveal; re-derive every poll |

## 5 · Typography / Color / Layout / Interaction systems

- **Type:** `Space Grotesk` (self-hosted, weights 300–700) for UI/display; `Space Mono`
  (self-hosted 400/700) for EVERY number (`font-variant-numeric: tabular-nums`). Scale:
  `--text-display clamp(56px,9vw,140px)`, `--text-h1 clamp(34px,5vw,64px)`, `--text-h2 24px`,
  `--text-body 16px`, `--text-meta 14px`; floor **13px**; chapter index numerals mono 700
  ghost; micro-labels uppercase `ls:.2em`. (Same families as wc26; meteo's serif rejected —
  the grotesk+mono pairing fits a cognitive-data portrait better and self-hosts cleanly.)
- **Color:** wc26-inspired night: `--bg:#0d0a1a` `--elev:#13102a` `--elev2:#191534`
  `--elev3:#211b42` `--border:#221c44` `--text:#f1eff8` `--muted:#b7b2d6` `--dim:#8f89ad`
  `--accent:#7d97ff` (periwinkle) + semantic `success/warn/danger/info`; light theme keeps
  the v2-verified tokens. All three contrast gates (`ss-caption/panel-caption/metric-card .label`
  on their backgrounds) stay ≥4.5:1 in both themes.
- **Layout:** body scrolls; sticky minimal topbar (brand · live clock · Auto/Export/Theme);
  sidebar becomes a slide-in **system drawer** (all v2 ids preserved); hero 100vh; chapters
  max-width 1200px with ghost numerals + hairlines; panels go plate-less (hairline + radius,
  hover lift) — the `.main > * { flex-shrink:0 }` visibility contract stays.
- **Interaction:** scroll-reveal (IntersectionObserver → `.reveal.in`), live badge, clickable
  domain chips (existing KG highlight), chart hover shows the real last-cycle values,
  drawer opens system readouts on demand; reduced-motion renders everything static.

## 6 · File plan + test implications

| File | Action |
|---|---|
| `telos/dashboard/fonts/{fonts.css, space-grotesk.woff2, space-mono-400.woff2, space-mono-700.woff2}` | NEW — self-hosted type (no CDN) |
| `telos/dashboard.html` | REWRITE — hero + 5 chapters + deep-dive; every v2 id preserved |
| `telos/dashboard/css/dashboard.css` | REWRITE — editorial design system, tokens intact (same names), gates intact |
| `telos/dashboard/js/hero.js` | NEW — backdrop pulse canvas, title dye, pull-quotes, scroll reveal |
| `telos/dashboard/js/chart.js` | UPGRADE — larger cinematic render, real last-cycle readout |
| `telos/dashboard/js/story.js` | MINOR — expose overview for hero; wording stays derived |
| `telos/dashboard/js/dashboard.js` | MINOR — drawer toggle, topbar wiring; state/animate untouched |
| `tests/core/test_dashboard_dom_contract.py` | UPDATE — keep all gates; add hero-backdrop to canvas loop; extend browser probe with overlap + new-section asserts |
| `telos/dashboard/DESIGN.md` | REWRITE v3 rules (editorial system) |
| `telos/dashboard/STORYTELLING.md` | ADD v3 addendum (scroll-narrative shift, references) |

DOM contract: **every** `getElementById` target keeps its id; `graph-wall` class + the six
canvas ids + `story-strip` (no `data-section`) stay; no `display:none` inline inside `<main>`;
`onclick` handlers resolve to existing functions; The five mode chapters are explicit hand-written HTML by decision (2026-08-15, user-approved) — no template factory; ids stay literal for DOM-contract testability. `.main > * { flex-shrink:0 }`, type tokens,
13px floor, contrast gates, no-Math.random-in-chart all stay green.

## 7 · Verification plan
Full pytest suite green · headless Chromium at 1440×900 + 1920×1080: zero overlaps (paint-at
probe), zero console errors, story visible ≥400px, real data renders (non-zero decisions after
producer burst), contrast ≥4.5 · screenshots → `telos/dashboard/screenshots/dashboard_after.png`
(old preserved as `dashboard_old_v1.png`) · `git diff --stat` + `git status` (NO commit).
