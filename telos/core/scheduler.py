"""
ProactiveScheduler — Periodic codebase health checks via TELOS pipeline.

Runs pipeline.execute() on a timer, feeding codebase snapshots through the
DevDomainAdapter. Findings are pushed through the SuggestionChannel.

Usage:
    scheduler = ProactiveScheduler("/path/to/project", interval_minutes=5)
    scheduler.start()  # runs in background thread
    # ...
    scheduler.stop()
"""

import time
import logging
import threading
from typing import Optional, Callable, List

import numpy as np

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
    DepHealthValidator, TestCoverageValidator, CodeQualityValidator,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.adapters.dev_domain_adapter import DevDomainSim, DevDomainAdpt, CodebaseSnapshot

logger = logging.getLogger('telos_scheduler')


class ProactiveScheduler:
    """Periodically scans a codebase and runs TELOS reasoning on it."""

    def __init__(self, project_path: str, interval_minutes: int = 5,
                 on_findings: Optional[Callable[[List[str]], None]] = None):
        self.project_path = project_path
        self.interval = interval_minutes * 60
        self.on_findings = on_findings
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._cycle = 0

        # Build TELOS pipeline with DevDomainAdapter
        self.sim = DevDomainSim(project_path)
        self.pipeline = TelosV14Pipeline(PipelineConfig(
            adapter=DevDomainAdpt(), simulator=self.sim,
            compute_budget_ms=50.0, state_dim=11, n_worlds=5, horizon=3,
        ))
        skill_lib = SkillLibrary()
        sim_engine = CounterfactualEngine(self.sim)
        self.pipeline.register_stream(ReflexStream(skill_lib))
        self.pipeline.register_stream(PerceptionStream(skill_lib))
        self.pipeline.register_stream(MemoryStream(skill_lib))
        self.pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
        self.pipeline.register_validator(RealityValidator())
        self.pipeline.register_validator(ConstraintValidator())
        self.pipeline.register_validator(MemoryAdvisor(skill_lib))
        self.pipeline.register_validator(MissionDriftDetector(drift_threshold=3.0))
        # Dev-domain validators for codebase health checks
        self.pipeline.register_validator(DepHealthValidator())
        self.pipeline.register_validator(TestCoverageValidator())
        self.pipeline.register_validator(CodeQualityValidator())

    def start(self):
        """Start the scheduler in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"Scheduler started — scanning {self.project_path} every {self.interval // 60}m")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            self._cycle += 1
            try:
                state = self.sim.snapshot()
                result = self.pipeline.execute(state, user_name="TELOS-DevAgent")
                findings = self.sim._last_snapshot.findings if self.sim._last_snapshot else []

                if findings:
                    logger.info(f"[Cycle {self._cycle}] {len(findings)} findings")
                    if self.on_findings:
                        self.on_findings(findings)

                # Adapt horizon based on findings count
                if len(findings) > 5:
                    self.pipeline._infra_manager.adaptive_horizon = 5
                else:
                    self.pipeline._infra_manager.adaptive_horizon = 3

            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            # Sleep, checking every second for stop signal
            for _ in range(self.interval):
                if not self._running:
                    return
                time.sleep(1)
