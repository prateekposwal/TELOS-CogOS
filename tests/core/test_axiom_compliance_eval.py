"""
Live axiom-compliance evaluation — schema, fail-closed verdict, determinism.

This harness measures per-cycle axiom compliance of the REAL pipeline. These
tests lock the three properties the task requires:

  * writer <-> reader schema linkage: the artifact `summarize`/`evaluate`
    writes is readable by the same `read_measurement` contract the scorecard
    uses (this repo has been bitten by writer/reader key drift before);
  * the verdict is FAIL-CLOSED: missing cycles, missing traces, or an
    incomplete axiom set can never produce a passing verdict;
  * a genuinely degraded measurement is NOT smoothed into a green number;
  * the real-pipeline run is deterministic enough to be repeatable (two
    identical-seed runs produce the same per-cycle fingerprint).
"""
import json

import pytest

from telos.core.axioms.registry import AXIOM_IDS
from telos.core.verifier.measurement import provenance, read_measurement
from telos.tools import axiom_compliance_eval as ace


def _record(failed):
    """Build a complete (42-id) per-cycle record with `failed` failing."""
    failed = sorted(failed)
    return {
        "passed": len(AXIOM_IDS) - len(failed),
        "failed": failed,
        "axiom_ids": list(AXIOM_IDS),
        "reasons": {aid: f"reason for {aid}" for aid in failed},
    }


def _payload(records, requested):
    p = ace.summarize(records, requested, "fast", 42)
    p["provenance"] = provenance(ace.PRODUCER, ace.CRITERIA)
    return p


def test_canonical_axiom_count_is_42():
    assert ace.EXPECTED_AXIOMS == 42
    assert len(AXIOM_IDS) == 42


def test_summarize_schema_matches_reader(tmp_path):
    failed = ["2.7", "4.5", "4.8", "4.9", "4.10", "4.11",
              "6.3", "6.4", "6.5", "6.6", "6.7", "6.8", "6.9", "6.10"]
    records = [_record(failed), _record([])]
    payload = _payload(records, 2)

    # Every field the task requires is present with the right type.
    for key in ("cycles", "cycles_with_trace", "mean_compliance",
                "min_compliance", "p10_compliance", "worst_failed_axioms",
                "healthy_cycles", "degraded_cycles", "verdict", "criteria"):
        assert key in payload, f"missing artifact key: {key}"
    assert isinstance(payload["worst_failed_axioms"], list)
    assert payload["mean_compliance"] == pytest.approx((42 + 28) / 2 / 42)
    assert payload["healthy_cycles"] == 1
    assert payload["degraded_cycles"] == 1

    # Writer <-> reader linkage: the scorecard's contract accepts the file.
    out = tmp_path / "axiom_compliance.json"
    out.write_text(json.dumps(payload))
    measured = read_measurement(str(tmp_path), "axiom_compliance.json",
                                tuple(ace.CRITERIA))
    assert measured is not None
    assert measured.verdict_passed is True
    assert set(measured.criteria) == set(ace.CRITERIA)
    assert all(measured.criteria.values())


def test_verdict_fail_closed_on_no_cycles():
    payload = _payload([], 5)
    assert payload["criteria"]["cycles_measured"] is False
    assert payload["criteria"]["traces_present"] is False
    assert payload["criteria"]["axiom_set_complete"] is False
    assert ace.ci_ok(payload) is False


def test_verdict_fail_closed_on_missing_traces():
    payload = _payload([None, None], 2)
    assert payload["criteria"]["cycles_measured"] is False
    assert payload["criteria"]["traces_present"] is False
    assert ace.ci_ok(payload) is False


def test_verdict_fail_closed_on_incomplete_axiom_set():
    # A cycle that produced only 41 of the 42 axiom ids must fail the
    # completeness criterion even though cycles/traces are present.
    partial = {
        "passed": 41,
        "failed": [],
        "axiom_ids": list(AXIOM_IDS)[:-1],
        "reasons": {},
    }
    payload = _payload([partial], 1)
    assert payload["criteria"]["cycles_measured"] is True
    assert payload["criteria"]["traces_present"] is True
    assert payload["criteria"]["axiom_set_complete"] is False
    assert ace.ci_ok(payload) is False


def test_ci_ok_rejects_malformed_payloads():
    assert ace.ci_ok({}) is False
    assert ace.ci_ok({"verdict": {"passed": True}, "criteria": {}}) is False
    # A missing criterion must fail closed, never be treated as passing.
    payload = _payload([_record([])], 1)
    del payload["criteria"]["traces_present"]
    assert ace.ci_ok(payload) is False
    # Explicit False also fails.
    payload["verdict"]["passed"] = False
    assert ace.ci_ok(payload) is False


def test_degraded_result_is_not_smoothed():
    # All measured cycles pass only 28/42: the artifact must say so, list the
    # 14 failing axioms, and report the proposed floor as FAILING.
    failed = ["2.7", "4.5", "4.8", "4.9", "4.10", "4.11",
              "6.3", "6.4", "6.5", "6.6", "6.7", "6.8", "6.9", "6.10"]
    payload = _payload([_record(failed), _record(failed)], 2)
    assert payload["mean_compliance"] == pytest.approx(28 / 42)
    assert payload["min_compliance"] == pytest.approx(28 / 42)
    assert payload["healthy_cycles"] == 0
    assert payload["degraded_cycles"] == 2
    assert len(payload["worst_failed_axioms"]) == 14
    assert {row["axiom"] for row in payload["worst_failed_axioms"]} == set(failed)
    assert payload["proposed_compliance_gate"]["passes"] is False
    # The measurement is still WELL-FORMED (it measured real cycles).
    assert ace.ci_ok(payload) is True


def test_scorecard_criteria_lock_to_writer():
    # The scorecard reads the live-compliance artifact; its criterion names and
    # path must match what this harness writes (writer<->reader linkage).
    from telos.core.verifier import capability_scorecard as cs
    assert tuple(ace.CRITERIA) == cs.AXIOM_COMPLIANCE_CRITERIA
    assert cs.AXIOM_COMPLIANCE_ARTIFACT == "telos/audit/axiom_compliance.json"


def test_diagnosis_covers_every_measured_failure_category():
    # Every diagnosed id must be a real axiom id and carry a category+evidence.
    for aid, diag in ace.FAILING_AXIOM_DIAGNOSIS.items():
        assert aid in AXIOM_IDS
        assert diag.get("category")
        assert diag.get("evidence")


def test_real_pipeline_deterministic_and_well_formed(tmp_path):
    # Two identical-seed real runs must produce the same compliance series.
    payload = ace.evaluate(cycles=4, mode="fast", seed=42, determinism=True)
    assert payload["determinism"]["identical"] is True, payload["determinism"]
    assert ace.ci_ok(payload) is True
    assert payload["cycles_measured"] == 4
    assert payload["cycles_with_trace"] == 4

    # And the artifact evaluate() produces is readable by the shared contract.
    out = tmp_path / "axiom_compliance.json"
    out.write_text(json.dumps(payload))
    measured = read_measurement(str(tmp_path), "axiom_compliance.json",
                                tuple(ace.CRITERIA))
    assert measured is not None and measured.verdict_passed


def test_floor_gate_is_wired_and_fail_closed():
    # The constitutional floor is now a real gate: `floor_ok` fails closed on
    # a missing/malformed gate and on any measurement below 42/42. `ci_ok`
    # still checks measurement well-formedness only; the CLI requires both.
    good = _payload([_record([])], 1)
    assert good["proposed_compliance_gate"]["passes"] is True
    assert ace.floor_ok(good) is True
    assert ace.ci_ok(good) is True

    degraded = _payload([_record(["2.7", "4.5"])], 1)
    assert degraded["proposed_compliance_gate"]["passes"] is False
    assert ace.floor_ok(degraded) is False
    # The measurement itself is still well-formed (honest, not smoothed).
    assert ace.ci_ok(degraded) is True

    # Λ4.11 is conditionally violable: a cycle failing ONLY 4.11 is legitimate
    # (the crew did not overcome its alignment cost) and the gate passes — but
    # only because the conditional predicate still holds on the other cycle.
    conditional = _payload([_record(["4.11"]), _record([])], 2)
    assert conditional["proposed_compliance_gate"]["passes"] is True
    assert ace.floor_ok(conditional) is True
    # An always-false conditional predicate is NOT a pass: if every cycle fails
    # 4.11 the gate fails closed (the axiom must stay falsifiable, not dead).
    dead = _payload([_record(["4.11"]), _record(["4.11"])], 2)
    assert dead["proposed_compliance_gate"]["passes"] is False
    assert ace.floor_ok(dead) is False
    # A non-conditional failure alongside 4.11 still fails, and is named.
    mixed = _payload([_record(["4.11", "2.7"]), _record([])], 2)
    assert mixed["proposed_compliance_gate"]["passes"] is False
    assert mixed["proposed_compliance_gate"]["nonconditional_violations"] == ["2.7"]

    # Missing / malformed gate fails closed, never a silent pass.
    assert ace.floor_ok({}) is False
    assert ace.floor_ok({"proposed_compliance_gate": "nope"}) is False
    assert ace.floor_ok({"proposed_compliance_gate": {"passes": "yes"}}) is False


def test_diagnosis_is_attached_only_for_current_failures():
    # The wiring-gap catalog stays the reference; an all-green run ships an
    # empty per-run diagnosis rather than a stale list of fixed gaps.
    assert set(ace.FAILING_AXIOM_DIAGNOSIS) >= {
        "2.7", "4.5", "4.8", "4.9", "4.10", "4.11",
        "6.3", "6.4", "6.5", "6.6", "6.7", "6.8", "6.9", "6.10"}
    payload = ace.evaluate(cycles=2, mode="fast", seed=42)
    assert payload["worst_failed_axioms"] == []
    assert payload["diagnosis"] == {}


def test_live_cycle_exposes_the_prover_inputs_on_ctx(tmp_path):
    # Every value the fixed predicates read is written where they read it.
    import numpy as np

    pipe = ace._build(str(tmp_path), "fast", 42)
    captured = {}
    original = pipe._axiom_prover.verify

    def _capture(trace, ctx, **kwargs):
        captured["ctx"] = ctx
        return original(trace, ctx, **kwargs)

    pipe._axiom_prover.verify = _capture
    pipe.execute(np.array([0.0, 0.0]), user_name="axiom-inputs-test")
    ctx = captured["ctx"]
    assert ctx.error_attribution_status in ("attributed", "not_applicable")
    assert ctx.relational_context is not None
    assert hasattr(ctx.relational_context, "relational_coherence")
    assert ctx.local_optima_escape is not None
    assert ctx.cooperative_verdict is not None


def test_live_compliance_floor_does_not_regress():
    # MEANING: the wiring/exposure fixes raised live per-cycle axiom
    # compliance from 28/42 (mean=min=0.667) to 42/42 (1.0). If a future
    # change silently starves the prover of a live component again, this
    # assertion fails loudly instead of only the committed artifact drifting.
    payload = ace.evaluate(cycles=8, mode="fast", seed=42)
    assert payload["min_compliance"] >= 1.0
    assert payload["mean_compliance"] >= 1.0
    assert payload["healthy_cycles"] == payload["cycles_measured"]


def test_standard_mode_conditional_4_11_floor():
    # STRICT-SEMANTICS REGRESSION: standard mode runs the advisory crew. On a
    # unanimous cycle (all DI == 1.0, no validation split) alignment_cost is 0
    # and the crew cooperates. On an md-cap cycle the validation-axis split
    # raises C_align above the crew's surplus, so Λ4.11 legitimately fails that
    # cycle. The harness must (a) still report every NON-conditional axiom green
    # on every cycle, and (b) pass its conditional floor while recording the
    # 4.11 failures — never smoothing them away.
    payload = ace.evaluate(cycles=4, mode="standard", seed=42)
    failed_ids = {row["axiom"] for row in payload["worst_failed_axioms"]}
    assert failed_ids <= {"4.11"}, payload["worst_failed_axioms"]
    gate = payload["proposed_compliance_gate"]
    assert gate["nonconditional_violations"] == []
    assert gate["passes"] is True
    assert ace.floor_ok(payload) is True
    # The conditional predicate is not always-false: at least one cycle passes.
    assert payload["healthy_cycles"] >= 1
