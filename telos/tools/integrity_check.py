#!/usr/bin/env python3
"""
Integrity Check — TELOS Architecture Scanner

Scans the telos/ codebase for exported classes and verifies they have
consumers outside their own file. Helps detect dead code, orphaned
exports, and misaligned interfaces.

Usage:
    python3 telos/tools/integrity_check.py
    python3 telos/tools/integrity_check.py --fix  (not yet implemented)
"""

import ast
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple


TELOS_ROOT = Path(__file__).resolve().parent.parent
IGNORE_DIRS = {"__pycache__", ".git", "node_modules", "tools"}
IGNORE_FILES = {"__init__.py", "setup.py"}


def find_python_files(root: Path) -> List[Path]:
    """Recursively find all .py files under root, excluding ignored dirs."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored dirs
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for f in filenames:
            if f.endswith(".py") and f not in IGNORE_FILES:
                files.append(Path(dirpath) / f)
    return files


def extract_exported_classes(filepath: Path) -> List[Tuple[str, int]]:
    """
    Extract top-level class definitions from a Python file.
    Returns list of (class_name, line_number).
    """
    try:
        with open(filepath, "r") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"  [WARN] Could not parse {filepath}: {e}")
        return []

    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Skip private classes (starting with _)
            if node.name.startswith("_"):
                continue
            # Skip ABC/abstract base classes
            bases = [b.id if isinstance(b, ast.Name) else None for b in node.bases]
            if "ABC" in bases or "Protocol" in bases:
                continue
            classes.append((node.name, node.lineno))
    return classes


def extract_imported_names(filepath: Path) -> Set[str]:
    """
    Extract all names imported in a file (from ... import ..., import ...).
    Helps find which classes are consumed.
    """
    try:
        with open(filepath, "r") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[-1])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for alias in node.names:
                    names.add(alias.name)
                    full = f"{node.module}.{alias.name}"
                    names.add(full)
    return names


def extract_all_references(filepath: Path) -> Set[str]:
    """
    Extract all name references in a file.
    Helps find which classes are consumed.
    """
    try:
        with open(filepath, "r") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def get_module_path(filepath: Path) -> str:
    """Convert file path to dotted module path."""
    rel = filepath.relative_to(TELOS_ROOT.parent if TELOS_ROOT.name == "telos" else TELOS_ROOT)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]  # remove .py
    return ".".join(parts)


def run_integrity_check() -> Dict[str, List[str]]:
    """
    Scan the codebase and return a dict mapping file paths to
    orphaned classes (defined but never imported outside their own file).
    """
    py_files = find_python_files(TELOS_ROOT)
    print(f"Scanning {len(py_files)} Python files in {TELOS_ROOT}...\n")

    # Map: file_path -> [(class_name, line)]
    file_exports: Dict[Path, List[Tuple[str, int]]] = {}

    # Gather all exported classes per file
    for fpath in py_files:
        classes = extract_exported_classes(fpath)
        if classes:
            file_exports[fpath] = classes

    # Gather all imported names per file (excluding self)
    imported_across_codebase: Set[str] = set()
    for fpath in py_files:
        imported = extract_imported_names(fpath)
        imported_across_codebase.update(imported)

    # Also add references from all files
    all_refs: Set[str] = set()
    for fpath in py_files:
        refs = extract_all_references(fpath)
        all_refs.update(refs)

    # Find orphans: classes exported from a file but never referenced
    # in any other file
    orphans: Dict[str, List[str]] = {}
    all_exported_classes: Set[str] = set()

    for fpath, classes in file_exports.items():
        module = get_module_path(fpath)
        for cls_name, lineno in classes:
            all_exported_classes.add(cls_name)

    # For each exported class, check if it's referenced elsewhere
    for fpath, classes in file_exports.items():
        module = get_module_path(fpath)
        file_orphans = []
        for cls_name, lineno in classes:
            # Check if this name is imported or referenced in any OTHER file
            consumed = False
            for other_fpath in py_files:
                if other_fpath == fpath:
                    continue
                other_imports = extract_imported_names(other_fpath)
                other_refs = extract_all_references(other_fpath)
                if cls_name in other_imports or cls_name in other_refs:
                    consumed = True
                    break

            if not consumed:
                file_orphans.append(f"{cls_name} (line {lineno})")

        if file_orphans:
            orphans[str(fpath.relative_to(TELOS_ROOT))] = file_orphans

    return orphans


def print_report(orphans: Dict[str, List[str]]) -> None:
    """Print a formatted integrity report."""
    print("=" * 72)
    print("  TELOS INTEGRITY CHECK — Class Consumer Analysis")
    print("=" * 72)

    if not orphans:
        print("\n  ✅ All exported classes have consumers. No orphans detected.")
        return

    total_orphans = sum(len(v) for v in orphans.values())
    print(f"\n  ⚠️  Found {total_orphans} potentially orphaned class(es) in {len(orphans)} file(s):\n")

    for filepath, cls_list in sorted(orphans.items()):
        print(f"  📄 {filepath}")
        for cls in cls_list:
            print(f"     🚫 {cls}")
        print()

    print("  NOTE: Some classes may be consumed via dynamic dispatch, ")
    print("  factory patterns, or plugin registration. Manual review required.")
    print()


def main():
    orphans = run_integrity_check()
    print_report(orphans)
    return len(orphans)


if __name__ == "__main__":
    sys.exit(main())
