"""
Experience Manager — External Learning Observer

The ExperienceManager is the ONLY component that performs learning.
It lives OUTSIDE the Pipeline and observes PipelineResult after
each decision cycle. When a trajectory scores above threshold,
it indexes the trajectory as a Skill in the SkillLibrary.

This separation ensures the Pipeline remains a pure reasoning
engine — stateless, deterministic, and testable. Learning is
an additive capability that can be swapped, upgraded, or
disabled without touching the core runtime.
"""

from __future__ import annotations

import time
import logging
import uuid
from typing import Optional, List, Any, TYPE_CHECKING
from dataclasses import dataclass

from telos.core.ledger.skill_library import SkillLibrary, Skill

if TYPE_CHECKING:
    from telos.core.runtime import PipelineResult

logger = logging.getLogger('telos_experience')


@dataclass
class ExperienceConfig:
    utility_threshold: float = 0.1
    index_interval: int = 1
    max_skills: int = 100
    log_level: str = "INFO"
    # Verified acquisition (Λ2.3, SkillAcquisition): when True a trajectory
    # above ``utility_threshold`` becomes a CANDIDATE — a skill enters the
    # library only after a verification signal (outcome >=
    # ``acquisition_min_outcome``) is observed on a LATER cycle with the SAME
    # situation fingerprint. This generalises the write-side fix-loop rule
    # ("done only when verified") to learning. Default False keeps the
    # historical direct-index behavior byte-identical for existing consumers.
    verified_acquisition: bool = False
    acquisition_min_outcome: float = 0.6
    acquisition_candidate_ttl_cycles: int = 50


class ExperienceManager:
    """External observer that learns from Pipeline decisions.

    Usage:
        manager = ExperienceManager(skill_library, config)
        manager.observe(pipeline_result)  # Called after each execute()

    The manager NEVER modifies Pipeline state. It only writes to
    the SkillLibrary — a separate, persistent ledger.

    When ``config.verified_acquisition`` is on, admission is routed through
    the one canonical verifier (``SkillAcquisition``): propose on a
    promising cycle, admit only once a later matching cycle confirms the
    outcome. The direct-index behavior is the default and is unchanged.
    """

    def __init__(self, skill_library: SkillLibrary,
                 config: Optional[ExperienceConfig] = None):
        self.skill_library = skill_library
        self.config = config or ExperienceConfig()
        self._observations: List[dict] = []
        self._skills_indexed: int = 0
        self._cycle_count: int = 0
        # ONE canonical acquisition controller, constructed here when the
        # flag is on. Lazy import avoids a ledger<->learning import cycle.
        self.acquisition = None
        if self.config.verified_acquisition:
            from telos.core.learning.acquisition import SkillAcquisition
            self.acquisition = SkillAcquisition(
                self.skill_library,
                min_outcome=self.config.acquisition_min_outcome,
                candidate_ttl_cycles=self.config.acquisition_candidate_ttl_cycles,
            )

    def observe(self, result: PipelineResult) -> Optional[Skill]:
        """Process a PipelineResult and optionally index a new Skill.

        Returns the indexed Skill if one was created, else None.

        Args:
            result: the PipelineResult of the cycle just executed.
        """
        self._cycle_count += 1
        if self.acquisition is not None:
            return self._observe_verified(result)
        return self._observe_direct(result)

    def _observe_direct(self, result: PipelineResult) -> Optional[Skill]:
        """Historical behavior: index immediately when above threshold."""
        if result.selected_trajectory is None:
            logger.debug(f"ExperienceManager: REJECTED — no selected_trajectory in PipelineResult")
            self._log_observation(result, indexed=False, reason="no_trajectory")
            return None

        if result.health_score < self.config.utility_threshold:
            logger.debug(f"ExperienceManager: REJECTED — health_score={result.health_score:.4f} < utility_threshold={self.config.utility_threshold}")
            self._log_observation(result, indexed=False, reason="below_threshold")
            return None

        if self._cycle_count % self.config.index_interval != 0:
            logger.debug(f"ExperienceManager: REJECTED — cycle {self._cycle_count} not at index_interval={self.config.index_interval}")
            self._log_observation(result, indexed=False, reason="not_interval")
            return None

        skill = self._create_skill(result)
        self.skill_library.index_skill(skill)
        self._skills_indexed += 1

        self._log_observation(result, indexed=True, skill_id=skill.skill_id)
        logger.info(f"ExperienceManager: indexed skill {skill.skill_id} "
                     f"(utility={result.health_score:.3f}, total={self._skills_indexed})")

        return skill

    def _trajectory(self, result: PipelineResult) -> dict:
        """The serializable trajectory payload for a candidate."""
        intent = result.selected_trajectory
        return {
            "intent_type": intent.intent_type if intent else "unknown",
            "confidence": intent.confidence if intent else 0.0,
            "params": intent.params if intent else {},
        }

    def _observe_verified(self, result: PipelineResult) -> Optional[Skill]:
        """Verified admission: propose then confirm on a later match.

        A matching outstanding candidate is verified FIRST (a repeated
        situation with a sufficient outcome is the verification signal);
        otherwise a promising cycle proposes a new candidate. Unverified
        candidates never enter the library and retire on TTL (Λ2.3).
        """
        cycle = self._cycle_count
        if result.selected_trajectory is None:
            logger.debug("ExperienceManager: REJECTED — no selected_trajectory")
            self._log_observation(result, indexed=False, reason="no_trajectory")
            return None

        outcome = float(result.health_score)
        trace = result.decision_trace
        fingerprint = self._compute_fingerprint(
            trace.world_state_snapshot if trace else None)

        # 1. Verification of an outstanding matching candidate.
        for candidate in self.acquisition.candidates:
            if candidate.fingerprint != fingerprint:
                continue
            if self.acquisition.verify(candidate.candidate_id, outcome,
                                        cycle=cycle):
                skill = self.acquisition.last_acquired
                if skill is not None:
                    self._skills_indexed += 1
                    self._log_observation(result, indexed=True,
                                          skill_id=skill.skill_id)
                    logger.info(
                        f"ExperienceManager: VERIFIED skill {skill.skill_id} "
                        f"(utility={outcome:.3f}, total={self._skills_indexed})")
                    return skill
            break

        # 2. Proposal for a promising, interval-aligned observation.
        if (outcome >= self.config.utility_threshold
                and cycle % self.config.index_interval == 0):
            self.acquisition.propose(fingerprint, self._trajectory(result),
                                     cycle=cycle, source="runtime")
            self._log_observation(result, indexed=False, reason="candidate")
        else:
            self._log_observation(result, indexed=False, reason="below_threshold")
        return None

    def index_recent(self, checkpoints_dir: str, cycles: int = 5) -> int:
        """Index recent decision traces from checkpoint files into the skill library.
        
        Scans checkpoint files in the given directory and indexes skills from
        the most recent decision traces to warm up the skill library on startup.
        
        Args:
            checkpoints_dir: Path to checkpoint directory
            cycles: Number of recent checkpoints to process
            
        Returns:
            Number of skills indexed
        """
        import os
        import json
        indexed = 0
        
        if not os.path.isdir(checkpoints_dir):
            logger.warning(f"index_recent: checkpoint dir {checkpoints_dir} not found")
            return 0
        
        # Find checkpoint files, sorted by modification time
        cp_files = sorted(
            [f for f in os.listdir(checkpoints_dir) if f.startswith("checkpoint_") and f.endswith(".json")],
            key=lambda f: os.path.getmtime(os.path.join(checkpoints_dir, f)),
        )
        
        # Take most recent `cycles` checkpoints
        for cp_file in cp_files[-cycles:]:
            cp_path = os.path.join(checkpoints_dir, cp_file)
            try:
                with open(cp_path) as f:
                    data = json.load(f)
                
                # Extract decision traces from checkpoint
                traces = data.get("decision_traces", data.get("traces", []))
                if not traces:
                    traces = [data]  # maybe the checkpoint itself is a trace
                
                for trace_data in traces:
                    health = trace_data.get("health_score", trace_data.get("decision_integrity", 0.5))
                    intent_type = trace_data.get("intent_type", "unknown")
                    worlds_gen = trace_data.get("worlds_generated", 0)
                    
                    if health >= self.config.utility_threshold:
                        # Create a skill from this trace
                        from telos.core.ledger.skill_library import Skill
                        import uuid
                        
                        skill = Skill(
                            skill_id=f"skill_replay_{uuid.uuid4().hex[:8]}",
                            fingerprint=trace_data.get("fingerprint", "replay_" + cp_file),
                            trajectory={
                                "intent_type": intent_type,
                                "confidence": trace_data.get("confidence", 0.5),
                                "params": trace_data.get("params", {}),
                            },
                            utility_score=health,
                            metadata={
                                "cycle_id": trace_data.get("cycle_id", 0),
                                "worlds_generated": worlds_gen,
                                "source": f"checkpoint:{cp_file}",
                                "timestamp": time.time(),
                            },
                        )
                        self.skill_library.index_skill(skill)
                        self._skills_indexed += 1
                        indexed += 1
                        logger.info(f"ExperienceManager: indexed replay skill {skill.skill_id} "
                                     f"(utility={health:.3f}, source={cp_file})")
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.debug(f"index_recent: error processing {cp_file}: {e}")
        
        logger.info(f"ExperienceManager: index_recent completed — {indexed} skills indexed from {len(cp_files[-cycles:])} checkpoints")
        return indexed

    def _create_skill(self, result: PipelineResult) -> Skill:
        trace = result.decision_trace
        state_snapshot = trace.world_state_snapshot if trace else None
        intent = result.selected_trajectory

        return Skill(
            skill_id=f"skill_{uuid.uuid4().hex[:8]}",
            fingerprint=self._compute_fingerprint(state_snapshot),
            trajectory={
                "intent_type": intent.intent_type if intent else "unknown",
                "confidence": intent.confidence if intent else 0.0,
                "params": intent.params if intent else {},
            },
            utility_score=result.health_score,
            metadata={
                "cycle_id": trace.cycle_id if trace else self._cycle_count,
                "worlds_generated": result.worlds_generated,
                "budget_consumed": trace.budget_consumed_ms if trace else 0.0,
                "timestamp": time.time(),
            },
        )

    def _compute_fingerprint(self, state) -> str:
        if state is None:
            return "null_state"
        import hashlib
        state_bytes = state.tobytes()
        return hashlib.md5(state_bytes).hexdigest()[:12]

    def observe_user_interaction(self, user_name: str, intent_type: str,
                                  confidence: float, cycle: int,
                                  ledger: 'WorldLedger') -> None:
        """Record identity delta for a known user after each cycle.
        
        This closes the loop: after TELOS acts, the ExperienceManager
        writes identity deltas to the WorldLedger so next cycle's
        PERCEIVE phase can retrieve the updated profile.
        Args:
            user_name: the user_name argument for this call.
            intent_type: the intent_type argument for this call.
            confidence: the confidence argument for this call.
        """
        ledger.record_user_interaction(user_name, intent_type, confidence, cycle)
        logger.debug(
            f"IdentityDelta: user={user_name} intent={intent_type} "
            f"cycle={cycle}"
        )

    def _log_observation(self, result: PipelineResult, indexed: bool,
                         reason: str = "", skill_id: str = "") -> None:
        entry = {
            "cycle": self._cycle_count,
            "health": result.health_score,
            "worlds": result.worlds_generated,
            "indexed": indexed,
            "reason": reason,
            "skill_id": skill_id,
            "timestamp": time.time(),
        }
        self._observations.append(entry)

        if len(self._observations) > 1000:
            self._observations = self._observations[-500:]

    @property
    def stats(self) -> dict:
        out = {
            "total_observations": len(self._observations),
            "skills_indexed": self._skills_indexed,
            "skill_library_size": len(self.skill_library.skills),
            "indexed_rate": (
                self._skills_indexed / max(len(self._observations), 1)
            ),
        }
        if self.acquisition is not None:
            out["acquisition"] = self.acquisition.stats()
        return out
