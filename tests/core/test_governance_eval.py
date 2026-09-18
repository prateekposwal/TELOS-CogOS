"""
Governance evaluation — behavioral measurement + scorecard schema linkage.

The self_governance dimension used to be a four-file existence count. These
tests lock the behaviorally-measured replacement: the harness criteria match
what the scorecard reads, the real governance machinery passes them, and the
scorecard credits measured points ONLY from a provenance-stamped artifact with
a passing verdict (missing/failing -> base only).
"""

import json
import subprocess
import sys
import os

import pytest

from telos.core.verifier.capability_scorecard import (
    GOVERNANCE_CRITERIA, _score_governance,
)
from telos.core.verifier.measurement import provenance
from telos.tools.governance_eval import (
    GOVERNANCE_CRITERIA as WRITER_CRITERIA, evaluate,
)

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODULES = (
    "telos/core/council/base.py",
    "telos/core/governance/firewall.py",
    "telos/core/governance/capability_authorization.py",
    "telos/core/governance/governor.py",
)


def _build_repo(root, artifact=None):
    """Create the minimal repo tree the governance scorer reads.

    Args:
        root: temporary repo root (pathlib.Path).
        artifact: the governance_eval.json payload, or None for none.

    Returns:
        The repo root as a string.
    """
    for module in MODULES:
        path = root / module
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    if artifact is not None:
        out = root / "telos" / "audit" / "governance_eval.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(artifact), encoding="utf-8")
    return str(root)


def _valid_artifact(criteria=None, source="first_party"):
    """Build a valid, passing governance artifact.

    Args:
        criteria: criterion names (defaults to the canonical tuple).
        source: provenance source class.

    Returns:
        The artifact payload.
    """
    names = list(criteria or GOVERNANCE_CRITERIA)
    return {
        "provenance": provenance(
            "telos/tools/governance_eval.py", names, source=source),
        "criteria": {name: True for name in names},
        "verdict": {"passed": True, "passed_count": len(names),
                    "total": len(names)},
    }


# ── writer/reader schema linkage ─────────────────────────────────────────

def test_writer_emits_exactly_the_keys_the_reader_reads():
    """The harness criteria tuple is the one the scorecard requires."""
    assert tuple(WRITER_CRITERIA) == tuple(GOVERNANCE_CRITERIA)


def test_harness_criteria_all_pass():
    """The real governance machinery passes every criterion."""
    result = evaluate()
    assert set(result["criteria"]) == set(GOVERNANCE_CRITERIA)
    assert all(result["criteria"].values()), result["criteria"]
    assert result["verdict"]["passed"] is True
    assert result["verdict"]["passed_count"] == len(GOVERNANCE_CRITERIA)


# ── scorer credits measured points only from a valid artifact ────────────

def test_score_awards_measured_points_when_artifact_passes(tmp_path):
    """A valid passing artifact earns the full behavioral component."""
    root = _build_repo(tmp_path, _valid_artifact())
    result = _score_governance(root)
    assert result.score == 5.0
    assert result.artifact_backed is True
    assert result.independently_measured is True
    assert result.external is False
    assert result.measurement == "telos/audit/governance_eval.json"
    assert any("measured behaviors 11/11" in e for e in result.evidence)


def test_no_credit_without_the_artifact(tmp_path):
    """Missing artifact -> existence-only base, no flags."""
    root = _build_repo(tmp_path, None)
    result = _score_governance(root)
    assert result.score == 1.0
    assert result.artifact_backed is False
    assert result.independently_measured is False
    assert result.external is False
    assert any("no machine-checkable" in e for e in result.evidence)


def test_failing_verdict_withholds_the_measured_component(tmp_path):
    """A present artifact whose verdict FAILs credits only the base."""
    artifact = _valid_artifact()
    artifact["verdict"] = {"passed": False, "passed_count": 1,
                           "total": len(GOVERNANCE_CRITERIA)}
    artifact["criteria"]["low_integrity_blocked"] = False
    root = _build_repo(tmp_path, artifact)
    result = _score_governance(root)
    assert result.score == 1.0
    assert any("verdict FAIL" in e for e in result.evidence)


def test_artifact_without_provenance_gets_no_flags_and_no_measured_points(tmp_path):
    """An artifact lacking required provenance fails closed."""
    root = _build_repo(tmp_path, {
        "criteria": {k: True for k in GOVERNANCE_CRITERIA},
        "verdict": {"passed": True, "passed_count": len(GOVERNANCE_CRITERIA),
                    "total": len(GOVERNANCE_CRITERIA)},
    })
    result = _score_governance(root)
    assert result.score == 1.0
    assert result.artifact_backed is False
    assert result.measurement is None


def test_external_source_earns_the_external_flag(tmp_path):
    """A genuinely out-of-toolchain artifact flips external True."""
    root = _build_repo(tmp_path, _valid_artifact(source="external"))
    result = _score_governance(root)
    assert result.external is True
    assert result.independently_measured is True
    assert result.artifact_backed is True


# ── the harness CLI exits 0 ──────────────────────────────────────────────

def test_harness_ci_exits_zero(tmp_path):
    """`governance_eval.py --ci` exits 0 on a passing run."""
    out = tmp_path / "governance_eval.json"
    proc = subprocess.run(
        [sys.executable, os.path.join(PROJECT, "telos", "tools", "governance_eval.py"),
         "--ci", "--json", str(out)],
        cwd=PROJECT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": PROJECT},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(out.read_text())["verdict"]["passed"] is True
