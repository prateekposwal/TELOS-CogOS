from __future__ import annotations
import json
import logging
logger = logging.getLogger("telos_benchmark")
import os
from typing import Dict, Optional
from telos.benchmarks.metrics.report import BenchmarkReport
def save_baseline(report: BenchmarkReport, path: str) -> None:
    """Save a benchmark report as a baseline for future comparison.
        Args:
            path: the file/system path
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, 'w') as f:
        json.dump({
            "session_id": report.session_id,
            "generated_at": report.generated_at,
            "cycle_count": report.cycle_count,
            "system_score": report.current_system_score,
            "mission_score": report.current_mission_score,
            "epoch_aggregates": {
                label: summary.aggregate()
                for label, summary in report.epochs.items()
            },
            "trends": report.trends,
        }, f, indent=2, default=str)
    logger.info(f"Baseline saved to {path}")


def load_baseline(path: str) -> Optional[Dict]:
    """Load a saved baseline for comparison.
        Args:
            path: the file/system path
    """
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════
# Main Collector Class
# ═══════════════════════════════════════════════════════════════════
