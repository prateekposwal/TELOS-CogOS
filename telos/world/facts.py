from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import numpy as np

from telos.world.evidence import EvidenceInfo


@dataclass
class DomainFacts:
    """
    Standardized semantic envelope for domain observations.
    All simulators must report facts in this shape to maintain 
    runtime portability.
    """
    state: np.ndarray
    resources: Dict[str, float]
    constraints: List[str]
    events: List[str]
    metrics: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    # TELOS v6 (Phase 2): optional evidence provenance for the facts. When a
    # simulator supplies evidence (e.g. metrics stamped SIMULATION+ASSUMED vs
    # EXTERNAL_SOLVER+MEASURED), downstream logic can refuse to treat assumed
    # evidence as measured evidence. Backwards-compatible: defaults to None.
    evidence: Optional[EvidenceInfo] = None

