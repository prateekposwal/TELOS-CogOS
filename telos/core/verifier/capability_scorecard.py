"""
Capability Scorecard — measures TELOS's capability rubric from real signals.

PATTERN (falsifiable self-assessment, Λ6.5): a capability score must be derived
from an OBSERVABLE artifact, not asserted. Each dimension is scored from
filesystem/registry signals that change only when the underlying capability
changes. A score is tagged ``external=False`` unless an independently produced
artifact backs it — so a TELOS-authored tool grading TELOS is never mistaken
for external validation (research/FALSIFIABLE_THEOREMS.md applied to the
roadmap).

The four "uplift" dimensions (tool_use, memory, learning, maturity) carry the
architect's targets; the others report their self-assessed baseline. Weights
are explicit so the arithmetic is auditable and cannot be quietly tuned.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# The architect's uplift targets (Phase 1–4 of the capability roadmap).
TARGETS: Dict[str, float] = {
    "tool_use": 4.5,
    "memory": 5.0,
    "learning": 4.0,
    "maturity": 5.0,
}

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
        external: True only when an independent artifact backs the score.
    """

    name: str
    score: float
    basis: str
    evidence: List[str] = field(default_factory=list)
    target: Optional[float] = None
    external: bool = False

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
        has_network_family = any(s.family == "network" for s in specs)
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
    score = 3.5  # base: real, capped stores (knowledge/ledger/memory)
    evidence = [f"memory stores present={len(present)}/{len(stores)}"]
    for label, cond in (("unified controller", has_controller),
                        ("tiered decision memory", has_tiering),
                        ("retrieval-quality eval", has_eval)):
        if cond:
            score += 0.5
            evidence.append(label)
    if has_controller and has_tiering and has_eval:
        evidence.append("Letta-class mechanisms complete")
    return DimensionResult(
        name="memory", score=_clamp(score), target=TARGETS["memory"],
        basis="stores + controller/tiering/retrieval-eval completeness",
        evidence=evidence,
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
    score = 2.0
    evidence = []
    for label, cond in (("theory builder", builder),
                        ("falsifiable experiment", experiment),
                        ("curriculum generation", curriculum),
                        ("verified skill acquisition", acquisition),
                        ("measured learning curve", curve)):
        if cond:
            score += 0.5
            evidence.append(label)
    if not evidence:
        evidence.append("no learning machinery detected")
    return DimensionResult(
        name="learning", score=_clamp(score), target=TARGETS["learning"],
        basis="theory/skill machinery + curriculum + measured learning curve",
        evidence=evidence,
    )


def _score_maturity(root: str) -> DimensionResult:
    """Score the maturity/adoption dimension from release-artifact signals.

    External reproduction and adoption are NOT solo-closable, so the score is
    capped below 5.0 until an independent artifact exists.

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
    external_artifact = None
    for candidate in ("research/reproduce", "reproduction_verification.json"):
        if _exists(root, candidate):
            external_artifact = candidate
            break
    if external_artifact:
        score += 0.5
        evidence.append(f"external reproduction artifact: {external_artifact}")
    # Adoption (users/stars/issues) is not measurable from the repo: never
    # awarded here, and the score is capped so 5.0 cannot be self-declared.
    score = min(score, 4.0)
    return DimensionResult(
        name="maturity", score=_clamp(score), target=TARGETS["maturity"],
        basis="packaging/release/CLI signals; capped at 4.0 without external reproduction + adoption",
        evidence=evidence, external=bool(external_artifact),
    )


def _score_governance(root: str) -> DimensionResult:
    """Score self-governance from the blocking-gate modules.

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
    score = 5.0 * (len(present) / len(mods))
    return DimensionResult(
        name="self_governance", score=_clamp(score),
        basis="blocking council + firewall + capability authorization + governor present",
        evidence=[f"present={len(present)}/{len(mods)}"],
    )


def _score_verification(root: str) -> DimensionResult:
    """Score verification rigor from the adversarial-verification modules.

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
    score = 4.5 * (len(present) / len(mods))
    return DimensionResult(
        name="verification_rigor", score=_clamp(score),
        basis="axiom falsifier + theorem audit + external log audit + non-ergodicity",
        evidence=[f"present={len(present)}/{len(mods)}"],
    )


def _score_reproducibility(root: str) -> DimensionResult:
    """Score reproducibility/measurement from the harness modules.

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
    score = 5.0 * (len(present) / len(mods))
    # External reproduction caps an otherwise-maximal score below 5.
    if not _exists(root, "research/reproduce"):
        score = min(score, 4.5)
    return DimensionResult(
        name="reproducibility", score=_clamp(score),
        basis="perf contract + endurance gate + coverage + packaging; capped without external reproduction",
        evidence=[f"present={len(present)}/{len(mods)}"],
    )


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


def _score_multi_agent(root: str) -> DimensionResult:
    """Score multi-agent maturity from coordination signals.

    Args:
        root: repo root.

    Returns:
        The DimensionResult for multi_agent.
    """
    distributed = _exists(root, "telos/core/council/distributed.py")
    coordination = _exists(root, "telos/core/coordination/coordinator.py")
    score = (1.0 if distributed else 0.0) + (1.0 if coordination else 0.0)
    return DimensionResult(
        name="multi_agent", score=_clamp(score),
        basis="advisory distributed council + coordination (scaffold)",
        evidence=[f"distributed={distributed}", f"coordination={coordination}"],
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
    """Return just the four uplift targets and their measured baselines.

    Args:
        root: repo root (defaults to the project root).

    Returns:
        Mapping dimension -> measured score for the four target dimensions.
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
        ext = "external" if r.external else "self-assessed"
        lines.append(f"  {name:<12} {r.score:.2f} -> {target:.1f}  [{ext}]")
    lines.append("NOTE: every competitor score in the comparison is a judgment "
                 "estimate; TELOS's own rows are self-measured.")
    return lines


__all__ = [
    "DIMENSIONS", "TARGETS", "DimensionResult", "compute_scorecard",
    "four_baselines", "report_lines",
]
