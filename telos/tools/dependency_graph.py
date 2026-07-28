#!/usr/bin/env python3
"""
TELOS Dependency Graph Tool.

Builds a directed dependency graph from import statements in telos/**/*.py and finds:
  - Circular dependencies
  - Orphan modules (files with zero incoming imports)
  - Top 10 most imported modules

Usage:
    python3 telos/tools/dependency_graph.py

Exit code:
    0 — no circular dependencies found
    1 — circular dependencies exist
"""

import ast
import os
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TELOS_DIR = BASE_DIR / "telos"

EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_DIRS_CHECK = {"telos/benchmarks/data"}
EXCLUDE_ORPHAN_PREFIXES = {
    "telos/tools",
    "telos/benchmarks",
    "telos/serve_dashboard.py",
    "telos_task.py",
}


def get_all_py_files():
    files = []
    for root, dirs, fnames in os.walk(str(TELOS_DIR)):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel = os.path.relpath(root, str(BASE_DIR))
        skip = False
        for e in EXCLUDE_DIRS_CHECK:
            if rel == e or rel.startswith(e + "/"):
                skip = True
                break
        if skip:
            continue
        for fname in fnames:
            if fname.endswith(".py"):
                files.append(os.path.join(root, fname))
    return sorted(files)


def rel_path(filepath):
    return os.path.relpath(filepath, str(BASE_DIR))


def module_to_filepath(mod_name):
    stripped = mod_name
    for prefix in ("telos.", "telos"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]
            break
    rel = stripped.replace(".", "/") + ".py"
    candidate = TELOS_DIR / rel
    if candidate.exists():
        return str(candidate)
    alt_rel = "telos/" + rel
    candidate2 = BASE_DIR / alt_rel
    if candidate2.exists():
        return str(candidate2)
    init_rel = stripped.replace(".", "/") + "/__init__.py"
    candidate3 = TELOS_DIR / init_rel
    if candidate3.exists():
        return str(candidate3)
    alt_init = "telos/" + init_rel
    candidate4 = BASE_DIR / alt_init
    if candidate4.exists():
        return str(candidate4)
    return None


def _in_type_checking_block(node, tree):
    """Check if an AST node is inside an `if TYPE_CHECKING:` block."""
    for parent in ast.walk(tree):
        if isinstance(parent, ast.If):
            test = parent.test
            if (isinstance(test, ast.Name) and test.id == 'TYPE_CHECKING'):
                for child in ast.walk(parent):
                    if child is node:
                        return True
    return False


def extract_imports(filepath):
    imports = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if _in_type_checking_block(node, tree):
                continue
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if _in_type_checking_block(node, tree):
                continue
            if node.module and node.level == 0:
                imports.add(node.module)
    return imports


def build_graph(py_files):
    file_to_module = {}
    module_to_file = {}
    for fp in py_files:
        mod = rel_path(fp).replace(".py", "").replace("/", ".")
        file_to_module[fp] = mod
        module_to_file[mod] = fp

    adjacency = defaultdict(set)
    reverse = defaultdict(set)

    for fp in py_files:
        src_mod = file_to_module[fp]
        for imported in extract_imports(fp):
            dst_fp = module_to_filepath(imported)
            if dst_fp and dst_fp in file_to_module:
                dst_mod = file_to_module[dst_fp]
                if src_mod != dst_mod:
                    adjacency[src_mod].add(dst_mod)
                    reverse[dst_mod].add(src_mod)

    return adjacency, reverse, file_to_module, module_to_file


def find_circular_dependencies(adjacency, file_to_module):
    visited = set()
    cycles = []

    def dfs(node, path):
        visited.add(node)
        path.append(node)
        for neighbor in adjacency.get(node, set()):
            if neighbor not in visited:
                if dfs(neighbor, path):
                    return True
            elif neighbor in path:
                idx = path.index(neighbor)
                cycle = path[idx:] + [neighbor]
                fp_cycle = [file_to_module.get(m, m).replace(".", "/") + ".py" for m in cycle]
                cycles.append(" -> ".join(fp_cycle))
                return True
        path.pop()
        return False

    all_nodes = set(adjacency.keys())
    for node in adjacency:
        for dep in adjacency[node]:
            all_nodes.add(dep)

    for node in sorted(all_nodes):
        if node not in visited:
            dfs(node, [])

    return cycles


def find_orphan_modules(reverse, file_to_module, module_to_file):
    all_modules = set(file_to_module.values())
    imported = set(reverse.keys())
    orphan_mods = all_modules - imported

    result = []
    for mod in sorted(orphan_mods):
        fp = module_to_file.get(mod)
        if fp is None:
            for m, f in file_to_module.items():
                if f == mod:
                    fp = m
                    break
        if fp:
            rp = rel_path(fp)
            skip = False
            for prefix in EXCLUDE_ORPHAN_PREFIXES:
                if rp == prefix or rp.startswith(prefix + "/"):
                    skip = True
                    break
            if not skip:
                result.append(rp)
    return result


def find_most_imported(reverse, module_to_file):
    counts = {mod: len(deps) for mod, deps in reverse.items()}
    sorted_mods = sorted(counts.items(), key=lambda x: -x[1])
    result = []
    for mod, count in sorted_mods[:10]:
        fp = module_to_file.get(mod)
        if fp:
            rp = rel_path(fp)
            result.append((rp, count))
    return result


def main():
    py_files = get_all_py_files()
    adjacency, reverse, file_to_module, module_to_file = build_graph(py_files)

    print("=== Circular Dependencies ===")
    cycles = find_circular_dependencies(adjacency, file_to_module)
    if cycles:
        for c in cycles:
            print(f"  Cycle: {c}")
    else:
        print("  No circular dependencies found.")
    print()

    print("=== Orphan Modules (0 incoming imports) ===")
    orphans = find_orphan_modules(reverse, file_to_module, module_to_file)
    if orphans:
        for o in orphans:
            print(f"  {o}")
    else:
        print("  No orphan modules found.")
    print()

    print("=== Top 10 Most Imported Modules ===")
    top = find_most_imported(reverse, module_to_file)
    if top:
        for i, (rp, count) in enumerate(top, 1):
            print(f"  {i}. {rp} \u2014 imported by {count} files")
    else:
        print("  No import relationships found.")

    return 1 if cycles else 0


if __name__ == "__main__":
    sys.exit(main())
