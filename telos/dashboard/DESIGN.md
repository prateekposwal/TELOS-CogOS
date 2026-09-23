# TELOS Dashboard — Design Principles (v3, 2026-08-15 · "Cognitive Data Portraits")

Source of truth for any dashboard UI change. Read BEFORE editing markup or styles.
Violating these is a pattern regression, not a style preference.

v4 amendment (2026-08-15): one mode per section — each KG mode (tree/solar/bubble)
and each Mind mode (orbit/root) is a standalone full-width chapter in the GRIDWORLD
pattern; the memory timeline is a compact panel matching the chat panel.
**Decision record (2026-08-15, user-approved): the five mode chapters are EXPLICIT, hand-written HTML — Memory: `kg-panel-tree` / `kg-panel-solar` / `kg-panel-bubble`; Mind: `brain-panel-orbit` / `brain-panel-tree`. A JS/template factory is INTENTIONALLY NOT used. Repeated chapter-mark markup is deliberate: every section stays statically readable and every `getElementById` target stays a literal, greppable id, keeping the DOM-contract tests meaningful. Do not 'helpfully' refactor these into a factory. (Mirrored in STORYTELLING.md v4 note + BIGDATA_BRIEF.md DOM-contract para.)

v5 amendment (2026-08-15, "Out of the box — energy of wc26, originality of TELOS"):
the three evidence families are redesigned as ORIGINAL data-portraits, never
literal copies of the reference:
- **World (02) = The Scanned Perimeter** — a 2D cartographic sonar replacing the
  isometric game renderer: fog-of-war reveals only cells the REAL position has
  mapped/scanned, the trail is the real visited path with a traveling light
  pulse, reward flares spend down with the REAL reward_collected/available
  ratio, and the coverage ring's arc is the REAL world_coverage. The scan sweep
  angle is a data clock (golden-angle step per real cycle).
- **Memory (03–05) = The Canopy / Orbital Ecology / Nebula Clusters** — all
  three now draw the REAL edges as color-coded filaments (edge_type = meaning;
  sampled deterministically for performance, real total labeled). Tree → domain
  branches with real-thickness trunks and buds raised by real importance;
  Solar → domain orbital bands (width = real count) with bodies orbiting at
  real-importance speed; Bubble → layered nebula clouds (radius = real count)
  with constellation points sized by REAL degree. Layout is deterministic.
- **Mind (06–07) = Activation Aurora / Synapse Rhizome** — the fake
  timer-driven "active phase" and the rainbow are gone. Aurora: the sky is
  tinted by real DI, ribbons are the real stream_activations (width/brightness
  = measured priority), the ring carries the REAL meta_cognition.mode; phases
  are honest structure. Rhizome: trunk growth rings = real diHistory, roots =
  real streams grown to their measured mean priority, canopy tinted by real
  system mood. The fabricated core label and the static personal-name text are gone.
Honesty hardening in v5: ONE canonical domain palette (window._DOMAIN_COLORS_STORY
in story.js — knowledge-graph.js reads it, never defines a copy); real edges are
drawn (never isolated dots for a graph that has connections); phases are never
claimed active without real per-phase data. Enforced by tests
(test_v5_memory_modes_draw_real_edges_and_canonical_palette,
test_v5_mind_modes_real_signals_and_no_fabrication,
test_v5_world_is_scanned_perimeter_not_iso_game).

v6/v7 amendment (2026-08-15, "performance & UX pass" — Items 6–8 of the
frontend brief; mirror in STORYTELLING.md + BIGDATA_BRIEF.md):
- **Perf 1 — gzip + cache headers (serve_dashboard.py).** Static assets
  (.js/.css/.json/.html/.svg/.map/.txt/.xml) are gzipped when the client sends
  `Accept-Encoding: gzip` (`Content-Encoding: gzip` + `Vary: Accept-Encoding`);
  identity body otherwise (API/WebSocket endpoints untouched — `/api/*` keeps
  `no-cache, no-store, must-revalidate`, the WS lives on its own port).
  `Cache-Control` policy is explicit per class: `/dashboard/vendor/*` →
  `public, max-age=31536000, immutable` (three.js/OrbitControls never change);
  `/dashboard/*` → `public, max-age=3600`; the HTML shell + entry JS stay
  no-cache (they change every session). `If-Modified-Since` still answers 304.
- **Perf 2 — three.js is LAZY-LOADED (`lazy-3d.js`, new).** The ~600 KB vendor
  chain (three.min.js → OrbitControls.js → knowledge-3d.js) is NOT eager
  script tags. An IntersectionObserver on `#kg-panel-bubble` (chapter 05, the
  3D Memory Nebula) with a 900px preload margin injects the chain in strict
  order (chained onload + `async=false`) when the nebula approaches the
  viewport. Initial load is never blocked by the 600 KB file. Failure is
  honest: a failed vendor script logs (Λ2.3) and knowledge-3d.js's own
  `typeof THREE === 'undefined'` gate keeps the 2D nebula fallback. Exposed
  `window.__kg3dLazy` for probes. The DOM-contract load-order test now asserts
  the LOADER's chain order, not HTML tag order (deliberate test update).
- **UX — nebula hint pill (`#kg3d-hint`, chapter 05).** "drag to orbit · scroll
  to zoom · click a star" — bottom-center chip, design-system tokens, 13px
  mono floor, `pointer-events:none` (never intercepts orbit/drag), fades
  (`.fade` opacity transition) on first `pointerdown` or after 6s. Wired in
  knowledge-3d.js BEFORE the WebGL gates so the hint dismisses even when the
  2D fallback owns the canvas.
- **UX — chapter scrollspy mini-nav (`#mini-nav` + `scrollspy.js`, new).**
  Fixed right-rail listing the nine story stops (chapters 01–08 + DD), visible
  ≥1280px where the page margin is wide enough to never overlap the 1200px
  content column (labels appear ≥1600px). Native anchor click-to-scroll
  (scroll-margin-top 72px clears the sticky topbar; smooth scrolling is CSS,
  reduced-motion falls back to instant). Current chapter is highlighted by an
  IntersectionObserver band (`-30% 0px -60% 0px`) with `aria-current="true"`.
- **Mobile pass (Item 7b).** ≤768px: the memory/mind panel zoom/pause/
  fullscreen buttons grow to ≥44×44px touch targets (`.panel-controls .zoom-btn`
  min-width/min-height). The 3D canvas renders at 375px width (canvas 380px
  tall, renderer tracks clientWidth/clientHeight — verified in the browser
  probe with real pixel sampling).

## Direction (owner, 2026-08-15)
v2 was "better and more visible than the old fashion, but not what I'm looking for."
References studied: **meteo.ashwyn.studio** (data IS the artwork — full-viewport 3D canvas,
editorial serif+sans, narrow data-derived palette) and **wc26.bogachev.fr** (primary — a living
data-portrait: Space Grotesk + Space Mono, indigo night, ghost numerals, no plates, honest
claim first: "Nothing is staged"). Codified spec: `telos/dashboard/BIGDATA_BRIEF.md`.

## The 12 rules (v3)

0. **Visibility is a contract.** Every direct child of `.main` is `flex-shrink: 0`
   (`.main > * { flex-shrink: 0; }`). The column NEVER compresses a section; children scroll
   instead of shrinking. The DOM-contract browser probe asserts the story strip renders
   ≥400px at 1440×900 AND that every key element's center paints to itself (no overlap).
1. **8pt spacing scale.** All whitespace from `--space-1..8`. Never free-hand margins.
2. **One design system, two themes.** Tokens on `:root` / `body.theme-light`. NO hard-coded
   hex in components — canvas colors read tokens via `getComputedStyle` (see chart.js/hero.js).
   NO `!important` (reduced-motion block exempted by DESIGN.md rule 11's media query).
3. **Type scale, not type soup.** Fluid tokens: `--text-display clamp(56px,9vw,140px)`,
   `--text-h1 clamp(34px,5vw,64px)`, `--text-h2 24px`, `--text-body 16px`, `--text-meta 14px`.
   **13px absolute floor everywhere.** Space Grotesk = UI/display; Space Mono = EVERY number
   (`font-variant-numeric: tabular-nums`). Micro-labels uppercase + wide letter-spacing.
4. **Numbers are heroes.** Hierarchy IS explanation: the hero decision count is
   `clamp(72px,11vw,150px)` mono; chapter readouts 40–64px mono; captions 14px dim.
   One hero number per section, not N equal stats (STORYTELLING.md P4).
5. **Editorial scroll narrative.** The page reads top→bottom: hero → chapters 01–05 →
   deep-dive. Chapter markers = ghost mono numeral + grotesk title + count + hairline.
   NO BI tab-bar, NO always-on sidebar: system readouts live in a slide-in drawer
   (all v2 ids preserved, `toggleSidebar()` opens it; default closed — the story leads).
6. **No plates.** Sections are hairline-bordered, not boxed; content floats on the night.
   Cards keep hover-lift affordance (wc26 `translateY(-6px)` pattern, applied as transforms).
7. **Color carries meaning.** Periwinkle accent (`#7d97ff` dark) + semantic
   success/warn/danger/info; domain colors come from the shared JS palette (story.js) that
   maps REAL knowledge domains. Title letters are dyed with real domain colors — a domain
   that isn't in the live graph stays ink (honest, never a fake hue).
8. **Pull-quotes are data.** Every `blockquote.pullquote` body is computed in hero.js from
   real fields (`recent_decisions`, `position`, `episodes`, `knowledge`, `stream_activations`).
   Never a hand-written claim. Empty states say exactly what is missing ("awaiting the first
   decision cycle…"), never a fabricated number.
9. **Honesty is structural.** (Inherited v2.) No fabricated data, no Math.random for data,
   no demo traces; thin live data renders thin and graceful. The hero backdrop draws ONLY
   `state.diHistory`/`state.mdHistory`; the chart draws ONLY the same series.
10. **Motion is restrained.** Scroll-reveal (fade + 16px rise, .6s), one pulsing endpoint on
    the hero + chart, live badge breathe. Motion must be *signal*, never noise. Canvas motion
    is gated by `window.__reducedMotion`; the CSS media query kills CSS motion.
11. **Reduced motion & accessibility.** `@media (prefers-reduced-motion: reduce)` block last in
    file kills reveals/live-dot/countPop and transitions; canvases render one static frame.
    Contrast gates (≥4.5:1, both themes): `.ss-caption`, `.panel-caption`,
    `.metric-card .label`, `.pullquote .pq-cite`, `.story-hero-label` — enforced by tests.
12. **Responsive.** Hero title wraps below 768px; signal columns stack; canvases scale
    via CSS (JS reads clientWidth/clientHeight); drawer maxes at 88vw; topbar wraps.
    Mode canvases drop to 380px on small screens.

## Sources
- v2 sources (NN/g heuristics, web.dev typography/macro-layout, MD 8dp) — still load-bearing.
- New: the two reference sites above (studied 2026-08-15, honest capture notes in
  `BIGDATA_BRIEF.md` §1).
