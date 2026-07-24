"""
TELOS v15: Influence Field Propagation Engine

Simulates cascading consequences of decisions across an interconnected network.
Models influence as waves that propagate, amplify, and decay.
"""
import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import deque

@dataclass
class InfluenceField:
    source_node: str
    magnitude: float
    damping: float = 0.1
    decay_rate: float = 0.05

    def calculate_cost(self, distance: float, time_elapsed: float) -> float:
        """I(t,d) = A * e^(-lambda * d) * f(t)"""
        # f(t) modeled as exponential decay over time
        time_decay = np.exp(-self.decay_rate * time_elapsed)
        spatial_decay = np.exp(-self.damping * distance)
        return float(self.magnitude * spatial_decay * time_decay)

class InfluenceFieldEngine:
    """Calculates downstream propagation costs (Phi) of trajectories."""
    
    def __init__(self, damping: float = 0.1, max_fields: int = 1000):
        self.damping = damping
        self.max_fields = max_fields
        # Track simulated entity interactions with bounded buffer
        self.influence_fields: deque = deque(maxlen=max_fields)

    def register_event(self, node_id: str, magnitude: float) -> None:
        self.influence_fields.append(InfluenceField(node_id, magnitude, self.damping))

    def propagate(self, affected_node_id: str, distance: float, time: float) -> float:
        """Sum total ripple costs across all active influence fields."""
        total_phi = 0.0
        for field in self.influence_fields:
            total_phi += field.calculate_cost(distance, time)
        return total_phi

    def clear(self) -> None:
        self.influence_fields = []
