"""
ResolutionGate — Governance-level block when input quality is insufficient.

Called by the Pipeline during the PERCEIVE/STREAMS boundary. If the
PerceptionQuality report indicates the target is undetectable, the Gate
blocks ball-specific streams and notifies the Council.

This is a lightweight governance component (not a full Firewall check),
designed to be fast and decisive.
"""

from __future__ import annotations

import logging
from typing import Optional, List
from dataclasses import dataclass

from telos.core.perception.quality import QualityReport

logger = logging.getLogger('telos_perception')


@dataclass
class GateVerdict:
    passed: bool
    reason: str
    proxy_activated: bool = False
    blocked_streams: List[str] = None

    def __post_init__(self):
        if self.blocked_streams is None:
            self.blocked_streams = []


class ResolutionGate:

    def __init__(self, threshold: float = 0.35):
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        self._threshold = max(0.0, min(1.0, value))

    def evaluate(self, report: QualityReport,
                 target_streams: Optional[List[str]] = None) -> GateVerdict:
        if target_streams is None:
            target_streams = []

        if report.quality_score >= self._threshold:
            return GateVerdict(
                passed=True,
                reason=f"Quality {report.quality_score:.3f} ≥ threshold {self._threshold:.3f}",
                proxy_activated=False,
                blocked_streams=[],
            )

        logger.info(
            f"[ResolutionGate] BLOCKING {len(target_streams)} streams: "
            f"quality={report.quality_score:.3f} < {self._threshold:.3f}"
        )

        return GateVerdict(
            passed=False,
            reason=(
                f"Input quality {report.quality_score:.3f} below threshold "
                f"{self._threshold:.3f}. {report.notes}"
            ),
            proxy_activated=True,
            blocked_streams=target_streams,
        )
