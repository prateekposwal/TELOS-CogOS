"""
AxiomEvolution — System Proposes New Axioms, Human Approves.

Prateek's insight #8: "Axiom Evolution — system proposes new axioms,
human approves. Never self-edits."

The current axioms are static (20 axioms in AXIOMS.md). This module
enables the system to observe its own behavior, detect gaps in the
axiom framework, and propose new axioms for human approval.

Architecture:
  - The AxiomEvolution engine monitors system behavior for patterns
    that suggest a missing axiom
  - When it detects a gap, it formulates a proposed axiom with:
      * Name and description
      * Layer assignment (based on the existing 5-layer structure)
      * Evidence: what observations suggest this axiom is needed
      * Implementation suggestion: where in the codebase
  - Proposals are stored for human review
  - The system NEVER self-edits axioms — only proposes

This is a PROPOSAL module. The human approval workflow is not yet
implemented (requires HumanGateway extension).
"""

from __future__ import annotations

import logging
import time
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_axiom_evolution')


class AxiomLayer(Enum):
    ARCHITECTURAL = 1
    FEEDBACK_MEMORY = 2
    ADAPTIVE_CAPACITY = 3
    EMERGENT_INTELLIGENCE = 4
    COMMITMENT_THEORY = 5
    NEW_LAYER = 6  # For axioms that don't fit existing layers


@dataclass
class AxiomProposal:
    """A proposed new axiom for human review."""
    id: str
    name: str
    description: str
    layer: AxiomLayer
    rationale: str
    evidence: List[str]  # Observations supporting this axiom
    implementation_suggestion: str
    proposed_by: str = "AxiomEvolution"
    status: str = "proposed"  # proposed, under_review, approved, rejected
    created: float = 0.0
    reviewed_by: Optional[str] = None
    review_notes: Optional[str] = None
    confidence: float = 0.0  # How confident the system is that this is needed


class AxiomEvolutionEngine:
    """Monitors system behavior and proposes new axioms.

    Detection triggers:
      1. Repeated pattern of council blocks with no clear resolution
      2. Decision Integrity consistently affected by unhandled edge cases
      3. Recurring states where the 42 axioms don't provide guidance
      4. User requests for capabilities that current axioms don't cover

    This engine is OBSERVATIONAL only. It never modifies axioms.
    All proposals require human approval.
    """

    def __init__(self):
        self._proposals: Dict[str, AxiomProposal] = {}
        self._observation_history: List[Dict] = []
        self._max_observations = 200
        self._total_proposals = 0
        self._detection_counters: Dict[str, int] = {}

    def observe(self, cycle: int, di: float, md: float,
                was_blocked: bool, council_signals: List[Dict],
                stream_activations: List[Dict],
                identity_state: Dict) -> Optional[AxiomProposal]:
        """Observe a pipeline cycle and detect potential axiom gaps.

        Returns an AxiomProposal if a gap is detected, None otherwise.
        """
        observation = {
            "cycle": cycle,
            "di": di,
            "md": md,
            "was_blocked": was_blocked,
            "timestamp": time.time(),
        }
        self._observation_history.append(observation)
        if len(self._observation_history) > self._max_observations:
            self._observation_history.pop(0)

        # Check for axiom gap patterns
        proposal = None

        # Pattern 1: Frequent council blocks without resolution
        recent_blocks = sum(1 for o in self._observation_history[-20:] if o.get('was_blocked'))
        if recent_blocks >= 10 and was_blocked:
            key = "council_deadlock"
            self._detection_counters[key] = self._detection_counters.get(key, 0) + 1
            if self._detection_counters[key] == 1:  # Only propose once
                proposal = AxiomProposal(
                    id=self._generate_id("axiom_council_resolution"),
                    name="Council Deadlock Resolution",
                    description="When the Council consistently blocks with high confidence, "
                               "the system should have a formal resolution protocol — "
                               "escalation to a higher authority (human or meta-validator).",
                    layer=AxiomLayer.FEEDBACK_MEMORY,
                    rationale=f"Council blocked {recent_blocks}/20 recent cycles without resolution. "
                             "The current architecture has no deadlock-breaking mechanism.",
                    evidence=[f"Consecutive blocks: {recent_blocks}/20"],
                    implementation_suggestion="Add a CouncilResolution protocol in `telos/core/council/resolution.py` "
                                             "that triggers after N consecutive blocks.",
                    confidence=0.7,
                )

        # Pattern 2: Low DI without clear cause
        if di < 0.3 and len(self._observation_history) > 10:
            key = "unexplained_di_drop"
            self._detection_counters[key] = self._detection_counters.get(key, 0) + 1
            if self._detection_counters[key] == 1:
                proposal = AxiomProposal(
                    id=self._generate_id("axiom_epistemic_audit"),
                    name="Mandatory Epistemic Audit on Low DI",
                    description="When Decision Integrity drops below 0.3, the system "
                               "must perform a full epistemic audit before proceeding.",
                    layer=AxiomLayer.ADAPTIVE_CAPACITY,
                    rationale=f"DI dropped to {di:.2f} without clear subsystem attribution. "
                             "The current repair mechanism is reactive, not investigative.",
                    evidence=[f"DI={di:.2f} unexplained by current axioms"],
                    implementation_suggestion="Add EpistemicAuditPhase between Council and Act in pipeline.",
                    confidence=0.6,
                )

        return proposal

    def _generate_id(self, prefix: str) -> str:
        self._total_proposals += 1
        return f"{prefix}_{self._total_proposals}"

    def propose(self, name: str, description: str,
                layer: AxiomLayer, rationale: str,
                evidence: List[str],
                implementation_suggestion: str,
                confidence: float = 0.5) -> AxiomProposal:
        """Manually propose a new axiom."""
        pid = self._generate_id("axiom_manual")
        proposal = AxiomProposal(
            id=pid,
            name=name,
            description=description,
            layer=layer,
            rationale=rationale,
            evidence=evidence,
            implementation_suggestion=implementation_suggestion,
            confidence=confidence,
            created=time.time(),
        )
        self._proposals[pid] = proposal
        logger.warning(
            f"AxiomEvolution: new proposal '{name}' "
            f"(layer {layer.value}, confidence={confidence:.2f})"
        )
        return proposal

    def review(self, proposal_id: str, approved: bool,
               reviewer: str = "human", notes: Optional[str] = None) -> bool:
        """Review and approve/reject an axiom proposal."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            logger.warning(f"AxiomEvolution: unknown proposal '{proposal_id}'")
            return False

        proposal.status = "approved" if approved else "rejected"
        proposal.reviewed_by = reviewer
        proposal.review_notes = notes

        if approved:
            logger.warning(
                f"AxiomEvolution: PROPOSAL APPROVED — '{proposal.name}' "
                f"— human must implement in AXIOMS.md"
            )
        else:
            logger.info(
                f"AxiomEvolution: proposal rejected by {reviewer}: {notes}"
            )

        return True

    def get_pending_proposals(self) -> List[AxiomProposal]:
        return [p for p in self._proposals.values() if p.status == "proposed"]

    def get_approved_proposals(self) -> List[AxiomProposal]:
        return [p for p in self._proposals.values() if p.status == "approved"]

    def to_dict(self) -> Dict:
        return {
            "total_proposals": self._total_proposals,
            "pending": len(self.get_pending_proposals()),
            "approved": len(self.get_approved_proposals()),
            "proposals": [
                {
                    "id": p.id,
                    "name": p.name,
                    "status": p.status,
                    "layer": p.layer.value,
                    "confidence": p.confidence,
                }
                for p in self._proposals.values()
            ],
        }
