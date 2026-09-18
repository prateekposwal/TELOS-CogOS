"""
Capability Scorecard — measures TELOS's capability rubric from real signals.

PATTERN (falsifiable self-assessment, Λ6.5): a capability score must be derived
from an OBSERVABLE artifact, not asserted. A dimension that counts module paths
says the modules EXIST, not that the capability WORKS; those dimensions are
scored from behavioral harnesses that drive the real machinery and write a
machine-checkable artifact (explicit criteria + verdict) with provenance.

Each result distinguishes three claims, so a TELOS-authored tool grading TELOS
is never mistaken for outside validation:

  * ``artifact_backed`` — the score is credited from a real measurement
    artifact (provenance-stamped, machine-checkable criteria + verdict);
  * ``independently_measured`` — that artifact was written by a tool separate
    from this scoring code path (a first-party harness process qualifies);
  * ``external`` — the artifact's provenance declares a source OUTSIDE TELOS's
    own first-party toolchain (``external``/``operator``). A first-party
    harness does NOT earn this, even run as its own process — TELOS grading
    TELOS is not external validation (research/FALSIFIABLE_THEOREMS.md).

The three flags are computed in ``telos/core/verifier/measurement.py`` and are
surfaced verbatim in ``capability_scorecard.json`` so a reader can see exactly
what backs each score instead of a bare number.

The "uplift" dimensions (tool_use, memory, learning, maturity, multi_agent)
carry the architect's targets; the others report their self-assessed baseline.
Weights are explicit so the arithmetic is auditable and cannot be quietly
tuned.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from telos.core.verifier.measurement import (
    flags_from_provenance, read_measurement, read_provenance,
)

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# The architect's uplift targets (Phase 1–4 of the capability roadmap).
TARGETS: Dict[str, float] = {
    "tool_use": 4.5,
    "memory": 5.0,
    "learning": 4.0,
    "maturity": 5.0,
    "multi_agent": 4.5,
}

# The measured criteria the multi-agent eval writes into
# telos/audit/multi_agent_eval.json. Locked to the writer by
# tests/core/test_multi_agent_coordination.py (schema-linkage guard: this
# project was previously bitten by writer/reader key drift).
MULTI_AGENT_CRITERIA: tuple = (
    "rejection_with_reason",
    "acceptance",
    "independent_verifier",
    "deterministic_conflict_resolution",
    "delegation_recorded",
    "bounded",
    "determinism",
)

_MULTI_AGENT_LABELS: Dict[str, str] = {
    "rejection_with_reason": "independent rejection with a recorded reason",
    "acceptance": "independent acceptance of a valid proposal",
    "independent_verifier": "verifier cannot audit its own proposal",
    "deterministic_conflict_resolution": "deterministic conflict resolution",
    "delegation_recorded": "recorded delegation between agents",
    "bounded": "bounded collaboration (rounds + handoffs)",
    "determinism": "two independent runs identical",
}

# The behavioral criteria the governance harness writes into
# telos/audit/governance_eval.json. Locked to the writer by
# tests/core/test_governance_eval.py.
GOVERNANCE_CRITERIA: tuple = (
    "low_integrity_blocked",
    "repeat_trap_blocked",
    "council_rejection_blocked",
    "legitimate_admitted",
    "low_fidelity_vetoed",
    "hard_boundary_blocked",
    "governor_act_on_clean",
    "governor_defer_on_capability_gap",
    "governor_abstain_on_unmodeled",
    "governor_escalate_when_required",
    "deterministic_replay",
)

_GOVERNANCE_LABELS: Dict[str, str] = {
    "low_integrity_blocked": "firewall blocks a low-integrity proposal",
    "repeat_trap_blocked": "firewall blocks a repeat-trap (action_loop) intent",
    "council_rejection_blocked": "firewall upholds a council rejection",
    "legitimate_admitted": "firewall admits a legitimate clean proposal",
    "low_fidelity_vetoed": "capability gate vetoes a low-fidelity proposal",
    "hard_boundary_blocked": "governor BLOCKs on a hard capability boundary",
    "governor_act_on_clean": "governor maps clean capability to ACT",
    "governor_defer_on_capability_gap": "governor DEFERs on a capability gap",
    "governor_abstain_on_unmodeled": "governor ABSTAINs on an UNMODELED state",
    "governor_escalate_when_required": "governor ESCALATEs when required",
    "deterministic_replay": "two governance runs produce identical verdicts",
}

# The behavioral criteria the verification harness writes into
# telos/audit/verification_eval.json.
VERIFICATION_CRITERIA: tuple = (
    "axioms_baseline_green",
    "axioms_all_falsifiable",
    "axiom_count_complete",
    "theorems_all_hold",
)

_VERIFICATION_LABELS: Dict[str, str] = {
    "axioms_baseline_green": "all axioms pass on the healthy prover input",
    "axioms_all_falsifiable": "every axiom can be made to fail (falsifiable)",
    "axiom_count_complete": "the falsifier sees the whole constitution (42)",
    "theorems_all_hold": "the theorem catalogue holds against its declared nulls",
}

# The behavioral criteria the reproducibility harness writes into
# telos/audit/reproducibility_eval.json.
REPRODUCIBILITY_CRITERIA: tuple = (
    "determinism_same_seed_identical",
    "distinct_seed_differs",
    "rng_isolation_zero_global",
)

_REPRODUCIBILITY_LABELS: Dict[str, str] = {
    "determinism_same_seed_identical": "same seed -> identical fingerprint",
    "distinct_seed_differs": "a different seed changes the fingerprint",
    "rng_isolation_zero_global": "zero global RNG calls in production paths",
}

# An independent (external/operator) reproduction is the ONLY evidence that
# legitimately lifts the maturity ceiling above the first-party cap. It must be
# a provenance-stamped, machine-checkable JSON artifact (see measurement.py)
# located at one of these repo-relative paths; a first-party harness does NOT
# qualify no matter where it sits.
REPRODUCTION_ARTIFACT_PATHS: tuple = (
    "reproduction_verification.json",
    "research/reproduce/reproduction_verification.json",
)

# The criteria an independent reproduction artifact must report and pass. A
# missing/torn/partial artifact, or one whose verdict does not pass, credits
# nothing (fail closed).
REPRODUCTION_CRITERIA: tuple = (
    "independent_environment",
    "fingerprint_reproduced",
    "axioms_reproduced",
)

# The honest first-party ceiling: packaging/release/CLI structure can never
# exceed this on its own. Adoption (users/stars/issues) is not measurable from
# the repo, and 5.0 is reserved for it — never awarded by this scorer.
_FIRST_PARTY_MATURITY_CEILING = 4.0

# The uplift granted when a VALIDATED external/operator artifact passes. With
# the first-party maximum (4.4) this yields 4.9, so maturity can rise above the
# 4.0 cap on genuine independent provenance but still cannot reach 5.0.
_EXTERNAL_REPRODUCTION_UPLIFT = 0.5

# The full rubric (the competitive table's dimensions).
DIMENSIONS: List[str] = [
    "autonomy", "self_governance", "verification_rigor", "memory",
    "learning", "reproducibility", "multi_agent", "tool_use", "maturity",
    "docs",
]


@dataclass(frozen=True)
class DimensionResult:
    """One rubric row: its score, target (if any), basis, and evidence.

    Attributes:
        name: the dimension name.
        score: measured score in [0, 5].
        target: the uplift target, or None for baseline dimensions.
        basis: one-line explanation of how the score was derived.
        evidence: concrete signals (paths / counts) backing the score.
        external: True only when the backing artifact's provenance declares a
            source OUTSIDE TELOS's first-party toolchain.
        independently_measured: True when a tool OTHER than this scorer wrote
            the backing artifact (a first-party harness qualifies).
        artifact_backed: True when the score is credited from a validated,
            machine-checkable measurement artifact (not a path check).
        measurement: repo-relative path of the backing artifact, or None.
    """

    name: str
    score: float
    basis: str
    evidence: List[str] = field(default_factory=list)
    target: Optional[float] = None
    external: bool = False
    independently_measured: bool = False
    artifact_backed: bool = False
    measurement: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        """Serializable form for JSON output."""
        return {
            "name": self.name,
            "score": round(self.score, 2),
            "target": self.target,
            "gap": round(self.target - self.score, 2) if self.target else None,
            "basis": self.basis,
            "evidence": self.evidence,
            "external": self.external,
            "independently_measured": self.independently_measured,
            "artifact_backed": self.artifact_backed,
            "measurement_artifact": self.measurement,
            "backing": _backing_label(
                self.artifact_backed, self.independently_measured, self.external),
        }


def _exists(root: str, relpath: str) -> bool:
    """True when a repo-relative path exists.

    Args:
        root: repo root.
        relpath: POSIX-style relative path.

    Returns:
        True if the path exists.
    """
    return os.path.exists(os.path.join(root, relpath))


def _clamp(value: float) -> float:
    """Clamp a score into [0, 5].

    Args:
        value: raw score.

    Returns:
        The value bounded to [0, 5].
    """
    return max(0.0, min(5.0, value))


def _backing_label(artifact_backed: bool, independently_measured: bool,
                   external: bool) -> str:
    """Human-readable label of what backs a score.

    Args:
        artifact_backed: a validated measurement artifact backs the score.
        independently_measured: a non-scorer tool wrote that artifact.
        external: the artifact's source is outside the first-party toolchain.

    Returns:
        A label: "external", "independently_measured (first-party artifact)",
        "artifact_backed (self-measured)", or "existence-only".
    """
    if external:
        return "external"
    if artifact_backed and independently_measured:
        return "independently_measured (first-party artifact)"
    if artifact_backed:
        return "artifact_backed (self-measured)"
    return "existence-only"


def _measurement_flags(root: str, relpath: str):
    """Read an artifact's provenance into (backed, independent, external).

    Args:
        root: repo root.
        relpath: repo-relative path of the artifact.

    Returns:
        The three flags; all False when the artifact/provenance is absent.
    """
    if not _exists(root, relpath):
        return (False, False, False)
    return flags_from_provenance(read_provenance(root, relpath))


def _read(root: str, relpath: str) -> str:
    """Read a repo-relative text file, returning "" on any failure.

    Args:
        root: repo root.
        relpath: POSIX-style relative path.

    Returns:
        File contents, or "" when unreadable.
    """
    try:
        with open(os.path.join(root, relpath), "r", encoding="utf-8",
                  errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _memory_eval_beats_naive(root: str) -> bool:
    """Whether the measured memory eval shows the CONTROLLER beating baselines.

    Reads the schema `memory_eval.py` actually emits: `beats_baselines` plus the
    `semantic` arm's `recall@1`. (An earlier version read `beats_naive` /
    `controller`, which the eval stopped emitting — so this silently returned
    False and the memory score did not count the retrieval evidence at all.
    `tests/core/test_scorecard_eval_schema.py` now locks the two together.)

    Args:
        root: repo root.

    Returns:
        True only when telos/audit/memory_eval.json exists, reports
        beats_baselines, and the semantic recall@1 is >= 0.9.
    """
    path = os.path.join(root, "telos", "audit", "memory_eval.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("beats_baselines")) and \
            float(data.get("semantic", {}).get("recall@1", 0.0)) >= 0.9
    except (OSError, ValueError, TypeError):
        return False


def _memory_consumed_in_real_cycles(root: str) -> bool:
    """Whether the runtime artifact proves SUSTAINED memory consumption.

    A short test run is not evidence of a working memory layer. This requires
    the artifact to report consumed_in_real_cycles=True AND either an explicit
    sustained cycle span (cycles_observed >= min_cycles_required, written by
    the long-running producer) or a recalled count that only sustained use
    produces.

    Args:
        root: repo root.

    Returns:
        True only when the artifact evidences sustained consumption.
    """
    path = os.path.join(root, "telos", "audit", "memory_consumption.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("consumed_in_real_cycles"):
            return False
        if int(data.get("memory_consumed", 0)) <= 0:
            return False
        cycles = int(data.get("cycles_observed", 0))
        required = int(data.get("min_cycles_required", 0))
        if required > 0:
            return cycles >= required
        # No declared span: fall back to a strong count floor (a test run
        # observes a handful of cycles; sustained use observes many recalls).
        return int(data.get("memory_consumed", 0)) >= 50
    except (OSError, ValueError, TypeError):
        return False


def _learning_env_beats_control(root: str) -> bool:
    """Whether the REAL-environment harness shows learning beating control.

    Args:
        root: repo root.

    Returns:
        True only when telos/audit/learning_env.json reports beats_control.
    """
    path = os.path.join(root, "telos", "audit", "learning_env.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("beats_control"))
    except (OSError, ValueError, TypeError):
        return False


def _learning_curve_beats_control(root: str) -> bool:
    """Whether the measured learning curve shows the learned arm winning.

    Args:
        root: repo root.

    Returns:
        True only when telos/audit/learning_curve.json reports beats_control.
    """
    path = os.path.join(root, "telos", "audit", "learning_curve.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("beats_control"))
    except (OSError, ValueError, TypeError):
        return False


def _git_tag_count(root: str) -> int:
    """Count git tags from the refs on disk (no subprocess).

    Reads ``.git/refs/tags`` and ``.git/packed-refs`` so the scorecard never
    spawns a process (it must itself stay inside the governed-channel rule).

    Args:
        root: repo root.

    Returns:
        Number of tags found (0 when the repo has no tags / no .git).
    """
    count = 0
    tags_dir = os.path.join(root, ".git", "refs", "tags")
    if os.path.isdir(tags_dir):
        for dirpath, _dirnames, filenames in os.walk(tags_dir):
            count += len(filenames)
    packed = os.path.join(root, ".git", "packed-refs")
    if os.path.isfile(packed):
        try:
            with open(packed, "r", encoding="utf-8", errors="replace") as f:
                count += sum(1 for line in f
                             if " refs/tags/" in line and not line.startswith("#"))
        except OSError:
            pass
    return count


def _tool_families(root: str) -> Optional[int]:
    """Number of tool families in the canonical registry (or None).

    Args:
        root: repo root (unused, kept for signature symmetry).

    Returns:
        Family count, or None when the registry cannot be imported.
    """
    try:
        from telos.core.actions.registry import DEFAULT_REGISTRY
        return len(DEFAULT_REGISTRY.families())
    except Exception:
        return None


def _registry_specs(root: str) -> Optional[list]:
    """Return the canonical tool specs (or None when unimportable).

    Args:
        root: repo root (unused).

    Returns:
        List of ToolSpec, or None.
    """
    try:
        from telos.core.actions.registry import DEFAULT_REGISTRY
        return list(DEFAULT_REGISTRY.as_allowlist().values())
    except Exception:
        return None


def _unknown_tool_channels(root: str) -> Optional[int]:
    """Count unknown (ungoverned) tool channels from the channel scanner.

    Args:
        root: repo root.

    Returns:
        Unknown-site count, or None when the scanner cannot be imported.
    """
    try:
        from telos.tools.tool_channel_scan import scan
        return int(scan(root)["counts"]["unknown_sites"])  # type: ignore[index]
    except Exception:
        return None


def _score_tool_use(root: str) -> DimensionResult:
    """Score the tool-use dimension from registry + channel signals.

    Args:
        root: repo root.

    Returns:
        The DimensionResult for tool_use.
    """
    specs = _registry_specs(root)
    families = _tool_families(root)
    unknown = _unknown_tool_channels(root)
    has_network_family = False
    has_per_tool_capability = False
    if specs:
        has_network_family = any(s.family.startswith("network") for s in specs)
        has_per_tool_capability = any(s.capability for s in specs)
    has_sandbox = _exists(root, "telos/core/actions/sandbox.py")

    score = 2.0  # base: audited executor with allowlist + firewall gates
    evidence = ["telos/core/actions/executor.py (4 hard gates)"]
    if families is not None:
        evidence.append(f"registry families={families}")
        if families >= 3:
            score += 0.5
    if unknown is not None:
        evidence.append(f"unknown ungoverned channels={unknown}")
        if unknown == 0:
            score += 0.5
    if has_network_family:
        score += 0.5
        evidence.append("network tool family governed")
    if has_per_tool_capability:
        score += 0.75
        evidence.append("per-tool capability authorization declared")
    if has_sandbox:
        score += 0.75
        evidence.append("sandbox.py present")
    return DimensionResult(
        name="tool_use", score=_clamp(score), target=TARGETS["tool_use"],
        basis="registry families + ungoverned-channel count + capability/sandbox coverage",
        evidence=evidence,
    )


def _score_memory(root: str) -> DimensionResult:
    """Score the memory dimension from store/mechanism signals.

    Args:
        root: repo root.

    Returns:
        The DimensionResult for memory.
    """
    stores = [
        "telos/core/knowledge/graph.py",
        "telos/core/ledger/world_ledger.py",
        "telos/core/ledger/skill_library.py",
        "telos/core/memory/regret_memory.py",
        "telos/core/memory/active_forgetting.py",
    ]
    present = [p for p in stores if _exists(root, p)]
    has_controller = _exists(root, "telos/core/memory/controller.py")
    has_tiering = _exists(root, "telos/core/memory/tiering.py")
    has_eval = _exists(root, "telos/tools/memory_eval.py")
    eval_ok = _memory_eval_beats_naive(root)
    score = 3.5  # base: real, capped stores (knowledge/ledger/memory)
    evidence = [f"memory stores present={len(present)}/{len(stores)}"]
    if has_controller:
        score += 0.5
        evidence.append("unified controller")
    if has_tiering:
        score += 0.5
        evidence.append("tiered decision memory")
    if has_eval:
        score += 0.5
        evidence.append(
            "retrieval eval measured (beats naive)" if eval_ok
            else "retrieval eval present but not passing"
        )
    if not eval_ok:
        # The retrieval point only counts when the eval actually passes.
        score -= 0.5
    # The final 0.5 requires memory consumed by REAL pipeline cycles, not just
    # a fixture; the runtime writes telos/audit/memory_consumption.json at
    # shutdown with consumed_in_real_cycles=True.
    if _memory_consumed_in_real_cycles(root):
        score += 0.5
        evidence.append("consumed in real cycles (memory_consumption.json)")
    else:
        score = min(score, 4.5)
        evidence.append("capped 4.5 until memory is consumed in real cycles")
    backed, independent, external = _measurement_flags(
        root, "telos/audit/memory_eval.json")
    return DimensionResult(
        name="memory", score=_clamp(score), target=TARGETS["memory"],
        basis="stores + controller/tiering + measured retrieval eval + runtime consumption",
        evidence=evidence,
        external=external, independently_measured=independent,
        artifact_backed=backed,
        measurement="telos/audit/memory_eval.json" if backed else None,
    )


def _score_learning(root: str) -> DimensionResult:
    """Score the learning dimension from theory/skill machinery signals.

    Args:
        root: repo root.

    Returns:
        The DimensionResult for learning.
    """
    builder = _exists(root, "telos/core/reasoning/theory/builder.py")
    experiment = _exists(root, "telos/core/reasoning/theory/experiment.py")
    curriculum = _exists(root, "telos/core/learning/curriculum.py")
    acquisition = _exists(root, "telos/core/learning/acquisition.py")
    curve = _exists(root, "telos/tools/learning_curve.py")
    env = _exists(root, "telos/tools/learning_env.py")
    curve_ok = _learning_curve_beats_control(root)
    env_ok = _learning_env_beats_control(root)
    score = 2.0
    evidence = []
    for label, cond in (("theory builder", builder),
                        ("falsifiable experiment", experiment),
                        ("curriculum generation", curriculum),
                        ("verified skill acquisition", acquisition)):
        if cond:
            score += 0.5
            evidence.append(label)
    if curve:
        evidence.append(
            "measured learning curve (beats frozen control)" if curve_ok
            else "learning curve present but not passing"
        )
        if curve_ok:
            score += 0.5
        else:
            score -= 0.5
    # Real-environment evidence: the reward comes from the world simulator, not
    # a hand-written outcome function. This is the stronger claim.
    if env:
        evidence.append(
            "REAL-environment learning (world-defined reward, beats control)"
            if env_ok else "real-env harness present but not passing"
        )
        if env_ok:
            score += 0.5
    if not evidence:
        evidence.append("no learning machinery detected")
    backed, independent, external = _measurement_flags(
        root, "telos/audit/learning_env.json")
    return DimensionResult(
        name="learning", score=_clamp(score), target=TARGETS["learning"],
        basis="theory/skill machinery + curriculum + measured curve + real-env learning",
        evidence=evidence,
        external=external, independently_measured=independent,
        artifact_backed=backed,
        measurement="telos/audit/learning_env.json" if backed else None,
    )


def _validated_external_reproduction(root: str):
    """Read the first VALIDATED external/operator reproduction artifact.

    Fail-closed by construction: a missing, malformed, torn, or
    partially-written artifact makes ``read_measurement`` return None; an
    artifact that does not declare an out-of-toolchain source (``external`` /
    ``operator``) or whose machine-checkable verdict does not pass is skipped.
    Only genuine independent provenance can lift the maturity ceiling.

    Args:
        root: repo root.

    Returns:
        The validated Measurement, or None when no qualifying artifact exists.
    """
    for relpath in REPRODUCTION_ARTIFACT_PATHS:
        measured = read_measurement(root, relpath, REPRODUCTION_CRITERIA)
        if measured is None:
            continue
        if not measured.external or not measured.verdict_passed:
            continue
        return measured
    return None


def _score_maturity(root: str) -> DimensionResult:
    """Score the maturity/adoption dimension from release-artifact signals.

    The first-party structure (packaging, version, tags, examples, release
    process, CI, version lock) can never reach 5.0 on its own. The cap is
    CONDITIONAL, not structural:

      * with NO validated external/operator reproduction artifact the score is
        capped at the honest first-party ceiling ``4.0`` (documented partial
        value: max first-party structure is 4.4, withheld above 4.0);
      * with a validated artifact whose provenance ``source`` is ``external``
        or ``operator`` AND whose machine-checkable criteria all pass, the
        uplift (+0.5) is granted and the 4.0 cap lifts — the honest ceiling
        becomes 4.9, because adoption (users/stars/issues) is still not
        measurable and 5.0 stays reserved for it.

    A first-party harness is ``independently_measured`` but NOT ``external``,
    so it can never trigger the uplift. A missing, malformed, torn, or
    otherwise unreadable artifact credits nothing (fail closed).

    Args:
        root: repo root.

    Returns:
        The DimensionResult for maturity.
    """
    signals = [
        ("pyproject.toml", _exists(root, "pyproject.toml")),
        ("LICENSE", _exists(root, "LICENSE")),
        ("CHANGELOG.md", _exists(root, "CHANGELOG.md")),
        ("telos/cli.py", _exists(root, "telos/cli.py")),
        ("telos/__main__.py", _exists(root, "telos/__main__.py")),
        ("README.md", _exists(root, "README.md")),
    ]
    score = 1.0
    evidence = []
    for label, cond in signals:
        if cond:
            score += 0.3
            evidence.append(label)
    has_version = "__version__" in _read(root, "telos/__init__.py")
    if has_version:
        score += 0.3
        evidence.append("__version__")
    tags = _git_tag_count(root)
    evidence.append(f"git tags={tags}")
    if tags > 0:
        score += 0.4
    examples = _exists(root, "examples/quickstart.py")
    if examples:
        score += 0.4
        evidence.append("examples/quickstart.py")
    if _exists(root, "RELEASE.md"):
        score += 0.2
        evidence.append("RELEASE.md (versioning + release process)")
    if _exists(root, ".github/workflows/gates.yml"):
        score += 0.2
        evidence.append("CI gates workflow")
    if _exists(root, "tests/core/test_version.py"):
        score += 0.1
        evidence.append("version lock test")
    # Adoption (users/stars/issues) is not measurable from the repo and is
    # never awarded here. Without validated independent reproduction the
    # first-party structure is capped at 4.0.
    reproduction = _validated_external_reproduction(root)
    if reproduction is None:
        score = min(score, _FIRST_PARTY_MATURITY_CEILING)
        evidence.append(
            "capped 4.0: no validated external/operator reproduction artifact")
        return DimensionResult(
            name="maturity", score=_clamp(score), target=TARGETS["maturity"],
            basis="packaging/release/CLI signals; capped at the 4.0 first-party "
                  "ceiling until a validated external/operator reproduction "
                  "artifact passes its criteria",
            evidence=evidence)
    score += _EXTERNAL_REPRODUCTION_UPLIFT
    evidence.append(
        f"validated external reproduction: {reproduction.artifact} "
        f"({reproduction.passed_count}/{reproduction.total} criteria)")
    return DimensionResult(
        name="maturity", score=_clamp(score), target=TARGETS["maturity"],
        basis="packaging/release/CLI signals + validated independent "
              "reproduction; the 4.0 first-party ceiling lifts on external "
              "provenance (5.0 reserved for adoption, not awarded here)",
        evidence=evidence,
        external=reproduction.external,
        independently_measured=reproduction.independently_measured,
        artifact_backed=reproduction.artifact_backed,
        measurement=reproduction.artifact)


def _score_governance(root: str) -> DimensionResult:
    """Score self-governance from MEASURED blocking/admitting behavior.

    Structure earns only a small base; the rest is credited when the
    governance harness demonstrated the real firewall/capability/governor
    behavior and its machine-checkable verdict passed. A missing or failing
    harness credits nothing beyond the base (never a silent pass).

    Args:
        root: repo root.

    Returns:
        The DimensionResult for self_governance.
    """
    mods = [
        "telos/core/council/base.py",
        "telos/core/governance/firewall.py",
        "telos/core/governance/capability_authorization.py",
        "telos/core/governance/governor.py",
    ]
    present = [m for m in mods if _exists(root, m)]
    base = 1.0 * (len(present) / len(mods))
    measured = read_measurement(
        root, "telos/audit/governance_eval.json", GOVERNANCE_CRITERIA)
    evidence = [f"structure present={len(present)}/{len(mods)}"]
    if measured is None:
        evidence.append(
            "no machine-checkable governance_eval.json — existence-only base")
        return DimensionResult(
            name="self_governance", score=_clamp(base),
            basis="governance modules present; behavioral measurement missing",
            evidence=evidence)
    evidence.append(
        f"measured behaviors {measured.passed_count}/{measured.total} "
        "(governance_eval.json)")
    for name in GOVERNANCE_CRITERIA:
        if measured.criteria.get(name):
            evidence.append(f"measured: {_GOVERNANCE_LABELS[name]}")
    score = base + (4.0 if measured.verdict_passed else 0.0)
    if not measured.verdict_passed:
        evidence.append(
            "governance_eval verdict FAIL — measured component withheld")
    return DimensionResult(
        name="self_governance", score=_clamp(score),
        basis="real firewall/capability/governor behavior measured by "
              "governance_eval.json",
        evidence=evidence,
        external=measured.external,
        independently_measured=measured.independently_measured,
        artifact_backed=measured.artifact_backed,
        measurement=measured.artifact)


def _score_verification(root: str) -> DimensionResult:
    """Score verification rigor from EXECUTED adversarial verifiers.

    Structure earns only a small base; the rest is credited when the
    verification harness actually ran the axiom falsifier and theorem audit
    and its machine-checkable verdict passed. A missing/failing harness
    credits nothing beyond the base (never a silent pass).

    Args:
        root: repo root.

    Returns:
        The DimensionResult for verification_rigor.
    """
    mods = [
        "telos/core/verifier/axiom_falsifier.py",
        "telos/core/verifier/theorem_audit.py",
        "telos/core/verifier/decision_log_audit.py",
        "telos/core/verifier/non_ergodicity.py",
    ]
    present = [m for m in mods if _exists(root, m)]
    base = 1.0 * (len(present) / len(mods))
    measured = read_measurement(
        root, "telos/audit/verification_eval.json", VERIFICATION_CRITERIA)
    evidence = [f"structure present={len(present)}/{len(mods)}"]
    if measured is None:
        evidence.append(
            "no machine-checkable verification_eval.json — existence-only base")
        return DimensionResult(
            name="verification_rigor", score=_clamp(base),
            basis="verifier modules present; behavioral measurement missing",
            evidence=evidence)
    evidence.append(
        f"measured criteria {measured.passed_count}/{measured.total} "
        "(verification_eval.json)")
    for name in VERIFICATION_CRITERIA:
        if measured.criteria.get(name):
            evidence.append(f"measured: {_VERIFICATION_LABELS[name]}")
    score = base + (4.0 if measured.verdict_passed else 0.0)
    if not measured.verdict_passed:
        evidence.append(
            "verification_eval verdict FAIL — measured component withheld")
    return DimensionResult(
        name="verification_rigor", score=_clamp(score),
        basis="axiom falsifier + theorem audit EXECUTED by verification_eval.json",
        evidence=evidence,
        external=measured.external,
        independently_measured=measured.independently_measured,
        artifact_backed=measured.artifact_backed,
        measurement=measured.artifact)


def _score_reproducibility(root: str) -> DimensionResult:
    """Score reproducibility from MEASURED determinism + RNG isolation.

    Structure earns only a small base; the rest is credited when the
    reproducibility harness actually measured same-seed determinism, seed
    sensitivity and zero global-RNG calls, with a passing verdict. External
    reproduction still caps an otherwise-maximal score below 5.

    Args:
        root: repo root.

    Returns:
        The DimensionResult for reproducibility.
    """
    mods = [
        "telos/tools/perf_profiler.py",
        "telos/tools/endurance.py",
        "telos/tools/branch_coverage.py",
        "pyproject.toml",
    ]
    present = [m for m in mods if _exists(root, m)]
    base = 1.0 * (len(present) / len(mods))
    measured = read_measurement(
        root, "telos/audit/reproducibility_eval.json",
        REPRODUCIBILITY_CRITERIA)
    evidence = [f"structure present={len(present)}/{len(mods)}"]
    if measured is None:
        evidence.append(
            "no machine-checkable reproducibility_eval.json — existence-only base")
        return DimensionResult(
            name="reproducibility", score=_clamp(base),
            basis="harness modules present; behavioral measurement missing",
            evidence=evidence)
    evidence.append(
        f"measured criteria {measured.passed_count}/{measured.total} "
        "(reproducibility_eval.json)")
    for name in REPRODUCIBILITY_CRITERIA:
        if measured.criteria.get(name):
            evidence.append(f"measured: {_REPRODUCIBILITY_LABELS[name]}")
    score = base + (4.0 if measured.verdict_passed else 0.0)
    if not measured.verdict_passed:
        evidence.append(
            "reproducibility_eval verdict FAIL — measured component withheld")
    # External reproduction caps an otherwise-maximal score below 5.
    if not _exists(root, "research/reproduce"):
        score = min(score, 4.5)
        evidence.append("capped 4.5 without external reproduction")
    return DimensionResult(
        name="reproducibility", score=_clamp(score),
        basis="determinism + seed sensitivity + RNG isolation MEASURED by "
              "reproducibility_eval.json; capped without external reproduction",
        evidence=evidence,
        external=measured.external,
        independently_measured=measured.independently_measured,
        artifact_backed=measured.artifact_backed,
        measurement=measured.artifact)


def _score_autonomy(root: str) -> DimensionResult:
    """Score autonomy from the self-directed loop signals.

    Args:
        root: repo root.

    Returns:
        The DimensionResult for autonomy.
    """
    signals = [
        _exists(root, "telos/core/streams/inquiry_stream.py"),
        _exists(root, "telos/core/curiosity/drive.py"),
        _exists(root, "telos/dashboard/producer.py"),
    ]
    score = 3.5 * (sum(1 for s in signals if s) / len(signals))
    return DimensionResult(
        name="autonomy", score=_clamp(score),
        basis="self-directed inquiry + curiosity + live producer loop",
        evidence=[f"signals={sum(1 for s in signals if s)}/{len(signals)}"],
    )


def _multi_agent_eval_criteria(root: str) -> Dict[str, bool]:
    """Read the measured multi-agent coordination criteria from the artifact.

    The score is credited from an OBSERVED protocol run, not from files that
    mention agents — the same measured-artifact pattern as memory and learning.
    Missing / malformed / partially-passing artifacts credit nothing beyond the
    structural base (never a silent pass).

    Args:
        root: repo root.

    Returns:
        Mapping criterion -> passed for the canonical criteria, or {} when the
        artifact is missing or unreadable. Only a criteria mapping that carries
        every canonical key is returned, so a reader/writer key drift fails
        closed.
    """
    path = os.path.join(root, "telos", "audit", "multi_agent_eval.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        criteria = data.get("criteria")
        if not isinstance(criteria, dict):
            return {}
        return {name: bool(criteria.get(name)) for name in MULTI_AGENT_CRITERIA}
    except (OSError, ValueError, TypeError):
        return {}


def _score_multi_agent(root: str) -> DimensionResult:
    """Score multi-agent maturity from structures + measured coordination.

    Args:
        root: repo root.

    Returns:
        The DimensionResult for multi_agent.
    """
    distributed = _exists(root, "telos/core/council/distributed.py")
    delegation = _exists(root, "telos/core/coordination/delegation.py")
    # Base: the real advisory crew with weighted aggregation. Without the
    # measured eval this is where the score stays (the pre-measurement value).
    score = 1.5 if distributed else 0.0
    evidence: List[str] = []
    if distributed:
        evidence.append("telos/core/council/distributed.py (advisory crew)")
    if delegation:
        score += 0.5
        evidence.append(
            "telos/core/coordination/delegation.py (bounded protocol)")
    criteria = _multi_agent_eval_criteria(root)
    if criteria:
        total = len(MULTI_AGENT_CRITERIA)
        passed = 0
        for name in MULTI_AGENT_CRITERIA:
            if criteria.get(name):
                passed += 1
                evidence.append(
                    f"measured: {_MULTI_AGENT_LABELS[name]}")
        # The measured component is worth 2.5: all criteria pass -> 4.5 total
        # (target). Partial passes scale down honestly; a missing artifact
        # credits nothing.
        score += 2.5 * (passed / total)
        if passed < total:
            evidence.append(
                f"multi_agent_eval present but only {passed}/{total} "
                "criteria pass")
    else:
        evidence.append("no measured multi-agent eval (structure-only credit)")
    # First-party evidence alone can never reach 5.0: independent multi-agent
    # reproduction is the missing external artifact, so the honest ceiling for
    # measured-but-first-party coordination is 4.5.
    score = min(score, 4.5)
    backed, independent, external = _measurement_flags(
        root, "telos/audit/multi_agent_eval.json")
    return DimensionResult(
        name="multi_agent", score=_clamp(score),
        target=TARGETS["multi_agent"],
        basis="advisory crew + bounded delegation/verification/resolution, "
              "credited from measured multi_agent_eval.json; capped at 4.5 "
              "(first-party evidence)",
        evidence=evidence,
        external=external, independently_measured=independent,
        artifact_backed=backed,
        measurement="telos/audit/multi_agent_eval.json" if backed else None,
    )


def _score_docs(root: str) -> DimensionResult:
    """Score documentation from the architecture-doc signals.

    Args:
        root: repo root.

    Returns:
        The DimensionResult for docs.
    """
    docs = [
        "AGENTS.md", "README.md", "TELOS_V7.md", "CHANGELOG.md",
        "telos/AXIOMS.md",
    ]
    present = [d for d in docs if _exists(root, d)]
    score = 4.0 * (len(present) / len(docs))
    drift = _exists(root, "docs/known-issues.md")
    return DimensionResult(
        name="docs", score=_clamp(score),
        basis="architecture + axioms + readme + changelog; drift not auto-detected",
        evidence=[f"present={len(present)}/{len(docs)}",
                  f"known_issues_tracked={drift}"],
    )


_SCORERS = {
    "tool_use": _score_tool_use,
    "memory": _score_memory,
    "learning": _score_learning,
    "maturity": _score_maturity,
    "self_governance": _score_governance,
    "verification_rigor": _score_verification,
    "reproducibility": _score_reproducibility,
    "autonomy": _score_autonomy,
    "multi_agent": _score_multi_agent,
    "docs": _score_docs,
}


def compute_scorecard(root: Optional[str] = None) -> Dict[str, DimensionResult]:
    """Compute every rubric dimension from measured signals.

    Args:
        root: repo root (defaults to the project root).

    Returns:
        Mapping dimension name -> DimensionResult, for all DIMENSIONS.
    """
    root = root or PROJECT
    results: Dict[str, DimensionResult] = {}
    for name in DIMENSIONS:
        scorer = _SCORERS.get(name)
        if scorer is None:
            continue
        results[name] = scorer(root)
    return results


def four_baselines(root: Optional[str] = None) -> Dict[str, float]:
    """Return the uplift targets and their measured baselines.

    Args:
        root: repo root (defaults to the project root).

    Returns:
        Mapping dimension -> measured score for every target dimension.
    """
    card = compute_scorecard(root)
    return {name: card[name].score for name in TARGETS if name in card}


def report_lines(root: Optional[str] = None) -> List[str]:
    """Render the scorecard as printable lines.

    Args:
        root: repo root (defaults to the project root).

    Returns:
        A list of lines (rubric table + uplift target table).
    """
    card = compute_scorecard(root)
    lines = ["", f"{'TELOS Capability Scorecard':^74}", "=" * 74,
             f"{'dimension':<22}{'score':>7}{'target':>8}{'gap':>7}  basis", "-" * 74]
    for name in DIMENSIONS:
        r = card.get(name)
        if r is None:
            continue
        tgt = f"{r.target:.1f}" if r.target else "-"
        gap = f"{r.target - r.score:+.1f}" if r.target else "-"
        lines.append(f"{r.name:<22}{r.score:>7.2f}{tgt:>8}{gap:>7}  {r.basis}")
    lines.append("=" * 74)
    lines.append("Uplift baselines (target):")
    for name, target in TARGETS.items():
        r = card.get(name)
        if r is None:
            continue
        backing = _backing_label(
            r.artifact_backed, r.independently_measured, r.external)
        lines.append(f"  {name:<12} {r.score:.2f} -> {target:.1f}  [{backing}]")
    lines.append("-" * 74)
    lines.append("Measurement backing (what actually backs each score):")
    for name in DIMENSIONS:
        r = card.get(name)
        if r is None:
            continue
        backing = _backing_label(
            r.artifact_backed, r.independently_measured, r.external)
        artifact = r.measurement or "-"
        lines.append(f"  {r.name:<22}{backing:<46}  {artifact}")
    lines.append("  legend: external = artifact sourced outside TELOS's "
                 "first-party toolchain;")
    lines.append("          independently_measured = artifact written by a "
                 "separate first-party harness;")
    lines.append("          artifact_backed = machine-checkable criteria + "
                 "verdict; existence-only = file/path count.")
    lines.append("NOTE: every competitor score in the comparison is a judgment "
                 "estimate; TELOS's own rows are self-measured.")
    return lines


__all__ = [
    "DIMENSIONS", "TARGETS", "MULTI_AGENT_CRITERIA", "GOVERNANCE_CRITERIA",
    "VERIFICATION_CRITERIA", "REPRODUCIBILITY_CRITERIA",
    "REPRODUCTION_ARTIFACT_PATHS", "REPRODUCTION_CRITERIA", "DimensionResult",
    "compute_scorecard", "four_baselines", "report_lines",
]
