"""
CheckpointManager — Durable execution with crash recovery.

Saves Pipeline state after each cycle so TELOS can resume from the
last complete cycle after a crash. Serialization per subsystem
is delegated to checkpoint_serializers.py.

Persisted state:
  - cycle_count, WorldLedger, SkillLibrary, StreamCalibrator
  - FailureLedger, MissionPolicy, KnowledgeGraph, DecisionTrace
  - SimEngine, PlanningHorizon, PatternLibrary, SystemSelf
"""

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from telos.core.infra_manager.checkpoint_serializers import (
    dump_ledger, dump_skills, dump_calibrator, dump_failures,
    dump_policy, dump_knowledge, dump_sim_engine,
    dump_planning_horizon, dump_trace,
    load_ledger, load_skills, load_calibrator, load_failures,
    load_policy, load_knowledge,
    load_session_essence, load_truncated_history,
)

logger = logging.getLogger('telos_checkpoint')


@dataclass
class CheckpointData:
    cycle: int
    timestamp: float
    world_ledger: Dict
    skill_library: Dict
    stream_calibrator: Dict
    failure_ledger: List[Dict]
    mission_policy: Dict
    decision_trace: Optional[Dict] = None
    knowledge_graph: Optional[Dict] = None
    sim_engine: Optional[List[Dict]] = None
    planning_horizon: Optional[Dict] = None
    patterns_path: Optional[str] = None
    system_self_path: Optional[str] = None
    session_essence: Optional[Dict] = None
    truncated_history: Optional[List[Dict]] = None
    omega_threshold_learner_data: Optional[Dict] = None
    # ── Bitcoin-inspired Chain ──────────────────────────────────────────
    prev_checkpoint_hash: str = ""  # SHA-256 of the previous checkpoint


class CheckpointManager:
    """Manages save/load of Pipeline state to disk.

    Usage:
        mgr = CheckpointManager(path="/tmp/telos_checkpoints")
        mgr.save(...)   # after each execute()
        cp = mgr.load() # on restart
    """

    def __init__(self, path: str = ".telos_checkpoints",
                 max_checkpoints: int = 10):
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._max_checkpoints = max_checkpoints
        self._last_save_path: Optional[Path] = None
        self._save_count: int = 0
        self._hmac_key = os.environ.get('TELOS_CHECKPOINT_SECRET', 'telos-dev-key').encode()
        # ── Checkpoint Chain ────────────────────────────────────────────
        self._last_checkpoint_hash: str = ""  # SHA-256 of last saved checkpoint
        # On init, load the latest checkpoint's hash to continue the chain
        latest = self.latest_path
        if latest:
            try:
                with open(latest) as lf:
                    raw = json.load(lf)
                # Reconstruct the hash that was stored as prev_checkpoint_hash
                # for the NEXT checkpoint
                stored_prev = raw.get("prev_checkpoint_hash", "")
                if stored_prev:
                    self._last_checkpoint_hash = stored_prev
                    logger.debug(f"CheckpointChain initialized with prev_hash={stored_prev[:16]}...")
            except Exception:
                pass
        CHECKPOINT_SCHEMA = {
            "type": "object",
            "properties": {
                "cycle": {"type": "integer", "minimum": 0},
                "hmac": {"type": "string"},
            },
            "required": ["cycle", "hmac"],
        }
        self._schema = CHECKPOINT_SCHEMA

    def _compute_hmac(self, payload: Dict) -> str:
        raw = json.dumps(payload, default=str, sort_keys=True)
        return hmac.new(self._hmac_key, raw.encode(), hashlib.sha256).hexdigest()

    @property
    def latest_path(self) -> Optional[Path]:
        checkpoints = sorted(self._path.glob("checkpoint_*.json"))
        return checkpoints[-1] if checkpoints else None

    def save(self, cycle: int,
             world_ledger: Any = None,
             skill_library: Any = None,
             stream_calibrator: Any = None,
             failure_ledger: Any = None,
             mission_policy: Any = None,
             decision_trace: Optional[Any] = None,
             knowledge_graph: Optional[Any] = None,
             sim_engine: Optional[Any] = None,
             planning_horizon: Optional[Any] = None,
             pattern_library: Optional[Any] = None,
             infrastructure_manager: Optional[Any] = None,
             session_essence: Optional[Dict] = None,
             truncated_history: Optional[List[Dict]] = None,
             omega_threshold_learner: Optional[Any] = None) -> Path:
        """Serialize Pipeline state to a checkpoint file."""
        patterns_path_value = None
        if pattern_library is not None and hasattr(pattern_library, 'save'):
            patterns_path_value = os.path.join(self._path, f"patterns_{cycle}.json")
            try:
                pattern_library.save(patterns_path_value)
            except Exception as e:
                logger.warning(f"PatternLibrary save failed: {e}")
                patterns_path_value = None

        system_self_path_value = None
        if infrastructure_manager and hasattr(infrastructure_manager, 'system_self'):
            try:
                ss_path = os.path.join(self._path, f"system_self_{cycle}.json")
                infrastructure_manager.system_self.save(ss_path)
                system_self_path_value = ss_path
            except Exception as e:
                logger.warning(f"SystemSelf save failed: {e}")

        data = CheckpointData(
            cycle=cycle,
            timestamp=time.time(),
            world_ledger=dump_ledger(world_ledger) if world_ledger else {},
            skill_library=dump_skills(skill_library) if skill_library else {},
            stream_calibrator=dump_calibrator(stream_calibrator) if stream_calibrator else {},
            failure_ledger=dump_failures(failure_ledger) if failure_ledger else [],
            mission_policy=dump_policy(mission_policy) if mission_policy else {},
            decision_trace=dump_trace(decision_trace),
            knowledge_graph=dump_knowledge(knowledge_graph),
            sim_engine=dump_sim_engine(sim_engine),
            planning_horizon=dump_planning_horizon(planning_horizon),
            patterns_path=patterns_path_value,
            system_self_path=system_self_path_value,
            session_essence=session_essence,
            truncated_history=truncated_history,
            omega_threshold_learner_data=omega_threshold_learner.to_dict() if omega_threshold_learner else None,
        )

        self._save_count += 1
        tmp_path = self._path / "checkpoint_tmp.json"
        final_path = self._path / f"checkpoint_{cycle:04d}.json"
        payload = {
            "cycle": data.cycle, "timestamp": data.timestamp,
            "world_ledger": data.world_ledger,
            "skill_library": data.skill_library,
            "stream_calibrator": data.stream_calibrator,
            "failure_ledger": data.failure_ledger,
            "mission_policy": data.mission_policy,
            "decision_trace": data.decision_trace,
            "knowledge_graph": data.knowledge_graph,
            "sim_engine": data.sim_engine,
            "planning_horizon": data.planning_horizon,
            "patterns_path": data.patterns_path,
            "system_self_path": data.system_self_path,
            "session_essence": data.session_essence,
            "truncated_history": data.truncated_history,
            "omega_threshold_learner": data.omega_threshold_learner_data,
            # ── Checkpoint Chain ───────────────────────────────────────────
            "prev_checkpoint_hash": self._last_checkpoint_hash,
        }
        # Compute this checkpoint's own hash for chain continuity
        raw_for_hash = json.dumps(payload, default=str, sort_keys=True)
        checkpoint_hash = hashlib.sha256(raw_for_hash.encode()).hexdigest()
        data.prev_checkpoint_hash = checkpoint_hash
        payload["prev_checkpoint_hash"] = checkpoint_hash
        self._last_checkpoint_hash = checkpoint_hash
        payload["hmac"] = self._compute_hmac(payload)
        with open(tmp_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        os.replace(tmp_path, final_path)
        self._last_save_path = final_path
        self._prune()
        logger.debug(f"Checkpoint saved: {final_path} (cycle {cycle})")
        return final_path

    def load(self) -> Optional[CheckpointData]:
        path = self.latest_path
        if not path:
            logger.info("No checkpoint found")
            return None
        try:
            with open(path) as f:
                raw = json.load(f)

            # HMAC verification
            stored_hmac = raw.pop("hmac", None)
            if not stored_hmac:
                # Legacy checkpoint without HMAC — warn but accept
                logger.warning(f"Checkpoint without HMAC: {path} (pre-security upgrade)")
            else:
                computed_hmac = self._compute_hmac(raw)
                if not hmac.compare_digest(stored_hmac, computed_hmac):
                    logger.error(f"Checkpoint HMAC mismatch — rejecting {path} (tampered?)")
                    return None
            data = CheckpointData(
                cycle=raw.get("cycle", 0),
                timestamp=raw.get("timestamp", 0),
                world_ledger=raw.get("world_ledger", {}),
                skill_library=raw.get("skill_library", {}),
                stream_calibrator=raw.get("stream_calibrator", {}),
                failure_ledger=raw.get("failure_ledger", []),
                mission_policy=raw.get("mission_policy", {}),
                decision_trace=raw.get("decision_trace"),
                knowledge_graph=raw.get("knowledge_graph"),
                sim_engine=raw.get("sim_engine"),
                planning_horizon=raw.get("planning_horizon"),
                patterns_path=raw.get("patterns_path"),
                system_self_path=raw.get("system_self_path"),
                session_essence=raw.get("session_essence"),
                truncated_history=raw.get("truncated_history"),
                omega_threshold_learner_data=raw.get("omega_threshold_learner"),
                prev_checkpoint_hash=raw.get("prev_checkpoint_hash", ""),
            )

            # ── Checkpoint Chain Verification ────────────────────────────────
            # Every checkpoint stores prev_checkpoint_hash which is the hash of
            # the previous checkpoint. Verify chain continuity.
            if data.prev_checkpoint_hash:
                # Load the previous checkpoint and verify its hash matches
                prev_path = self._path / f"checkpoint_{max(0, data.cycle - 1):04d}.json"
                if prev_path.exists():
                    try:
                        with open(prev_path) as pf:
                            prev_raw = json.load(pf)
                        # Verify: compute hash of previous checkpoint
                        prev_hmac = prev_raw.pop("hmac", None)
                        prev_raw_for_hash = json.dumps(prev_raw, default=str, sort_keys=True)
                        prev_computed_hash = hashlib.sha256(prev_raw_for_hash.encode()).hexdigest()
                        # The current checkpoint's prev_checkpoint_hash should match
                        # the hash of the previous checkpoint
                        stored_prev_hash = data.prev_checkpoint_hash
                        if stored_prev_hash != prev_computed_hash:
                            logger.warning(
                                f"Checkpoint chain MISMATCH: checkpoint {data.cycle} "
                                f"claims prev_hash={stored_prev_hash[:16]}... but "
                                f"checkpoint {data.cycle-1} computes to {prev_computed_hash[:16]}..."
                            )
                        else:
                            logger.debug(
                                f"Checkpoint chain verified: cycle {data.cycle} → "
                                f"prev_hash matches cycle {data.cycle-1}"
                            )
                    except Exception as e:
                        logger.warning(f"Checkpoint chain verification failed: {e}")
                else:
                    logger.debug(f"Checkpoint chain: no previous checkpoint to verify (cycle {data.cycle})")

                # Update the chain tracker
                self._last_checkpoint_hash = data.prev_checkpoint_hash

            logger.info(f"Checkpoint loaded: {path} (cycle {data.cycle})")
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return None

    def restore(self, pipeline: Any, data: CheckpointData) -> None:
        if hasattr(pipeline, '_cycle_count'):
            pipeline._cycle_count = data.cycle

        ledger = getattr(pipeline, 'ledger', None)
        load_ledger(data.world_ledger, ledger)

        infra = getattr(pipeline, '_infra_manager', None)
        if infra:
            load_knowledge(data.knowledge_graph or {}, infra.knowledge)
            load_failures(data.failure_ledger or [], infra.failures)
            load_calibrator(data.stream_calibrator or {}, infra.calibrator)
            load_policy(data.mission_policy or {}, infra.policy)

        skill_lib = getattr(pipeline, '_skill_library', None)
        if skill_lib:
            load_skills(data.skill_library or {}, skill_lib)

        if data.patterns_path and hasattr(pipeline, 'pattern_library'):
            try:
                pipeline.pattern_library.load(data.patterns_path)
                logger.info(f"PatternLibrary restored from {data.patterns_path}")
            except Exception as e:
                logger.warning(f"PatternLibrary restore failed: {e}")

        if data.system_self_path and pipeline._infra_manager:
            try:
                pipeline._infra_manager.system_self.load(data.system_self_path)
                logger.info(f"SystemSelf restored from {data.system_self_path}")
            except Exception as e:
                logger.warning(f"SystemSelf restore failed: {e}")

        # Restore session continuity data
        if hasattr(pipeline, '_cycle_count'):
            session = load_session_essence(data.session_essence)
            truncated = load_truncated_history(data.truncated_history)
            if session or truncated:
                pipeline._session_essence = session
                pipeline._truncated_history = truncated
                logger.info(f"Session continuity restored: essence={'yes' if session else 'no'}, history={len(truncated) if truncated else 0} items")

        logger.info(f"Pipeline restored to cycle {data.cycle}")

    def clear(self) -> None:
        for p in self._path.glob("checkpoint_*.json"):
            p.unlink()
        logger.info("All checkpoints cleared")

    def _prune(self) -> None:
        checkpoints = sorted(self._path.glob("checkpoint_*.json"))
        while len(checkpoints) > self._max_checkpoints:
            oldest = checkpoints.pop(0)
            oldest.unlink()
            logger.debug(f"Pruned checkpoint: {oldest}")
