"""Tests for tripartite_helper — SELECT-phase tripartite uncertainty
computation from whatever data is available on the pipeline/context."""

from types import SimpleNamespace

from telos.core.phases.tripartite_helper import _compute_tripartite_from_available
from telos.core.uncertainty.tripartite import TripartiteUncertainty
from telos.core.phases.base import PhaseContext, CouncilOutput


class _FakeAttention:
    def __init__(self, divergences=None):
        self._trajectory_divergences = divergences or []


class _FakeEntropy:
    def __init__(self, collapse_rate=None):
        self.collapse_rate = collapse_rate


class _FakeCouncilVerdict:
    def __init__(self, signals=None):
        self.signals = signals or []


class _FakeSignal:
    def __init__(self, passed=True):
        self.passed = passed


def make_pipeline(attention=None, entropy=None):
    return SimpleNamespace(
        _attention_engine=attention,
        _identity_entropy=entropy,
    )


class TestComputeFromAvailable:
    def test_returns_tripartite_instance(self):
        pipeline = make_pipeline()
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        assert isinstance(u, TripartiteUncertainty)

    def test_defaults_to_zero_uncertainty(self):
        pipeline = make_pipeline()
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        assert (u.U_W, u.U_I, u.U_O) == (0.0, 0.0, 0.0)

    def test_prediction_error_from_attention_divergences(self):
        # divergences [0.5, 0.5, 0.5] -> mean 0.5 -> *0.5 = 0.25 prediction error
        pipeline = make_pipeline(attention=_FakeAttention([0.5, 0.5, 0.5]))
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        assert u.U_W == 0.25 * 0.5

    def test_attention_uses_last_three_divergences(self):
        pipeline = make_pipeline(
            attention=_FakeAttention([1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0])
        )
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        # last 3 diverge = [0, 1, 1] -> mean 2/3 -> *0.5 = 1/3
        assert u.U_W == (1 / 3) * 0.5

    def test_identity_entropy(self):
        pipeline = make_pipeline(entropy=_FakeEntropy(collapse_rate=1.0))
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        assert u.U_I == 1.0 * 0.3

    def test_non_numeric_collapse_rate_is_guarded(self):
        pipeline = make_pipeline(
            entropy=_FakeEntropy(collapse_rate="not-a-number")
        )
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        assert u.U_I == 0.0

    def test_missing_entropy_defaults_zero(self):
        pipeline = SimpleNamespace(_attention_engine=None, _identity_entropy=None)
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        assert u.U_I == 0.0

    def test_council_disagreement_from_ctx_verdict(self):
        pipeline = make_pipeline()
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        ctx.verdict = _FakeCouncilVerdict(
            [_FakeSignal(passed=True), _FakeSignal(passed=False)]
        )
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        # 1 of 2 passed -> disagreement 0.5 -> U_O = 0.5 * 0.3
        assert u.U_O == 0.15

    def test_council_from_ctx_council_verdict(self):
        pipeline = make_pipeline()
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        ctx.council = CouncilOutput(verdict=None, council_blocked=False,
                                    semantic_depths=[])
        # ctx.council.verdict is None (falsy) -> no signals collected
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        assert u.U_O == 0.0

    def test_council_signals_guard_on_missing_verdict(self):
        pipeline = make_pipeline()
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        # ctx.verdict missing entirely -> falls through cleanly
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        assert u.U_O == 0.0

    def test_full_signal_blend(self):
        pipeline = make_pipeline(
            attention=_FakeAttention([1.0, 1.0]),
            entropy=_FakeEntropy(collapse_rate=0.5),
        )
        ctx = PhaseContext(cycle_count=1, state=None, user_name=None)
        ctx.verdict = _FakeCouncilVerdict([_FakeSignal(passed=False)])
        u = _compute_tripartite_from_available(None, pipeline, ctx)
        assert u.U_W == 0.25  # pred err 0.5 -> U_W = 0.5 * 0.5
        assert u.U_I == 0.15
        assert u.U_O == 0.3  # 0 passed -> disagreement 1.0 -> *0.3