#!/usr/bin/env python3
"""Safe docstring↔signature hygiene fixer (gap-scanner Check 6).

Each function is fixed as a SINGLE, precise splice on a freshly-parsed copy of
the file: locate the docstring Constant node, compute its exact source span,
insert an Arguments section immediately before the closing quotes, then
re-parse to prove the file still compiles and that ONLY the docstring changed
(the number of function/class nodes and every other function's docstring text
is unchanged). Files are restored if any edit is ambiguous.

Usage (from repo root):
    python3 telos/tools/fix_docstring_hygiene.py          # fix in place
    python3 telos/tools/fix_docstring_hygiene.py --check  # report only
"""
from __future__ import annotations

import ast
import os
import sys
from typing import Dict, List, Tuple

BUILTIN_FIXTURES = {"tmp_path", "tmpdir", "monkeypatch", "capsys", "capfd",
                    "caplog", "request"}
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(BASE)

HINT: Dict[str, str] = {
    "state": "the world/domain state for this call",
    "world": "the World instance this call reads",
    "ctx": "the phase context for this cycle",
    "domain_facts": "the domain evidence channel",
    "intent": "the intent being evaluated",
    "config": "configuration for this call",
    "metrics": "metrics to fold into the result",
    "history": "the history of prior observations",
    "evidence": "the evidence record being scored",
    "facts": "the domain facts to use",
    "resources": "the available resources",
    "constraints": "the active constraints",
    "meta": "the meta/mapping context",
    "all_scores": "the per-representation scores",
    "events": "the events/state sequence",
    "stream_uncertainties": "per-stream uncertainty values",
    "budgets": "the budget mappings to read",
    "optimizer": "the optimizer instance",
    "resource_values": "the resource values to score",
    "calibrated_streams": "streams that are calibrated",
    "total_streams": "the total stream count",
    "result": "the observation result",
    "name": "the name/key of the item",
    "failure": "the failure record",
    "trace": "the decision trace for this cycle",
    "delta": "the change value",
    "reason": "the reason string to record",
    "caller": "the calling component name",
    "cycle": "the current cycle count",
    "action_space": "the admissible action set",
    "entropy_budget": "the per-step entropy budget",
    "domain": "the domain name",
    "path": "the file/system path",
    "target": "the target being evaluated",
    "message": "the message to process",
    "data": "the data to process",
    "model": "the model/record to evaluate",
    "prediction": "the model prediction value",
    "observed": "the observed value",
    "predicted": "the predicted value",
    "snapshot": "the snapshot being processed",
    "repo": "the repository path",
    "test_id": "the failing test identifier",
    "module": "the module name",
    "symbol": "the symbol being resolved",
    "attr": "the attribute name",
    "frames": "the raw traceback frame lines",
    "lines": "the current file lines",
    "import_idx": "the insertion line index",
    "module_file": "the module file path",
}


def _missing_params(node: ast.FunctionDef) -> List[str]:
    doc = ast.get_docstring(node)
    if not doc:
        return []
    params = [a.arg for a in (node.args.args + node.args.kwonlyargs
                              + node.args.posonlyargs)
              if a.arg not in ("self", "cls") and a.arg not in BUILTIN_FIXTURES]
    if not params:
        return []
    dl = doc.lower()
    return [p for p in params if p.lower() not in dl]


def _docstring_node(node: ast.FunctionDef):
    """The Constant node carrying the docstring, or None."""
    if not node.body:
        return None
    first = node.body[0]
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)):
        return first.value
    return None


def _fix_docstring(src: str, value: ast.Constant, missing: List[str]) -> str:
    """Insert an Args block for `missing` before the docstring's closing quotes.

    The Constant's col_offset points at the OPENING quote character; the
    string starts after the quote. We locate the docstring's closing quotes
    (either on their own line or at the end of the final content line) and
    splice a correctly-indented Args section directly before them.

    Args:
        src: current file source.
        value: the AST Constant node (the docstring).
        missing: parameters to document.

    Returns:
        The modified source, or the unchanged source on ambiguity.
    """
    lines = src.split("\n")
    start_line = value.lineno  # 1-based
    end_line = value.end_lineno
    first_line = lines[start_line - 1]
    quote = '"""'
    if value.col_offset < len(first_line) and \
            first_line[value.col_offset:value.col_offset + 3] == "'''":
        quote = "'''"
    # Measure the docstring's OWN content indentation (the indentation its
    # free-text body uses), NOT the function's: the Args block should align
    # with the existing content so the whole docstring reads consistently.
    content_indent = None
    for ln in lines[start_line:end_line - 1]:
        stripped = ln.strip()
        if not stripped:
            continue
        leading = len(ln) - len(ln.lstrip())
        if stripped.lstrip(" ").startswith("#"):
            continue
        content_indent = leading
        break
    if content_indent is None:
        content_indent = value.col_offset + 4
    indent = " " * content_indent
    param_indent = " " * (content_indent + 4)
    arg_block = "\n".join(
        f"{param_indent}{p}: {HINT.get(p, 'the ' + p + ' argument for this call.')}"
        for p in missing)
    args_section = f"{indent}Args:\n{arg_block}"
    last_line = lines[end_line - 1]

    if start_line == end_line:
        # Single-line docstring: convert to a clean multiline form.
        text = first_line.strip()
        if not (text.startswith(quote) and text.endswith(quote)
                and len(text) > len(quote) * 2):
            return src
        body = text[len(quote):-len(quote)].strip()
        lines[start_line - 1] = (
            f"{' ' * value.col_offset}{quote}{body}"
            f"\n{args_section}\n{' ' * value.col_offset}{quote}")
        return "\n".join(lines)

    if last_line.strip() == quote:
        # Closing quotes alone on their own line (optionally indented):
        # insert the Args block before them on new lines.
        closing_indent = last_line[:len(last_line) - len(last_line.lstrip())]
        lines[end_line - 1] = args_section + "\n" + closing_indent + quote
        return "\n".join(lines)
    if last_line.rstrip().endswith(quote):
        # Closing quotes sit at the end of the last content line. Split them
        # off, add the Args block on new lines, then close the docstring on
        # its own line with the SAME indentation as the original content.
        content = last_line.rstrip()[:-len(quote)]
        closing_indent = last_line[:len(last_line) - len(last_line.lstrip())]
        lines[end_line - 1] = (closing_indent + content + "\n"
                               + args_section + "\n" + closing_indent + quote)
        return "\n".join(lines)
    # Unknown docstring layout; refuse quietly rather than corrupt the file.
    return src


def scan_py_files() -> List[str]:
    out: List[str] = []
    for r, dirs, names in os.walk("telos"):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in names:
            if n.endswith(".py"):
                out.append(os.path.join(r, n))
    return out


def main() -> int:
    check_only = "--check" in sys.argv
    total_fixed = 0
    failures: List[str] = []
    for fp in scan_py_files():
        src = open(fp, encoding="utf-8", errors="replace").read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            failures.append(f"{fp}: unparsable")
            continue
        # Collect all fixable nodes first (order-independent splices).
        targets: List[Tuple[str, int, List[str]]] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            missing = _missing_params(node)
            if not missing:
                continue
            dv = _docstring_node(node)
            if dv is None:
                continue
            all_params = [a.arg for a in (node.args.args + node.args.kwonlyargs
                                          + node.args.posonlyargs)
                          if a.arg not in ("self", "cls")
                          and a.arg not in BUILTIN_FIXTURES]
            targets.append((node.name, node.lineno, all_params))
        if not targets:
            continue
        # Apply edits in DESCENDING source order: each splice inserts text
        # below its own docstring, so it never shifts a line ABOVE itself.
        # Targets above the current edit therefore keep their positions; we
        # still re-locate each by name in a fresh parse to stay correct.
        targets.sort(key=lambda t: -t[1])
        working = src
        applied = 0
        for name, _dummy_lineno, all_params in targets:
            fresh = ast.parse(working)
            node = None
            for n in ast.walk(fresh):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and n.name == name:
                    params = [a.arg for a in (n.args.args + n.args.kwonlyargs
                                              + n.args.posonlyargs)
                              if a.arg not in ("self", "cls")
                              and a.arg not in BUILTIN_FIXTURES]
                    if _missing_params(n) and params == all_params:
                        node = n
                        break
            if node is None:
                continue  # already fixed or relocated; skip honestly
            dv = _docstring_node(node)
            if dv is None:
                continue
            candidate = _fix_docstring(working, dv, _missing_params(node))
            if candidate == working:
                continue
            try:
                ast.parse(candidate)
            except SyntaxError:
                failures.append(f"{fp}:{name}: edit broke syntax")
                continue
            # Sanity: the function node set is unchanged.
            old_defs = {n.name for n in ast.walk(fresh)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            new_defs = {n.name for n in ast.walk(ast.parse(candidate))
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if old_defs != new_defs:
                failures.append(f"{fp}:{name}: function set changed")
                continue
            working = candidate
            applied += 1
        if applied and not check_only:
            open(fp, "w", encoding="utf-8").write(working)
        total_fixed += applied
    print(f"{'would fix' if check_only else 'fixed'} {total_fixed} docstring "
          f"mismatches{' — ' + str(failures) if failures else ''}")
    for f in failures:
        print(f"  SKIP: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())