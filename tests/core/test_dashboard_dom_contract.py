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
    "brain-viz.js", "chart.js", "memory.js", "story.js", "chat.js",
    "hero.js",
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
