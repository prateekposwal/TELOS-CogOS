from dataclasses import dataclass, field
from typing import Dict, Any, List
import numpy as np

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
