"""
Selection policy (A/B) — bounded, gated, and default-inert.

`selection_policy="control"` must be byte-identical to before (no mission
hook, no damping). With a mission-progress hook, `mission_progress` damps the
inquiry blend by the best executable candidate's progress, bounded to 0.6.
`mission_progress_readiness` only damps when a high-confidence executable
candidate exists (enough information to act).
"""
from types import SimpleNamespace

from telos.core.phases.select import SelectPhase
from telos.intent_ir import IntentIR


def _pipe(policy, hook=None):
    return SimpleNamespace(
        config=SimpleNamespace(selection_policy=policy),
        _mission_progress_fn=hook,
    )


def _ctx(intents):
    return SimpleNamespace(
        cycle_count=1, state=None, intents=intents,
        _inquiry_blend_effective=None,
    )


def _exec_intent(conf=0.9):
    return IntentIR(intent_type="plan_trajectory", confidence=conf)


def _inquiry_intent():
    return IntentIR(intent_type="blended_inquiry", confidence=0.9)


def test_control_is_inert():
    sp = SelectPhase()
    ctx = _ctx([(_exec_intent(), 0.5)])
    out = sp._apply_selection_policy(_pipe("control", lambda s, i: 0.9), ctx, 0.8)
    assert out == 0.8
    assert ctx._inquiry_blend_effective == 0.8


def test_mission_progress_damps_blend_bounded():
    sp = SelectPhase()
    ctx = _ctx([(_exec_intent(), 0.5)])
    out = sp._apply_selection_policy(
        _pipe("mission_progress", lambda s, i: 1.0), ctx, 0.8)
    assert abs(out - 0.8 * (1 - 0.6)) < 1e-9  # 0.32
    assert ctx._inquiry_blend_effective == out


def test_no_hook_is_inert():
    sp = SelectPhase()
    ctx = _ctx([(_exec_intent(), 0.5)])
    assert sp._apply_selection_policy(_pipe("mission_progress", None), ctx, 0.8) == 0.8


def test_all_inquiry_candidates_are_inert():
    sp = SelectPhase()
    ctx = _ctx([(_inquiry_intent(), 0.5)])
    out = sp._apply_selection_policy(
        _pipe("mission_progress", lambda s, i: 0.9), ctx, 0.8)
    assert out == 0.8


def test_readiness_requires_high_confidence_executable():
    sp = SelectPhase()
    hook = lambda s, i: 0.9  # noqa: E731
    # low-confidence executable → not ready → inert
    ctx = _ctx([(_exec_intent(conf=0.3), 0.5)])
    assert sp._apply_selection_policy(
        _pipe("mission_progress_readiness", hook), ctx, 0.8) == 0.8
    # high-confidence executable → ready → damped
    ctx2 = _ctx([(_exec_intent(conf=0.9), 0.5)])
    assert sp._apply_selection_policy(
        _pipe("mission_progress_readiness", hook), ctx2, 0.8) < 0.8


def test_zero_progress_is_inert():
    sp = SelectPhase()
    ctx = _ctx([(_exec_intent(), 0.5)])
    out = sp._apply_selection_policy(
        _pipe("mission_progress", lambda s, i: 0.0), ctx, 0.8)
    assert out == 0.8
