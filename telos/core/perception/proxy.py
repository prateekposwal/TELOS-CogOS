"""
ProxyStream — Tracks proxy objects when direct detection is impossible.

When the ResolutionGate blocks ball-specific detection streams (because
the target is too small for the input resolution), the ProxyStream
activates. Instead of tracking the ball, it tracks proxy indicators:

  1. Player cluster positions (via motion/color blobs)
  2. Field deformation (via optical flow divergence)
  3. Motion hotspots (via frame differencing)

The detection method is injectable (at construction time), so callers
can provide their own implementation. By default, ProxyStream uses
OpenCV Farneback optical flow when cv2 is available, falling back to
a simple numpy-based frame difference.

This satisfies Λ3.4 (Adaptive Capacity): the system adjusts its strategy
based on input quality, rather than failing silently.
"""

from __future__ import annotations

import logging
import numpy as np
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

from telos.core.streams.base import CognitiveStream
from telos.core.ledger.skill_library import SkillLibrary
from telos.world.world import World
from telos.intent_ir import IntentIR

logger = logging.getLogger('telos_perception')

_HAS_CV2 = False
try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    pass


@dataclass
class ProxyReport:
    method: str
    confidence: float
    estimated_position: Optional[np.ndarray]
    motion_hotspots: List[Dict[str, Any]] = field(default_factory=list)
    field_center: Optional[np.ndarray] = None
    notes: str = ""


def compute_motion_hotspots(prev_gray: np.ndarray,
                            current_gray: np.ndarray,
                            top_n: int = 5,
                            percentile: int = 85) -> List[Dict]:
    """Shared motion hotspot detection. Used by both ProxyStream and
        batch video analyzers to avoid duplicate code.
        Args:
            prev_gray: the prev_gray argument for this call.
            current_gray: the current_gray argument for this call.
            top_n: the top_n argument for this call.
            percentile: the percentile argument for this call.
    """
    if _HAS_CV2:
        import cv2
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, current_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    else:
        diff = current_gray.astype(np.float32) - prev_gray.astype(np.float32)
        mag = np.abs(diff)

    threshold = np.percentile(mag, percentile) if mag.size > 0 else 15
    mag_copy = mag.copy()
    hotspots = []
    for _ in range(top_n):
        idx = np.argmax(mag_copy)
        if mag_copy.flat[idx] < threshold:
            break
        y, x = np.unravel_index(idx, mag_copy.shape)
        hotspots.append({"x": int(x), "y": int(y), "magnitude": float(mag[y, x])})
        y0, y1 = max(0, y - 8), min(mag.shape[0], y + 8)
        x0, x1 = max(0, x - 8), min(mag.shape[1], x + 8)
        mag_copy[y0:y1, x0:x1] = 0
    return hotspots


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 3:
        if _HAS_CV2:
            import cv2
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return np.mean(frame, axis=2).astype(np.uint8)
    return frame.astype(np.uint8)


class ProxyStream(CognitiveStream):

    PRIORITY = 0.6

    def __init__(self, skill_library: SkillLibrary,
                 detect_fn: Optional[Callable] = None):
        super().__init__(skill_library)
        self._detect_fn = detect_fn or compute_motion_hotspots
        self._prev_gray: Optional[np.ndarray] = None

    @property
    def priority(self) -> float:
        return self.PRIORITY

    def process(self, world: World) -> IntentIR:
        state = world.state
        metadata = world.metadata or {}

        is_proxy_mode = metadata.get("proxy_mode", False)

        if not is_proxy_mode:
            return IntentIR(
                intent_type="proxy_idle",
                confidence=0.1,
                params={"reason": "direct detection available, proxy not needed"},
                metadata={"stream": "proxy"},
            )

        proxy_report = self._compute_proxy(state, metadata)

        return IntentIR(
            intent_type="proxy_track",
            confidence=proxy_report.confidence,
            params={
                "method": proxy_report.method,
                "estimated_position": (
                    proxy_report.estimated_position.tolist()
                    if proxy_report.estimated_position is not None else None
                ),
                "motion_hotspots": proxy_report.motion_hotspots,
                "field_center": (
                    proxy_report.field_center.tolist()
                    if proxy_report.field_center is not None else None
                ),
                "notes": proxy_report.notes,
            },
            metadata={
                "stream": "proxy",
                "proxy_method": proxy_report.method,
                "proxy_confidence": proxy_report.confidence,
            },
        )

    def _compute_proxy(self, state: np.ndarray,
                       metadata: Dict[str, Any]) -> ProxyReport:
        frame_data = metadata.get("frame_data", None)
        reset_proxy = metadata.get("reset_proxy", False)

        if reset_proxy:
            self._prev_gray = None

        if frame_data is not None and isinstance(frame_data, np.ndarray):
            return self._motion_based_proxy(frame_data, metadata)

        return self._state_based_proxy(state, metadata)

    def _motion_based_proxy(self, frame: np.ndarray,
                            metadata: Dict[str, Any]) -> ProxyReport:
        gray = _to_gray(frame)
        fw = metadata.get("frame_width", gray.shape[1])
        fh = metadata.get("frame_height", gray.shape[0])
        field_center = np.array([fw / 2, fh / 2])

        hotspots = []
        if self._prev_gray is not None:
            hotspots = self._detect_fn(self._prev_gray, gray)
        self._prev_gray = gray

        if hotspots:
            avg_x = np.mean([h["x"] for h in hotspots])
            avg_y = np.mean([h["y"] for h in hotspots])
            estimated = np.array([avg_x, avg_y])
            confidence = min(0.6, 0.3 + 0.05 * len(hotspots))
        else:
            estimated = field_center.copy()
            confidence = 0.2

        return ProxyReport(
            method="motion_hotspot",
            confidence=confidence,
            estimated_position=estimated,
            motion_hotspots=hotspots[:5],
            field_center=field_center,
            notes=f"proxy tracking via {len(hotspots)} motion hotspots",
        )

    def _state_based_proxy(self, state: np.ndarray,
                           metadata: Dict[str, Any]) -> ProxyReport:
        fw = metadata.get("frame_width", 640)
        fh = metadata.get("frame_height", 480)
        field_center = np.array([fw / 2, fh / 2])

        return ProxyReport(
            method="state_estimate",
            confidence=0.15,
            estimated_position=field_center.copy(),
            field_center=field_center,
            notes="no frame data available — estimating from field center",
        )
