# TELOS Dashboard — Design Principles (v2, 2026-08-14)

Source of truth for any dashboard UI change. Read BEFORE editing markup or styles.
Violating these is a pattern regression, not a style preference.

## Sources (fetched and read this session)
1. **NN/g — 10 Usability Heuristics** (Nielsen, rev. 2024)
   https://www.nngroup.com/articles/ten-usability-heuristics/
   Applied: visibility of system status (#1), consistency & standards (#4),
   recognition rather than recall (#6), aesthetic & minimalist (#8),
   user control & freedom (#3 — no dead buttons).
2. **web.dev — Learn Responsive Design: Typography**
   https://web.dev/learn/design/typography
   Applied: type-scale hierarchy, unitless line-height, 45–75ch measure,
   clamp() for fluid type.
3. **web.dev — Learn Responsive Design: Macro Layouts**
   https://web.dev/learn/design/macro-layouts
   Applied: content-flow-first single column, flex/grid for cards
   (auto-fill minmax), minimal media queries.
4. **Material Design 2 spacing (8dp grid)** — https://m2.material.io/design/layout/spacing-methods.html
   (page is JS-gated; the 8dp convention is applied from standard practice).

## The 10 rules
1. **8pt spacing scale.** All whitespace comes from
   `--space-1..8` (4/8/12/16/24/32/48/64px). Never free-hand margins/padding.
2. **One design system, two themes.** Colors/radii/shadows/fonts are CSS custom
   properties on `:root`; light theme overrides the tokens on `body.theme-light`.
   NO hard-coded hex in components. NO `!important` (drop it when you touch a rule).
3. **Type scale, not type soup.** Four steps: display (brand), panel-title
   (uppercase, letter-spaced), body (14px), meta (11–12px, muted). Muted = token,
   not random greys.
4. **Visual hierarchy by contrast, not size alone.** Primary data (DI/MD/cycles)
   is high-contrast on elevated cards; secondary streams/resources are dimmer.
5. **One primary action per panel.** A panel header has its controls grouped and
   visually secondary to the content; the toolbar's Auto-refresh is the one
   primary action on the page (accent color).
6. **Breathing room.** Cards never touch: 16px+ gaps, 16–20px panel padding,
   section spacing on the 8pt scale. Density is an accessibility feature.
7. **Empty states breathe.** No raw "—" clutter. When data is absent, show a
   muted, centered state with a short line ("Awaiting data…"). The knowledge
   graph keeps its honest empty-set rendering — never fabricate nodes/edges.
8. **Clear affordance.** Every interactive element has hover/focus/active states,
   a pointer cursor, and consistent shape (buttons, tabs, zoom chips).
9. **Responsive.** Sidebar collapses to a top cluster < 1024px; panels stack
   full-width; canvases scale via CSS (JS reads clientWidth/clientHeight).
10. **No inline-style spaghetti.** Markup carries classes only; JS runtime
    style writes are allowed (fullscreen toggles, gauge widths, canvas anims)
    but static layout styles live in the stylesheet.
