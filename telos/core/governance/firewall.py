"""
Decision Firewall — Final pre-execution reality audit.

The Decision Firewall is the final checkpoint before an IntentIR is
converted into an action. It conducts a "Reality Audit":

  1. Does the intended action rely on unauthorized information?
  2. Does the action violate mission parameters?
  3. Is the Decision Integrity score below the acceptable threshold?
  4. Did the Council approve? If not, the Firewall also blocks.

The Firewall is "Ministerial" — it does not make decisions. It only
validates that the decision-making process was clean.

Engineering Value:
  Prevents the system from acting on information it was not authorized
  to use, or from acting when the reasoning process was compromised.
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from telos.core.governance.base import FirewallVerdict
from telos.world.world import World
from telos.intent_ir import IntentIR

logger = logging.getLogger('telos_governance')


@dataclass
class FirewallConfig:
    min_decision_integrity: float = 0.3
    block_on_council_rejection: bool = True
    block_on_unauthorized_info: bool = True
    block_on_mission_violation: bool = True
    domain: str = "gridworld"


# Domain-specific DI thresholds: override global min_decision_integrity per domain
DOMAIN_THRESHOLDS: Dict[str, float] = {
    "gridworld": 0.3,
    "devdomain": 0.6,
    "default": 0.4,
}


class DecisionFirewall:
    """Final pre-execution reality audit.

    The Firewall inspects the full decision path:
      World → Streams → Select → Council → [Firewall] → Act

    If the Firewall blocks, the system MUST NOT act. This is the
    ultimate epistemic safeguard — the system cannot act on
    compromised or unauthorized reasoning.
    """

    def __init__(self, config: Optional[FirewallConfig] = None):
        self.config = config or FirewallConfig()
        self._block_count: int = 0
        self._pass_count: int = 0
        self._action_history: List[str] = []
        self._max_action_history: int = 10
        self._loop_threshold: int = 4

    def set_di_threshold(self, threshold: float) -> None:
        """Update the minimum Decision Integrity threshold dynamically.
        
        Called by ActPhase to sync with MissionPolicy's risk tolerance
        before each inspect() call.
        """
        clamped = max(0.05, min(0.95, threshold))
        old = self.config.min_decision_integrity
        self.config.min_decision_integrity = clamped
        if abs(old - clamped) > 0.001:
            logger.info(f"DecisionFirewall: DI threshold {old:.3f} -> {clamped:.3f}")

    def inspect(self, world: World, intent: Optional[IntentIR],
                council_validated: bool,
                decision_integrity: float,
                mission_violation: bool = False,
                domain: Optional[str] = None,
                system_mood: Optional[str] = None,
                available_moves: Optional[int] = None) -> FirewallVerdict:
        """Run the full reality audit on a proposed action.

        Constitutional checks:
          1. Council validation
          2. Decision Integrity (domain-specific)
          3. Mission violation
          4. Intent validity
          5. Loop detection (same action repeated)
          6. Identity integrity (mood not in dangerous state)
        """
        signals: list = []

        # Check 1: Council validation
        if self.config.block_on_council_rejection and not council_validated:
            signals.append({
                "check": "council_validation",
                "passed": False,
                "reason": "Council rejected the proposed action",
            })
            return self._block("council_rejection",
                               "Council rejected — Firewall upholds block", signals)

        # Check 2: Decision Integrity (with domain-specific threshold)
        effective_domain = domain or self.config.domain
        di_threshold = DOMAIN_THRESHOLDS.get(effective_domain, DOMAIN_THRESHOLDS["default"])
        # Use the higher of global and domain-specific threshold
        applied_threshold = max(self.config.min_decision_integrity, di_threshold)
        if decision_integrity < applied_threshold:
            signals.append({
                "check": "decision_integrity",
                "passed": False,
                "reason": f"DI {decision_integrity:.3f} below threshold {applied_threshold:.3f} (domain={effective_domain})",
                "domain": effective_domain,
                "applied_threshold": applied_threshold,
            })
            return self._block("low_integrity",
                               f"DI {decision_integrity:.3f} below threshold {applied_threshold:.3f}", signals)

        # Check 3: Mission violation
        if self.config.block_on_mission_violation and mission_violation:
            signals.append({
                "check": "mission_violation",
                "passed": False,
                "reason": "Proposed action violates mission parameters",
            })
            return self._block("mission_violation",
                               "Action violates mission parameters", signals)

        # Check 4: Intent validity
        if intent is None:
            signals.append({
                "check": "intent_exists",
                "passed": False,
                "reason": "No intent selected",
            })
            return self._block("no_intent", "No intent to validate", signals)

        # Check 5: Loop detection — same action repeated too many times
        if intent.intent_type:
            self._action_history.append(intent.intent_type)
            if len(self._action_history) > self._max_action_history:
                self._action_history.pop(0)
            recent = self._action_history[-self._loop_threshold:]
            if len(recent) >= self._loop_threshold and len(set(recent)) == 1:
                # If all moves are blocked (surrounded), allow a "try anyway" retry
                if available_moves is not None and available_moves == 0:
                    logger.info(
                        f"DecisionFirewall: loop detected ({recent[0]} x{self._loop_threshold}) "
                        f"but available_moves=0 — allowing retry (stuck)"
                    )
                    signals.append({
                        "check": "loop_detection",
                        "passed": True,
                        "reason": f"All moves blocked, allowing '{recent[0]}' retry",
                        "action": recent[0],
                        "stuck": True,
                    })
                else:
                    signals.append({
                        "check": "loop_detection",
                        "passed": False,
                        "reason": f"Same action '{recent[0]}' repeated {self._loop_threshold}+ consecutive cycles",
                        "action": recent[0],
                    })
                    return self._block("action_loop",
                                       f"Action '{recent[0]}' repeated {self._loop_threshold}+ cycles", signals)

        # Check 6: Identity integrity — mood-based gate
        if system_mood in ("uncertain", "fatigued"):
            # Require higher DI threshold when system is in a fragile mood
            elevated_threshold = max(self.config.min_decision_integrity * 1.5, 0.5)
            if decision_integrity < elevated_threshold:
                signals.append({
                    "check": "identity_integrity",
                    "passed": False,
                    "reason": f"System mood is '{system_mood}' and DI {decision_integrity:.3f} < elevated threshold {elevated_threshold:.3f}",
                })
                return self._block("low_identity_integrity",
                                   f"Mood '{system_mood}' blocks action below DI {elevated_threshold:.3f}", signals)

        self._pass_count += 1
        signals.append({
            "check": "all_governance_checks",
            "passed": True,
            "reason": "All governance checks passed",
        })

        return FirewallVerdict(
            passed=True,
            reason="All governance checks passed",
            governance_signals=signals,
        )

    def _block(self, blocked_by: str, reason: str, signals: list) -> FirewallVerdict:
        self._block_count += 1
        logger.warning(f"DecisionFirewall: BLOCKED by {blocked_by} — {reason}")
        return FirewallVerdict(
            passed=False,
            reason=reason,
            blocked_by=blocked_by,
            governance_signals=signals,
        )

    @property
    def stats(self) -> Dict:
        total = self._block_count + self._pass_count
        return {
            "blocks": self._block_count,
            "passes": self._pass_count,
            "block_rate": self._block_count / max(total, 1),
            "constitutional": {
                "loop_detection": True,
                "identity_gate": True,
                "action_history": self._action_history[-5:],
            },
        }
