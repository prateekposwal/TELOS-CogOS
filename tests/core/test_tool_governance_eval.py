"""
Tool-governance measurement — behavioral channel governance + scorecard linkage.

Locks three things:
  1. the writer's criteria == the scorecard's read criteria (writer/reader
     schema-linkage guard — this project was bitten by key drift repeatedly);
  2. the real sandbox/executor block what they must (measured, not asserted);
  3. the ``tool_use`` score is credited ONLY from a passing, machine-checkable
     artifact (fail closed on missing/malformed/failing).
"""

import json

from telos.core.verifier.capability_scorecard import (
    TOOL_GOVERNANCE_CRITERIA as READER_CRITERIA,
    _score_tool_use,
)
from telos.core.verifier.measurement import provenance
from telos.tools.tool_governance_eval import (
    TOOL_GOVERNANCE_CRITERIA as WRITER_CRITERIA,
    PRODUCER,
    _executor_checks,
    _sandbox_checks,
    _scanner_checks,
)
from telos.tools.tool_channel_scan import scan


def test_writer_reader_criteria_match():
    """The artifact's criteria are locked between writer and reader."""
    assert tuple(WRITER_CRITERIA) == tuple(READER_CRITERIA)
    assert len(READER_CRITERIA) == len(set(READER_CRITERIA))


def test_schema_linkage_against_the_written_artifact():
    """The on-disk artifact carries exactly the criteria the reader requires."""
    import os
    path = os.path.join("telos", "audit", "tool_governance_eval.json")
    if not os.path.isfile(path):
        return  # the eval writes it; skip when not yet generated
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert set(data["criteria"]) == set(READER_CRITERIA)
    assert isinstance(data["verdict"]["passed"], bool)


def test_scanner_reports_no_unknown():
    """Production code carries no unknown ungoverned channel."""
    assert scan()["counts"]["unknown_sites"] == 0


def test_sandbox_and_executor_actually_block():
    """Measured: the real sandbox and executor block the must-block cases."""
    sandbox = _sandbox_checks()
    assert sandbox["sandbox_blocks_unlisted_host"]["passed"]
    assert sandbox["sandbox_blocks_unlisted_route"]["passed"]
    assert sandbox["sandbox_blocks_plain_http_nonloopback"]["passed"]
    assert sandbox["sandbox_blocks_oversized_body"]["passed"]
    assert sandbox["sandbox_allows_declared_loopback"]["passed"]
    executor = _executor_checks()
    assert executor["executor_blocks_unlisted_tool"]["passed"]
    assert executor["executor_blocks_unpermitted_source"]["passed"]
    assert executor["executor_blocks_without_firewall"]["passed"]
    assert executor["executor_blocks_capability_fail"]["passed"]
    assert all(_scanner_checks()[k]["passed"] for k in _scanner_checks())


def _fake_root(tmp_path, artifact):
    """Build a minimal repo root for _score_tool_use.

    Args:
        tmp_path: pytest tmp_path.
        artifact: the artifact dict to write, or None for a missing artifact.

    Returns:
        The root path.
    """
    root = tmp_path
    (root / "telos" / "core" / "actions").mkdir(parents=True)
    (root / "telos" / "audit").mkdir(parents=True)
    (root / "telos" / "core" / "actions" / "executor.py").write_text("")
    if artifact is not None:
        (root / "telos" / "audit" / "tool_governance_eval.json").write_text(
            json.dumps(artifact))
    return str(root)


def _artifact(all_pass=True, provenance_block=True):
    """A valid (or deliberately broken) tool-governance artifact."""
    payload = {
        "criteria": {name: all_pass for name in WRITER_CRITERIA},
        "verdict": {"passed": all_pass, "passed_count": len(WRITER_CRITERIA),
                    "total": len(WRITER_CRITERIA)},
    }
    if provenance_block:
        payload["provenance"] = provenance(PRODUCER, list(WRITER_CRITERIA))
    return payload


def test_score_fails_closed_when_artifact_missing(tmp_path):
    """No artifact ⇒ only the structure base; never a measured score."""
    root = _fake_root(tmp_path, None)
    result = _score_tool_use(root)
    assert result.score == 1.0
    assert result.artifact_backed is False
    assert result.measurement is None


def test_score_fails_closed_when_artifact_malformed(tmp_path):
    """No provenance ⇒ not machine-checkable ⇒ only the structure base."""
    root = _fake_root(tmp_path, _artifact(provenance_block=False))
    result = _score_tool_use(root)
    assert result.score == 1.0
    assert result.artifact_backed is False


def test_score_fails_closed_when_verdict_fails(tmp_path):
    """A structurally valid but FAILING artifact credits no measured points."""
    root = _fake_root(tmp_path, _artifact(all_pass=False))
    result = _score_tool_use(root)
    assert result.score == 1.0
    assert result.artifact_backed is True
    assert any("FAIL" in e for e in result.evidence)


def test_score_credits_only_a_passing_artifact(tmp_path):
    """A passing, machine-checkable artifact earns the measured component."""
    root = _fake_root(tmp_path, _artifact(all_pass=True))
    result = _score_tool_use(root)
    assert result.score == 4.5
    assert result.artifact_backed is True
    assert result.independently_measured is True
    assert result.measurement == "telos/audit/tool_governance_eval.json"
    assert any("registry families" in e for e in result.evidence)
