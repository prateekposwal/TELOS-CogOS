"""
TELOS v6 — EvidenceSource / evidence envelope.

Phase 2. An incremental, minimal evidence provenance layer. The dangerous
failure is NOT uncertainty — it is "simulation certainty mistaken for
physical truth". Every important belief should carry an evidence source and
a validation status so TELOS can distinguish:

    test_health = 1.0  source=SIMULATION  validation=ASSUMED
from
    test_health = 1.0  source=EXTERNAL_EXECUTION  validation=MEASURED

The first must NEVER silently masquerade as the second.

This is deliberately minimal (v6 minimum): `source` + `validation_status`,
with optional `confidence`/`fidelity`/`timestamp`. It is NOT the giant
provenance dependency graph (future scope).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Dict
import time


class EvidenceSource(str, Enum):
    SIMULATION = "SIMULATION"
    MEASUREMENT = "MEASUREMENT"
    EXPERIMENT = "EXPERIMENT"
    HUMAN_EXPERT = "HUMAN_EXPERT"
    EXTERNAL_SOLVER = "EXTERNAL_SOLVER"   # e.g. compiler/tests/type-checker
    HISTORICAL_DATA = "HISTORICAL_DATA"
    DERIVED_INFERENCE = "DERIVED_INFERENCE"


class ValidationStatus(str, Enum):
    ASSUMED = "ASSUMED"           # assumed, never confirmed (must not = measured)
    OBSERVED = "OBSERVED"         # observed but not rigorously validated
    MEASURED = "MEASURED"         # measured by an external solver/tool
    VALIDATED = "VALIDATED"       # repeatedly confirmed against reality
    FALSIFIED = "FALSIFIED"       # contradicted by observation
    UNVALIDATED = "UNVALIDATED"   # no validation performed yet


@dataclass
class EvidenceInfo:
    """Minimal evidence provenance envelope attached to a belief/value.

    The essential property: a value stamped `source=SIMULATION` +
    `validation=ASSUMED` is structurally distinguishable from one stamped
    `source=EXTERNAL_SOLVER` + `validation=MEASURED`. Downstream logic may
    refuse to treat assumed evidence as measured evidence.
    """
    source: EvidenceSource = EvidenceSource.DERIVED_INFERENCE
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED
    confidence: Optional[float] = None
    fidelity: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def is_measured(self) -> bool:
        return self.validation_status in (ValidationStatus.MEASURED,
                                          ValidationStatus.VALIDATED,
                                          ValidationStatus.OBSERVED)

    @property
    def is_assumed(self) -> bool:
        return self.validation_status == ValidationStatus.ASSUMED

    @property
    def is_falsified(self) -> bool:
        return self.validation_status == ValidationStatus.FALSIFIED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.value if isinstance(self.source, EvidenceSource) else str(self.source),
            "validation_status": (
                self.validation_status.value
                if isinstance(self.validation_status, ValidationStatus)
                else str(self.validation_status)
            ),
            "confidence": self.confidence,
            "fidelity": self.fidelity,
            "timestamp": self.timestamp,
            "is_measured": self.is_measured,
        }


def measured(source: EvidenceSource = EvidenceSource.EXTERNAL_SOLVER,
             confidence: float = None, fidelity: float = None) -> EvidenceInfo:
    """Convenience: build a MEASURED evidence stamp.

    Args:
        source: the source the measurement came from.
        confidence: the confidence to attach (None -> default).
        fidelity: the world-model fidelity to attach (None -> default).
    """
    return EvidenceInfo(source=source, validation_status=ValidationStatus.MEASURED,
                        confidence=confidence, fidelity=fidelity)


def assumed(source: EvidenceSource = EvidenceSource.SIMULATION,
            confidence: float = None) -> EvidenceInfo:
    """Convenience: build an ASSUMED evidence stamp (never == measured).

    Args:
        source: the source the assumption came from.
        confidence: the confidence to attach (None -> default).
    """
    return EvidenceInfo(source=source, validation_status=ValidationStatus.ASSUMED,
                        confidence=confidence)
