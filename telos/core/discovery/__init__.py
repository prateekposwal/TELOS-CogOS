"""
Discovery package — the pre-existing general DiscoveryOrchestrator, plus the
endogenous Assumption Discovery research prototype.
"""

from telos.core.discovery.orchestrator import DiscoveryOrchestrator
from telos.core.discovery.assumption_discovery import (
    AssumptionDiscoverer, DiscoveredAssumption, Transition,
)
from telos.core.discovery.causal_probe import (
    CausalProbe, CausalStatus, DiscoveredRelation,
)
from telos.core.discovery.experiment_selection import (
    CanonicalExperimentSelector, Hypothesis, ExperimentOption,
)
from telos.core.discovery.planner import (
    PlannerAwareSelector, PlannerMode, Plan,
)
from telos.core.discovery.causal_planner import CausalPlanner
from telos.core.discovery.hypothesis_generation import (
    HypothesisGenerator, HypothesisCandidate,
)
from telos.core.discovery.structure_invention import (
    StructureInventor, StructuralHypothesis, VariableStatus,
)
from telos.core.discovery.model_class import (
    assess, ModelClassVerdict, ModelClass, AcyclicModel, StatefulModel,
    CausalStructure, CausalRelation, discover_structure,
)

__all__ = [
    "DiscoveryOrchestrator",
    "AssumptionDiscoverer", "DiscoveredAssumption", "Transition",
    "CausalProbe", "CausalStatus", "DiscoveredRelation",
    "CanonicalExperimentSelector", "Hypothesis", "ExperimentOption",
    "PlannerAwareSelector", "PlannerMode", "Plan", "CausalPlanner",
    "HypothesisGenerator", "HypothesisCandidate",
    "StructureInventor", "StructuralHypothesis", "VariableStatus",
    "assess", "ModelClassVerdict", "ModelClass", "AcyclicModel", "StatefulModel",
    "CausalStructure", "CausalRelation", "discover_structure",
]
