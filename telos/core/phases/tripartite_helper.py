"""Tripartite uncertainty computation helper."""
import math
import numpy as np
from telos.core.uncertainty.tripartite import TripartiteUncertainty

def _compute_tripartite_from_available(self, pipeline, ctx):
        """Compute tripartite uncertainty from data available during SELECT phase.
        
        This fixes the timing issue where tripartite U was computed in ACT phase
        but consumed in SELECT phase.
        """
        # Prediction error from attention trajectory divergences
        attn = getattr(pipeline, '_attention_engine', None)
        prediction_error = 0.0
        if attn and hasattr(attn, '_trajectory_divergences') and attn._trajectory_divergences:
            recent_divs = attn._trajectory_divergences[-3:]
            prediction_error = min(1.0, sum(recent_divs) / max(len(recent_divs), 1) * 0.5)
        
        # Identity entropy — guard against mock/non-numeric values in tests
        identity_entropy = getattr(pipeline, '_identity_entropy', None)
        identity_entropy_val = 0.0
        if identity_entropy is not None:
            try:
                raw = identity_entropy.collapse_rate
                identity_entropy_val = abs(float(raw))
            except (TypeError, ValueError):
                identity_entropy_val = 0.0
        
        # Council signals (from current or previous cycle)
        council_signals = []
        if ctx.verdict:
            try:
                council_signals = ctx.verdict.signals
            except Exception:
                council_signals = []
        elif ctx.council and ctx.council.verdict:
            try:
                council_signals = ctx.council.verdict.signals
            except Exception:
                council_signals = []
        
        # Use the classmethod to compute from available data
        return TripartiteUncertainty.compute_from_available(
            prediction_error=prediction_error,
            identity_entropy=identity_entropy_val,
            council_signals=council_signals,
        )
