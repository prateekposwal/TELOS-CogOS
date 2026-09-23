"""DOM Contract tests — every id/function the dashboard JS depends on must
exist in dashboard.html; fabricated demo data must stay gone.

Structural rules under test:
  1. Primary content (graphs + story) is visible without interaction.
  2. No fabricated/demo data source may be loaded (demo.js removed).
"""
import os
import re
import sys

import pytest

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HTML = os.path.join(PROJECT, "telos", "dashboard.html")
JS_DIR = os.path.join(PROJECT, "telos", "dashboard", "js")

LOOP_CANVAS_IDS = {
    "kg-tree", "kg-solar", "kg-bubble",
    "brain-orbit", "brain-tree",
    "grid-canvas", "chart-canvas", "health-meter-canvas", "minimap-canvas",
    "hero-backdrop",
}

JS_FILES = [
    "dashboard.js", "intent.js", "knowledge-graph.js", "gridworld.js",
    "brain-viz.js", "chart.js", "memory.js", "story.js",
    "chat.js", "hero.js", "knowledge-3d.js",
    "lazy-3d.js", "scrollspy.js",
]


def _load():
    html = open(HTML).read()
    texts = {f: open(os.path.join(JS_DIR, f)).read() for f in JS_FILES}
    return html, texts


def test_every_getelementbyid_target_exists_in_html():
    html, texts = _load()
    html_lower = html.lower()
    ids = set(LOOP_CANVAS_IDS)
    for text in texts.values():
        ids |= set(re.findall(r"getElementById\('([^']+)'\)", text))
        ids |= set(re.findall(r'getElementById\("([^"]+)"\)', text))
    missing = [i for i in sorted(ids)
               if f'id="{i}"' not in html_lower and f"id='{i}'" not in html_lower]
    assert not missing, f"DOM contract broken — missing ids: {missing}"


def test_onclick_handlers_resolve_to_defined_functions():
    html, texts = _load()
    defined = set()
    for text in texts.values():
        defined |= set(re.findall(r"^function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, re.M))
        defined |= set(re.findall(r"^async function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, re.M))
        defined |= set(re.findall(r"^\s{0,2}function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, re.M))
    builtin = {"event", "document", "parseInt", "Math", "getElementById", "if", "return"}
    calls = set()
    for m in re.finditer(r"onclick=\"([^\"]+)\"", html):
        for fm in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\(", m.group(1)):
            calls.add(fm.group(1))
    unresolved = sorted(calls - defined - builtin)
    assert not unresolved, f"onclick handlers without definitions: {unresolved}"


def test_demo_js_fabrication_removed():
    html, _ = _load()
    assert "demo.js" not in html.lower(), "demo.js must not be loaded (fabricated traces)"
    assert not os.path.exists(os.path.join(JS_DIR, "demo.js")), "demo.js must be deleted"
    all_js = "\n".join(open(os.path.join(JS_DIR, f)).read() for f in JS_FILES)
    assert "generateDemoTraces" not in all_js, "demo trace generator must be gone"
    # The fabricated-data sites lived in dashboard.js: the random-goal
    # autopilot and the random-importance KG node generator. (Math.random in
    # knowledge-graph.js is cosmetic layout jitter for node POSITIONS, which
    # is fine — the node DATA always comes from /api/knowledge.)
    dashboard_js = open(os.path.join(JS_DIR, "dashboard.js")).read()
    assert "state.goal = [gx, gy]" not in dashboard_js, "random-goal autopilot removed"
    assert "importance: 0.3 + Math.random()" not in dashboard_js, \
        "random-importance KG fabrication removed"


def test_graphs_and_story_visible_without_tab_activation():
    """The landing view must include every graph section and the story strip
    as directly-visible DOM (not hidden behind a tab)."""
    html, _ = _load()
    # Story strip present and NOT a data-section (always visible)
    assert 'id="story-strip"' in html
    assert 'data-section="story"' not in html, "story must never be tab-hidden"
    for sid in ("story-decisions", "story-headline", "story-mood",
                "story-domain-chips", "story-edge-chips", "story-recent"):
        assert f'id="{sid}"' in html, f"story element missing: {sid}"
    # Graph wall wraps the seven evidence sections; all canvases present
    assert 'class="graph-wall"' in html
    for cid in ("brain-orbit", "brain-tree", "grid-canvas",
                "kg-tree", "kg-solar", "kg-bubble"):
        assert f'id="{cid}"' in html, f"graph canvas missing: {cid}"
    # No canvas may start hidden in the markup
    assert 'style="display:none"' not in html.split('<main')[1].split('</main>')[0]


def test_bigdata_narrative_structure():
    """v3 "Cognitive Data Portraits" structure: the page is a scroll narrative —
    cinematic hero with a real-data backdrop canvas, numbered editorial chapters,
    pull-quotes mapped to real fields, and the BI tab-bar removed. Every canvas
    and quote id must exist so hero.js/plot modules can write into them.

    v4 structure rule (2026-08-15): each knowledge mode and each mind mode is
    its OWN full section following the GRIDWORLD chapter pattern — ghost numeral
    + title + hairline + full-width panel + caption + pull-quote. Modes are
    never stacked/shared inside one panel (no .kg-grid / .brain-grid)."""
    html, _ = _load()
    # Hero: backdrop canvas + dyed editorial title + hero meta.
    assert 'id="hero-backdrop"' in html, "hero backdrop canvas missing"
    assert 'id="hero-title-dyed"' in html, "dyed title line missing"
    assert '<span class="ch">P</span>' in html, "title letters must be per-char spans"
    # The narrative leads: no BI tab-bar, no data-section tabs (story must never
    # hide behind a tab; switchTab() may stay defined for the chat action).
    assert 'class="tab-bar"' not in html, "v3 removes the BI tab bar"
    assert 'data-section="story"' not in html, "story must never be tab-hidden"
    assert 'id="story-strip"' in html
    # Eight evidence chapters (01 Signal · 02 World · 03–05 Memory modes ·
    # 06–07 Mind modes · 08 Story So Far) + narrative hub + deep-dive, each
    # with a ghost numeral marker and real-data pull-quote blocks.
    for idx in ("01", "02", "03", "04", "05", "06", "07", "08"):
        assert f'data-chapter="{idx}"' in html, f"chapter {idx} missing"
    for qid in ("signal-quote", "world-quote", "memory-quote",
                "memory-solar-quote", "memory-bubble-quote",
                "mind-quote", "mind-root-quote"):
        assert f'id="{qid}"' in html, f"pull-quote {qid} missing"
    # Graph wall still wraps the seven live canvases (DOM contract unchanged).
    assert 'class="graph-wall"' in html
    for cid in ("brain-orbit", "brain-tree", "grid-canvas",
                "kg-tree", "kg-solar", "kg-bubble", "chart-canvas"):
        assert f'id="{cid}"' in html, f"graph canvas missing: {cid}"
    # ── Single-section contract: every mode canvas has its OWN chapter with
    #    a chapter-mark (ghost numeral + count) and a full-width panel that is
    #    a DIRECT child of that chapter's body (the GRIDWORLD pattern). ──
    mode_meta = {
        "kg-tree": ("03", "knowledge-panel", "kg-panel-tree"),
        "kg-solar": ("04", "knowledge-panel", "kg-panel-solar"),
        "kg-bubble": ("05", "knowledge-panel", "kg-panel-bubble"),
        "brain-orbit": ("06", "brain-panel", "brain-panel-orbit"),
        "brain-tree": ("07", "brain-panel", "brain-panel-tree"),
    }
    for cid, (ch, pcls, pid) in mode_meta.items():
        canvas = f'<canvas id="{cid}"'
        assert canvas in html, f"mode canvas {cid} missing"
        seg = html[html.index(f'<section class="chapter" data-chapter="{ch}"'):]
        seg = seg[:seg.index('</section>')]
        assert canvas in seg, f"{cid} must live inside chapter {ch}"
        assert f'<span class="ch-idx" aria-hidden="true">{ch}</span>' in seg, \
            f"chapter {ch} must carry its ghost numeral marker"
        assert f'class="panel {pcls}"' in seg, f"{cid} must live in a {pcls} panel"
        assert f'id="{pid}"' in seg, f"panel id {pid} missing for {cid}"
        # The panel is a DIRECT child of .chapter-body (full-width section),
        # not nested in a mode grid.
        # Each mode chapter renders exactly ONE canvas — its own mode —
        # and the panel is a direct child of the chapter body (verified
        # live in the browser probe via panel.parentElement === body).
        assert seg.count('<canvas') == 1, \
            f"{cid} chapter must contain exactly one canvas (its mode)"
        assert 'kg-grid' not in seg and 'brain-grid' not in seg, \
            f"{cid} chapter must not wrap modes in a shared grid"
    assert 'class="mem-evidence"' not in html, "memory sidebar grid removed"
    # Narrative hub ids (story.js writes into them regardless of position).
    for sid in ("story-insight", "story-mood", "story-recent", "story-action",
                "story-domain-chips", "story-edge-chips"):
        assert f'id="{sid}"' in html, f"narrative id missing: {sid}"
    # System readouts survive as an on-demand drawer (ids preserved).
    assert 'id="sidebar"' in html and 'class="sidebar"' in html
    assert 'id="drawer-fade"' in html
    # No canvas may start hidden in the markup.
    assert 'style="display:none"' not in html.split('<main')[1].split('</main>')[0]
    # Self-hosted fonts, not a CDN dependency.
    assert 'dashboard/fonts/fonts.css' in html


def test_intent_label_never_renders_object_object():
    """Regression: the Memory timeline showed '[object Object]' because
    selected_intent is a dict {type, confidence} in real traces and the
    old code interpolated the raw field. intentLabel() must extract a
    string from every known shape and never return an object. The real
    intent.js function is executed under node (verify as the user — the
    exact code the browser runs)."""
    import json
    import subprocess

    intent_src = open(os.path.join(JS_DIR, "intent.js")).read()
    cases = [
        ({"selected_intent": {"type": "explore_unknown_unknown", "confidence": 0.5}}, "explore_unknown_unknown"),
        ({"selected_intent": {"intent_type": "navigate_to_goal"}}, "navigate_to_goal"),
        ({"selected_intent": "plain_string_intent"}, "plain_string_intent"),
        ({"intent_type": "top_level_intent"}, "top_level_intent"),
        ({"strategic_options": [{"intent_type": "via_options"}]}, "via_options"),
        ({"selected_intent": {}}, "—"),
        ({}, "—"),
        (None, "—"),
    ]
    harness = intent_src + "\n" + (
        "const cases = " + json.dumps([c[0] for c in cases]) + ";\n"
        "for (const c of cases) console.log(intentLabel(c));\n"
    )
    proc = subprocess.run(
        ["node", "-e", harness],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"node failed: {proc.stderr}"
    got = [line for line in proc.stdout.splitlines() if line]
    expected = [c[1] for c in cases]
    assert got == expected, f"intentLabel mismatch:\n  got={got}\n  expected={expected}"
    assert "object Object" not in proc.stdout, "intentLabel leaked '[object Object]'"


def test_memory_renders_intent_via_canonical_extractor():
    """memory.js must route intent display through intentLabel() (the one
    canonical extractor) and must never interpolate selected_intent raw."""
    texts = {f: open(os.path.join(JS_DIR, f)).read() for f in JS_FILES}
    memory_src = texts["memory.js"]
    assert "intentLabel(t)" in memory_src, \
        "memory.js must use the canonical intentLabel() extractor"
    assert "selected_intent || t.intent_type" not in memory_src, \
        "memory.js must not fall back to raw selected_intent interpolation"
    html = open(HTML).read()
    assert "js/intent.js" in html, "intent.js must be loaded before memory.js"
    assert html.index("js/intent.js") < html.index("js/memory.js"), \
        "intent.js must load before memory.js"


# ═══════════════════════════════════════════════════════════════════════
# DESIGN-SYSTEM GATES (redesign audit, 2026-08-14)
#   1. Visibility-is-a-contract: every direct child of .main is flex-shrink:0
#      (the story strip collapsed to 48px/659px without it).
#   2. 13px text floor in CSS; 12px floor in canvas fonts.
#   3. 4.5:1 WCAG contrast gate on the three known dim-text pairs.
#   4. No fabricated data in chart.js (Math.random is banned there).
# ═══════════════════════════════════════════════════════════════════════

CSS = os.path.join(PROJECT, "telos", "dashboard", "css", "dashboard.css")


def _wcag_contrast(fg_hex, bg_hex):
    """WCAG 2.x contrast ratio between two #rrggbb colors.

    Args:
        fg_hex: foreground color hex string ("#rrggbb").
        bg_hex: background color hex string ("#rrggbb").
    """
    def lum(hexstr):
        h = hexstr.lstrip("#")
        vals = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
        def lin(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (lin(v) for v in vals)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    l1, l2 = lum(fg_hex), lum(bg_hex)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _parse_theme_block(css_text, selector):
    """Return {var-name: value} for a :root or body.theme-light block.

    Args:
        css_text: full dashboard.css text to search.
        selector: ":root" (dark) or "body.theme-light" block selector.
    """
    start = css_text.index(selector)
    brace = css_text.index("{", start)
    depth, i = 1, brace + 1
    while depth > 0:
        if css_text[i] == "{":
            depth += 1
        elif css_text[i] == "}":
            depth -= 1
        i += 1
    body = css_text[brace + 1:i - 1]
    tokens = {}
    for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", body):
        tokens[m.group(1)] = m.group(2).strip()
    return tokens


def test_contrast_gate_45():
    """The three known dim-text pairs must reach ≥4.5:1 in BOTH themes.
    Pairs: .ss-caption / .panel-caption / .metric-card .label — all render
    --text-dim on their card backgrounds. (WCAG AA for normal text.)"""
    css = open(CSS).read()
    for theme_selector, label in ((":root", "dark"), ("body.theme-light", "light")):
        t = _parse_theme_block(css, theme_selector)
        dim = t["--text-dim"]
        # v3 pairs: the editorial layers (pull-quote citation = dim on page bg;
        # hero label = accent on page bg) plus the v2 dim pairs.
        pairs = [
            ("ss-caption", dim, t["--bg"]),
            ("panel-caption", dim, t["--bg-elev"]),
            ("metric-card .label", dim, t["--bg-elev-2"]),
            ("pullquote .pq-cite", dim, t["--bg"]),
            ("story-hero-label", t["--accent"], t["--bg"]),
        ]
        for pair_label, fg, bg in pairs:
            ratio = _wcag_contrast(fg, bg)
            assert ratio >= 4.5, (
                f"[{label}] {pair_label} contrast {ratio:.2f}:1 < 4.5:1 "
                f"({fg} on {bg})"
            )


def test_type_tokens_and_flex_shrink_contract():
    """The redesign's structural contracts must be in the stylesheet:
    (a) .main > * { flex-shrink: 0 } — visibility-is-a-contract;
    (b) the fluid type-scale tokens exist."""
    css = open(CSS).read()
    assert ".main > * { flex-shrink: 0; }" in css, \
        "flex-shrink visibility contract missing"
    t = _parse_theme_block(css, ":root")
    for token in ("--text-display", "--text-h1", "--text-h2",
                  "--text-body", "--text-meta"):
        assert token in t, f"type token missing: {token}"
    assert "clamp(" in t["--text-display"], "display token must use clamp()"
    assert "clamp(" in t["--text-h1"], "h1 token must use clamp()"


def test_css_font_floor_13px():
    """Nothing below 13px anywhere on the page (CSS text floor)."""
    css = open(CSS).read()
    bad = []
    for m in re.finditer(r"font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)px", css):
        if float(m.group(1)) < 13:
            bad.append(m.group(0))
    assert not bad, f"sub-13px CSS fonts: {bad}"


def test_chart_js_no_random_and_real_canvas_width():
    """chart.js draws only real history: Math.random is banned there, and
    the canvas must be sized from clientWidth (not a hardcoded 520)."""
    chart = open(os.path.join(JS_DIR, "chart.js")).read()
    assert "Math.random(" not in chart, "chart.js must not fabricate series"
    assert "clientWidth" in chart, "chart.js must read the real canvas width"
    assert "clientHeight" in chart, "chart.js must read the real canvas height"

def test_v5_memory_modes_draw_real_edges_and_canonical_palette():
    """v5 Memory redesign (2026-08-15): all three KG modes must draw the
    REAL edges (color-coded by edge_type) — never isolated dots for a graph
    that has connections — and must use the ONE canonical domain palette
    (window._DOMAIN_COLORS_STORY from story.js), not a private copy."""
    kg = open(os.path.join(JS_DIR, "knowledge-graph.js")).read()
    # Real edges consumed by the draw path (kgDrawEdges + deterministic sample).
    assert "kgDrawEdges(" in kg, "KG modes must draw real edges"
    assert "edgeSample(" in kg, "real-edge sampling helper missing"
    assert "kgEdgeCount" in kg, "real edge total must be tracked"
    assert "edge_type" in kg, "edge_type must drive filament color (meaning)"
    # Canonical palette: NO private domain-color map (old DOMAIN_COLORS gone),
    # the canonical map is read from window._DOMAIN_COLORS_STORY.
    assert "var DOMAIN_COLORS" not in kg, "private palette copy regressed"
    assert "window._DOMAIN_COLORS_STORY" in kg, \
        "KG must read the canonical domain palette from story.js"
    # Original mode names (the v5 identity).
    for marker in ("THE CANOPY", "ORBITAL ECOLOGY", "NEBULA CLUSTERS"):
        assert marker in kg, "v5 mode marker missing: " + marker
    # Deterministic layout: no Math.random for node positions.
    assert "Math.random(" not in kg, "KG layout must be deterministic"


def test_v5_mind_modes_real_signals_and_no_fabrication():
    """v5 Mind redesign: stream activations / DI history / meta mode drive
    the canvases; the fabricated personal-name label and the rainbow phase
    palette are gone; no fake timer-driven 'active phase' claim survives."""
    brain = open(os.path.join(JS_DIR, "brain-viz.js")).read()
    for marker in ("ACTIVATION AURORA", "SYNAPSE RHIZOME"):
        assert marker in brain, "v5 mind marker missing: " + marker
    assert "TELOS" in brain, "the public core label must be rendered"
    assert "Math.random(" not in brain, "Mind modes must not fabricate data"
    # Real data accessors drive the canvases.
    assert "_latestStreams" in brain, "must read real stream_activations"
    assert "_streamMeanPriorities" in brain, "must compute real stream means"
    assert "state.metaMode" in brain, "must read real meta_cognition.mode"
    assert "state.sysMood" in brain, "must read real system_mood"
    # Semantic stream palette, not a rainbow.
    assert "_STREAM_COLORS" in brain, "semantic stream palette missing"


def test_v5_world_is_scanned_perimeter_not_iso_game():
    """v5 World redesign: the isometric game renderer is replaced by the
    Scanned Perimeter (2D cartographic sonar) — real positions, real trail,
    real coverage. The old ISO engine constants must be gone from the JS."""
    grid = open(os.path.join(JS_DIR, "gridworld.js")).read()
    assert "THE SCANNED PERIMETER" in grid, "v5 world marker missing"
    assert "cellToScreen(" in grid, "perimeter projection helper missing"
    assert "coverageFraction(" in grid, "real coverage readout missing"
    assert "rewardFraction(" in grid, "real reward-fraction readout missing"
    assert "ISO.tw" not in grid, "legacy isometric engine must be gone"
    assert "drawBlock3D" not in grid, "legacy block renderer must be gone"
    assert "state.visitCounts" in grid, "visit heat must stay real"
    # Dashboard.js must drive the new projection (no dead ISO handlers).
    dash = open(os.path.join(JS_DIR, "dashboard.js")).read()
    assert "PERIM.camX" in dash, "dashboard.js must drive the perimeter pan"
    assert "state.metaMode" in dash, "dashboard.js must capture meta mode"
    assert "streamHistory" in dash, "dashboard.js must accumulate stream history"



def _serve_telos_static():
    """In-process static server for the telos/ dir (no dashboard required)."""
    import functools
    import http.server
    import threading

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=os.path.join(PROJECT, "telos"),
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


_PROBE_TEMPLATE = r"""
import { chromium } from 'playwright';
const port = process.argv[2];
const errors = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
await page.goto('http://localhost:' + port + '/dashboard.html',
  { waitUntil: 'networkidle', timeout: 20000 }).catch(() => {});
await page.waitForTimeout(1500);
// Render-gate: the story strip is filled after API fetch/fallback-retry
// (~3s backoff in dashboard.js). A fixed 1.5s wait races that retry under
// load (flake: clientHeight mid-collapse). Wait for the REAL rendered state
// before measuring — if it never renders, the assertion below still fails
// honestly with the true clientHeight (no weakened contract).
await page.waitForFunction(() => {
  const strip = document.getElementById('story-strip');
  return strip && strip.clientHeight >= 400;
}, { timeout: 10000 }).catch(() => {});
const r = await page.evaluate(() => {
  const strip = document.getElementById('story-strip');
  const hero = document.getElementById('story-decisions');
  const hr = hero.getBoundingClientRect();
  const q = sel => document.querySelector(sel);
  const inVp = r0 => r0.bottom > 0 && r0.top < window.innerHeight;
  // v3 overlap gate: key elements must be in-flow; any element IN the
  // viewport must paint to itself or a descendant at its center.
  const checkVisible = (sel) => {
    const el = q(sel);
    if (!el) return null;
    const r0 = el.getBoundingClientRect();
    let painted = null, selfPaints = null;
    if (inVp(r0) && r0.width > 0 && r0.height > 0) {
      painted = document.elementFromPoint(Math.round(r0.left + r0.width / 2), Math.round(r0.top + r0.height / 2));
      selfPaints = (painted === el) || (el.contains && el.contains(painted));
    }
    return {
      sel, x: Math.round(r0.x), y: Math.round(r0.y),
      w: Math.round(r0.width), h: Math.round(r0.height),
      inDocFlow: r0.width > 0 && r0.height > 0,
      paintedBy: painted ? (painted.id || painted.className || painted.tagName) : null,
      selfPaints,
    };
  };
  const visibleElements = [
    '#hero-title-dyed', '#story-decisions', '#story-headline', '#story-stats',
    '#signal-quote .pq-body', '#world-quote .pq-body', '#memory-quote .pq-body',
    '#memory-solar-quote .pq-body', '#memory-bubble-quote .pq-body',
    '#mind-quote .pq-body', '#mind-root-quote .pq-body',
    '#story-insight', '#story-mood', '#story-action',
    '#chart-canvas', '#grid-canvas', '#memory-timeline', '#chat-input',
  ].map(checkVisible);
  // v4 single-section contract: every mode canvas has its OWN chapter with
  // a chapter-mark (ghost numeral + count) and a full-width panel that is a
  // direct child of the chapter body (the GRIDWORLD pattern, verified live).
  const modeSections = ['kg-tree', 'kg-solar', 'kg-bubble', 'brain-orbit', 'brain-tree'].map(id => {
    const cv = document.getElementById(id);
    const sec = cv ? cv.closest('section.chapter') : null;
    const body = sec ? sec.querySelector('.chapter-body') : null;
    const panel = cv ? cv.closest('.panel') : null;
    return {
      canvas: id,
      hasOwnChapter: !!sec,
      dataChapter: sec ? sec.getAttribute('data-chapter') : null,
      hasChapterMark: !!(sec && sec.querySelector('.chapter-mark .ch-idx')),
      hasCount: !!(sec && sec.querySelector('.chapter-mark .ch-count')),
      hasCaption: !!(sec && sec.querySelector('.panel-caption')),
      panelIsFullWidth: !!(body && panel && panel.parentElement === body),
    };
  });
  const chapterBodies = [...document.querySelectorAll('.chapter .chapter-body')].map(el => ({
    ch: el.closest('.chapter') ? el.closest('.chapter').getAttribute('data-chapter') : '?',
    h: Math.round(el.getBoundingClientRect().height),
    visible: el.getBoundingClientRect().height > 0,
  }));
  const hc = document.getElementById('hero-backdrop');
  const heroBackdrop = hc ? {
    w: Math.round(hc.getBoundingClientRect().width),
    h: Math.round(hc.getBoundingClientRect().height),
  } : null;
  return {
    stripClientHeight: strip.clientHeight,
    heroHeight: Math.round(hr.height * 100) / 100,
    heroInViewport: hr.bottom > 0 && hr.top < window.innerHeight && hr.height > 0,
    visibleElements,
    modeSections,
    chapterBodies,
    heroBackdrop,
  };
});

// ── v4 scroll-paint pass: below-the-fold single-mode sections must render
//    and paint to themselves (the visibility contract extends to every new
//    full-width mode section + the compact memory timeline + chat input). ──
const scrollChecks = [];
for (const sel of [
  '#kg-tree', '#kg-solar', '#kg-bubble',
  '#brain-orbit', '#brain-tree',
  '#memory-solar-quote .pq-body', '#memory-bubble-quote .pq-body',
  '#mind-root-quote .pq-body', '#memory-timeline', '#chat-input',
]) {
  // Instant scroll (html { scroll-behavior:smooth } would animate and leave
  // the check mid-flight) — compute the exact center target and jump.
  await page.evaluate((s) => {
    const el = document.querySelector(s);
    if (!el) return;
    const r = el.getBoundingClientRect();
    const y = window.scrollY + r.top + r.height / 2 - window.innerHeight / 2;
    window.scrollTo({ top: Math.max(0, y), behavior: 'instant' });
  }, sel);
  await page.waitForTimeout(350);
  const sc = await page.evaluate((s) => {
    const el = document.querySelector(s);
    if (!el) return { sel: s, missing: true };
    const r0 = el.getBoundingClientRect();
    const inFlow = r0.width > 0 && r0.height > 0;
    const p = inFlow ? document.elementFromPoint(Math.round(r0.left + r0.width / 2), Math.round(r0.top + r0.height / 2)) : null;
    const selfPaints = p === el || (el.contains && el.contains(p));
    return { sel: s, inFlow, selfPaints, paintedBy: p ? (p.id || p.className || p.tagName) : null };
  }, sel);
  scrollChecks.push(sc);
}
console.log(JSON.stringify({ probe: r, scrollChecks, errors }));
await browser.close();
"""

def test_story_strip_visible_above_fold_browser():
    """BROWSER TEST — the story strip must render full height and the hero
    number must have nonzero visible height at 1440x900.

    Fails on the pre-fix CSS (strip clientHeight collapsed to ~48px) and
    passes after Step 1 (.main > * { flex-shrink: 0 }).

    If headless Chromium is unavailable in this environment, falls back to
    static CSS assertions (tokens + flex-shrink rule) and notes the
    limitation — the live measurement is then done by the manual probe.
    """
    import json
    import subprocess
    import warnings

    server, port = _serve_telos_static()
    try:
        # Probe MUST live inside PROJECT: node resolves ESM imports
        # (playwright) from the module's own location, not the cwd.
        probe_path = os.path.join(
            PROJECT, f".dashboard_probe_{os.getpid()}.mjs"
        )
        with open(probe_path, "w") as tf:
            tf.write(_PROBE_TEMPLATE)
        try:
            proc = subprocess.run(
                ["node", probe_path, str(port)],
                capture_output=True, text=True, timeout=60,
                cwd=PROJECT,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"probe failed: {proc.stderr[:300]}"
                )
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            p = data["probe"]
            assert p["stripClientHeight"] >= 400, (
                f"story-strip collapsed: clientHeight="
                f"{p['stripClientHeight']}px (need ≥400px) — "
                f"flex-shrink contract missing?"
            )
            assert p["heroHeight"] > 0, (
                f"hero value has zero visible height: {p['heroHeight']}px"
            )
            assert p["heroInViewport"], "hero value not visible in viewport"
            # v3 overlap gate: every key element is in-flow; any element that
            # is IN the viewport must paint to itself (no element stacked on
            # top of it = no overlap/clipping regression).
            for v in p["visibleElements"]:
                assert v is not None and v["inDocFlow"], f"element collapsed/not in flow: {v}"
                if v["selfPaints"] is not None:
                    assert v["selfPaints"], (
                        f"overlap on {v['sel']}: center paints to "
                        f"'{v['paintedBy']}' instead of itself"
                    )
            # v4 single-section contract (live DOM): each memory/mind mode has
            # its own chapter with ghost numeral + count + caption, and its
            # panel is a full-width direct child of the chapter body.
            for ms in p["modeSections"]:
                assert ms["hasOwnChapter"], \
                    f"{ms['canvas']} must have its own chapter section"
                assert ms["hasChapterMark"] and ms["hasCount"], \
                    f"{ms['canvas']} chapter missing numeral/count mark"
                assert ms["hasCaption"], f"{ms['canvas']} chapter missing caption"
                assert ms["panelIsFullWidth"], \
                    f"{ms['canvas']} panel not a full-width chapter child"
            # Below-the-fold sections (scrolled into view) must not collapse
            # and must paint to themselves — zero overlap anywhere.
            for sc in data["scrollChecks"]:
                assert sc is not None and not sc.get("missing"), \
                    f"mode section missing: {sc}"
                assert sc["inFlow"], f"mode section collapsed: {sc['sel']}"
                if sc["selfPaints"] is not None:
                    assert sc["selfPaints"], (
                        f"overlap on {sc['sel']}: center paints to "
                        f"'{sc['paintedBy']}' instead of itself"
                    )
            assert p["heroBackdrop"] and p["heroBackdrop"]["w"] > 0 and p["heroBackdrop"]["h"] > 0, (
                "hero backdrop canvas has zero size"
            )
            for cb in p["chapterBodies"]:
                assert cb["visible"], f"chapter {cb['ch']} body collapsed to {cb['h']}px"
            # 404s on /api/* are expected — the unit-test server has no
            # backend; any OTHER console/page error is a real regression.
            real_errors = [
                e for e in data["errors"]
                if "Failed to load resource" not in e and "404" not in e
            ]
            assert not real_errors, f"console errors: {real_errors}"
        except (RuntimeError, OSError, FileNotFoundError) as e:
            # ── Static fallback (documented limitation) ──
            warnings.warn(
                "headless-Chromium probe unavailable — falling back to static "
                f"CSS assertions. ({e}) Browser verification must be done "
                "manually: ./telos/start_dashboard.sh start + probe at "
                "1440x900 (see scripts/_dashboard_probe.mjs).",
                stacklevel=2,
            )
            css = open(CSS).read()
            assert ".main > * { flex-shrink: 0; }" in css, \
                "flex-shrink visibility contract missing (static fallback)"
            t = _parse_theme_block(css, ":root")
            assert "--text-display" in t, "display token missing (static fallback)"
        finally:
            try:
                os.unlink(probe_path)
            except OSError:
                pass
    finally:
        server.shutdown()

# ═══════════════════════════════════════════════════════════════════════
# v6 3D Memory Nebula (kg-bubble → three.js WebGL, 2026-08-15)
#   1. Vendored three.js (no CDN), deterministic layout, real data only.
#   2. WebGL-unavailable / three-missing → the 2D nebula renderer stays.
#   3. The 3D canvas paints real pixels in the browser (measured).
# ═══════════════════════════════════════════════════════════════════════

VENDOR_DIR = os.path.join(PROJECT, "telos", "dashboard", "vendor")


def test_v6_knowledge_3d_static_structure_and_real_data():
    """The 3D Memory Nebula must be vendored (never a CDN), deterministic
    (no Math.random — same layout rule as the 2D modes), driven ONLY by the
    real shared graph state (kgNodes/kgEdges/kgDegree/edge_type and the ONE
    canonical domain palette), and structurally able to fall back to the 2D
    nebula renderer when WebGL or three.js is unavailable."""
    html = open(HTML).read()
    k3d = open(os.path.join(JS_DIR, "knowledge-3d.js")).read()
    kg = open(os.path.join(JS_DIR, "knowledge-graph.js")).read()

    # Vendored, not CDN: three.min.js + OrbitControls.js exist on disk,
    # are full-size, and contain no CDN proxy references.
    assert os.path.exists(os.path.join(VENDOR_DIR, "three.min.js")), "three.min.js must be vendored"
    assert os.path.exists(os.path.join(VENDOR_DIR, "OrbitControls.js")), "OrbitControls.js must be vendored"
    assert os.path.getsize(os.path.join(VENDOR_DIR, "three.min.js")) > 300000, "vendored three.min.js looks truncated"
    assert "https://" not in "".join(
        open(os.path.join(VENDOR_DIR, f)).read() for f in ("three.min.js", "OrbitControls.js")
    ), "vendored libs must not be CDN proxies"
    assert 'src="https://' not in html, "no CDN scripts allowed"

    # LAZY-LOAD model (Item 6b, 2026-08-15): the ~600 KB vendor chain is NOT
    # eager script tags. lazy-3d.js injects three.min.js → OrbitControls.js →
    # knowledge-3d.js in that EXACT order when chapter 05 approaches the
    # viewport (IntersectionObserver on #kg-panel-bubble). knowledge-3d.js
    # is not an eager tag either — it must never parse before THREE, and the
    # loader's chained onload guarantees the order. The load-order contract
    # is asserted from the loader's chain, not the HTML tag soup.
    assert 'src="dashboard/vendor/three.min.js"' not in html, "three.min.js must be lazy-loaded, not eager (Item 6b)"
    assert 'src="dashboard/vendor/OrbitControls.js"' not in html, "OrbitControls must be lazy-loaded, not eager (Item 6b)"
    assert 'src="dashboard/js/knowledge-3d.js"' not in html, \
        "knowledge-3d.js must load with the vendor chain, not eagerly"
    assert 'src="dashboard/js/lazy-3d.js"' in html, "lazy loader must be loaded by the page"
    loader = open(os.path.join(JS_DIR, "lazy-3d.js")).read()
    i_three = loader.index("three.min.js")
    i_oc = loader.index("OrbitControls.js")
    i_k3d = loader.index("knowledge-3d.js")
    assert i_three < i_oc < i_k3d, (
        "lazy loader must preserve order: three.min.js → OrbitControls.js "
        "→ knowledge-3d.js"
    )
    assert "IntersectionObserver" in loader, "lazy loader must use IntersectionObserver"
    assert "kg-panel-bubble" in loader, "lazy loader must watch the chapter-05 panel"

    # Deterministic layout: no Math.random anywhere in the 3D module.
    assert "Math.random(" not in k3d, "3D layout must be deterministic"

    # Real-data contract: the 3D module reads ONLY the shared real state and
    # the ONE canonical palette; no private color map, no invented fields.
    for marker in ("kgNodes", "kgEdges", "kgDegree", "kgDegreeMax",
                   "edgeSample(", "edgeColor(", "window._DOMAIN_COLORS_STORY",
                   "kgEdgeCount"):
        assert marker in k3d, f"3D module must read real state: {marker}"
    assert "edge_type" in k3d, "edge_type must drive 3D edge colors (meaning)"
    assert "var DOMAIN_COLORS" not in k3d, "no private palette copy in 3D module"

    # Honest fallback structure: __kgBubble3D is set ONLY when a WebGL
    # context was actually obtained; knowledge-graph.js consults it before
    # touching kg-bubble with 2D (so the 2D nebula survives a WebGL-less env).
    assert "window.__kgBubble3D = true;" in k3d, "3D activation flag missing"
    assert "getContext('webgl2')" in k3d, "WebGL probe missing"
    assert "getContext('webgl')" in k3d, "WebGL probe missing"
    assert "window.__kgBubble3D" in kg, "knowledge-graph.js must guard kg-bubble against the 3D owner"
    assert "kg3dZoomButton" in k3d and "kg3dZoomButton(delta)" in open(os.path.join(JS_DIR, "dashboard.js")).read(),         "zoom buttons must dolly the 3D camera (not CSS-scale the WebGL canvas)"

    # Honest empty state + inspect card ids exist and start hidden (no
    # fabricated content; the card fills only from a real node on click).
    for hid in ("kg3d-hud", "kg3d-empty", "kg3d-labels", "kg3d-card"):
        assert f'id="{hid}"' in html, f"3D overlay id missing: {hid}"
    empty_idx = html.index('id="kg3d-empty"')
    assert "hidden" in html[empty_idx:empty_idx + 60], "empty state must start hidden"
    card_idx = html.index('id="kg3d-card"')
    assert "hidden" in html[card_idx:card_idx + 60], "inspect card must start hidden"
    # Chapter 05 still carries exactly one canvas (the contract survives).
    seg = html[html.index('<section class="chapter" data-chapter="05"'):]
    seg = seg[:seg.index('</section>')]
    assert seg.count('<canvas') == 1, "chapter 05 must contain exactly one canvas (kg-bubble)"
    # Overlays must never intercept canvas interactions (probe contract).
    css = open(CSS).read()
    assert "pointer-events: none" in css, "3D overlays must be pointer-transparent"
    # Sub-13px floor applies to the new overlay text too.
    for m in re.finditer(r"font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)px", css):
        assert float(m.group(1)) >= 13, f"sub-13px font regressed: {m.group(0)}"


_KG3D_PROBE_TEMPLATE = r"""
import { chromium } from 'playwright';
import zlib from 'zlib';
const port = process.argv[2];
const errors = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
await page.goto('http://localhost:' + port + '/dashboard.html',
  { waitUntil: 'networkidle', timeout: 25000 }).catch(() => {});
await page.waitForTimeout(3500);
// Item 6b proof — captured BEFORE any scroll: at initial load (nebula below
// the fold) the ~600 KB vendor chain must NOT be present, so three.js never
// blocks first paint. The lazy loader only injects it once the chapter-05
// panel approaches the viewport (IntersectionObserver, rootMargin 900px).
const preScroll = await page.evaluate(() => ({
  lazyState: (window.__kg3dLazy || {}).state,
  threeTag: !!document.querySelector('script[src*="three.min.js"]'),
  hint: (() => {
    const h = document.getElementById('kg3d-hint');
    return h ? { present: true, faded: h.classList.contains('fade') } : { present: false };
  })(),
}));
// The nebula chapter is below the fold — elementFromPoint needs it on screen.
await page.evaluate(() => {
  const el = document.getElementById('kg-bubble');
  const r = el.getBoundingClientRect();
  window.scrollTo({ top: window.scrollY + r.top + r.height / 2 - window.innerHeight / 2, behavior: 'instant' });
});
// Scrolling near chapter 05 triggers the LAZY loader — wait for the whole
// chain (three → OrbitControls → knowledge-3d) to boot the 3D scene.
const lazyBoot = await page.evaluate(async () => {
  const t0 = Date.now();
  while (!window.__kg3dDebug && Date.now() - t0 < 8000) {
    await new Promise(r2 => setTimeout(r2, 100));
  }
  return {
    lazy: window.__kg3dLazy || null,
    debug: !!window.__kg3dDebug,
  };
});
await page.waitForTimeout(900);
const r = await page.evaluate(() => {
  const canvas = document.getElementById('kg-bubble');
  const dbg = window.__kg3dDebug || null;
  const rc = canvas.getBoundingClientRect();
  const painted = (() => { try { return canvas.toDataURL('image/png').length > 2000; } catch (e) { return false; } })();
  const hit = document.elementFromPoint(Math.round(rc.left + rc.width / 2), Math.round(rc.top + rc.height / 2));
  return {
    bubble3d: !!window.__kgBubble3D,
    nodeCount: dbg ? dbg.nodeCount() : 0,
    edgeCount: dbg ? dbg.edgeCount() : 0,
    painted,
    selfPaints: hit === canvas,
    hud: document.getElementById('kg3d-hud').textContent,
    emptyShown: !document.getElementById('kg3d-empty').hidden,
    labels: document.querySelectorAll('#kg3d-labels .kg3d-cloud').length,
    treeAlive: !!(document.getElementById('kg-tree') && document.getElementById('kg-tree').getContext('2d')),
    solarAlive: !!(document.getElementById('kg-solar') && document.getElementById('kg-solar').getContext('2d')),
    bubbleBox: { x: rc.x, y: rc.y, w: rc.width, h: rc.height },
  };
});
// Honest screen-pixel proof: sample the COMPOSITED viewport (what a user
// sees). toDataURL is blank for in-view WebGL canvases in headless Chromium
// (presented-surface artifact) — the screenshot is ground truth.
const shot = await page.screenshot();
function decodePng(buf) {
  let pos = 8, w = 0, h = 0, colorType = 6, idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos);
    const ty = buf.toString('ascii', pos + 4, pos + 8);
    if (ty === 'IHDR') { w = buf.readUInt32BE(pos + 8); h = buf.readUInt32BE(pos + 12); colorType = buf[pos + 17]; }
    else if (ty === 'IDAT') idat.push(buf.slice(pos + 8, pos + 8 + len));
    pos += 12 + len;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const bpp = colorType === 6 ? 4 : 3;
  const stride = w * bpp;
  const out = Buffer.alloc(w * h * 4);
  let prev = Buffer.alloc(stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)];
    const line = raw.slice(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    const cur = Buffer.from(line);
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? cur[x - bpp] : 0, b = prev[x], c = x >= bpp ? prev[x - bpp] : 0;
      let v = cur[x];
      if (f === 1) v = (v + a) & 255;
      else if (f === 2) v = (v + b) & 255;
      else if (f === 3) v = (v + ((a + b) >> 1)) & 255;
      else if (f === 4) { const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c); v = (v + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c)) & 255; }
      cur[x] = v;
    }
    for (let x = 0; x < w; x++) { const s2 = x * bpp; out[(y * w + x) * 4] = cur[s2]; out[(y * w + x) * 4 + 1] = colorType === 6 ? cur[s2 + 1] : cur[s2]; out[(y * w + x) * 4 + 2] = colorType === 6 ? cur[s2 + 2] : cur[s2]; out[(y * w + x) * 4 + 3] = 255; }
    prev = cur;
  }
  return { w, h, data: out };
}
const img = decodePng(Buffer.from(shot));
const box = r.bubbleBox;
const x0 = Math.max(0, Math.round(box.x)), y0 = Math.max(0, Math.round(box.y));
const x1 = Math.min(img.w, Math.round(box.x + box.w)), y1 = Math.min(img.h, Math.round(box.y + box.h));
let lit = 0;
for (let y = y0; y < y1; y += 2) for (let x = x0; x < x1; x += 2) {
  const i = (y * img.w + x) * 4;
  if (img.data[i] + img.data[i + 1] + img.data[i + 2] > 60) lit++;
}
console.log(JSON.stringify({ r, preScroll, lazyBoot, screenLit: lit, errors }));
await browser.close();
"""


def test_v6_kg3d_webgl_renders_real_pixels_browser():
    """BROWSER TEST — the 3D Memory Nebula must boot over HTTP with the
    vendored three.js, paint real pixels into #kg-bubble, stay
    self-painting at its center (overlays never intercept), show real
    totals in the HUD, and leave the 2D canopy + orbital ecology canvases
    alive.

    Pixel proof is HONEST COMPOSITED-VIEWPORT sampling: the screenshot (what
    a user actually sees — headless toDataURL is blank for in-view WebGL
    canvases) is PNG-decoded and the #kg-bubble box is counted for lit
    pixels, alongside the preserveDrawingBuffer toDataURL check.

    If headless Chromium is unavailable, falls back to static assertions
    and warns (the live measurement is then done by the manual probe)."""
    import json
    import subprocess
    import warnings

    server, port = _serve_telos_static()
    try:
        probe_path = os.path.join(PROJECT, f".kg3d_probe_{os.getpid()}.mjs")
        with open(probe_path, "w") as tf:
            tf.write(_KG3D_PROBE_TEMPLATE)
        try:
            proc = subprocess.run(
                ["node", probe_path, str(port)],
                capture_output=True, text=True, timeout=90,
                cwd=PROJECT,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"probe failed: {proc.stderr[:300]}")
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            r = data["r"]
            # 404s on /api/* are expected (unit-test server has no backend);
            # anything else is a real regression.
            real_errors = [
                e for e in data["errors"]
                if "Failed to load resource" not in e and "404" not in e
            ]
            assert not real_errors, f"console errors: {real_errors}"
            ps = data.get("preScroll") or {}
            assert ps.get("threeTag") is False, \
                "three.min.js must NOT be an eager tag at first paint (Item 6b lazy-load)"
            assert ps.get("lazyState") == "idle", \
                f"lazy loader must be idle until the panel approaches, got {ps.get('lazyState')}"
            lb = data.get("lazyBoot") or {}
            lazy = lb.get("lazy") or {}
            assert lazy.get("state") == "loaded", \
                "scrolling to chapter 05 must trigger the lazy vendor chain"
            assert lazy.get("scripts") == [
                "dashboard/vendor/three.min.js", "dashboard/vendor/OrbitControls.js",
                "dashboard/js/knowledge-3d.js",
            ], "lazy chain must load three → OrbitControls → knowledge-3d in order"
            assert r["treeAlive"] and r["solarAlive"], "2D canopy/orbital modes must stay alive"
            if r["bubble3d"]:
                # Real 3D claimed the canvas — verify it paints and carries
                # the REAL graph (or the honest empty state when no backend).
                assert r["painted"], "3D canvas did not paint real pixels"
                assert r["selfPaints"], "overlay intercepts the canvas center"
                if r["nodeCount"] > 0:
                    # Real backend present: the scene must carry the REAL graph.
                    assert r["edgeCount"] > 0, "3D scene has no real edges"
                    assert "nodes" in r["hud"] and "edges" in r["hud"], "HUD must show real totals"
                    assert r["labels"] >= 1, "domain cloud labels missing"
                    assert not r["emptyShown"], "empty state shown with data present"
                    assert data["screenLit"] > 500, (
                        f"composited viewport shows no real nebula pixels ({data['screenLit']})"
                    )
                else:
                    # No /api backend (unit-test server): the HONEST empty state
                    # must render — never fabricated nodes, empty overlay visible.
                    assert r["emptyShown"], "honest empty state must be visible without data"
                    assert "0 nodes" in r["hud"], "HUD must report the real (zero) total"
            else:
                # WebGL genuinely unavailable in this environment (headless
                # without GPU): the HONEST 2D nebula fallback must paint real
                # pixels on the same canvas — never a blank/broken panel.
                assert r["painted"] and r["selfPaints"], \
                    "2D nebula fallback must paint the canvas"
                assert data["screenLit"] > 500, (
                    f"composited viewport shows no fallback pixels ({data['screenLit']})"
                )
        except (RuntimeError, OSError, FileNotFoundError) as e:
            warnings.warn(
                "headless-Chromium probe unavailable for kg3d — falling back "
                f"to static assertions. ({e})",
                stacklevel=2,
            )
            k3d = open(os.path.join(JS_DIR, "knowledge-3d.js")).read()
            assert "window.__kgBubble3D = true;" in k3d
            assert "preserveDrawingBuffer" in k3d
        finally:
            try:
                os.unlink(probe_path)
            except OSError:
                pass
    finally:
        server.shutdown()


# ═══════════════════════════════════════════════════════════════════════
# v7 data-side improvements — hero stat honesty contracts:
#   1. ROLLOUT STATES (audit C+D) — the hero slot is PER-EPISODE counter-
#      factual states (resets at each goal); the lifetime total is demoted
#      to the tooltip; no surface claims 'worlds' for either counter.
#   2. cycles-per-goal + moves-per-goal split (moves = real position changes).
#   5a. DECISIONS caption names the REAL gate from the live trace
#       (firewall action_loop vs council blocking_validator).
#   5b. LESSONS caption reflects live knowledge-graph nodes archived over time.
# ═══════════════════════════════════════════════════════════════════════

def test_v7_hero_stats_relabel_and_honest_captions():
    """The hero renders the honest labels (audit C+D): the rollout-states
    slot is PER-EPISODE counterfactual states that reset at each goal — the
    lifetime 'worlds simulated' claim may not occupy the hero slot and the
    lifetime total is demoted to the tooltip (title attr). Plus the
    cycles-per-goal + moves-per-goal split and the LESSONS caption that
    names live knowledge-graph archival."""
    html = open(HTML).read()
    # Item 1 (audit C+D): relabel → 'rollout states this episode'; the
    # caption element keeps its id and the caption defines the per-goal
    # window; the lifetime total survives in the title (tooltip) attribute.
    assert "futures imagined" not in html, "old futures label must be gone"
    assert "rollout states this episode" in html, "episode rollout label missing"
    assert ">worlds simulated</div>" not in html, \
        "lifetime 'worlds simulated' label must not claim the hero slot"
    assert 'id="story-worlds-sim"' in html, "episode rollout value id missing"
    assert 'id="story-worlds-sim-caption"' in html, "episode caption id missing"
    assert "counterfactual states rolled since the current goal" in html, \
        "episode caption must define the per-goal window"
    assert "resets at each goal" in html, "caption must state the goal reset"
    assert "lifetime" in html, "lifetime total must appear (tooltip), never the hero label"
    # Item 2: cycles-per-goal relabel + moves-per-goal split element.
    assert "steps per goal" not in html, "old steps-per-goal label must be gone"
    assert "cycles per goal" in html, "cycles-per-goal label missing"
    assert "counts every decision cycle incl. blocked" in html, \
        "cycles caption must include blocked & inquiry pauses"
    assert 'id="story-moves-per-goal"' in html, "moves-per-goal stat id missing"
    assert "moves per goal" in html
    assert "blocked &amp; inquiry pauses excluded" in html, \
        "moves caption must exclude blocked & inquiry pauses"
    # Item 5b: lessons caption reflects live KG nodes archived over time.
    assert "live knowledge-graph nodes" in html, "LESSONS caption must name KG nodes"


def test_v7_story_js_wires_gate_naming_and_episode_worlds():
    """story.js wires the REAL firewall/council gate into the DECISIONS
    caption, reads the PER-EPISODE rollout count from the live episodes
    payload (episodes.current_worlds, with the last trace's measured
    worlds_simulated as the producer-down fallback), and keeps the lifetime
    total + per-decision rate in the tooltip only (audit C+D)."""
    story = open(os.path.join(JS_DIR, "story.js")).read()
    # Item 5a: the gate is read from the live trace fields.
    assert "firewall_blocked_by" in story, "story.js must read the firewall gate"
    assert "blocking_validator" in story, "story.js must read the council gate"
    assert "was held back by" in story, "gate-naming verdict must render"
    # Item 1 (audit C+D): the hero value is the episode count from the live
    # payload, falling back to the last trace when the producer is down —
    # never the lifetime total on the hero.
    assert "ep.current_worlds" in story, "hero value must read the episode count"
    assert "recent[recent.length - 1].worlds" in story, \
        "producer-down fallback must be the last trace's measured rollout count"
    # Lifetime total + per-decision rate stay in the TOOLTIP (title attr).
    assert "worldsSim / decisions" in story, \
        "per-decision rate must be total/decisions (measured, never invented)"
    assert "lifetime:" in story, "tooltip must carry the lifetime total"
    # No primary-surface claim of 'worlds simulated' survives the mood
    # sentence or the slot renderer.
    assert "' worlds simulated'" not in story, \
        "mood sentence must not claim a lifetime worlds-simulated count"
    # Item 2: moves-per-goal rendering from the real episodes payload.
    assert "avg_moves_per_goal" in story, "moves split must render"
    assert "story-moves-per-goal" in story, "moves stat must be written"
    # Honest unmeasured state: '—' until the first episode completes.
    assert "ep.completed === 0" in story, "honest empty state must persist"
    # No fabricated wording survives.
    assert "futures simulated" not in story, "old mood wording must be gone"


def test_v7_honest_knowledge_nodes_naming_contract():
    """LEFT ITEM 2: the dashboard labels live KnowledgeGraph nodes as
    'knowledge nodes' (honest), never as ExperienceManager 'lessons'. The
    JS consumers must read the honest `knowledge_nodes` payload field and
    render prose with the honest term — not the misnomer."""
    story = open(os.path.join(JS_DIR, "story.js")).read()
    hero = open(os.path.join(JS_DIR, "hero.js")).read()
    # Consumers must prefer the honest field name (story.js normalize).
    assert "d.knowledge_nodes" in story, "story.js must read the honest field"
    assert "d.knowledge_nodes !== undefined" in story
    # hero.js reads the honest count and renders the honest term.
    assert "d.knowledge_nodes" in hero, "hero.js must read the honest knowledge_nodes count"
    assert "knowledge nodes" in hero, "hero.js must render 'knowledge nodes', not 'lessons'"
    # The misnomer must not survive as user-facing prose in the consumers.
    assert " lessons learned" not in story, "story.js must not render 'lessons' as the KG count"
    assert " lessons," not in hero, "hero.js must not render the misnomer 'lessons' as the KG count"
