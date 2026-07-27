"""
Counterfactual Engine — Domain-agnostic simulation with StrategicOption queries.

The engine generates alternative future trajectories and provides query
methods for Axiom 4.3 (Possibility Preservation): the system must always
maintain a set of alternative future trajectories.

Law of Attention Integration:
  - Counterfactual Diversity: variance of simulated futures quantifies
    decision quality bounds (Axiom 4.7)
  - Attention-weighted generation: when attention allocation is provided,
    worlds are generated based on threat/opportunity focus
"""

import logging
import numpy as np
from typing import List, Any, Optional, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum
from telos.core.contracts.domain_model import DomainSimulator

logger = logging.getLogger('telos_simulation')


@dataclass
class ProbabilisticScore:
    """Uncertainty-quantified score — mean, variance, and 95% CI."""
    mean: float
    std: float
    n_samples: int
    ci_lower: float
    ci_upper: float
    min_score: float
    max_score: float


class TrajectoryClass(str, Enum):
    """P3: Compressed trajectory class for Value of Information pruning.
    
    Raw trajectories are compressed into one of five action classes:
      - EXPLORE: High-uncertainty, wide search
      - EXPLOIT: Low-uncertainty, narrow optimization
      - RECOVER: Recovery from failure/degradation
      - WAIT: Resource preservation, no action
      - EXIT: Terminal/escape trajectory
    """
    EXPLORE = "explore"
    EXPLOIT = "exploit"
    RECOVER = "recover"
    WAIT = "wait"
    EXIT = "exit"



@dataclass
class StrategicOption:
    """An alternative future trajectory — proof of Possibility Preservation (Axiom 4.3)."""
    world: Any
    score: float
    rank: int
    project_id: str = "default"
    horizon: int = 0
    metadata: Dict = field(default_factory=dict)
    probabilistic: Optional[ProbabilisticScore] = None

    @property
    def variance(self) -> float:
        return self.probabilistic.std ** 2 if self.probabilistic else 0.0
