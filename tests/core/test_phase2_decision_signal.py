"""v8 Phase 2 — decision-signal invariants.

The controlled ablation matrix (telos/tools/causal_ablation.py) established
that the Unified Cognitive Functional (all J terms) is DECORATIVE for
selection on the post-Phase-1 baseline: C* is one scalar per cycle, so scaling
every candidate by it cannot change their ranking. It also exposed a latent
bug — a C* of exactly 0.0 collapsed the stable sort to input order, which the
council's Λ4.3 fallback then read as "best alternative". These tests lock the
corrected causality:

  * C* is telemetry, never a ranking key (zero C* cannot scramble selection);
  * the Axiom-5.1 attention feedback reads the optimizer's own recent
    commitment (PERCEIVE runs before SELECT, so the current cycle's C* does not
    exist yet — the old read was always the default 1.0, dead code).
"""
import numpy as np
import pytest
from unittest import mock
from unittest.mock import MagicMock

from telos.core.phases.base import PhaseContext
from telos.core.phases.perceive import PerceivePhase
from telos.core.phases import perceive as perceive_mod
from telos.core.phases.select import SelectPhase
from telos.intent_ir import IntentIR


def _select_ctx(simulation_confidence: float = 1.0) -> PhaseContext:
    """Build a select-phase context with two weighted candidates.

    Args:
        simulation_confidence: per-cycle scalar applied to intent weights.

    Returns:
        A PhaseContext with a low-weight and a high-weight intent.
    """
    ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
    ctx.simulation_confidence = simulation_confidence
    ctx.intents = [
        (IntentIR(intent_type="low", confidence=0.5), 0.3),
        (IntentIR(intent_type="high", confidence=0.9), 1.0),
    ]
    return ctx


def _select_pipeline(commitment: float) -> MagicMock:
    """Build a mock pipeline whose commitment optimizer returns a fixed C*.

    Args:
        commitment: the value CommitmentScore.commitment reports.

    Returns:
        The configured MagicMock pipeline.
    """
    pipeline = MagicMock()
    score = MagicMock()
    score.commitment = commitment
    pipeline._commitment_optimizer.evaluate.return_value = score
    # Provide real numerics for the signals the commitment block compares
    # (a bare MagicMock would raise on `div > 0` and skip the computation).
    pipeline._sim_engine.rolling_diversity = 0.5
    pipeline._identity_entropy = None
    pipeline._attention_engine = None
    pipeline._identity_utility = None
    pipeline._surprise_budget = None
    pipeline._theory_builder = None
    pipeline._tripartite_u = None
    pipeline._model_competition = None
    pipeline._identity_compression = None
    pipeline._trust_manager = None
    pipeline._interpretation_engine = None
    pipeline._strategic_coherence = None
    pipeline._project_portfolio = None
    pipeline._mission_portfolio = None
    pipeline._infra_manager.cost_tracker = None
    return pipeline


class TestCommitmentIsNotARankingKey:

    def test_zero_commitment_does_not_collapse_selection(self):
        # The old code multiplied every weight by C*; at C* == 0 the stable
        # sort preserved input order, selecting 'low' (the first candidate).
        # C* is telemetry, so the highest-weighted intent must still win.
        ctx = _select_ctx()
        SelectPhase()._run_selection(_select_pipeline(0.0), ctx)
        assert ctx.selected_intent.intent_type == "high"
        weights = [w for _, w in ctx.intents]
        assert weights == sorted(weights, reverse=True)
        assert weights[0] > 0.0

    def test_commitment_is_still_recorded_as_telemetry(self):
        # De-scoped from the ranking key, C* remains the honest execution-weight
        # signal in the context (Axiom 5.1 record) — never silently dropped.
        ctx = _select_ctx()
        SelectPhase()._run_selection(_select_pipeline(0.42), ctx)
        assert ctx.commitment_score == 0.42
        assert ctx.j_term_breakdown is not None
        assert ctx.j_term_breakdown["commitment"] == 0.42


def _perceive_pipeline(recent_commitment) -> MagicMock:
    """Build the minimal mock pipeline PerceivePhase needs.

    Args:
        recent_commitment: value returned by the optimizer's property.

    Returns:
        The configured MagicMock pipeline.
    """
    pipeline = MagicMock()
    pipeline._infra_manager.consult_knowledge.return_value = {
        "adjust_risk": 0.0, "adjust_exploration": 0.0, "quality_adjustment": 0.0,
    }
    pipeline._perception_quality.assess.return_value = MagicMock(
        to_dict=lambda: {"quality_score": 0.8},
    )
    pipeline._resolution_gate.evaluate.return_value = MagicMock(
        passed=True, proxy_activated=False, reason="ok",
    )
    pipeline.config.simulator = MagicMock()
    pipeline.config.simulator.get_facts.return_value = MagicMock(
        metrics={"uncertainty": 0.1}, constraints=[],
    )
    pipeline.config.simulator.domain = "test_domain"
    pipeline.config.n_worlds = 30
    pipeline.config.adaptive_worlds_enabled = True
    pipeline.trust_manager.authorize_knowledge_release.return_value = True
    pipeline._infra_manager.policy.current.recovery_mode = False
    # Isolate the commitment feedback from the identity-collapse clamp.
    pipeline._identity_entropy = None
    pipeline._commitment_optimizer.recent_commitment = recent_commitment
    return pipeline


def _run_perceive(recent_commitment):
    """Drive PerceivePhase while capturing the attention commitment_mod.

    Args:
        recent_commitment: optimizer recent-commitment value for this run.

    Returns:
        (captured_kwargs, ctx) from the run.
    """
    captured = {}
    real = perceive_mod.allocate_attention_budget

    def spy(**kwargs):
        captured.update(kwargs)
        return real(**kwargs)

    with mock.patch.object(perceive_mod, "allocate_attention_budget", spy):
        ctx = PhaseContext(cycle_count=1, state=np.zeros(6), user_name=None)
        PerceivePhase().execute(_perceive_pipeline(recent_commitment), ctx)
    return captured, ctx


class TestCommitmentAttentionFeedback:

    def test_uses_recent_commitment_when_cycle_value_absent(self):
        # PERCEIVE runs before SELECT, so ctx.commitment_score is absent. The
        # feedback must read the optimizer's prior-cycle commitment instead of
        # a hard-coded 1.0 (the dead-code bug).
        captured, _ = _run_perceive(0.2)
        assert captured["commitment_mod"] == pytest.approx(0.2)

    def test_low_commitment_boosts_opportunity(self):
        low, low_ctx = _run_perceive(0.2)
        high, high_ctx = _run_perceive(0.9)
        assert low["commitment_mod"] == pytest.approx(0.2)
        assert high["commitment_mod"] == pytest.approx(0.9)
        assert (low_ctx.attention_allocation.opportunity_ratio
                > high_ctx.attention_allocation.opportunity_ratio)
