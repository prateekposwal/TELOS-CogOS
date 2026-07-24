"""
InquiryStream — 5th Cognitive Stream

Priority: 0.8 (between Perception 0.9 and Memory 0.7)
Generates questions Q* = argmax[ΔJ(Q) - Cost(Q)] from tripartite uncertainty
instead of directly producing action intents.

This stream absorbs:
- The old U > 0.7 → EXPLORE rule from meta_cognition.py
- The old uncertainty > 0.8 → Reflex rule from implementations.py

Instead of hardcoded thresholds, InquiryStream uses the Ω Operator to
determine if a question is worth asking, and if so, which question.
"""

import logging
from typing import Optional, Dict, List, Any

import numpy as np

from telos.core.streams.base import CognitiveStream
from telos.core.ledger.skill_library import SkillLibrary
from telos.intent_ir import IntentIR
from telos.world.world import World

logger = logging.getLogger('telos_streams')


class InquiryStream(CognitiveStream):
    """5th cognitive stream — generates questions instead of actions.
    
    Priority: 0.8 (between Perception 0.9 and Memory 0.7)
    Generates questions Q* = argmax[ΔJ(Q) - Cost(Q)] from tripartite uncertainty.
    
    The InquiryStream does NOT directly produce action intents. Instead, it
    wraps a question inside an IntentIR with question_type. The OmegaOperator
    in the SelectPhase determines whether to enter Inquiry Mode or proceed
    with normal action selection.
    """

    def __init__(self, skill_library: SkillLibrary,
                 omega_operator: Optional[Any] = None):
        super().__init__(skill_library)
        self._omega_operator = omega_operator
        # Track whether we're currently in inquiry mode
        self._inquiry_active: bool = False
        self._last_question: Optional[Dict] = None
        self._last_omega: float = 0.0

    @property
    def priority(self) -> float:
        return 0.8

    @property
    def estimated_cost_ms(self) -> float:
        return 4.0

    def process(self, world: World) -> IntentIR:
        """Process the World and generate a question if uncertainty warrants it.
        
        The InquiryStream reads tripartite uncertainty from world metadata
        and generates a question intent. The actual Ω computation happens
        in the SelectPhase (where council signals are available), but this
        stream provides the initial question generation.
        
        Returns an IntentIR with:
          - intent_type = "inquiry"
          - params containing the question dict and uncertainty context
        """
        # Read tripartite uncertainty from world metadata if available
        u_w = world.metadata.get('U_W', 0.0)
        u_i = world.metadata.get('U_I', 0.0)
        u_o = world.metadata.get('U_O', 0.0)
        
        # Read council signals if available
        council_signals = world.metadata.get('council_signals', [])
        
        # Composite uncertainty assessment
        composite_u = (u_w + u_i + u_o) / 3.0 if (u_w + u_i + u_o) > 0 else 0.0
        
        # Build a rich question context from world state
        question_context = {
            'U_W': u_w,
            'U_I': u_i,
            'U_O': u_o,
            'composite_uncertainty': composite_u,
            'council_signal_count': len(council_signals),
            'council_blockers': sum(
                1 for s in council_signals if not s.get('passed', True)
            ),
            'state_norm': float(np.linalg.norm(world.state)) if hasattr(world, 'state') else 0.0,
        }
        
        # Determine inquiry mode based on uncertainty composition
        # (The actual Ω gate happens in SelectPhase; this is just the stream output)
        candidate_questions = self._generate_candidates(u_w, u_i, u_o, council_signals)
        
        return IntentIR(
            intent_type="inquiry",
            confidence=min(1.0, composite_u * 1.2),  # Scale confidence with uncertainty
            params={
                "question_context": question_context,
                "candidate_questions": candidate_questions,
                "U_W": u_w,
                "U_I": u_i,
                "U_O": u_o,
                "composite_uncertainty": composite_u,
                "candidate_count": len(candidate_questions),
            },
            metadata={
                "stream": "inquiry",
                "inquiry_active": composite_u > 0.3,
                "candidate_count": len(candidate_questions),
            },
        )

    def _generate_candidates(self, u_w: float, u_i: float, u_o: float,
                              council_signals: List[Dict]) -> List[Dict]:
        """Generate candidate questions based on uncertainty profile.
        
        Replaces the old hardcoded thresholds with structured question generation.
        Each candidate has an id, type, domain, and prior that feeds into
        the Ω operator scoring.
        """
        candidates = []
        
        if u_w > 0.3:
            candidates.append({
                'id': 'explore_terrain',
                'type': 'explore',
                'domain': 'world',
                'prior': u_w,
                'estimated_horizon': 5,
                'estimated_worlds': 10,
                'question': 'Should I explore the terrain to reduce environmental uncertainty?',
            })
        
        if u_i > 0.3:
            candidates.append({
                'id': 'recalibrate_identity',
                'type': 'recalibrate',
                'domain': 'identity',
                'prior': u_i,
                'estimated_horizon': 3,
                'estimated_worlds': 5,
                'question': 'Should I recalibrate my goals to reduce identity uncertainty?',
            })
        
        if u_o > 0.3:
            candidates.append({
                'id': 'resolve_disagreement',
                'type': 'investigate',
                'domain': 'council',
                'prior': u_o,
                'estimated_horizon': 4,
                'estimated_worlds': 8,
                'question': 'Should I investigate council disagreement to reduce conflict?',
            })
        
        # Always include a default "proceed" option
        candidates.append({
            'id': 'default_navigate',
            'type': 'proceed',
            'domain': 'action',
            'prior': 0.3,
            'estimated_horizon': 2,
            'estimated_worlds': 3,
            'question': 'Should I proceed with normal action selection?',
        })
        
        return candidates

    @property
    def inquiry_active(self) -> bool:
        return self._inquiry_active

    @inquiry_active.setter
    def inquiry_active(self, value: bool) -> None:
        self._inquiry_active = value

    @property
    def last_question(self) -> Optional[Dict]:
        return self._last_question

    @last_question.setter
    def last_question(self, value: Optional[Dict]) -> None:
        self._last_question = value

    @property
    def last_omega(self) -> float:
        return self._last_omega

    @last_omega.setter
    def last_omega(self, value: float) -> None:
        self._last_omega = value
