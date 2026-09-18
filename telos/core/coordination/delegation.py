"""
Delegation & Verification Protocol — real multi-agent coordination (bounded).

LangGraph/crew-class frameworks give agents three capabilities the advisory
DistributedCouncil did not have:

  1. DELEGATION with accountability — one agent hands a task to another, and
     the handoff (who asked, who answered, what came back, was it accepted) is
     recorded. A self-delegation or an unknown recipient is refused with a
     recorded reason.
  2. INDEPENDENT VERIFICATION — a second agent can REJECT a first agent's
     proposal with a recorded reason. The verifier's decision is derived from
     the proposal's CONTENT (evidence, declared violations, confidence) and its
     own policy, never from the author's opinion of its own work. A verifier may
     not audit its own proposal.
  3. CONFLICT RESOLUTION — when agents disagree, a deterministic, auditable
     rule (hard veto / weighted vote / authority tiebreak) decides and the
     resolution is recorded.

Everything is BOUNDED (max rounds + max handoffs) and DETERMINISTIC (monotonic
counters, no RNG, no wall clock, no global state). The DistributedCouncil stays
advisory (Λ1.2); this protocol produces a recorded coordination outcome that is
attached to the distributed verdict and flows into the DecisionTrace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_MAX_ROUNDS = 4
DEFAULT_MAX_HANDOFFS = 8

# Default authority per role (mirrors the distributed council's consensus
# authority so conflict resolution and the advisory aggregate agree).
DEFAULT_AUTHORITY: Dict[str, float] = {
    "primary": 1.0,
    "skeptic": 0.8,
    "conservative": 0.7,
    "explorer": 0.6,
    "domain_expert": 0.6,
    "analyst": 0.5,
}

# Roles whose rejection is a hard veto in conflict resolution: independent
# adversarial verification can refuse even against a weighted majority.
HARD_VETO_ROLES = ("skeptic",)

# Per-role minimum confidence a proposal must carry to pass verification. The
# skeptic (adversarial verifier) demands the strongest evidence.
VERIFY_MIN_CONFIDENCE: Dict[str, float] = {
    "skeptic": 0.5,
    "conservative": 0.6,
    "primary": 0.5,
    "domain_expert": 0.5,
    "explorer": 0.3,
    "analyst": 0.4,
}


@dataclass
class HandoffRecord:
    """One recorded delegation between two agents.

    Attributes:
        handoff_id: deterministic id for this handoff.
        task: the delegated task description.
        from_agent: the delegating agent.
        to_agent: the agent the task was handed to.
        round: the coordination round the handoff was made in.
        accepted: whether the handoff was accepted.
        reason: why it was accepted or refused.
        response: optional payload returned by the recipient.
    """

    handoff_id: str
    task: str
    from_agent: str
    to_agent: str
    round: int
    accepted: bool
    reason: str
    response: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this handoff to a plain dict.

        Returns:
            A JSON-serializable dict of the handoff record.
        """
        return {
            "handoff_id": self.handoff_id,
            "task": self.task,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "round": self.round,
            "accepted": self.accepted,
            "reason": self.reason,
            "response": self.response,
        }


@dataclass
class VerificationRecord:
    """One recorded verification of a proposal by an independent agent.

    Attributes:
        proposal_id: the verified proposal's id.
        author: the agent that authored the proposal.
        verifier: the independent agent that audited it.
        accepted: whether the proposal passed verification.
        reason: why it was accepted or rejected (never empty).
        round: the coordination round verification ran in.
        checks: per-check detail (name, passed, detail).
    """

    proposal_id: str
    author: str
    verifier: str
    accepted: bool
    reason: str
    round: int
    checks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this verification to a plain dict.

        Returns:
            A JSON-serializable dict of the verification record.
        """
        return {
            "proposal_id": self.proposal_id,
            "author": self.author,
            "verifier": self.verifier,
            "accepted": self.accepted,
            "reason": self.reason,
            "round": self.round,
            "checks": self.checks,
        }


@dataclass
class ResolutionRecord:
    """One recorded conflict resolution over a crew of agent positions.

    Attributes:
        method: how the outcome was decided (unanimous / hard_veto /
            weighted_majority / authority_tiebreak / no_agents).
        validated: the resolved boolean outcome.
        outcome: "validated", "rejected", or "no_agents".
        conflict: whether the agents genuinely disagreed.
        escalated: whether a hard veto escalated against a majority.
        weight_for: total authority weight voting to validate.
        weight_against: total authority weight voting to reject.
        dissenters: agent ids that voted against the resolved outcome.
        reason: human-readable basis for the outcome.
        round: the coordination round resolution ran in.
    """

    method: str
    validated: bool
    outcome: str
    conflict: bool
    escalated: bool
    weight_for: float
    weight_against: float
    dissenters: List[str]
    reason: str
    round: int

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this resolution to a plain dict.

        Returns:
            A JSON-serializable dict of the resolution record.
        """
        return {
            "method": self.method,
            "validated": self.validated,
            "outcome": self.outcome,
            "conflict": self.conflict,
            "escalated": self.escalated,
            "weight_for": round(self.weight_for, 4),
            "weight_against": round(self.weight_against, 4),
            "dissenters": self.dissenters,
            "reason": self.reason,
            "round": self.round,
        }


class CoordinationProtocol:
    """Bounded, deterministic delegation + verification + conflict resolution.

    The protocol owns a registry of named agents, a bounded round counter, and a
    bounded handoff budget. Every interaction appends an immutable record; the
    audit() snapshot reports whether the collaboration stayed bounded.
    """

    def __init__(self, max_rounds: int = DEFAULT_MAX_ROUNDS,
                 max_handoffs: int = DEFAULT_MAX_HANDOFFS):
        """Initialize the protocol.

        Args:
            max_rounds: hard ceiling on coordination rounds.
            max_handoffs: hard ceiling on delegated handoffs.
        """
        self._agents: Dict[str, str] = {}
        self._authority: Dict[str, float] = {}
        self._max_rounds = max(1, int(max_rounds))
        self._max_handoffs = max(1, int(max_handoffs))
        self._round = 0
        self._seq = 0
        self._handoffs: List[HandoffRecord] = []
        self._verifications: List[VerificationRecord] = []
        self._resolutions: List[ResolutionRecord] = []
        self._exhausted_reason: Optional[str] = None

    def _next_id(self, prefix: str) -> str:
        """Allocate the next deterministic id for a record.

        Args:
            prefix: the record kind prefix.

        Returns:
            A deterministic id like ``handoff-0003``.
        """
        self._seq += 1
        return f"{prefix}-{self._seq:04d}"

    def register_agent(self, agent_id: str, role: str = "analyst",
                       authority: Optional[float] = None) -> None:
        """Register an agent and its consensus authority.

        Args:
            agent_id: unique agent identifier.
            role: the agent's role (used for veto + verification policy).
            authority: optional explicit weight; role default when omitted.
        """
        self._agents[agent_id] = role
        if authority is None:
            authority = DEFAULT_AUTHORITY.get(role, 1.0)
        self._authority[agent_id] = float(authority)

    def advance_round(self) -> bool:
        """Advance the bounded round counter.

        Returns:
            True when a new round was opened; False when the round ceiling was
            reached (the protocol records why it is exhausted).
        """
        if self._round >= self._max_rounds:
            self._exhausted_reason = "max_rounds_reached"
            return False
        self._round += 1
        return True

    def delegate(self, task: str, from_agent: str, to_agent: str,
                 response: Optional[Dict[str, Any]] = None,
                 accept: bool = True, reason: str = "") -> HandoffRecord:
        """Record a delegation from one agent to another.

        The handoff is refused (with a recorded reason) when the delegator or
        recipient is unregistered, when an agent delegates to itself, or when
        the handoff budget is exhausted. A refused handoff is still recorded.

        Args:
            task: the delegated task description.
            from_agent: the delegating agent id.
            to_agent: the recipient agent id.
            response: optional payload returned by the recipient.
            accept: whether the recipient accepted the task.
            reason: optional acceptance/refusal reason.

        Returns:
            The recorded HandoffRecord.
        """
        hid = self._next_id("handoff")
        accepted = bool(accept)
        if from_agent not in self._agents:
            accepted, reason = False, f"unknown delegator: {from_agent}"
        elif to_agent not in self._agents:
            accepted, reason = False, f"unknown recipient: {to_agent}"
        elif from_agent == to_agent:
            accepted, reason = False, "self-delegation refused"
        elif sum(1 for h in self._handoffs if h.accepted) >= self._max_handoffs:
            accepted, reason = False, "handoff_budget_exhausted"
            self._exhausted_reason = "max_handoffs_reached"
        elif not reason:
            reason = "delegated" if accepted else "recipient declined"
        record = HandoffRecord(
            handoff_id=hid, task=str(task), from_agent=from_agent,
            to_agent=to_agent, round=self._round, accepted=accepted,
            reason=reason, response=response if accepted else None,
        )
        self._handoffs.append(record)
        return record

    def verify(self, proposal: Dict[str, Any], verifier_agent: str) -> VerificationRecord:
        """Independently verify a proposal; accept or reject with a reason.

        The verifier's policy is derived from the proposal content — declared
        evidence, declared violations, and confidence — plus the verifier's
        own role threshold. It never trusts the author's self-assessment, and
        it will not audit a proposal it authored (independence gate).

        Args:
            proposal: dict with proposal_id, author, evidence (list),
                violates (list), and confidence (float).
            verifier_agent: the independent agent performing the audit.

        Returns:
            The recorded VerificationRecord (accepted, with a non-empty reason).
        """
        pid = str(proposal.get("proposal_id", self._next_id("proposal")))
        author = str(proposal.get("author", "unknown"))
        role = self._agents.get(verifier_agent, "")
        checks: List[Dict[str, Any]] = []

        if verifier_agent not in self._agents:
            return self._record_verification(
                pid, author, verifier_agent, False,
                f"unknown verifier: {verifier_agent}", checks,
            )
        if verifier_agent == author:
            checks.append({"check": "independence", "passed": False,
                           "detail": "verifier authored the proposal"})
            return self._record_verification(
                pid, author, verifier_agent, False,
                "independence violated: verifier cannot audit its own proposal",
                checks,
            )
        checks.append({"check": "independence", "passed": True,
                       "detail": "verifier differs from author"})

        evidence = proposal.get("evidence") or []
        evidence_ok = bool(evidence)
        checks.append({"check": "evidence_present", "passed": evidence_ok,
                       "detail": f"{len(evidence)} evidence item(s)"})
        if not evidence_ok:
            return self._record_verification(
                pid, author, verifier_agent, False,
                "no supporting evidence provided", checks,
            )

        violations = [str(v) for v in (proposal.get("violates") or [])]
        checks.append({"check": "no_declared_violation", "passed": not violations,
                       "detail": ", ".join(violations) if violations else "none"})
        if violations:
            return self._record_verification(
                pid, author, verifier_agent, False,
                "proposal violates " + ", ".join(violations), checks,
            )

        try:
            confidence = float(proposal.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        threshold = VERIFY_MIN_CONFIDENCE.get(role, 0.5)
        conf_ok = confidence >= threshold
        checks.append({"check": "confidence_threshold", "passed": conf_ok,
                       "detail": f"confidence={confidence:.3f} >= {threshold:.3f}"})
        if not conf_ok:
            return self._record_verification(
                pid, author, verifier_agent, False,
                f"confidence {confidence:.3f} below {role or 'verifier'} "
                f"threshold {threshold:.3f}", checks,
            )

        return self._record_verification(
            pid, author, verifier_agent, True,
            "proposal verified: evidence present, no violations, confidence met",
            checks,
        )

    def _record_verification(self, proposal_id: str, author: str,
                             verifier: str, accepted: bool, reason: str,
                             checks: List[Dict[str, Any]]) -> VerificationRecord:
        """Append a verification record and return it.

        Args:
            proposal_id: the proposal id.
            author: the proposal author.
            verifier: the verifying agent.
            accepted: the verification outcome.
            reason: the non-empty rationale.
            checks: per-check detail.

        Returns:
            The recorded VerificationRecord.
        """
        record = VerificationRecord(
            proposal_id=proposal_id, author=author, verifier=verifier,
            accepted=accepted, reason=reason, round=self._round, checks=checks,
        )
        self._verifications.append(record)
        return record

    def resolve(self, agents: List[Dict[str, Any]]) -> ResolutionRecord:
        """Resolve a crew's disagreement deterministically.

        Rule order: unanimity first; a hard-veto role's rejection overrides a
        weighted majority; otherwise an authority-weighted majority decides, and
        an exact tie breaks by highest authority then lexicographically smallest
        agent id. Every branch is deterministic and audited.

        Args:
            agents: crew positions, each a dict with agent_id, validated,
                weight (optional), and role (optional).

        Returns:
            The recorded ResolutionRecord.
        """
        positions = list(agents or [])
        if not positions:
            return self._record_resolution(ResolutionRecord(
                method="no_agents", validated=True, outcome="no_agents",
                conflict=False, escalated=False, weight_for=0.0,
                weight_against=0.0, dissenters=[], reason="no agents to resolve",
                round=self._round,
            ))

        for_agents: List[Dict[str, Any]] = []
        against_agents: List[Dict[str, Any]] = []
        for agent in positions:
            (for_agents if agent.get("validated") else against_agents).append(agent)
        w_for = sum(self._weight_of(a) for a in for_agents)
        w_against = sum(self._weight_of(a) for a in against_agents)
        conflict = bool(for_agents) and bool(against_agents)

        if not conflict:
            validated = bool(for_agents)
            outcome = "validated" if validated else "rejected"
            return self._record_resolution(ResolutionRecord(
                method="unanimous", validated=validated, outcome=outcome,
                conflict=False, escalated=False, weight_for=w_for,
                weight_against=w_against, dissenters=[],
                reason="unanimous crew position", round=self._round,
            ))

        vetoers = [a for a in against_agents
                   if self._role_of(a) in HARD_VETO_ROLES]
        if vetoers:
            names = [self._agent_id(a) for a in vetoers]
            return self._record_resolution(ResolutionRecord(
                method="hard_veto", validated=False, outcome="rejected",
                conflict=True, escalated=True, weight_for=w_for,
                weight_against=w_against, dissenters=[],
                reason="hard veto by " + ", ".join(names) + " overrode the crew",
                round=self._round,
            ))

        if abs(w_for - w_against) > 1e-9:
            validated = w_for > w_against
            method = "weighted_majority"
            reason = (f"authority-weighted majority "
                      f"(for={w_for:.3f}, against={w_against:.3f})")
        else:
            ranked = sorted(positions, key=lambda a: (
                -self._weight_of(a), self._agent_id(a)))
            winner = ranked[0]
            validated = bool(winner.get("validated"))
            method = "authority_tiebreak"
            reason = (f"tie {w_for:.3f}={w_against:.3f}; highest-authority "
                      f"agent {self._agent_id(winner)} decides")
        dissenters = [self._agent_id(a) for a in against_agents] if validated \
            else [self._agent_id(a) for a in for_agents]
        return self._record_resolution(ResolutionRecord(
            method=method, validated=validated,
            outcome="validated" if validated else "rejected", conflict=True,
            escalated=False, weight_for=w_for, weight_against=w_against,
            dissenters=dissenters, reason=reason, round=self._round,
        ))

    def _record_resolution(self, record: ResolutionRecord) -> ResolutionRecord:
        """Append a resolution record and return it.

        Args:
            record: the resolution record to store.

        Returns:
            The same record.
        """
        self._resolutions.append(record)
        return record

    def _agent_id(self, agent: Dict[str, Any]) -> str:
        """Read an agent's id from a position dict.

        Args:
            agent: a crew position dict.

        Returns:
            The agent id (or "unknown").
        """
        return str(agent.get("agent_id", "unknown"))

    def _role_of(self, agent: Dict[str, Any]) -> str:
        """Read an agent's role, defaulting to the registry then "analyst".

        Args:
            agent: a crew position dict.

        Returns:
            The role string.
        """
        role = agent.get("role")
        if role:
            return str(role)
        return self._agents.get(self._agent_id(agent), "analyst")

    def _weight_of(self, agent: Dict[str, Any]) -> float:
        """Read an agent's authority weight from the dict or the registry.

        Args:
            agent: a crew position dict.

        Returns:
            The non-negative weight.
        """
        raw = agent.get("weight")
        if raw is None:
            raw = self._authority.get(self._agent_id(agent), 1.0)
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return 0.0

    @property
    def rounds_used(self) -> int:
        """The number of coordination rounds opened so far.

        Returns:
            The round count.
        """
        return self._round

    def audit(self) -> Dict[str, Any]:
        """Return a bounded, measurable audit snapshot of the collaboration.

        Returns:
            Dict with delegation/verification/resolution counts, round and
            handoff usage against their ceilings, and a ``bounded`` verdict.
        """
        rejections_with_reason = sum(
            1 for v in self._verifications
            if not v.accepted and bool(v.reason)
        )
        conflicts_resolved = sum(
            1 for r in self._resolutions if r.conflict
        )
        accepted_handoffs = sum(1 for h in self._handoffs if h.accepted)
        bounded = (
            self._round <= self._max_rounds
            and accepted_handoffs <= self._max_handoffs
        )
        return {
            "delegations": len(self._handoffs),
            "handoffs_accepted": sum(1 for h in self._handoffs if h.accepted),
            "handoffs_rejected": sum(1 for h in self._handoffs if not h.accepted),
            "verifications": len(self._verifications),
            "acceptances": sum(1 for v in self._verifications if v.accepted),
            "rejections_with_reason": rejections_with_reason,
            "conflicts_resolved": conflicts_resolved,
            "rounds_used": self._round,
            "max_rounds": self._max_rounds,
            "handoff_budget": self._max_handoffs,
            "bounded": bounded,
            "exhausted_reason": self._exhausted_reason,
        }

    def records(self) -> Dict[str, Any]:
        """Serialize every recorded interaction.

        Returns:
            Dict with handoffs, verifications, and resolutions lists.
        """
        return {
            "handoffs": [h.to_dict() for h in self._handoffs],
            "verifications": [v.to_dict() for v in self._verifications],
            "resolutions": [r.to_dict() for r in self._resolutions],
        }


__all__ = [
    "CoordinationProtocol",
    "HandoffRecord",
    "VerificationRecord",
    "ResolutionRecord",
    "HARD_VETO_ROLES",
    "DEFAULT_MAX_ROUNDS",
    "DEFAULT_MAX_HANDOFFS",
    "DEFAULT_AUTHORITY",
    "VERIFY_MIN_CONFIDENCE",
]
