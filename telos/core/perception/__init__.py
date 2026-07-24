"""
TELOS Perception Layer — Resolution-Aware Input Quality Analysis.

Components:
  - PerceptionQuality: Assesses whether input resolution supports object detection
  - ResolutionGate: Governance-level block when input quality is insufficient
  - ProxyStream: Tracks proxy objects when direct detection is impossible
  - PerceptionExplainer: Translates quality reports into human-readable explanations
  - CapabilityRegistry: Knows what the system can detect under what conditions
"""

from telos.core.perception.quality import PerceptionQuality, QualityReport
from telos.core.perception.gate import ResolutionGate, GateVerdict
from telos.core.perception.proxy import ProxyStream
from telos.core.perception.explainer import PerceptionExplainer
from telos.core.perception.capabilities import CapabilityRegistry, DetectionCapability

__all__ = [
    "PerceptionQuality", "QualityReport",
    "ResolutionGate", "GateVerdict",
    "ProxyStream",
    "PerceptionExplainer",
    "CapabilityRegistry", "DetectionCapability",
]
