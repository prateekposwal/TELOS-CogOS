"""
Decision Calibration — honest confidence, measured against realized outcomes.

Borrowed from the System One model discipline (TypeSafe / Jev): a decision is
only automatable when its stated confidence is CALIBRATED — higher confidence
must mean higher realized accuracy. TELOS already emits rich confidence
signals (intent confidence, DI, tripartite uncertainty) but never measured
whether those claims were TRUE. This package closes that loop.
"""

from telos.core.calibration.tracker import CalibrationTracker, CalibrationStats

__all__ = ["CalibrationTracker", "CalibrationStats"]
