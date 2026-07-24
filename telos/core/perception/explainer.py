"""
PerceptionExplainer — Translates QualityReport + GateVerdict into
human-readable explanations and actionable suggestions.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from telos.core.perception.quality import QualityReport, PerceptionQuality
from telos.core.perception.gate import GateVerdict


class PerceptionExplainer:

    MIN_PX = PerceptionQuality.MIN_PX_FOR_DETECTION

    def explain(self, report: QualityReport,
                verdict: GateVerdict) -> Dict:
        parts = []
        details = []

        w, h = report.resolution
        res_label = self._resolution_name(w, h)
        parts.append(f"Input is {res_label} ({w}x{h})")
        details.append({"aspect": "resolution", "value": f"{w}x{h}", "label": res_label})

        if report.target_size_px is not None:
            if report.target_size_px < self.MIN_PX:
                gap = self.MIN_PX - report.target_size_px
                parts.append(
                    f"Target is {report.target_size_px:.0f}px "
                    f"(needs >= {self.MIN_PX:.0f}px, gap {gap:.0f}px)"
                )
                details.append({
                    "aspect": "target_size", "value": f"{report.target_size_px:.0f}px",
                    "minimum": f"{self.MIN_PX:.0f}px", "gap": round(gap, 1),
                })
            else:
                parts.append(f"Target is {report.target_size_px:.0f}px (adequate)")

        quality_pct = round(report.quality_score * 100)
        parts.append(f"Quality score: {quality_pct}%")

        if report.params.get("resolution_score") is not None:
            details.append({
                "aspect": "resolution_score",
                "value": f"{report.params['resolution_score']:.3f}",
            })
        if report.params.get("size_score") is not None:
            details.append({
                "aspect": "size_score",
                "value": f"{report.params['size_score']:.3f}",
            })

        if not verdict.passed and verdict.proxy_activated:
            parts.append(f"Below threshold — blocked direct detection, using proxy mode")
            details.append({
                "aspect": "gate", "value": "blocked",
                "proxy_mode": True,
            })

        return {
            "summary": ". ".join(parts) + ".",
            "details": details,
            "suggestions": self._suggest(report),
            "quality_score": round(report.quality_score, 3),
            "proxy_mode": verdict.proxy_activated,
        }

    def summarize(self, report: QualityReport,
                  verdict: GateVerdict) -> str:
        return self.explain(report, verdict)["summary"]

    def _suggest(self, report: QualityReport) -> List[Dict]:
        suggestions = []
        w, h = report.resolution

        if w * h < 1280 * 720:
            suggestions.append({
                "action": "higher_resolution",
                "label": "Use a 720p+ video",
                "reason": f"{w}x{h} limits detection to objects >= {self.MIN_PX:.0f}px",
                "impact": "high",
            })

        if report.target_size_px is not None and report.target_size_px < self.MIN_PX:
            suggestions.append({
                "action": "closer_camera",
                "label": "Use closer camera angle",
                "reason": f"Ball is {report.target_size_px:.0f}px, needs >= {self.MIN_PX:.0f}px",
                "impact": "high",
            })

        suggestions.append({
            "action": "proxy_mode",
            "label": "Tracking motion hotspots",
            "reason": "Proxy mode active — following movement clusters",
            "impact": "medium",
        })

        if w < 480:
            suggestions.append({
                "action": "super_resolution",
                "label": "Apply 2x upscale",
                "reason": f"{w}px is very low — upscale may improve edge detection",
                "impact": "low",
            })

        return suggestions

    @staticmethod
    def _resolution_name(w: int, h: int) -> str:
        pixels = w * h
        if pixels >= 1920 * 1080:
            return "Full HD"
        elif pixels >= 1280 * 720:
            return "HD"
        elif pixels >= 854 * 480:
            return "SD (480p)"
        elif pixels >= 640 * 360:
            return "low (360p)"
        return "very low"
