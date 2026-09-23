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

Loop-trap escape (Λ3.1 Recovery Mode): when the same intent type is
blocked as `action_loop` on RECOVERY_AFTER_LOOP_BLOCKS consecutive
cycles, the block carries a `recovery_requested` signal so the pipeline
can select a differently-typed goal-seek intent next cycle. The block is
NEVER waived — recovery only changes what gets selected; the recovery
intent still passes through every check.

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

# Λ3.1 Recovery Mode: after this many consecutive action_loop blocks, the
# block verdict requests a goal-seek recovery intent (different intent_type)
# so the same-intent detector cannot trap the agent forever. The block is
# still enforced; recovery only informs the next selection.
RECOVERY_AFTER_LOOP_BLOCKS = 2


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
        # Consecutive action_loop blocks per TRAPPED TYPE — the Λ3.1 recovery
        # counter. Per-type (not one global int): a NON-loop block of a
        # DIFFERENT type (e.g. `blended_inquiry` blocked by low_integrity at
        # Check 2 during a `curiosity_explore` action_loop trap) must NOT
        # reset the looped type's accumulation — under alternation that
        # reset was a counter-neutralization that kept every escape path at
        # max 1, forever (the [4,1] lockout). A type's own non-loop block,
        # or any genuine pass, still clears it.
        self._loop_blocks_by_type: Dict[str, int] = {}

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

        Args:
            world: the current world state snapshot being audited.
            intent: the proposed IntentIR (None when no intent was produced).
            council_validated: whether the council approved the intent.
            decision_integrity: measured DI in [0, 1] for the proposal.
            mission_violation: whether the proposal violates the mission.
            domain: knowledge domain for the DI threshold lookup.
            system_mood: current measured system mood (identity gate).
            available_moves: legal moves in the world (0 == stuck retry).

        Returns:
            FirewallVerdict: passed with governance signals, or a blocking
            verdict (blocked_by names the failing check).
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
                               "Council rejected — Firewall upholds block", signals,
                               intent_type=intent.intent_type if intent is not None else None)

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
                               f"DI {decision_integrity:.3f} below threshold {applied_threshold:.3f}", signals,
                               intent_type=intent.intent_type if intent is not None else None)

        # Check 3: Mission violation
        if self.config.block_on_mission_violation and mission_violation:
            signals.append({
                "check": "mission_violation",
                "passed": False,
                "reason": "Proposed action violates mission parameters",
            })
            return self._block("mission_violation",
                               "Action violates mission parameters", signals,
                               intent_type=intent.intent_type if intent is not None else None)

        # Check 4: Intent validity
        if intent is None:
            signals.append({
                "check": "intent_exists",
                "passed": False,
                "reason": "No intent selected",
            })
            return self._block("no_intent", "No intent to validate", signals, intent_type=None)

        # Check 5: Loop detection — same action repeated too many times
        if intent.intent_type:
            loop_type = intent.intent_type
            # Designed recovery/escape intents (Λ3.1 answer types) are exempt
            # from the loop DETECTOR by their own nature: they exist to break
            # exactly this check. Their history slot is NOT recorded (they are
            # the interrupt, not the loop member), so a recovery that repeatedly
            # fires stays a pass — blocking the escape with the same trap it is
            # meant to break would make recovery impossible (the eternal
            # plateau's rebound: goal_seek filled the window, then the detector
            # blocked goal_seek itself). The canonical recovery set
            # (recovery_types.py) is the single source — any future escape
            # type is auto-exempt. They still pass every OTHER firewall check
            # + the council, so a genuinely invalid recovery is still blocked.
            from telos.core.governance.recovery_types import STAGNATION_EXEMPT_RECOVERY_TYPES
            # Novelty-varying actions (domain adapter visit-count exploration):
            # the intent TYPE repeats but the emitted ACTION varies, so a
            # repeated type is NOT a same-action loop. Exempt only when the
            # runtime flagged it (adapter novelty active) — control unchanged.
            _novelty_action = bool((getattr(intent, 'params', None) or {}).get('novelty_action'))
            if loop_type in STAGNATION_EXEMPT_RECOVERY_TYPES or _novelty_action:
                signals.append({
                    "check": "loop_detection",
                    "passed": True,
                    "reason": (f"'{loop_type}' is a designed escape type — exempt from loop detection (Λ3.1)"
                               if loop_type in STAGNATION_EXEMPT_RECOVERY_TYPES
                               else f"'{loop_type}' carries a novelty-varying action — repeated type is not a loop"),
                    "action": loop_type,
                })
            else:
                self._action_history.append(loop_type)
                if len(self._action_history) > self._max_action_history:
                    self._action_history.pop(0)
                recent = self._action_history[-self._loop_threshold:]
                if len(recent) >= self._loop_threshold and len(set(recent)) == 1:
                    # If all moves are blocked (surrounded), allow a "try anyway" retry
                    if available_moves is not None and available_moves == 0:
                        self._loop_blocks_by_type[recent[0]] = 0  # stuck retry is a pass
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
                        # Λ3.1 Recovery Mode: 2+ consecutive action_loop blocks
                        # request a goal-seek recovery intent (different type)
                        # so the same-intent detector cannot trap the agent.
                        # Per-family counter: this type's OWN accumulation
                        # (a different type's non-loop block must not reset it).
                        self._loop_blocks_by_type[recent[0]] = (
                            self._loop_blocks_by_type.get(recent[0], 0) + 1
                        )
                        recovery_requested = (
                            self._loop_blocks_by_type[recent[0]] >= RECOVERY_AFTER_LOOP_BLOCKS
                        )
                        signal = {
                            "check": "loop_detection",
                            "passed": False,
                            "reason": f"Same action '{recent[0]}' repeated {self._loop_threshold}+ consecutive cycles",
                            "action": recent[0],
                            "consecutive_loop_blocks": self._loop_blocks_by_type[recent[0]],
                        }
                        if recovery_requested:
                            signal["recovery_requested"] = True
                            signal["recovery"] = "goal_seek_escape"
                            signal["axiom"] = "3.1"
                            logger.info(
                                f"DecisionFirewall: loop recovery requested — "
                                f"{self._loop_blocks_by_type[recent[0]]} consecutive action_loop "
                                f"blocks on '{recent[0]}' (Λ3.1)"
                            )
                        signals.append(signal)
                        return self._block("action_loop",
                                           f"Action '{recent[0]}' repeated {self._loop_threshold}+ cycles", signals,
                                           intent_type=recent[0])

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
                                   f"Mood '{system_mood}' blocks action below DI {elevated_threshold:.3f}", signals,
                                   intent_type=intent.intent_type if intent is not None else None)

        self._pass_count += 1
        # Any genuine pass clears the whole loop-recovery ledger: the agent
        # acted, so whatever trap existed is broken for every type.
        self._loop_blocks_by_type = {}
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

    def _block(self, blocked_by: str, reason: str, signals: list,
               intent_type: Optional[str] = None) -> FirewallVerdict:
        self._block_count += 1
        if blocked_by != "action_loop":
            # RESET ONLY THE BLOCKED TYPE's own loop-recovery streak. A
            # non-loop block of a DIFFERENT type (e.g. `blended_inquiry`
            # blocked by low_integrity at Check 2 while `curiosity_explore`
            # is mid-trap) must NOT wipe the looped type's accumulation —
            # that global reset was the [4,1] counter-neutralization that
            # kept every escape path at max 1 forever.
            # LOOP-DETECTOR-AWARE SAME-TYPE exception: a same-type non-loop
            # block (e.g. `curiosity_explore` low_integrity at Check 2 —
            # Check 2 fires BEFORE Check 5's loop detector) while THIS type
            # is mid-accumulation on the loop ledger (streak > 0) must NOT
            # cancel the in-flight escape either — that zeroing was the
            # same-type counter-neutralization that pinned the streak at 1
            # forever (RECOVERY_AFTER_LOOP_BLOCKS could never be reached).
            # A same-type block with NOTHING in flight (streak == 0), or any
            # genuine pass (which clears the whole ledger), is still an
            # honest break.
            if intent_type and self._loop_blocks_by_type.get(intent_type, 0) == 0:
                self._loop_blocks_by_type[intent_type] = 0
        logger.warning(f"DecisionFirewall: BLOCKED by {blocked_by} — {reason}")
        return FirewallVerdict(
            passed=False,
            reason=reason,
            blocked_by=blocked_by,
            governance_signals=signals,
        )

    @property
    def consecutive_loop_blocks(self) -> int:
        """Most-armed intent type's consecutive action_loop blocks (Λ3.1).

        Per-family: returns the maximum accumulation across trapped types, so
        under alternation a partner type's low_integrity block can no longer
        zero a sibling's streak (each type keeps its OWN ledger)."""
        return max(self._loop_blocks_by_type.values(), default=0)

    @property
    def stats(self) -> Dict:
        total = self._block_count + self._pass_count
        return {
            "blocks": self._block_count,
            "passes": self._pass_count,
            "block_rate": self._block_count / max(total, 1),
            "consecutive_loop_blocks": self.consecutive_loop_blocks,
            "constitutional": {
                "loop_detection": True,
                "identity_gate": True,
                "action_history": self._action_history[-5:],
            },
        }
