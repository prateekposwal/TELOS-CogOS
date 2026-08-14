#!/usr/bin/env python3
"""DOM Contract probe — every getElementById / canvas id the dashboard JS
depends on MUST exist in dashboard.html.

Run:  PYTHONPATH=. python3 telos/tools/dom_contract.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
HTML = os.path.join(PROJECT, "telos", "dashboard.html")
JS_DIR = os.path.join(PROJECT, "telos", "dashboard", "js")

# Canvas ids referenced via variable loops (not literal getElementById).
LOOP_CANVAS_IDS = {
    "kg-tree", "kg-solar", "kg-bubble",      # knowledge-graph.js kgIds
    "brain-orbit", "brain-tree",             # brain-viz.js
    "grid-canvas", "chart-canvas", "health-meter-canvas", "minimap-canvas",
}


def extract_ids(js_text: str) -> set:
    ids = set(LOOP_CANVAS_IDS) if False else set()
    ids |= set(re.findall(r"getElementById\('([^']+)'\)", js_text))
    ids |= set(re.findall(r'getElementById\("([^"]+)"\)', js_text))
    return ids


def extract_onclick(html_text: str) -> set:
    calls = set()
    for m in re.finditer(r"onclick=\"([^\"]+)\"", html_text):
        body = m.group(1)
        for fm in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\(", body):
            calls.add(fm.group(1))
    return calls


def js_function_names(js_text: str) -> set:
    names = set(re.findall(r"^function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", js_text, re.M))
    names |= set(re.findall(r"^async function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", js_text, re.M))
    names |= set(re.findall(r"^\s{0,2}function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", js_text, re.M))
    return names


def main() -> int:
    html = open(HTML).read()
    html_lower = html.lower()

    all_ids: set = set()
    all_functions: set = set()
    for fname in sorted(os.listdir(JS_DIR)):
        if not fname.endswith(".js"):
            continue
        path = os.path.join(JS_DIR, fname)
        text = open(path).read()
        all_ids |= extract_ids(text)
        all_functions |= js_function_names(text)
    # Also include the loop canvas ids directly (they are required targets).
    all_ids |= LOOP_CANVAS_IDS

    missing = sorted(i for i in all_ids if f'id="{i}"' not in html_lower and f"id='{i}'" not in html_lower)
    # onclick handlers referenced in HTML but not defined in any JS file
    html_calls = extract_onclick(html)
    # toggleSidebar/toggleTheme defined in dashboard.js; sendCmd in chat.js etc.
    builtin = {"event", "document", "parseInt", "Math", "getElementById"}
    missing_funcs = sorted(c for c in html_calls - all_functions - builtin if c not in ("if", "return"))

    # Fabrication check: demo.js must not be referenced (it fabricated traces).
    demo_ref = "demo.js" in html_lower or os.path.exists(os.path.join(JS_DIR, "demo.js"))

    print("DOM Contract probe")
    print("=" * 60)
    print(f"JS targets checked : {len(all_ids)}")
    print(f"onclick handlers   : {len(html_calls)}")
    print(f"missing IDs       : {missing if missing else 'NONE'}")
    print(f"missing functions : {missing_funcs if missing_funcs else 'NONE'}")
    print(f"demo.js referenced : {demo_ref}  (must be False — fabrication removed)")
    ok = not missing and not missing_funcs and not demo_ref
    print("RESULT:", "PASS ✅" if ok else "FAIL ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
