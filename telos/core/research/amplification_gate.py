"""
Research Amplification Gate — TELOS pre-PERCEIVE evidence-enrichment stage (Λ6.5).

DIAGNOSED PATTERN (2026-08-29, three consecutive category-research runs):
  bounded-evidence-mode — each run answered from analytic reasoning over a
  NARROW hand-selected evidence subset and reasoned as if the model's priors
  were complete, with NO deliberate external-research pass (primary sources,
  market indices, trade press, definitions, regulation status) BEFORE any
  stream/simulation/answer. Concretely: Run 2 declared Six Senses Vana and
  Aman "the competition" — a LOCAL-COMPETITOR frame — while the actual
  category battle is global (SHA Island, Eywa, Canyon Ranch, Longevity Suite
  × Visionnaire) and now regulated (Abu Dhabi licensing, GWI formal
  sub-category status).

THE STRUCTURAL FIX: this gate is a STANDING pre-PERCEIVE pipeline stage. It
enriches the evidence base from grounded external sources BEFORE any stream
or simulation consumes it.

FAILURE CONDITION (mandatory): a run that reaches streams/simulate without
this gate's evidence-enrichment pass is LEFT, not DONE. If any MANDATORY
evidence dimension has ZERO grounded external coverage, the gate returns
FAIL and the run is LEFT — answering anyway would repeat the diagnosed
pattern. "DONE" is only achievable through the amplification report.

Forearms the SAME honesty rule the council enforces (Λ2.3 Kintsugi, Λ6.5
evidence-grounded belief revision): claims not tied to a named external
source are scored as hypotheses, never as verified facts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger('telos_research_amplification')


class SourceClassification(str, Enum):
    """How an evidence source relates to the system's own reasoning."""
    PRIMARY = "primary"        # first-party category source / market index / regulator
    SECONDARY = "secondary"    # trade press / aggregator / search-snippet carry-over
    INTERNAL = "internal"      # the model's own prior reasoning — NOT external enrichment


# Mandatory evidence dimensions every category-research run must cover.
# A gap in ANY dimension = the run is LEFT (bounded-evidence-mode recurrence).
MANDATORY_DIMENSIONS: tuple = (
    "category_definition",        # what the asset class formally IS (classification body)
    "regulation_licensing",       # regulatory/licensing status of the category
    "premium_economics",          # measured premium data (branded residence %, wellness uplift)
    "building_level_evidence",    # evidence the physical building measurably works
    "market_players_structure",   # named live category entrants + market pipeline
    "capital_behaviour",          # how capital enters the category (funds/REIT/co-investment)
    "substance_vs_signage",       # the category's own diligence markers
)


@dataclass
class EvidenceSource:
    """A named external source feeding the amplification pass."""
    source_id: str                      # letter/slug used in citation, e.g. "A"
    name: str                           # e.g. "LI News — Buying Time: Longevity Moves Into Real Estate"
    venue: str                          # publication / venue
    fetched_at: str = "2026-08-29"
    classification: SourceClassification = SourceClassification.SECONDARY
    url: str = ""

    @property
    def is_external(self) -> bool:
        """True when the source is grounded OUTSIDE the model's own reasoning."""
        return self.classification != SourceClassification.INTERNAL

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "venue": self.venue,
            "fetched_at": self.fetched_at,
            "classification": self.classification.value,
            "url": self.url,
        }


@dataclass
class EvidenceClaim:
    """A single grounded claim: source + claim text + the dimension it covers."""
    source_id: str
    claim: str
    dimension: str
    confidence: float = 0.9   # confidence that the claim is genuinely supported by the source

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "claim": self.claim,
            "dimension": self.dimension,
            "confidence": self.confidence,
        }


@dataclass
class AmplificationReport:
    """The gate's verdict on a run: enriched (PASS) or evidence-gapped (FAIL/LEFT)."""
    passed: bool
    covered_dimensions: Dict[str, List[str]] = field(default_factory=dict)  # dim -> source_ids
    missing_dimensions: List[str] = field(default_factory=list)
    total_claims: int = 0
    total_external_sources: int = 0
    run_status: str = "DONE"          # "DONE" only when passed; else "LEFT"
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "covered_dimensions": {k: sorted(v) for k, v in self.covered_dimensions.items()},
            "missing_dimensions": self.missing_dimensions,
            "total_claims": self.total_claims,
            "total_external_sources": self.total_external_sources,
            "run_status": self.run_status,
            "reason": self.reason,
        }


class ResearchAmplificationGate:
    """Standing pre-PERCEIVE stage: enrich evidence BEFORE streams consume it.

    The gate holds the run's registered external evidence. Its `run()` verdict
    is the run's license to proceed to STREAMS/SIMULATE: if any mandatory
    dimension lacks grounded EXTERNAL coverage, the gate fails the run —
    a category answer produced under a coverage gap is LEFT, not DONE.

    Future runs MUST call `run()` before any stream/simulation consumes the
    brief. Skipping the gate IS the diagnosed failure mode.
    """

    def __init__(self) -> None:
        self._sources: Dict[str, EvidenceSource] = {}
        self._claims: List[EvidenceClaim] = []
        self.last_report: Optional[AmplificationReport] = None

    # ── registration ────────────────────────────────────────────────────────
    def register_source(self, source: EvidenceSource) -> None:
        if source.source_id in self._sources:
            raise ValueError(f"duplicate source_id '{source.source_id}'")
        self._sources[source.source_id] = source

    def register_claim(self, claim: EvidenceClaim) -> None:
        if claim.source_id not in self._sources:
            raise ValueError(
                f"claim references unknown source '{claim.source_id}' — "
                "register the source first (Λ6.5: every claim needs a named source)"
            )
        if claim.dimension not in MANDATORY_DIMENSIONS:
            raise ValueError(
                f"claim dimension '{claim.dimension}' not in mandatory set "
                f"{MANDATORY_DIMENSIONS}"
            )
        self._claims.append(claim)

    @property
    def sources(self) -> List[EvidenceSource]:
        return list(self._sources.values())

    @property
    def claims(self) -> List[EvidenceClaim]:
        return list(self._claims)

    # ── the gate ────────────────────────────────────────────────────────────
    def run(self) -> AmplificationReport:
        """Evaluate the run's external-evidence coverage.

        Returns an AmplificationReport. passed=False means the run is LEFT:
        at least one mandatory dimension has zero EXTERNAL grounding and the
        answer cannot be called DONE without repeating bounded-evidence-mode.
        """
        if not self._sources:
            report = AmplificationReport(
                passed=False,
                missing_dimensions=list(MANDATORY_DIMENSIONS),
                reason="no external evidence sources registered — the run was "
                       "answered from internal priors only (bounded-evidence-mode)",
            )
            report.run_status = "LEFT"
            logger.warning(f"ResearchAmplificationGate: FAIL — {report.reason}")
            self.last_report = report
            return report

        coverage: Dict[str, Set[str]] = {d: set() for d in MANDATORY_DIMENSIONS}
        for c in self._claims:
            src = self._sources.get(c.source_id)
            if src is not None and src.is_external and c.dimension in coverage:
                coverage[c.dimension].add(c.source_id)

        missing = [d for d in MANDATORY_DIMENSIONS if not coverage[d]]
        report = AmplificationReport(
            passed=not missing,
            covered_dimensions={d: sorted(s) for d, s in coverage.items() if s},
            missing_dimensions=missing,
            total_claims=len(self._claims),
            total_external_sources=sum(1 for s in self._sources.values() if s.is_external),
        )
        if missing:
            report.run_status = "LEFT"
            report.reason = (
                f"evidence gap on: {', '.join(missing)} — run is LEFT; "
                "conduct the external-research pass before answering"
            )
            logger.warning(f"ResearchAmplificationGate: FAIL — {report.reason}")
        else:
            report.reason = (
                f"all {len(MANDATORY_DIMENSIONS)} mandatory dimensions covered "
                f"by {report.total_external_sources} external sources / "
                f"{report.total_claims} grounded claims — run may proceed to STREAMS"
            )
            logger.info(f"ResearchAmplificationGate: PASS — {report.reason}")
        self.last_report = report
        return report

    # ── serialization ───────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "sources": [s.to_dict() for s in self._sources.values()],
            "claims": [c.to_dict() for c in self._claims],
            "last_report": self.last_report.to_dict() if self.last_report else None,
        }


__all__ = [
    "ResearchAmplificationGate",
    "AmplificationReport",
    "EvidenceSource",
    "EvidenceClaim",
    "SourceClassification",
    "MANDATORY_DIMENSIONS",
]
