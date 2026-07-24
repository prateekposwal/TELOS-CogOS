"""
PerceptionQuality — Analyzes whether input resolution supports reliable object detection.

Produces a QualityReport that the Pipeline uses to decide:
  - Can any registered strategy detect the target at this resolution?
  - If not, should we fall back to proxy tracking?

Architecture:
  Called during the PERCEIVE phase, before Streams run. If quality is
  below threshold, the ResolutionGate blocks ball-specific streams
  and the ProxyStream activates instead.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger('telos_perception')


@dataclass
class QualityReport:
    quality_score: float
    resolution: tuple[int, int]
    target_size_px: Optional[float]
    notes: str
    proxy_recommended: bool = False
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quality_score": round(self.quality_score, 3),
            "resolution": list(self.resolution),
            "target_size_px": self.target_size_px,
            "notes": self.notes,
            "proxy_recommended": self.proxy_recommended,
        }


class PerceptionQuality:

    MIN_PX_FOR_DETECTION = 15.0

    def assess(self, frame_width: int, frame_height: int,
               estimated_target_px: Optional[float] = None,
               **kwargs) -> QualityReport:
        w, h = frame_width, frame_height
        if w <= 0 or h <= 0:
            return QualityReport(
                quality_score=0.0, resolution=(w, h),
                target_size_px=estimated_target_px,
                notes="Invalid frame dimensions",
                proxy_recommended=True,
            )

        aspect_ratio = max(w, h) / min(w, h)
        pixel_count = w * h
        resolution_score = min(1.0, pixel_count / (1280 * 720))

        if estimated_target_px is not None and estimated_target_px > 0:
            size_ratio = estimated_target_px / self.MIN_PX_FOR_DETECTION
            size_score = min(1.0, size_ratio)
        else:
            size_score = resolution_score * 0.5

        aspect_penalty = 0.0
        if aspect_ratio < 1.0:
            aspect_penalty = 0.05
        if aspect_ratio > 2.5:
            aspect_penalty = 0.1

        quality_score = max(0.0, min(1.0, 0.4 * resolution_score + 0.5 * size_score - aspect_penalty))

        needs_proxy = quality_score < 0.35

        notes_parts = []
        if resolution_score < 0.3:
            notes_parts.append(f"low resolution ({w}x{h})")
        if size_score is not None and size_score < 0.5 and estimated_target_px is not None:
            notes_parts.append(f"target too small ({estimated_target_px:.0f}px, need ≥{self.MIN_PX_FOR_DETECTION:.0f})")
        if aspect_penalty > 0:
            notes_parts.append(f"unusual aspect ratio ({aspect_ratio:.2f})")
        if needs_proxy:
            notes_parts.append("falling back to proxy tracking")
        notes = "; ".join(notes_parts) if notes_parts else "adequate quality"

        logger.info(
            f"[PerceptionQuality] {w}x{h} target={estimated_target_px}px → "
            f"quality={quality_score:.3f} {'proxy' if needs_proxy else 'direct'}"
        )

        return QualityReport(
            quality_score=quality_score,
            resolution=(w, h),
            target_size_px=estimated_target_px,
            notes=notes,
            proxy_recommended=needs_proxy,
            params={
                "resolution_score": round(resolution_score, 3),
                "size_score": round(size_score, 3) if size_score is not None else None,
                "aspect_penalty": round(aspect_penalty, 3),
            },
        )
