"""
Intent Intermediate Representation (Intent IR)

A structured, domain-agnostic representation of agent intent.
Pipeline produces IntentIR objects; pluggable adapters convert
them to domain-specific primitive actions.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class IntentIR:
    intent_type: str = "unknown"
    source: Any = None
    target: Any = None
    confidence: float = 1.0
    params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
