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
}

JS_FILES = [
    "dashboard.js", "knowledge-graph.js", "gridworld.js", "brain-viz.js",
    "chart.js", "memory.js", "story.js", "chat.js",
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
    """The landing view must include the three graph panels and the story
    strip as directly-visible DOM (not hidden behind a tab)."""
    html, _ = _load()
    # Story strip present and NOT a data-section (always visible)
    assert 'id="story-strip"' in html
    assert 'data-section="story"' not in html, "story must never be tab-hidden"
    for sid in ("story-decisions", "story-headline", "story-mood",
                "story-domain-chips", "story-edge-chips", "story-recent"):
        assert f'id="{sid}"' in html, f"story element missing: {sid}"
    # Graph wall wraps the three panels; all canvases present
    assert 'class="graph-wall"' in html
    for cid in ("brain-orbit", "brain-tree", "grid-canvas",
                "kg-tree", "kg-solar", "kg-bubble"):
        assert f'id="{cid}"' in html, f"graph canvas missing: {cid}"
    # No canvas may start hidden in the markup
    assert 'style="display:none"' not in html.split('<main')[1].split('</main>')[0]
