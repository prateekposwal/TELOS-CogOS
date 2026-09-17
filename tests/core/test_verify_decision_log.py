"""
telos-verify — external decision-log audit contract.

The auditor must reward honest, measurable logs and honestly punish missing
evidence; absent axes are reported as None, never imputed.
"""
import json

from telos.core.verifier.decision_log_audit import score_log, as_records, score_decisions
from telos.tools.verify_decision_log import main


def _good(i=0):
    return {"decision_integrity": 0.9, "council_validated": True,
            "budget_consumed_ms": 10.0, "budget_total_ms": 100.0, "cycle_id": i}


def _no_evidence(i=0):
    return {"cycle_id": i}


def test_as_records_shapes():
    assert as_records([{"a": 1}]) == [{"a": 1}]
    assert as_records({"decisions": [{"a": 1}]}) == [{"a": 1}]
    assert as_records({"nope": 1}) == []
    assert as_records("garbage") == []


def test_healthy_log_scores_high():
    r = score_log([_good(i) for i in range(5)])
    assert r["n"] == 5
    assert r["epistemic"] > 0.8
    assert r["computational"] == 1.0
    assert r["governance"] == 1.0
    assert r["grade"] in ("A", "B")


def test_missing_evidence_scores_zero_epistemic():
    r = score_log([_no_evidence(i) for i in range(4)])
    assert r["epistemic"] == 0.0
    assert r["grade"] == "F"


def test_budget_overrun_fails_computational():
    bad = dict(_good(), budget_consumed_ms=500.0, budget_total_ms=100.0)
    r = score_log([bad, bad])
    assert r["computational"] == 0.0


def test_absent_budget_axis_is_none_not_imputed():
    rec = {"decision_integrity": 0.8, "council_validated": True}
    r = score_log([rec])
    assert r["computational"] is None
    assert any("budget" in n for n in r["notes"])


def test_empty_log_is_honest():
    r = score_decisions([])
    assert r["grade"] == "F" and r["composite"] is None


def test_cli_ci_threshold(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps([_good(i) for i in range(5)]))
    assert main(["--json", str(good), "--ci"]) == 0

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([_no_evidence(i) for i in range(5)]))
    assert main(["--json", str(bad), "--ci", "--threshold", "0.5"]) == 1
