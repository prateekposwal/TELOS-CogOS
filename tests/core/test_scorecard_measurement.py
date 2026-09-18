"""
Measurement provenance + the artifact/independence flag semantics.

The scorecard's single `external` boolean used to conflate three claims. These
tests lock the replacement contract in `telos/core/verifier/measurement.py`:
`artifact_backed` (machine-checkable measurement), `independently_measured`
(written by a separate tool) and `external` (sourced outside the first-party
toolchain, NEVER granted to a first-party harness). They also lock the
behavioral rewiring of the verification_rigor and reproducibility dimensions.
"""

import json
import os
import subprocess
import sys

import pytest

from telos.core.verifier import capability_scorecard as cs
from telos.core.verifier.measurement import (
    ARTIFACT_SCHEMA_VERSION, SCORER_PRODUCER, flags_from_provenance,
    provenance, read_measurement,
)

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── flag semantics ───────────────────────────────────────────────────────

def test_first_party_harness_is_independent_but_not_external():
    """A first-party separate-process harness earns independent, not external."""
    backed, independent, external = flags_from_provenance(
        provenance("telos/tools/governance_eval.py", ["x"]))
    assert backed is True
    assert independent is True
    assert external is False


def test_external_source_earns_the_external_flag():
    """Only an out-of-toolchain source earns the strong external flag."""
    backed, independent, external = flags_from_provenance(
        provenance("operator/reproduce.py", ["x"], source="operator"))
    assert (backed, independent, external) == (True, True, True)


def test_missing_provenance_fails_closed():
    """No provenance / wrong schema / not machine-checkable -> no flags."""
    assert flags_from_provenance(None) == (False, False, False)
    assert flags_from_provenance({}) == (False, False, False)
    bad = provenance("telos/tools/x.py", ["x"])
    bad["schema_version"] = ARTIFACT_SCHEMA_VERSION + 99
    assert flags_from_provenance(bad) == (False, False, False)
    uncheckable = provenance("telos/tools/x.py", ["x"])
    uncheckable["machine_checkable"] = False
    assert flags_from_provenance(uncheckable) == (False, False, False)


def test_scorer_written_artifact_is_not_independently_measured():
    """An artifact written by the scorer itself cannot claim independence."""
    backed, independent, external = flags_from_provenance(
        provenance(SCORER_PRODUCER, ["x"]))
    assert backed is True
    assert independent is False
    assert external is False


# ── read_measurement schema enforcement ──────────────────────────────────

def _write(tmp_path, payload, name="eval.json"):
    """Write an artifact under a temp repo's telos/audit directory.

    Args:
        tmp_path: pytest temp path.
        payload: the artifact payload.
        name: artifact filename.

    Returns:
        The repo root as a string.
    """
    out = tmp_path / "telos" / "audit" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload), encoding="utf-8")
    return str(tmp_path)


def _artifact(criteria, producer="telos/tools/x.py", verdict=True,
              source="first_party"):
    """Build a measurement artifact payload.

    Args:
        criteria: criterion names.
        producer: provenance producer path.
        verdict: overall verdict passed flag.
        source: provenance source class.

    Returns:
        The artifact payload.
    """
    return {
        "provenance": provenance(producer, list(criteria), source=source),
        "criteria": {name: True for name in criteria},
        "verdict": {"passed": verdict, "passed_count": len(criteria),
                    "total": len(criteria)},
    }


def test_read_measurement_requires_the_schema(tmp_path):
    """Missing criteria/verdict/provenance returns None (no credit)."""
    relpath = "telos/audit/eval.json"
    assert read_measurement(str(tmp_path), relpath, ("a",)) is None
    root = _write(tmp_path, _artifact(["a"]))
    assert read_measurement(root, relpath, ("a",)) is not None
    root = _write(tmp_path, {"criteria": {"a": True}, "verdict": {"passed": True}})
    assert read_measurement(root, relpath, ("a",)) is None
    artifact = _artifact(["a"])
    artifact["criteria"] = {}
    root = _write(tmp_path, artifact)
    assert read_measurement(root, relpath, ("a",)) is None
    artifact = _artifact(["a"])
    artifact["verdict"] = {"passed": "yes"}
    root = _write(tmp_path, artifact)
    assert read_measurement(root, relpath, ("a",)) is None


def test_read_measurement_reports_verdict_and_flags(tmp_path):
    """A valid artifact surfaces its verdict and the three flags."""
    root = _write(tmp_path, _artifact(list(cs.GOVERNANCE_CRITERIA),
                                      source="operator"))
    measurement = read_measurement(
        root, "telos/audit/eval.json", tuple(cs.GOVERNANCE_CRITERIA))
    assert measurement is not None
    assert measurement.verdict_passed is True
    assert measurement.external is True
    assert measurement.independently_measured is True
    assert measurement.artifact_backed is True


# ── verification rigor rewiring ──────────────────────────────────────────

VERIF_MODULES = (
    "telos/core/verifier/axiom_falsifier.py",
    "telos/core/verifier/theorem_audit.py",
    "telos/core/verifier/decision_log_audit.py",
    "telos/core/verifier/non_ergodicity.py",
)


def _module_repo(tmp_path, modules, artifact=None, relpath=None):
    """Create a repo tree with the given modules and optional artifact.

    Args:
        tmp_path: pytest temp path.
        modules: repo-relative module paths to create.
        artifact: optional artifact payload.
        relpath: optional artifact repo-relative path.

    Returns:
        The repo root as a string.
    """
    for module in modules:
        path = tmp_path / module
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    if artifact is not None:
        out = tmp_path / relpath
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(artifact), encoding="utf-8")
    return str(tmp_path)


def test_verification_awards_only_with_a_passing_artifact(tmp_path):
    """Valid verification artifact -> 4.0 (base + adversarial); missing ->
    existence-only base. The live-compliance point needs its own artifact."""
    root = _module_repo(tmp_path, VERIF_MODULES, _artifact(
        list(cs.VERIFICATION_CRITERIA), producer="telos/tools/verification_eval.py"),
        "telos/audit/verification_eval.json")
    result = cs._score_verification(root)
    assert result.score == 4.0
    assert result.independently_measured is True
    assert result.external is False
    assert any("withheld" in e for e in result.evidence)

    empty = _module_repo(tmp_path / "empty", VERIF_MODULES)
    result = cs._score_verification(empty)
    assert result.score == 1.0
    assert result.artifact_backed is False


def _write_live_compliance(root, min_compliance):
    """Write a well-formed live axiom-compliance artifact into a repo tree.

    Args:
        root: repo root.
        min_compliance: the worst measured cycle's passed/42 ratio.

    Returns:
        The artifact path.
    """
    payload = _artifact(list(cs.AXIOM_COMPLIANCE_CRITERIA),
                        producer="telos/tools/axiom_compliance_eval.py")
    payload["min_compliance"] = min_compliance
    out = os.path.join(root, cs.AXIOM_COMPLIANCE_ARTIFACT)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return out


def test_verification_live_compliance_is_credited_proportionally(tmp_path):
    """The live-compliance point scales with the WORST measured cycle and is
    withheld entirely when the artifact is missing/malformed (fail closed)."""
    root = _module_repo(tmp_path, VERIF_MODULES, _artifact(
        list(cs.VERIFICATION_CRITERIA), producer="telos/tools/verification_eval.py"),
        "telos/audit/verification_eval.json")
    out = _write_live_compliance(root, 28 / 42)
    result = cs._score_verification(root)
    assert result.score == pytest.approx(1.0 + 3.0 + 28 / 42)
    assert any("0.667" in e for e in result.evidence)
    assert any("below 42/42" in e for e in result.evidence)

    # Full live compliance earns the full point.
    _write_live_compliance(root, 1.0)
    assert cs._score_verification(root).score == 5.0

    # A missing artifact can never silently credit the live point.
    os.remove(out)
    assert cs._score_verification(root).score == 4.0

    # A malformed artifact (bad provenance) is also withheld.
    _write_live_compliance(root, 1.0)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"min_compliance": 1.0}, f)
    assert cs._score_verification(root).score == 4.0

    # A structurally valid but FAILING measurement is not well-formed evidence.
    failing = _artifact(list(cs.AXIOM_COMPLIANCE_CRITERIA),
                        producer="telos/tools/axiom_compliance_eval.py",
                        verdict=False)
    failing["min_compliance"] = 1.0
    with open(out, "w", encoding="utf-8") as f:
        json.dump(failing, f)
    assert cs._score_verification(root).score == 4.0


def test_reproducibility_awards_and_caps_without_external_reproduction(tmp_path):
    """Valid artifact -> 4.5 (first-party cap); missing -> base."""
    modules = ("telos/tools/perf_profiler.py", "telos/tools/endurance.py",
               "telos/tools/branch_coverage.py", "pyproject.toml")
    root = _module_repo(tmp_path, modules, _artifact(
        list(cs.REPRODUCIBILITY_CRITERIA),
        producer="telos/tools/reproducibility_eval.py"),
        "telos/audit/reproducibility_eval.json")
    result = cs._score_reproducibility(root)
    assert result.score == 4.5
    assert result.artifact_backed is True
    assert any("capped 4.5" in e for e in result.evidence)

    empty = _module_repo(tmp_path / "empty", modules)
    result = cs._score_reproducibility(empty)
    assert result.score == 1.0
    assert result.artifact_backed is False


# ── harness CLIs exit 0 ──────────────────────────────────────────────────

def _run_ci(tool, tmp_path):
    """Run a harness CLI with --ci and return its exit code.

    Args:
        tool: harness filename under telos/tools/.
        tmp_path: pytest temp path for the JSON output.

    Returns:
        The process return code.
    """
    proc = subprocess.run(
        [sys.executable, os.path.join(PROJECT, "telos", "tools", tool),
         "--ci", "--json", str(tmp_path / f"{tool}.json")],
        cwd=PROJECT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": PROJECT},
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_verification_harness_ci_exits_zero(tmp_path):
    """`verification_eval.py --ci` exits 0."""
    code, output = _run_ci("verification_eval.py", tmp_path)
    assert code == 0, output


def test_reproducibility_harness_ci_exits_zero(tmp_path):
    """`reproducibility_eval.py --ci` exits 0."""
    code, output = _run_ci("reproducibility_eval.py", tmp_path)
    assert code == 0, output


# ── output is readable ───────────────────────────────────────────────────

def test_json_output_exposes_the_three_flags_and_backing():
    """Every dimension's serialized row names what backs the score."""
    for result in cs.compute_scorecard().values():
        row = result.to_dict()
        assert "artifact_backed" in row
        assert "independently_measured" in row
        assert "external" in row
        assert "backing" in row
        assert "measurement_artifact" in row


def test_report_lines_render_the_backing_section():
    """The printable report includes the backing legend."""
    text = "\n".join(cs.report_lines())
    assert "Measurement backing" in text
    assert "independently_measured" in text
    assert "external = artifact sourced outside" in text


# ── uniform artifact schema across every measured dimension ──────────────

def test_every_measured_writer_emits_the_uniform_schema():
    """Memory/learning/multi-agent writers also emit criteria + verdict."""
    from telos.tools.memory_eval import evaluate as memory_eval
    from telos.tools.learning_env import evaluate as learning_env
    from telos.tools.learning_curve import evaluate as learning_curve
    from telos.tools.multi_agent_eval import evaluate as multi_agent_eval

    for payload in (memory_eval(), learning_env(), learning_curve(),
                    multi_agent_eval()):
        assert payload["provenance"]["machine_checkable"] is True
        assert payload["provenance"]["producer"]
        assert isinstance(payload["criteria"], dict) and payload["criteria"]
        assert isinstance(payload["verdict"]["passed"], bool)


def test_shipped_artifacts_back_their_scores():
    """The committed measurement artifacts back the measured dimensions."""
    card = cs.compute_scorecard()
    for name in ("self_governance", "verification_rigor", "reproducibility",
                 "memory", "learning", "multi_agent"):
        result = card[name]
        assert result.artifact_backed is True, name
        assert result.independently_measured is True, name
        assert result.external is False, name
        assert result.measurement, name


# ── maturity: the cap is CONDITIONAL on external/operator reproduction ────

MATURITY_SIGNAL_FILES = (
    "pyproject.toml", "LICENSE", "CHANGELOG.md", "telos/cli.py",
    "telos/__main__.py", "README.md",
)


def _maturity_repo(tmp_path):
    """Create a repo whose first-party signals saturate the 4.0 cap.

    Args:
        tmp_path: pytest temp path.

    Returns:
        The repo root as a string.
    """
    for relpath in MATURITY_SIGNAL_FILES:
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (tmp_path / "telos" / "__init__.py").write_text(
        '__version__ = "0.1.0"\n', encoding="utf-8")
    tag = tmp_path / ".git" / "refs" / "tags" / "v0.1.0"
    tag.parent.mkdir(parents=True, exist_ok=True)
    tag.write_text("0" * 40 + "\n", encoding="utf-8")
    for relpath in ("examples/quickstart.py", "RELEASE.md",
                    ".github/workflows/gates.yml",
                    "tests/core/test_version.py"):
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return str(tmp_path)


def _write_reproduction(root, *, source="operator",
                        producer="operator/reproduce.py",
                        criteria=None, verdict=True,
                        relpath="research/reproduce/reproduction_verification.json",
                        raw=None):
    """Write an independent-reproduction artifact into a repo.

    Args:
        root: repo root.
        source: provenance source class.
        producer: provenance producer path.
        criteria: criterion -> passed mapping (defaults all pass).
        verdict: overall verdict passed flag.
        relpath: repo-relative artifact path.
        raw: optional raw text to write instead of a valid payload.

    Returns:
        The payload written (or the raw text when ``raw`` is given).
    """
    criteria = criteria or {
        name: True for name in cs.REPRODUCTION_CRITERIA}
    payload = {
        "provenance": provenance(
            producer, list(cs.REPRODUCTION_CRITERIA), source=source),
        "criteria": criteria,
        "verdict": {"passed": verdict,
                    "passed_count": sum(1 for v in criteria.values() if v),
                    "total": len(criteria)},
    }
    out = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(raw if raw is not None else json.dumps(payload))
    return payload


def test_maturity_is_capped_without_any_external_artifact(tmp_path):
    """No external artifact -> the honest first-party ceiling holds at 4.0."""
    result = cs._score_maturity(_maturity_repo(tmp_path))
    assert result.score == 4.0
    assert result.external is False
    assert result.artifact_backed is False
    assert any("capped 4.0" in e for e in result.evidence)


def test_maturity_lifts_above_4_on_valid_operator_artifact(tmp_path):
    """A validated operator-sourced artifact genuinely lifts the cap."""
    root = _maturity_repo(tmp_path)
    _write_reproduction(root, source="operator")
    result = cs._score_maturity(root)
    assert result.score > 4.0
    assert result.external is True
    assert result.independently_measured is True
    assert result.artifact_backed is True
    assert result.measurement == \
        "research/reproduce/reproduction_verification.json"


def test_maturity_uplift_works_for_the_file_form_and_external_source(tmp_path):
    """The top-level `reproduction_verification.json` form also qualifies."""
    root = _maturity_repo(tmp_path)
    _write_reproduction(root, source="external", producer="auditor/repro.py",
                        relpath="reproduction_verification.json")
    result = cs._score_maturity(root)
    assert result.score > 4.0
    assert result.external is True


def test_maturity_fails_closed_on_malformed_artifact(tmp_path):
    """A torn/unparseable artifact must not award the uplift."""
    root = _maturity_repo(tmp_path)
    _write_reproduction(root, raw="{ this is not valid json")
    result = cs._score_maturity(root)
    assert result.score == 4.0
    assert result.external is False


def test_maturity_fails_closed_on_failing_verdict(tmp_path):
    """A well-formed artifact whose criteria do not all pass credits nothing."""
    root = _maturity_repo(tmp_path)
    criteria = {name: True for name in cs.REPRODUCTION_CRITERIA}
    criteria[cs.REPRODUCTION_CRITERIA[0]] = False
    _write_reproduction(root, criteria=criteria, verdict=False)
    result = cs._score_maturity(root)
    assert result.score == 4.0
    assert result.external is False


def test_maturity_rejects_a_first_party_source_artifact(tmp_path):
    """A first-party-sourced artifact is independent but NOT external."""
    root = _maturity_repo(tmp_path)
    _write_reproduction(root, source="first_party",
                        producer="telos/tools/reproduce.py")
    result = cs._score_maturity(root)
    assert result.score == 4.0
    assert result.external is False


def test_maturity_fails_closed_on_missing_required_criteria(tmp_path):
    """An artifact omitting a required criterion is unreadable (no uplift)."""
    root = _maturity_repo(tmp_path)
    artifact = _artifact(list(cs.REPRODUCTION_CRITERIA),
                         producer="operator/reproduce.py", source="operator")
    artifact["criteria"] = {cs.REPRODUCTION_CRITERIA[0]: True}
    out = os.path.join(root, "reproduction_verification.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(artifact, f)
    result = cs._score_maturity(root)
    assert result.score == 4.0
    assert result.external is False
