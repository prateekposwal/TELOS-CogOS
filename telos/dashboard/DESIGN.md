# TELOS Dashboard — Design Principles (v3, 2026-08-15 · "Cognitive Data Portraits")

Source of truth for any dashboard UI change. Read BEFORE editing markup or styles.
Violating these is a pattern regression, not a style preference.

v4 amendment (2026-08-15): one mode per section — each KG mode (tree/solar/bubble)
and each Mind mode (orbit/root) is a standalone full-width chapter in the GRIDWORLD
pattern; the memory timeline is a compact panel matching the chat panel.
**Decision record (2026-08-15, user-approved): the five mode chapters are EXPLICIT, hand-written HTML — Memory: `kg-panel-tree` / `kg-panel-solar` / `kg-panel-bubble`; Mind: `brain-panel-orbit` / `brain-panel-tree`. A JS/template factory is INTENTIONALLY NOT used. Repeated chapter-mark markup is deliberate: every section stays statically readable and every `getElementById` target stays a literal, greppable id, keeping the DOM-contract tests meaningful. Do not 'helpfully' refactor these into a factory. (Mirrored in STORYTELLING.md v4 note + BIGDATA_BRIEF.md DOM-contract para.)

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
