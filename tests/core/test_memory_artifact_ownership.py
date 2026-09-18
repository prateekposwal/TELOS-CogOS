"""
Evidence-artifact ownership — the live producer must never clobber measured
memory-consumption evidence.

The capability scorecard's memory point reads
``telos/audit/memory_consumption.json``. A background producer writing that same
path would replace a measured 120-cycle run with a dashboard restart's partial
counts, silently degrading the evidence. The producer therefore owns a runtime
path, and the measurement run owns the evidence path. This test locks that.
"""

import ast
import os

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRODUCER = os.path.join(PROJECT, "telos", "dashboard", "producer.py")
EVIDENCE = os.path.join(PROJECT, "telos", "audit", "memory_consumption.json")


def _producer_source() -> str:
    with open(PRODUCER, encoding="utf-8") as f:
        return f.read()


def _string_literals(src: str):
    """Yield every non-docstring string literal in the module."""
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                yield node.value


def test_producer_does_not_reference_the_evidence_artifact():
    """producer.py must not USE the evidence path in code (docs may mention it).

    Only string literals outside docstrings count: a prose explanation of the
    separation is fine, a path used in open()/assignment is not.
    """
    src = _producer_source()
    for literal in _string_literals(src):
        assert "memory_consumption.json" not in literal, \
            f"producer uses the measured evidence path in code: {literal!r}"


def test_producer_writes_a_separate_live_stats_path():
    """The producer owns a distinct runtime path for its live stats."""
    src = _producer_source()
    assert "LIVE_MEMORY_STATS_PATH" in src
    assert "/tmp/telos_memory_live_stats.json" in src


def test_measurement_run_owns_the_evidence_path():
    """The measurement tool writes the evidence artifact."""
    path = os.path.join(PROJECT, "telos", "tools", "memory_consumption_run.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "telos" in src and "audit" in src and "memory_consumption.json" in src


def test_evidence_artifact_reports_a_source_when_present():
    """If evidence exists, it names an explicit measurement source."""
    if not os.path.isfile(EVIDENCE):
        return
    import json
    with open(EVIDENCE, encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("source") in (
        "memory_consumption_run", "runtime_pipeline",
    ), data.get("source")


def test_producer_parses_and_defines_no_evidence_path_constant():
    """producer.py parses cleanly and defines no evidence-path constant."""
    src = _producer_source()
    ast.parse(src)
    assert "MEMORY_CONSUMPTION_PATH" not in src
