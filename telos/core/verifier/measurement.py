"""
Measurement provenance — the difference between "an artifact exists" and "a
score is backed by an independently produced, machine-checkable measurement".

The scorecard's original honesty rule was a single ``external`` boolean that
stayed False for every dimension. That conflated three distinct claims:

  * ``artifact_backed`` — the score is credited from a real measurement
    artifact (not a path/file existence check). The artifact declares its own
    ``producer`` and is ``machine_checkable`` (explicit criteria + verdict).
  * ``independently_measured`` — the artifact was produced by a tool SEPARATE
    from the scoring code path. A first-party harness run as its own process
    qualifies here, but it is still TELOS grading TELOS.
  * ``external`` — the artifact's provenance declares a source OUTSIDE TELOS's
    own first-party toolchain (``EXTERNAL_SOURCES``), e.g. an operator-supplied
    reproduction file. This is the strong sense of external validation and is
    deliberately NOT granted to a first-party harness merely because it is a
    separate process.

Keeping the three separate is what stops the scorecard from overclaiming: the
output can say "artifact-backed, independently measured, first-party" without
pretending a TELOS-authored harness is an outside auditor
(research/FALSIFIABLE_THEOREMS.md, Λ6.5).

An artifact is a JSON object with:

    {
      "provenance": {
        "schema_version": 1,
        "producer": "telos/tools/governance_eval.py",
        "source": "first_party",          # or "external"/"operator"
        "machine_checkable": true,
        "criteria": ["...", "..."]
      },
      "criteria": {"<criterion>": true, ...},
      "verdict": {"passed": true, "passed_count": N, "total": M},
      ... tool-specific metrics ...
    }

A missing/malformed provenance block, schema version, producer, or verdict
fails CLOSED: the measurement is not read and no measured points are credited.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ARTIFACT_SCHEMA_VERSION = 1

# Provenance sources that are NOT TELOS first-party. Only these earn the strong
# ``external`` flag. A first-party harness (even a separate process) does not.
FIRST_PARTY_SOURCES = frozenset({"first_party"})
EXTERNAL_SOURCES = frozenset({"external", "operator"})

# The scoring module. An artifact written BY the scorecard can never be
# "independently measured" relative to it.
SCORER_PRODUCER = "telos/core/verifier/capability_scorecard.py"


def provenance(producer: str, criteria: List[str],
               source: str = "first_party") -> Dict[str, object]:
    """Build the provenance block every measurement artifact must carry.

    Args:
        producer: repo-relative path of the tool that writes the artifact.
        criteria: the criterion names the artifact reports.
        source: provenance class — "first_party" (default), "external", or
            "operator". Only non-first-party sources earn ``external``.

    Returns:
        The provenance mapping to embed under the artifact's "provenance" key.
    """
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "producer": producer,
        "source": source,
        "machine_checkable": True,
        "criteria": list(criteria),
    }


@dataclass(frozen=True)
class Measurement:
    """A validated, provenance-stamped measurement artifact.

    Attributes:
        artifact: repo-relative path the measurement was read from.
        criteria: validated criterion name -> passed.
        verdict_passed: the artifact's own overall verdict (all criteria pass).
        external: artifact sourced outside TELOS's first-party toolchain.
        independently_measured: artifact produced by a non-scorer tool.
        artifact_backed: artifact carries valid, machine-checkable provenance.
    """

    artifact: str
    criteria: Dict[str, bool]
    verdict_passed: bool
    external: bool
    independently_measured: bool
    artifact_backed: bool

    @property
    def passed_count(self) -> int:
        """How many of the artifact's criteria passed."""
        return sum(1 for v in self.criteria.values() if v)

    @property
    def total(self) -> int:
        """How many criteria the artifact reports."""
        return len(self.criteria)


def _classify(prov: object) -> Tuple[bool, bool, bool]:
    """Classify a provenance block into the three measurement flags.

    Args:
        prov: the raw "provenance" value from an artifact.

    Returns:
        (artifact_backed, independently_measured, external). All False when
        the provenance block is missing or malformed (fail closed).
    """
    if not isinstance(prov, dict):
        return (False, False, False)
    if prov.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        return (False, False, False)
    producer = str(prov.get("producer") or "")
    if not producer or prov.get("machine_checkable") is not True:
        return (False, False, False)
    source = str(prov.get("source") or "")
    artifact_backed = True
    independently_measured = producer != SCORER_PRODUCER
    external = independently_measured and source in EXTERNAL_SOURCES
    return (artifact_backed, independently_measured, external)


def read_measurement(root: str, relpath: str,
                     required_criteria: Tuple[str, ...]) -> Optional[Measurement]:
    """Read and validate a measurement artifact against its required schema.

    The artifact must carry a valid provenance block, report a boolean value
    for every required criterion, and declare a boolean overall verdict. Any
    failure returns None so the caller credits nothing (never a silent pass).

    Args:
        root: repo root.
        relpath: repo-relative path of the artifact.
        required_criteria: criterion names the artifact must report.

    Returns:
        A validated Measurement, or None when the artifact is missing,
        malformed, or does not carry every required criterion.
    """
    path = os.path.join(root, relpath)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    artifact_backed, independently_measured, external = _classify(
        data.get("provenance"))
    if not artifact_backed:
        return None
    raw_criteria = data.get("criteria")
    if not isinstance(raw_criteria, dict):
        return None
    for name in required_criteria:
        if not isinstance(raw_criteria.get(name), bool):
            return None
    verdict = data.get("verdict")
    if not isinstance(verdict, dict) or not isinstance(verdict.get("passed"), bool):
        return None
    criteria = {name: bool(raw_criteria[name]) for name in required_criteria}
    return Measurement(
        artifact=relpath,
        criteria=criteria,
        verdict_passed=bool(verdict["passed"]),
        external=external,
        independently_measured=independently_measured,
        artifact_backed=artifact_backed,
    )


def read_provenance(root: str, relpath: str) -> Dict[str, object]:
    """Read only the provenance block of an artifact (for flag reporting).

    Args:
        root: repo root.
        relpath: repo-relative path of the artifact.

    Returns:
        The raw provenance mapping, or {} when missing/unreadable.
    """
    path = os.path.join(root, relpath)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    prov = data.get("provenance")
    return prov if isinstance(prov, dict) else {}


def flags_from_provenance(prov: object) -> Tuple[bool, bool, bool]:
    """Public wrapper over provenance classification for scorers/tests.

    Args:
        prov: a raw provenance mapping (or anything else).

    Returns:
        (artifact_backed, independently_measured, external).
    """
    return _classify(prov)


__all__ = [
    "ARTIFACT_SCHEMA_VERSION", "FIRST_PARTY_SOURCES", "EXTERNAL_SOURCES",
    "SCORER_PRODUCER", "Measurement", "provenance", "read_measurement",
    "read_provenance", "flags_from_provenance",
]
