"""
MultiAgentInternalDebate — Temporary Perspectives That Debate and Merge.

Prateek's insight: "Multi-agent internal debate — temporary perspectives
(optimist, skeptic, economist, engineer) that debate and merge. Not
validators — perspectives."

The Council uses validators that block/pass based on fixed criteria. Internal
Debate creates temporary perspective-agents that each evaluate the situation
from a different viewpoint. They debate, challenge each other, and produce
a synthesized perspective that no single agent would have reached alone.

Key differences from Council validators:
  - Perspectives are TEMPORARY (created per decision, destroyed after)
  - Perspectives don't block — they ARGUE and PERSUADE
  - The debate produces a synthesis, not a vote
  - Perspectives can be contradictory — that's the point

Built-in perspectives:
  - OPTIMIST: Sees opportunities. "What could go right?"
  - SKEPTIC: Challenges assumptions. "What's the catch?"
  - ECONOMIST: Considers resource efficiency. "Is this worth the cost?"
  - ENGINEER: Focuses on feasibility. "Can this actually work?"
  - ETHICIST: Weighs moral implications. "Is this the right thing to do?"

Architecture:
  - Perspective: a lightweight agent with a role, arguments, and counter-arguments
  - Debate: structured exchange of arguments between perspectives
  - Synthesis: merging of winning arguments into a coherent recommendation
  - DebateRecord: complete transcript for transparency
"""

from __future__ import annotations

import logging
import time
import math
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_internal_debate')


class PerspectiveRole(Enum):
    OPTIMIST = "optimist"
    SKEPTIC = "skeptic"
    ECONOMIST = "economist"
    ENGINEER = "engineer"
    ETHICIST = "ethicist"
    STRATEGIST = "strategist"


@dataclass
class Argument:
    """A single argument made by a perspective during debate."""
    id: str
    perspective: PerspectiveRole
    claim: str
    evidence: str
    strength: float  # 0-1 how confident the perspective is in this argument
    rebuttals: List[str] = field(default_factory=list)  # IDs of arguments rebutting this
    accepted: bool = False  # Was this argument accepted into the synthesis?


@dataclass
class Perspective:
    """A temporary perspective agent that evaluates from one viewpoint."""
    role: PerspectiveRole
    name: str
    description: str
    arguments: List[Argument] = field(default_factory=list)
    confidence: float = 0.5  # How confident this perspective is in its assessment
    bias_strength: float = 0.7  # How strongly it holds its perspective bias

    def generate_arguments(self, context: Dict[str, Any]) -> List[Argument]:
        """Generate arguments based on this perspective's viewpoint.

        To be extended with actual reasoning. Base implementation provides
        perspective-appropriate generic arguments.
        """
        # Stub — in production, each perspective would analyze the context
        return []


# ── Built-in perspective definitions ────────────────────────

OPTIMIST = Perspective(
    role=PerspectiveRole.OPTIMIST,
    name="Optimist",
    description="Focuses on opportunities, positive outcomes, and upsides. "
                "Asks 'what could go right?' and 'what opportunities exist?'",
    bias_strength=0.7,
)

SKEPTIC = Perspective(
    role=PerspectiveRole.SKEPTIC,
    name="Skeptic",
    description="Challenges assumptions, identifies risks, and questions claims. "
                "Asks 'what's the evidence?' and 'what could go wrong?'",
    bias_strength=0.8,
)

ECONOMIST = Perspective(
    role=PerspectiveRole.ECONOMIST,
    name="Economist",
    description="Evaluates resource efficiency, cost-benefit tradeoffs, and "
                "opportunity costs. Asks 'is this worth the investment?'",
    bias_strength=0.65,
)

ENGINEER = Perspective(
    role=PerspectiveRole.ENGINEER,
    name="Engineer",
    description="Assesses feasibility, technical soundness, and implementation "
                "details. Asks 'can this actually be built?'",
    bias_strength=0.75,
)

ETHICIST = Perspective(
    role=PerspectiveRole.ETHICIST,
    name="Ethicist",
    description="Weighs moral implications, fairness, and alignment with values. "
                "Asks 'is this the right thing to do?'",
    bias_strength=0.6,
)


@dataclass
class DebateRound:
    """A single round of debate."""
    round_number: int
    arguments: List[Argument]
    rebuttals: Dict[str, List[str]]  # argument_id -> list of rebutting argument IDs
    timestamp: float = field(default_factory=time.time)


@dataclass
class DebateRecord:
    """Complete record of a debate session."""
    id: str
    context_description: str
    perspectives_used: List[str]
    rounds: List[DebateRound]
    synthesis: str
    accepted_arguments: List[str]
    winning_perspective: Optional[str]
    consensus_level: float  # 0-1
    timestamp: float = field(default_factory=time.time)


class InternalDebate:
    """Temporary perspectives that debate and merge into synthesis.

    The debate process:
    1. Context is presented to all perspectives
    2. Each perspective generates arguments from its viewpoint
    3. Perspectives rebut each other's arguments (structured debate)
    4. Arguments are evaluated: strength, evidence, rebuttal resilience
    5. Synthesis: winning arguments are merged into a coherent assessment
    6. The synthesis is returned as the debate output

    Integration:
      - Called during the Council phase (before validators)
      - Output feeds into validator decision-making
      - Can be used independently for complex decisions
    """

    def __init__(self, max_rounds: int = 3,
                 min_arguments_per_perspective: int = 1,
                 synthesis_confidence_threshold: float = 0.6):
        self._max_rounds = max_rounds
        self._min_arguments = min_arguments_per_perspective
        self._synthesis_threshold = synthesis_confidence_threshold

        self._perspective_registry: Dict[PerspectiveRole, Perspective] = {
            PerspectiveRole.OPTIMIST: OPTIMIST,
            PerspectiveRole.SKEPTIC: SKEPTIC,
            PerspectiveRole.ECONOMIST: ECONOMIST,
            PerspectiveRole.ENGINEER: ENGINEER,
            PerspectiveRole.ETHICIST: ETHICIST,
        }

        self._debate_history: List[DebateRecord] = []
        self._max_history = 100
        self._total_debates: int = 0

    def register_perspective(self, perspective: Perspective) -> None:
        """Register a custom perspective."""
        self._perspective_registry[perspective.role] = perspective
        logger.info(f"InternalDebate: registered perspective '{perspective.name}'")

    def debate(self, context: Dict[str, Any],
               perspective_roles: Optional[List[PerspectiveRole]] = None,
               context_description: str = "") -> DebateRecord:
        """Run a debate on the given context using selected perspectives.

        Args:
            context: The decision context (state, options, goals)
            perspective_roles: Which perspectives to include (default: all)
            context_description: Human-readable context description

        Returns:
            DebateRecord with full transcript and synthesis
        """
        if perspective_roles is None:
            perspective_roles = list(PerspectiveRole)

        perspectives = [
            self._perspective_registry[role]
            for role in perspective_roles
            if role in self._perspective_registry
        ]

        if not perspectives:
            logger.warning("InternalDebate: no perspectives available")
            return DebateRecord(
                id=f"debate_{int(time.time()*1000)}",
                context_description=context_description,
                perspectives_used=[],
                rounds=[],
                synthesis="No perspectives available",
                accepted_arguments=[],
                winning_perspective=None,
                consensus_level=0.0,
            )

        rounds: List[DebateRound] = []
        all_arguments: Dict[str, Argument] = {}
        rebuttal_map: Dict[str, List[str]] = {}

        # Round 1: Each perspective generates initial arguments
        initial_args: List[Argument] = []
        for perspective in perspectives:
            args = self._generate_arguments_for_role(perspective.role, context)
            for arg in args:
                all_arguments[arg.id] = arg
            initial_args.extend(args)

        round1 = DebateRound(
            round_number=1,
            arguments=initial_args,
            rebuttals={},
        )
        rounds.append(round1)

        # Round 2..N: Perspectives rebut each other
        for round_num in range(2, self._max_rounds + 2):
            rebuttals: List[Argument] = []
            round_rebuttals: Dict[str, List[str]] = {}

            # Each perspective picks arguments from OTHER perspectives to rebut
            for perspective in perspectives:
                # Find arguments from other perspectives
                others_args = [
                    a for a in all_arguments.values()
                    if a.perspective != perspective.role and not a.accepted
                ]
                # Pick the strongest argument from each other perspective
                for other_arg in others_args[:2]:  # Max 2 rebuttals per round
                    rebuttal = Argument(
                        id=f"rebut_{round_num}_{perspective.role.value}_{len(rebuttals)}",
                        perspective=perspective.role,
                        claim=f"Rebuttal to '{other_arg.claim[:40]}...': "
                              f"counter-argument from {perspective.name} viewpoint",
                        evidence=f"{perspective.name} perspective challenges this",
                        strength=0.5 + perspective.bias_strength * 0.3,
                        rebuttals=[],
                    )
                    rebuttals.append(rebuttal)
                    all_arguments[rebuttal.id] = rebuttal
                    if other_arg.id not in round_rebuttals:
                        round_rebuttals[other_arg.id] = []
                    round_rebuttals[other_arg.id].append(rebuttal.id)

            if not rebuttals:
                break  # No more rebuttals to make

            round_n = DebateRound(
                round_number=round_num,
                arguments=rebuttals,
                rebuttals=round_rebuttals,
            )
            rounds.append(round_n)

        # Evaluate arguments and produce synthesis
        accepted_args = self._evaluate_arguments(all_arguments, rebuttal_map)
        synthesis, winner = self._synthesize(accepted_args, perspectives, context)

        # Compute consensus level (how much agreement among perspectives)
        consensus = self._compute_consensus(perspectives, accepted_args)

        record = DebateRecord(
            id=f"debate_{int(time.time()*1000)}",
            context_description=context_description,
            perspectives_used=[p.name for p in perspectives],
            rounds=rounds,
            synthesis=synthesis,
            accepted_arguments=[a.id for a in accepted_args],
            winning_perspective=winner.name if winner else None,
            consensus_level=consensus,
        )

        self._debate_history.append(record)
        if len(self._debate_history) > self._max_history:
            self._debate_history.pop(0)
        self._total_debates += 1

        logger.info(
            f"InternalDebate: debate complete — {len(perspectives)} perspectives, "
            f"{len(rounds)} rounds, {len(accepted_args)} accepted arguments, "
            f"winner={winner.name if winner else 'none'}, "
            f"consensus={consensus:.2f}"
        )

        return record

    def _generate_arguments_for_role(self, role: PerspectiveRole,
                                      context: Dict[str, Any]) -> List[Argument]:
        """Generate perspective-appropriate arguments from context.

        This is the core reasoning method. In production, this would use
        LLM calls or structured reasoning. Here we provide a template.
        """
        args: List[Argument] = []
        base_id = f"arg_{int(time.time()*1000)}_{role.value}"

        perspective = self._perspective_registry.get(role)
        bias = perspective.bias_strength if perspective else 0.5

        # Extract key context elements
        options = context.get('options', [])
        goals = context.get('goals', {})
        resources = context.get('resources', {})

        if role == PerspectiveRole.OPTIMIST:
            if options:
                args.append(Argument(
                    id=f"{base_id}_0",
                    perspective=role,
                    claim=f"There are {len(options)} viable options to explore",
                    evidence=f"Multiple alternatives available for consideration",
                    strength=0.5 + bias * 0.3,
                ))
            args.append(Argument(
                id=f"{base_id}_1",
                perspective=role,
                claim="This situation presents learning opportunities regardless of outcome",
                evidence="Every decision generates data for model improvement",
                strength=0.6,
            ))

        elif role == PerspectiveRole.SKEPTIC:
            args.append(Argument(
                id=f"{base_id}_0",
                perspective=role,
                claim="Claims should be treated as provisional until verified",
                evidence="Cognitive biases can lead to overconfidence in initial assessments",
                strength=0.5 + bias * 0.3,
            ))
            if options:
                args.append(Argument(
                    id=f"{base_id}_1",
                    perspective=role,
                    claim="The best-seeming option may have hidden downsides",
                    evidence="Surface-level evaluation misses second-order effects",
                    strength=0.5,
                ))

        elif role == PerspectiveRole.ECONOMIST:
            budget = resources.get('budget', 100)
            args.append(Argument(
                id=f"{base_id}_0",
                perspective=role,
                claim=f"Resource efficiency matters: budget={budget}",
                evidence="Every compute cycle has an opportunity cost",
                strength=0.5 + bias * 0.2,
            ))

        elif role == PerspectiveRole.ENGINEER:
            args.append(Argument(
                id=f"{base_id}_0",
                perspective=role,
                claim="Feasibility depends on available capabilities",
                evidence="Not all options are implementable with current infrastructure",
                strength=0.5 + bias * 0.3,
            ))

        elif role == PerspectiveRole.ETHICIST:
            args.append(Argument(
                id=f"{base_id}_0",
                perspective=role,
                claim="Actions should align with stated values and principles",
                evidence="Value-aligned decisions build trust and coherence",
                strength=0.5 + bias * 0.2,
            ))

        return args

    def _evaluate_arguments(self, arguments: Dict[str, Argument],
                             rebuttal_map: Dict[str, List[str]]) -> List[Argument]:
        """Evaluate which arguments survive rebuttal.

        An argument is accepted if:
        - It has no rebuttals, OR
        - It has rebuttals but its strength exceeds the rebuttal strength
        """
        accepted: List[Argument] = []

        for arg_id, arg in arguments.items():
            rebuttals = rebuttal_map.get(arg_id, [])

            if not rebuttals:
                # No one challenged this — accepted by default
                arg.accepted = True
                accepted.append(arg)
            else:
                # Check if any rebuttal is stronger
                survived = True
                for rebut_id in rebuttals:
                    rebuttal = arguments.get(rebut_id)
                    if rebuttal and rebuttal.strength > arg.strength:
                        survived = False
                        break
                if survived:
                    arg.accepted = True
                    accepted.append(arg)

        return accepted

    def _synthesize(self, accepted_args: List[Argument],
                     perspectives: List[Perspective],
                     context: Dict[str, Any]) -> Tuple[str, Optional[Perspective]]:
        """Merge accepted arguments into a coherent synthesis.

        The winning perspective is the one with the most accepted arguments.
        """
        if not accepted_args:
            return ("No consensus reached. All arguments rebutted.", None)

        # Count accepted arguments per perspective
        perspective_counts: Dict[PerspectiveRole, int] = {}
        for arg in accepted_args:
            perspective_counts[arg.perspective] = perspective_counts.get(arg.perspective, 0) + 1

        # Find winning perspective
        winner_role = max(perspective_counts, key=perspective_counts.get) if perspective_counts else None
        winner = next((p for p in perspectives if p.role == winner_role), None) if winner_role else None

        # Build synthesis from accepted arguments
        lines = ["Debate Synthesis:"]
        for arg in accepted_args:
            perspective_name = arg.perspective.value.capitalize()
            lines.append(f"  - {perspective_name}: {arg.claim}")
            if arg.evidence:
                lines.append(f"    (evidence: {arg.evidence})")

        lines.append(f"\nWinning perspective: {winner.name if winner else 'None'}")

        return "\n".join(lines), winner

    def _compute_consensus(self, perspectives: List[Perspective],
                            accepted_args: List[Argument]) -> float:
        """Compute consensus level. 1.0 = all perspectives agree. 0.0 = total disagreement."""
        if not perspectives or not accepted_args:
            return 0.5

        # How many perspectives have accepted arguments?
        roles_with_args = {arg.perspective for arg in accepted_args}
        return len(roles_with_args) / len(perspectives)

    def latest_debate(self) -> Optional[DebateRecord]:
        """Get the most recent debate record."""
        return self._debate_history[-1] if self._debate_history else None

    @property
    def total_debates(self) -> int:
        return self._total_debates

    def to_dict(self) -> Dict:
        latest = self.latest_debate()
        return {
            "total_debates": self._total_debates,
            "perspectives_available": [
                {
                    "role": role.value,
                    "name": p.name,
                    "bias_strength": p.bias_strength,
                }
                for role, p in self._perspective_registry.items()
            ],
            "latest_debate": {
                "id": latest.id,
                "context": latest.context_description[:60],
                "perspectives": latest.perspectives_used,
                "rounds": len(latest.rounds),
                "accepted_arguments": len(latest.accepted_arguments),
                "winning_perspective": latest.winning_perspective,
                "consensus_level": round(latest.consensus_level, 3),
            } if latest else None,
        }
