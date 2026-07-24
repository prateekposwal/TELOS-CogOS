"""
Relational Context — scaffolding for Relational Reasoning (R) module.

Provides the RelationalContext dataclass and RelationalCoherence property
for the Relational Reasoning dimension of TELOS.

This is scaffolding only — full RelationalReasoning logic will be
implemented separately.
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class RelationalContext:
    """Encapsulates the relational reasoning state of the system.

    Fields represent the five relational dimensions that govern how
    TELOS interacts with users, agents, and itself:

        trust:         Level of epistemic trust in external information sources
        authority:     Deference to authoritative sources (policies, user directives)
        collaboration: Willingness to engage in cooperative problem-solving
        dependency:    Reliance on external systems or previous decisions
        responsibility: Accountability for outcomes and commitments
    """
    trust: float = 0.5
    authority: float = 0.5
    collaboration: float = 0.5
    dependency: float = 0.0
    responsibility: float = 0.5

    @property
    def relational_coherence(self) -> float:
        """Compute consistency across all relational variables.

        Placeholder: returns 1.0 (perfect coherence) until the full
        RelationalReasoning module is implemented.
        """
        return 1.0

    def to_dict(self) -> Dict[str, float]:
        """Serialize to JSON-compatible dict."""
        return {
            "trust": self.trust,
            "authority": self.authority,
            "collaboration": self.collaboration,
            "dependency": self.dependency,
            "responsibility": self.responsibility,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "RelationalContext":
        """Deserialize from a dict (returned by to_dict).

        Falls back to defaults for any missing key, enabling forward/backward
        compatibility as fields are added.
        """
        return cls(
            trust=float(data.get("trust", 0.5)),
            authority=float(data.get("authority", 0.5)),
            collaboration=float(data.get("collaboration", 0.5)),
            dependency=float(data.get("dependency", 0.0)),
            responsibility=float(data.get("responsibility", 0.5)),
        )
