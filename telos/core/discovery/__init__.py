"""
Discovery package — the pre-existing general DiscoveryOrchestrator, plus the
endogenous Assumption Discovery research prototype.
"""

from telos.core.discovery.orchestrator import DiscoveryOrchestrator
from telos.core.discovery.assumption_discovery import (
    AssumptionDiscoverer, DiscoveredAssumption, Transition,
)

__all__ = [
    "DiscoveryOrchestrator",
    "AssumptionDiscoverer", "DiscoveredAssumption", "Transition",
]
