"""
CapabilityRegistry — Knows what the system can detect under what conditions.

Each DetectionCapability defines a known operating envelope. The registry
matches current input against these envelopes and reports what's possible.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class DetectionCapability:
    name: str
    min_object_px: float
    min_width: int
    min_height: int
    description: str
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def can_detect(self, w: int, h: int, target_px: Optional[float]) -> Tuple[bool, str]:
        if w < self.min_width or h < self.min_height:
            return False, f"Resolution {w}x{h} below minimum {self.min_width}x{self.min_height}"
        if target_px is not None and target_px < self.min_object_px:
            return False, (
                f"Target {target_px:.0f}px below {self.name} minimum "
                f"{self.min_object_px:.0f}px"
            )
        return True, "OK"

    def match_score(self, w: int, h: int, target_px: Optional[float]) -> float:
        score = 1.0
        res_pixels = w * h
        ideal_pixels = self.min_width * self.min_height
        if res_pixels < ideal_pixels:
            score *= res_pixels / ideal_pixels
        if target_px is not None and target_px < self.min_object_px:
            score *= target_px / self.min_object_px
        return max(0.0, min(1.0, score))


class CapabilityRegistry:

    def __init__(self):
        self._capabilities: List[DetectionCapability] = [
            DetectionCapability(
                name="color_threshold",
                min_object_px=10, min_width=480, min_height=360,
                description="HSV color thresholding for white ball on green field",
                tags=["fast", "football", "color"],
            ),
            DetectionCapability(
                name="yolo_sports_ball",
                min_object_px=15, min_width=640, min_height=480,
                description="YOLOv8 sports ball detection (COCO class 32)",
                tags=["deep_learning", "accurate"],
            ),
            DetectionCapability(
                name="optical_flow_proxy",
                min_object_px=1, min_width=160, min_height=120,
                description="Motion hotspot tracking via optical flow",
                tags=["proxy", "robust", "low_res"],
            ),
            DetectionCapability(
                name="template_matching",
                min_object_px=8, min_width=320, min_height=240,
                description="Cross-correlation template matching",
                tags=["fast", "requires_template"],
            ),
            DetectionCapability(
                name="hough_circles",
                min_object_px=6, min_width=320, min_height=240,
                description="Hough Circle Transform for circular objects",
                tags=["geometric", "noisy"],
            ),
        ]

    def register(self, capability: DetectionCapability) -> None:
        self._capabilities.append(capability)

    def check(self, w: int, h: int,
              target_px: Optional[float] = None) -> List[Dict]:
        results = []
        for c in self._capabilities:
            ok, reason = c.can_detect(w, h, target_px)
            score = c.match_score(w, h, target_px)
            results.append({
                "name": c.name,
                "description": c.description,
                "feasible": ok,
                "match_score": round(score, 3),
                "reason": reason,
                "tags": c.tags,
            })
        results.sort(key=lambda r: -r["match_score"])
        return results

    def best(self, w: int, h: int,
             target_px: Optional[float] = None) -> Optional[Dict]:
        results = self.check(w, h, target_px)
        feasible = [r for r in results if r["feasible"]]
        if feasible:
            return feasible[0]
        return results[0] if results else None

    def suggest_improvements(self, w: int, h: int,
                              target_px: Optional[float] = None) -> List[str]:
        suggestions = []
        best = self.check(w, h, target_px)
        top = best[0] if best else None
        if top and not top["feasible"]:
            needed_w = max(c.min_width for c in self._capabilities if c.min_width > w)
            needed_h = max(c.min_height for c in self._capabilities if c.min_height > h)
            if needed_w > w or needed_h > h:
                suggestions.append(
                    f"Increase resolution to at least {needed_w}x{needed_h}px"
                )
            if target_px is not None:
                min_px = min(
                    c.min_object_px for c in self._capabilities
                    if c.min_object_px > target_px
                )
                if min_px > target_px:
                    suggestions.append(
                        f"Ball needs to be at least {min_px:.0f}px "
                        f"(currently {target_px:.0f}px) — use closer camera or higher res"
                    )
        return suggestions

    @property
    def stats(self) -> Dict:
        return {
            "total_capabilities": len(self._capabilities),
            "capabilities": [c.name for c in self._capabilities],
        }
