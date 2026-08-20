#!/usr/bin/env python3
"""
TELOS Gap Scanner — Comprehensive codebase health check.

Scans the TELOS codebase for:
 1. Dead code (classes/functions defined but never referenced elsewhere)
 2. Import health (syntax errors, circular imports)
 3. VISION_v2 component cross-reference
 4. Test coverage
 5. AGENTS.md file cross-reference
 6. Docstring vs signature mismatches

Usage:
    python3 telos/tools/gap_scanner.py                 # full-codebase scan
    python3 telos/tools/gap_scanner.py --staged        # scan only staged files (pre-commit)
"""

import ast
import os
import re
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TELOS_DIR = BASE_DIR / "telos"
TESTS_DIR = BASE_DIR / "tests"

EXCLUDE_DIRS_WALK = {"__pycache__"}
EXCLUDE_DIRS_CHECK = {"telos/benchmarks/data", "telos/audit"}
EXCLUDE_FROM_DEAD_CODE = {"telos/tools", "telos/benchmarks"}

# Framework dispatch methods: reached by the runtime via name-based dispatch
# (BaseHTTPRequestHandler.do_GET/log_message, Thread.run, browser WS handlers),
# so they never appear at a source call site. Flagging them as dead code is a
# false positive — they are reachable, just not by an explicit call.
FRAMEWORK_DISPATCH_METHODS = {
    "do_GET", "do_POST", "do_PUT", "do_DELETE", "do_HEAD", "do_OPTIONS",
    "log_message", "end_headers", "send_head", "translate_path",
    "run",  # threading.Thread / multiprocessing.Process
    "onmessage", "onclose", "onerror",  # browser WebSocket handlers
}

all_pass = True


def print_check(n, name):
    print(f"\n{'=' * 60}")
    print(f"CHECK {n}: {name}")
    print(f"{'=' * 60}")


def rel_path(filepath):
    return os.path.relpath(filepath, str(BASE_DIR))


def get_all_py_files(exclude_dirs=None):
    if exclude_dirs is None:
        exclude_dirs = EXCLUDE_DIRS_CHECK
    files = []
    for root, dirs, fnames in os.walk(str(TELOS_DIR)):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS_WALK]
        rel = os.path.relpath(root, str(BASE_DIR))
        skip = False
        for e in exclude_dirs:
            if rel == e or rel.startswith(e + "/"):
                skip = True
                break
        if skip:
            continue
        for fname in fnames:
            if fname.endswith(".py"):
                files.append(os.path.join(root, fname))
    return sorted(files)


def _all_test_py_files():
    """Return all .py files under the tests/ tree (for reference scans)."""
    tests_root = os.path.join(BASE_DIR, "tests")
    files = []
    if not os.path.isdir(tests_root):
        return files
    for root, dirs, fnames in os.walk(tests_root):
        for fname in fnames:
            if fname.endswith(".py"):
                files.append(os.path.join(root, fname))
    return sorted(files)


def get_staged_py_files():
    """Return staged .py files (git diff --cached). Used by --staged mode so the
    pre-commit gate checks NEW code only, not legacy debt (G-01)."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=10,
        ).stdout
        staged = [os.path.join(BASE_DIR, l.strip()) for l in out.splitlines()
                  if l.strip().endswith(".py") and os.path.exists(os.path.join(BASE_DIR, l.strip()))]
        return sorted(staged)
    except Exception:
        return []


SCAN_FILES = []  # populated in main(); full repo or staged set


def get_module_name(filepath):
    rel = rel_path(filepath)
    rel = rel.replace(".py", "").replace("/", ".")
    return rel


def parse_ast(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
        return tree, None, source
    except SyntaxError as e:
        return None, f"SyntaxError at line {e.lineno}: {e.msg}", None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", None


# ─────────────────────────────────────────────────────────
# CHECK 1: Dead Code Detection
# ─────────────────────────────────────────────────────────

def check_dead_code():
    print_check(1, "Dead Code Detection")

    py_files = SCAN_FILES
    definitions = {}      # fp -> {name: (kind, def_count)}
    name_to_files = defaultdict(set)

    for fp in py_files:
        tree, err, source = parse_ast(fp)
        if err or tree is None:
            continue
        defs = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue
                # Test classes are pytest-discovered by name, not called in source.
                if node.name.startswith("Test") and "test_" in fp:
                    continue
                kind, cnt = defs.get(node.name, ("class", 0))
                defs[node.name] = (kind, cnt + 1)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue
                # Test functions are pytest-discovered by name, never called in
                # source — flagging them as dead code is a false positive.
                if node.name.startswith("test_") and "test_" in fp:
                    continue
                kind, cnt = defs.get(node.name, ("function", 0))
                defs[node.name] = (kind, cnt + 1)
        definitions[fp] = defs
        for name in defs:
            name_to_files[name].add(fp)

    # Reference scan: evaluate against the WHOLE repo (not just staged files) so
    # a name used in a non-staged file (a test, a base class, an external caller)
    # is not misreported as dead code in staged mode. Staged mode only limits
    # which definitions are REPORTED, never which references count.
    all_py = sorted(get_all_py_files() + [os.path.join(p) for p in _all_test_py_files()])
    occ = defaultdict(int)   # name -> total occurrences across the repo
    for fp in all_py:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        for name in list(name_to_files.keys()):
            pattern = re.compile(r'\b' + re.escape(name) + r'\b')
            n = len(pattern.findall(content))
            if n:
                name_to_files[name].add(fp)
                occ[name] += n

    dead = []
    for fp, defs in definitions.items():
        rp = rel_path(fp)
        if any(rp.startswith(e) for e in EXCLUDE_FROM_DEAD_CODE):
            continue
        for name, (kind, def_count) in defs.items():
            # Framework dispatch methods are runtime-reachable by name, never
            # called at a source site — treat them as used (see Λ2.3: the
            # scanner must not manufacture false positives).
            if kind == "function" and name in FRAMEWORK_DISPATCH_METHODS:
                continue
            # Used if it appears in more than one file, or in its own file more
            # times than it is defined there (i.e. real call sites exist).
            in_other_file = len(name_to_files.get(name, {fp}) - {fp}) > 0
            used_in_own_file = occ.get(name, 0) > def_count
            if not in_other_file and not used_in_own_file:
                dead.append(f"{kind} '{name}' in {rp}")

    if dead:
        for item in dead:
            print(f"  \u2717 FAIL: {item}")
        return False
    else:
        print(f"  \u2713 PASS: no dead code detected")
        return True

    if dead:
        for item in dead:
            print(f"  \u2717 FAIL: {item}")
        return False
    else:
        print(f"  \u2713 PASS: no dead code detected")
        return True


# ─────────────────────────────────────────────────────────
# CHECK 2: Import Health
# ─────────────────────────────────────────────────────────

def check_import_health():
    print_check(2, "Import Health")

    py_files = SCAN_FILES
    errors = []
    import_graph = defaultdict(set)
    module_map = {}

    for fp in py_files:
        tree, err, source = parse_ast(fp)
        if err:
            errors.append(f"{rel_path(fp)}: {err}")
            continue
        if tree is None:
            continue

        mod_name = get_module_name(fp)
        module_map[mod_name] = fp
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    import_graph[mod_name].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_graph[mod_name].add(node.module)

    tracked = set(module_map.keys())
    cycles = set()

    def dfs(start, current, visited, path):
        if current in path:
            idx = path.index(current)
            cycle = path[idx:] + [current]
            cycles.add(" -> ".join(cycle))
            return
        if current in visited:
            return
        visited.add(current)
        path.append(current)
        for dep in import_graph.get(current, set()):
            if dep in tracked:
                dfs(start, dep, visited, path[:])
        visited.discard(current)

    for mod in tracked:
        dfs(mod, mod, set(), [])

    passed = True
    if errors:
        for e in errors:
            print(f"  \u2717 FAIL: {e}")
        passed = False
    if cycles:
        for c in sorted(cycles):
            print(f"  \u2717 FAIL: Circular import: {c}")
        passed = False
    if passed:
        print(f"  \u2713 PASS: all files compile, no circular imports")
    return passed


# ─────────────────────────────────────────────────────────
# CHECK 3: VISION_v2 Cross-Reference
# ─────────────────────────────────────────────────────────

def check_vision_v2():
    print_check(3, "VISION_v2 Cross-Reference")

    if "--staged" in sys.argv[1:]:
        print("  ✓ SKIP (staged mode — repo-wide check, not per-file)")
        return True

    vision_path = TELOS_DIR / "VISION_v2.md"
    if not vision_path.exists():
        print(f"  \u2717 FAIL: VISION_v2.md not found")
        return False

    with open(vision_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    # 1. Extract paths from **Implemented:** and **Implemented (proposal):**
    impl_paths = set()
    for line in lines:
        for m in re.finditer(r"\*\*Implemented[^:]*:\*\*\s*`([^`]+)`", line):
            impl_paths.add(m.group(1))

    # 2. Extract component names from Integration Map (code block)
    component_names = set()
    in_code_block = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block and "→" in line:
            for m in re.finditer(r"→\s+(\w+)", line):
                name = m.group(1)
                if name[0].isupper() and name not in ("New", "Component"):
                    component_names.add(name)

    # 3. Extract file paths from markdown tables
    table_paths = set()
    for line in lines:
        if line.strip().startswith("|"):
            for m in re.finditer(r"`([^`]+)`", line):
                table_paths.add(m.group(1))

    # Filter to Python file paths
    all_paths = impl_paths | table_paths
    check_paths = set()
    for p in all_paths:
        p = p.strip()
        if p.endswith(".py") and (p.startswith("telos/") or p.startswith("tests/") or p.startswith("archive/")):
            check_paths.add(p)

    # Read runtime.py and pipeline_finalize.py once
    runtime_path = TELOS_DIR / "core" / "runtime.py"
    pipeline_path = TELOS_DIR / "core" / "pipeline_finalize.py"
    if runtime_path.exists():
        runtime_content = runtime_path.read_text(encoding="utf-8")
    else:
        runtime_content = ""
    if pipeline_path.exists():
        pipeline_content = pipeline_path.read_text(encoding="utf-8")
    else:
        pipeline_content = ""

    # Identify files marked as ARCHIVED in the table
    archived_lines = set()
    for line in lines:
        if "ARCHIVED" in line or "\U0001f5d1" in line:
            for m in re.finditer(r"`([^`]+)`", line):
                archived_lines.add(m.group(1))

    missing_files = []
    not_imported_or_wired = []

    for p in sorted(check_paths):
        full = BASE_DIR / p
        if not full.exists():
            if p not in archived_lines:
                missing_files.append(p)
            continue
        # skip self-reference: runtime.py does not need to import itself
        if p == "telos/core/runtime.py":
            continue
        mod_path = p.replace(".py", "").replace("/", ".")
        if mod_path not in runtime_content and mod_path not in pipeline_content:
            basename = os.path.basename(p).replace(".py", "")
            if basename not in runtime_content and basename not in pipeline_content:
                not_imported_or_wired.append(p)

    # Check component names against filesystem
    all_py_basenames = set()
    for fp in SCAN_FILES:
        base = os.path.basename(fp).replace(".py", "").lower()
        all_py_basenames.add(base)

    component_not_found = []
    all_defs = set()
    for fp in SCAN_FILES:
        tree, err, source = parse_ast(fp)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                all_defs.add(node.name)

    for name in sorted(component_names):
        if name in all_defs:
            continue
        slug = name.lower()
        found = any(slug == b or slug.startswith(b) or b.startswith(slug) for b in all_py_basenames)
        if not found:
            component_not_found.append(name)

    passed = True
    if missing_files:
        for f in missing_files:
            print(f"  \u2717 FAIL: Missing from filesystem: {f}")
        passed = False
    if not_imported_or_wired:
        for f in not_imported_or_wired:
            print(f"  \u2717 FAIL: Not imported/wired in runtime.py/pipeline_finalize.py: {f}")
        passed = False
    if component_not_found:
        for c in component_not_found:
            print(f"  \u2717 FAIL: Component not found on filesystem: {c}")
        passed = False
    if passed:
        print(f"  \u2713 PASS: all VISION_v2 references resolved")
    return passed


# ─────────────────────────────────────────────────────────
# CHECK 4: Test Coverage
# ─────────────────────────────────────────────────────────

def check_test_coverage():
    print_check(4, "Test Coverage")

    if "--staged" in sys.argv[1:]:
        print("  ✓ SKIP (staged mode — repo-wide check, not per-file)")
        return True

    core_files = []
    for root, dirs, fnames in os.walk(str(TELOS_DIR / "core")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in fnames:
            if fname.endswith(".py") and fname != "__init__.py":
                fullpath = os.path.join(root, fname)
                rel = os.path.relpath(fullpath, str(TELOS_DIR / "core"))
                core_files.append((rel, fullpath))

    test_files_core = set()
    if (TESTS_DIR / "core").exists():
        for fname in os.listdir(str(TESTS_DIR / "core")):
            if fname.endswith(".py") and fname.startswith("test_"):
                test_files_core.add(fname)

    test_files_root = set()
    if TESTS_DIR.exists():
        for fname in os.listdir(str(TESTS_DIR)):
            if fname.endswith(".py") and fname.startswith("test_"):
                test_files_root.add(fname)

    untested = []
    for rel, fullpath in sorted(core_files):
        mod_basename = os.path.basename(rel).replace(".py", "")
        test_name = f"test_{mod_basename}.py"
        if test_name not in test_files_root and test_name not in test_files_core:
            with open(fullpath, "r", encoding="utf-8") as f:
                content = f.read()
            if "def test_" not in content:
                untested.append(f"core/{rel}")

    passed = True
    if untested:
        for u in untested:
            print(f"  \u2717 FAIL: No test file for {u}")
        passed = False
    else:
        print(f"  \u2713 PASS: all core modules have test files")

    print()
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-q", "--tb=no"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": str(BASE_DIR)},
        )
        lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        tail = "\n".join(lines[-3:]) if len(lines) >= 3 else result.stdout.strip()
        err_lines = [l for l in result.stderr.strip().split("\n") if l.strip()]
        if err_lines:
            err_tail = "\n".join(err_lines[-3:]) if len(err_lines) >= 3 else result.stderr.strip()
            tail += "\n" + err_tail
        print(f"  pytest: {tail.strip()}")
        if result.returncode != 0:
            passed = False
    except subprocess.TimeoutExpired:
        print(f"  pytest: TIMEOUT after 120s")
        passed = False
    except FileNotFoundError:
        print(f"  \u26a0 WARN: pytest not found, skipping")
    except Exception as e:
        print(f"  \u26a0 WARN: pytest error: {e}")

    return passed


# ─────────────────────────────────────────────────────────
# CHECK 5: AGENTS.md Cross-Reference
# ─────────────────────────────────────────────────────────

def check_agents_md():
    print_check(5, "AGENTS.md Cross-Reference")

    agents_path = BASE_DIR / "AGENTS.md"
    if not agents_path.exists():
        print(f"  \u2717 FAIL: AGENTS.md not found")
        return False

    with open(agents_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    file_paths = set()
    module_refs = set()

    for line in lines:
        for m in re.finditer(r"telos/[\w./-]+\.py", line):
            file_paths.add(m.group(0).rstrip('`').rstrip(')').rstrip('.'))
        for m in re.finditer(r"telos\.[\w.]+", line):
            module_refs.add(m.group(0).rstrip('`').rstrip(')').rstrip('.'))
        for m in re.finditer(r"python3\s+(telos/\S+)", line):
            file_paths.add(m.group(1).rstrip('`').rstrip(')'))
        if "telos_task.py" in line:
            file_paths.add("telos_task.py")

    missing_files = []
    for p in sorted(file_paths):
        full = BASE_DIR / p
        if not full.exists():
            missing_files.append(p)

    missing_modules = []
    for m in sorted(module_refs):
        parts = m.split(".")
        # Try to find as a file
        candidate = "/".join(parts) + ".py"
        full = BASE_DIR / candidate
        # Guard improvement: a dotted reference may name a PACKAGE (directory
        # with __init__.py) rather than a flat .py file — e.g. telos.benchmarks.
        # Resolve packages so AGENTS.md `python3 -m telos.benchmarks.demo` style
        # references do not false-positive as missing modules.
        if full.is_file():
            continue
        pkg_dir = BASE_DIR / "/".join(parts)
        if (pkg_dir / "__init__.py").is_file():
            continue
        # Try as a module within telos
        if parts[0] == "telos":
            candidate2 = "/".join(parts[1:]) + ".py"
            full2 = TELOS_DIR / candidate2
            if full2.is_file():
                continue
            pkg_dir2 = TELOS_DIR / "/".join(parts[1:])
            if (pkg_dir2 / "__init__.py").is_file():
                continue
            missing_modules.append(m)

    passed = True
    if missing_files:
        for f in missing_files:
            print(f"  \u2717 FAIL: Missing file: {f}")
        passed = False
    if missing_modules:
        for m in missing_modules:
            print(f"  \u2717 FAIL: Module not found: {m}")
        passed = False
    if passed:
        print(f"  \u2713 PASS: all AGENTS.md references exist")
    return passed


# ─────────────────────────────────────────────────────────
# CHECK 6: Docstring vs Signature
# ─────────────────────────────────────────────────────────

def check_docstring_signature():
    print_check(6, "Docstring vs Signature Mismatch")

    py_files = SCAN_FILES
    mismatches = []

    for fp in py_files:
        tree, err, source = parse_ast(fp)
        if tree is None:
            continue

        rp = rel_path(fp)
        # Collect pytest fixture names in this file so fixture params (which are
        # injected by pytest, not documented arguments) are not flagged.
        fixture_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.decorator_list:
                for dec in node.decorator_list:
                    dname = None
                    if isinstance(dec, ast.Name):
                        dname = dec.id
                    elif isinstance(dec, ast.Call):
                        f = dec.func
                        if isinstance(f, ast.Name):
                            dname = f.id
                        elif isinstance(f, ast.Attribute):
                            dname = f.attr
                    if dname in ("fixture",):
                        fixture_names.add(node.name)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("__") and node.name.endswith("__"):
                continue

            docstring = ast.get_docstring(node)
            if not docstring:
                continue

            sig_params = []
            for arg in node.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                if arg.arg in fixture_names:
                    continue
                sig_params.append(arg.arg)
            for arg in node.args.kwonlyargs:
                if arg.arg in fixture_names:
                    continue
                sig_params.append(arg.arg)
            for arg in node.args.posonlyargs:
                if arg.arg in ("self", "cls"):
                    continue
                if arg.arg in fixture_names:
                    continue
                sig_params.append(arg.arg)

            if not sig_params:
                continue

            doc_lower = docstring.lower()
            flagged = [p for p in sig_params if p not in doc_lower]
            if flagged:
                mismatches.append(f"{rp}:{node.lineno} '{node.name}' \u2014 params not in docstring: {', '.join(flagged)}")

    passed = True
    if mismatches:
        for m in mismatches[:10]:
            print(f"  \u2717 FAIL: {m}")
        if len(mismatches) > 10:
            print(f"  ... and {len(mismatches) - 10} more")
        passed = False
    else:
        print(f"  \u2713 PASS: all docstrings match signatures")
    return passed


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

def main():
    global SCAN_FILES
    staged_mode = "--staged" in sys.argv[1:]
    SCAN_FILES = get_staged_py_files() if staged_mode else get_all_py_files()
    if staged_mode:
        print(f"STAGED MODE: scanning {len(SCAN_FILES)} staged Python file(s)")

    checks = [
        ("Dead Code Detection", check_dead_code),
        ("Import Health", check_import_health),
        ("VISION_v2 Cross-Reference", check_vision_v2),
        ("Test Coverage", check_test_coverage),
        ("AGENTS.md Cross-Reference", check_agents_md),
        ("Docstring vs Signature Mismatch", check_docstring_signature),
    ]

    results = []
    for name, func in checks:
        try:
            results.append(func())
        except Exception as e:
            print(f"  \u2717 FAIL: {name} crashed: {e}")
            results.append(False)

    print(f"\n{'=' * 60}")
    passed = all(results)
    if passed:
        print("RESULT: ALL CHECKS PASSED")
    else:
        failed = sum(1 for r in results if not r)
        total = len(results)
        print(f"RESULT: {failed}/{total} check(s) FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
