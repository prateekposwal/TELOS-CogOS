"""
MetaCognitionModule — Self-Doubt and Recovery Triggers (P0 D8)

Implements meta-cognitive awareness:
  - Tracks uncertainty across streams
  - Triggers recovery mode when council blocks > 3 consecutive
  - Triggers epistemic repair when DI drops below 0.5
  - Logs all meta-cognitive states to the decision trace

NOTE: The old U > 0.7 → EXPLORE hardcoded threshold has been REMOVED.
Exploration mode is now driven by the InquiryStream (priority 0.8) and
the Ω Operator in the SelectPhase. When a high-value question is found
(Ω > 0.5), the pipeline enters Inquiry Mode instead of using a static
uncertainty threshold.

This is the system's "thinking about thinking" — a lightweight
meta-cognitive layer that detects when the system is failing
and triggers corrective modes.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_metacognition')


class MetaState(Enum):
    NOMINAL = "nominal"
    EXPLORING = "exploring"
    RECOVERING = "recovering"
    EPISTEMIC_REPAIR = "epistemic_repair"


@dataclass
class MetaCognitionReport:
    """A snapshot of the system's meta-cognitive state."""
    current_state: MetaState = MetaState.NOMINAL
    stream_uncertainties: Dict[str, float] = field(default_factory=dict)
    consecutive_council_blocks: int = 0
    current_di: float = 1.0
    trigger_reason: Optional[str] = None
    state_history: List[Dict] = field(default_factory=list)
    exploration_mode_active: bool = False
    recovery_mode_active: bool = False
    epistemic_repair_active: bool = False
    mode: str = "PLAN"


class MetaPolicy:
    """Π_M: S → {React, Plan, Explore, Delegate, Wait}
    
    Explicit meta-policy selector that determines the system's reasoning
    mode based on current state and tripartite uncertainty U = (U_W, U_I, U_O).
    
    Rules:
      - High U_W (environmental uncertainty) → EXPLORE (driven by InquiryStream)
      - High U_I (identity uncertainty) → DELEGATE (recalibrate)
      - High U_O (other-agent uncertainty) → PLAN (strategic modeling)
      - Low overall uncertainty + time pressure → REACT
      - Resource depletion → WAIT
    
    NOTE: The exploratory mode is no longer triggered by hardcoded thresholds
    here. The InquiryStream + Ω Operator handle question generation. MetaPolicy
    now reflects the InquiryStream's output rather than driving it.
    """
    MODES = ['REACT', 'PLAN', 'EXPLORE', 'DELEGATE', 'WAIT']
    
    HIGH_THRESHOLD = 0.6
    LOW_THRESHOLD = 0.3
    
    def __init__(self):
        self._last_mode: str = 'PLAN'
        self._mode_history: List[str] = []
        self._max_history: int = 50
    
    def select_mode(self, tripartite_U: Optional[Dict[str, float]] = None,
                    resource_depletion: float = 0.0,
                    time_pressure: float = 0.0,
                    inquiry_active: bool = False,
                    inquiry_omega_value: float = 0.0) -> str:
        """Determine reasoning mode from state + uncertainty.
        
        Key change: inquiry_active flag from InquiryStream overrides
        the old static U > 0.7 → EXPLORE rule.
        
        Args:
            tripartite_U: Dict with 'U_W', 'U_I', 'U_O' keys
            resource_depletion: 0-1, how depleted are resources
            time_pressure: 0-1, how much time pressure exists
            inquiry_active: Whether InquiryStream found a question worth asking
            inquiry_omega_value: The Ω value from the OmegaOperator
            
        Returns:
            One of: REACT, PLAN, EXPLORE, DELEGATE, WAIT
        """
        if resource_depletion > 0.8:
            return 'WAIT'
        
        # InquiryStream-driven exploration: if a high-value question exists
        if inquiry_active and inquiry_omega_value > 0.5:
            self._last_mode = 'EXPLORE'
            self._mode_history.append('EXPLORE')
            if len(self._mode_history) > self._max_history:
                self._mode_history.pop(0)
            return 'EXPLORE'
        
        if tripartite_U is None:
            return self._last_mode
        
        u_w = tripartite_U.get('U_W', 0.0)
        u_i = tripartite_U.get('U_I', 0.0)
        u_o = tripartite_U.get('U_O', 0.0)
        
        dominant = max([('environmental', u_w), ('identity', u_i), ('other', u_o)],
                       key=lambda x: x[1])
        
        if dominant[1] >= self.HIGH_THRESHOLD:
            if dominant[0] == 'environmental':
                mode = 'EXPLORE'
            elif dominant[0] == 'identity':
                mode = 'DELEGATE'
            else:  # 'other'
                mode = 'PLAN'
        elif u_w < self.LOW_THRESHOLD and u_i < self.LOW_THRESHOLD and u_o < self.LOW_THRESHOLD:
            if time_pressure > 0.6:
                mode = 'REACT'
            else:
                mode = 'PLAN'
        else:
            mode = 'PLAN'
        
        self._last_mode = mode
        self._mode_history.append(mode)
        if len(self._mode_history) > self._max_history:
            self._mode_history.pop(0)
        
        return mode
    
    @property
    def mode_history(self) -> List[str]:
        return list(self._mode_history)
    
    @property
    def current_mode(self) -> str:
        return self._last_mode
    
    def to_dict(self) -> Dict:
        return {
            "current_mode": self._last_mode,
            "mode_history": self._mode_history[-10:],
        }




class MetaCognitionModule:
    """Observes pipeline execution and triggers corrective meta-states.

    Integration points:
      - Reads stream calibrator uncertainties (stream.calibrator.uncertainty)
      - Monitors council block count
      - Tracks DI trajectory
      - Emits state change signals
    
    NOTE: The old exploration mode (U > 0.7 across all streams) has been
    removed. The InquiryStream now handles question generation and the
    MetaPolicy is driven by InquiryStream output, not hardcoded thresholds.
    """

    def __init__(self):
        self._state = MetaState.NOMINAL
        self._consecutive_blocks = 0
        self._total_blocks = 0
        self._di_history: List[float] = []
        self._uncertainty_history: List[Dict[str, float]] = []
        self._state_history: List[Dict] = []
        self._max_history = 100
        self._cycles_in_current_state = 0
        self._exploration_cycles = 0
        self._recovery_cycles = 0
        self._repair_cycles = 0
        self._meta_policy = MetaPolicy()

    @property
    def state(self) -> MetaState:
        return self._state

    @property
    def state_history(self) -> List[Dict]:
        return list(self._state_history)

    @property
    def consecutive_blocks(self) -> int:
        return self._consecutive_blocks

    def observe(self, stream_uncertainties: Dict[str, float],
                council_signals: List[Dict],
                decision_integrity: float,
                cycle_count: int,
                tripartite_u: Optional[Dict[str, float]] = None,
                inquiry_active: bool = False,
                inquiry_omega_value: float = 0.0,
                resource_depletion: float = 0.0,
                time_pressure: float = 0.0) -> MetaCognitionReport:
        """Process a single decision cycle's meta-cognitive data.

        Args:
            stream_uncertainties: Dict of stream_name -> uncertainty level
            council_signals: List of council validation signal dicts
            decision_integrity: Current DI value
            cycle_count: Current pipeline cycle number
            tripartite_u: Optional tripartite uncertainty dict (U_W, U_I, U_O)
            inquiry_active: Whether InquiryStream found a question worth asking
            inquiry_omega_value: The Ω value from the OmegaOperator

        Returns:
            MetaCognitionReport with current state, triggers, and flags
        """
        self._di_history.append(decision_integrity)
        if len(self._di_history) > self._max_history:
            self._di_history.pop(0)

        # Track uncertainties
        self._uncertainty_history.append(stream_uncertainties)
        if len(self._uncertainty_history) > self._max_history:
            self._uncertainty_history.pop(0)


        # P2: Select meta-policy mode from tripartite uncertainty + inquiry
        if tripartite_u is not None:
            self._meta_policy.select_mode(
                tripartite_U=tripartite_u,
                resource_depletion=resource_depletion,
                time_pressure=time_pressure,
                inquiry_active=inquiry_active,
                inquiry_omega_value=inquiry_omega_value,
            )
        # Count council blocks
        was_blocked = any(s.get("passed") == False for s in council_signals)
        if was_blocked:
            self._consecutive_blocks += 1
            self._total_blocks += 1
        else:
            self._consecutive_blocks = 0

        # Determine which meta-state to activate
        old_state = self._state
        new_state = self._determine_state(stream_uncertainties, decision_integrity,
                                          inquiry_active=inquiry_active)
        trigger_reason = None

        if new_state != old_state:
            trigger_reason = self._get_trigger_reason(
                new_state, stream_uncertainties, decision_integrity
            )
            logger.info(
                f"MetaCognition: {old_state.value} → {new_state.value} "
                f"(DI={decision_integrity:.3f}, blocks={self._consecutive_blocks}, "
                f"reason={trigger_reason})"
            )
            self._state = new_state
            self._cycles_in_current_state = 0

        self._cycles_in_current_state += 1

        # Track time spent in each state
        if self._state == MetaState.EXPLORING:
            self._exploration_cycles += 1
        elif self._state == MetaState.RECOVERING:
            self._recovery_cycles += 1
        elif self._state == MetaState.EPISTEMIC_REPAIR:
            self._repair_cycles += 1

        # Build report
        report = MetaCognitionReport(
            current_state=self._state,
            stream_uncertainties=stream_uncertainties,
            consecutive_council_blocks=self._consecutive_blocks,
            current_di=decision_integrity,
            trigger_reason=trigger_reason,
            exploration_mode_active=(self._state == MetaState.EXPLORING),
            recovery_mode_active=(self._state == MetaState.RECOVERING),
            mode=self._meta_policy.current_mode,
            epistemic_repair_active=(self._state == MetaState.EPISTEMIC_REPAIR),
        )

        # Record state snapshot
        snapshot = {
            "cycle": cycle_count,
            "state": self._state.value,
            "di": decision_integrity,
            "consecutive_blocks": self._consecutive_blocks,
            "total_blocks": self._total_blocks,
            "trigger": trigger_reason,
            "mean_uncertainty": (
                sum(stream_uncertainties.values()) / max(len(stream_uncertainties), 1)
            ),
            "inquiry_active": inquiry_active,
            "inquiry_omega": inquiry_omega_value,
        }
        self._state_history.append(snapshot)
        if len(self._state_history) > self._max_history:
            self._state_history.pop(0)

        return report

    def _determine_state(self, uncertainties: Dict[str, float],
                         di: float,
                         inquiry_active: bool = False) -> MetaState:
        """Apply state transition rules in priority order.
        
        NOTE: The old Rule 1 (U > 0.7 across all streams → EXPLORE) has been
        REMOVED. Exploration is now driven by the InquiryStream + Ω Operator.
        If inquiry_active is True and we're not already in a more severe state,
        we enter EXPLORING.
        """

        # Rule 3: DI drops below 0.5 → epistemic repair (highest priority)
        if di < 0.5 and self._state != MetaState.EPISTEMIC_REPAIR:
            return MetaState.EPISTEMIC_REPAIR

        # Rule 2: Council blocks > 3 consecutive → recovery mode
        if self._consecutive_blocks > 3 and self._state != MetaState.RECOVERING:
            return MetaState.RECOVERING

        # Rule 1 (REPLACED): InquiryStream-driven exploration
        # Instead of checking all uncertainties > 0.7, check if the InquiryStream
        # has detected a high-value question worth exploring
        if inquiry_active and self._state != MetaState.EXPLORING:
            return MetaState.EXPLORING

        # If currently in a meta-state, stay until conditions clear
        if self._state == MetaState.EXPLORING:
            # Stay exploring until inquiry completes (omega drops below threshold)
            if inquiry_active and self._cycles_in_current_state < 5:
                return MetaState.EXPLORING

        if self._state == MetaState.RECOVERING:
            # Stay in recovery for at least 2 cycles
            if self._cycles_in_current_state < 2:
                return MetaState.RECOVERING
            # Clear if no longer blocked
            if self._consecutive_blocks == 0:
                return MetaState.NOMINAL

        if self._state == MetaState.EPISTEMIC_REPAIR:
            # Stay in repair until DI recovers above 0.6 for at least 2 cycles
            if len(self._di_history) >= 2:
                if all(d > 0.6 for d in self._di_history[-2:]):
                    return MetaState.NOMINAL
            return MetaState.EPISTEMIC_REPAIR

        return MetaState.NOMINAL

    def _get_trigger_reason(self, new_state: MetaState,
                            uncertainties: Dict[str, float],
                            di: float) -> str:
        """Generate a human-readable trigger reason."""
        if new_state == MetaState.EXPLORING:
            return "InquiryStream: question worth asking (Ω > 0.5)"
        elif new_state == MetaState.RECOVERING:
            return f"Council blocked {self._consecutive_blocks}x consecutively"
        elif new_state == MetaState.EPISTEMIC_REPAIR:
            return f"DI dropped to {di:.3f} (threshold=0.5)"
        return "nominal operation"

    def get_stats(self) -> Dict:
        return {
            "current_state": self._state.value,
            "cycles_in_state": self._cycles_in_current_state,
            "consecutive_blocks": self._consecutive_blocks,
            "total_blocks": self._total_blocks,
            "exploration_cycles": self._exploration_cycles,
            "recovery_cycles": self._recovery_cycles,
            "repair_cycles": self._repair_cycles,
            "total_observations": len(self._state_history),
            "recent_states": [
                {"cycle": s["cycle"], "state": s["state"]}
                for s in self._state_history[-10:]
            ],
        }

    def to_dict(self) -> Dict:
        return self.get_stats()
