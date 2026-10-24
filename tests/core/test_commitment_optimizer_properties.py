"""
Hypothesis property-based tests for the CommitmentOptimizer / CommitmentScore
unified cognitive functional (Λ5.1).

Properties:
  P1 (reward monotonicity): raising expected_reward never lowers commitment.
  P2 (cost monotonicity): raising any cost term never raises commitment.
  P3 (bounds): commitment is always in [0, 1].
  P4 (gamma discount): for positive reward, average per-horizon term decreases
     with horizon (gamma < 1 discounts each future term).
  P5 (suppressed/full consistency): is_suppressed ⟺ commitment < 0.3;
     is_full ⟺ commitment > 0.8.
"""
from hypothesis import given, strategies as st, settings, HealthCheck
import numpy as np

from telos.core.decision.commitment_optimizer import (
    CommitmentScore, CommitmentOptimizer,
)


# ── strategies ──────────────────────────────────────────────────────────────

_reward = st.floats(allow_nan=False, allow_infinity=False, min_value=-10.0, max_value=10.0)
_cost = st.floats(allow_nan=False, allow_infinity=False, min_value=0.0, max_value=10.0)
_gamma = st.floats(allow_nan=False, allow_infinity=False, min_value=0.0, max_value=0.999)
_horizon = st.integers(min_value=1, max_value=8)


def _score(**kw):
    base = dict(
        expected_reward=1.0, maintenance_cost=0.0, recovery_cost=0.0,
        identity_cost=0.0, future_option_value=0.0, counterfactual_diversity=0.0,
        prediction_error=0.0, information_gain=0.0, theory_gain=0.0,
        uncertainty_bonus=0.0, alignment_cost=0.0, interpretation_energy=0.0,
        opportunity_cost=0.0, project_coherence_gain=0.0, aesthetic_value=0.0,
        gamma=0.95, horizon=1,
    )
    base.update(kw)
    return CommitmentScore(**base)


@settings(max_examples=200, suppress_health_check=list(HealthCheck))
@given(
    r1=_reward, r2=_reward,
    m=_cost, rec=_cost, i=_cost, align=_cost, opp=_cost,
    pe=_cost, ie=_cost,
    ig=st.floats(0.0, 0.5), tg=st.floats(0.0, 0.5),
    au=st.floats(0.0, 0.3), cf=st.floats(0.0, 0.5),
    pg=st.floats(0.0, 0.5), av=st.floats(0.0, 0.3),
)
def test_reward_monotonicity(r1, r2, m, rec, i, align, opp, pe, ie, ig, tg, au, cf, pg, av):
    """P1: higher expected_reward ⇒ higher-or-equal commitment."""
    if r2 < r1:
        r1, r2 = r2, r1  # ensure r2 >= r1
    low = _score(expected_reward=r1, maintenance_cost=m, recovery_cost=rec,
                 identity_cost=i, alignment_cost=align, opportunity_cost=opp,
                 prediction_error=pe, interpretation_energy=ie,
                 information_gain=ig, theory_gain=tg, uncertainty_bonus=au,
                 counterfactual_diversity=cf, project_coherence_gain=pg,
                 aesthetic_value=av)
    high = _score(expected_reward=r2, maintenance_cost=m, recovery_cost=rec,
                  identity_cost=i, alignment_cost=align, opportunity_cost=opp,
                  prediction_error=pe, interpretation_energy=ie,
                  information_gain=ig, theory_gain=tg, uncertainty_bonus=au,
                  counterfactual_diversity=cf, project_coherence_gain=pg,
                  aesthetic_value=av)
    assert high.commitment >= low.commitment - 1e-9


@settings(max_examples=200, suppress_health_check=list(HealthCheck))
@given(
    r=_reward,
    m1=_cost, m2=_cost, rec1=_cost, rec2=_cost, i1=_cost, i2=_cost,
    align1=_cost, align2=_cost, opp1=_cost, opp2=_cost,
    pe1=_cost, pe2=_cost, ie1=_cost, ie2=_cost,
)
def test_cost_monotonicity(r, m1, m2, rec1, rec2, i1, i2, align1, align2,
                           opp1, opp2, pe1, pe2, ie1, ie2):
    """P2: higher costs ⇒ lower-or-equal commitment (each cost term independently)."""
    base = dict(expected_reward=r)
    high_m = _score(**base, maintenance_cost=max(m1, m2))
    low_m = _score(**base, maintenance_cost=min(m1, m2))
    assert low_m.commitment >= high_m.commitment - 1e-9

    high_rec = _score(**base, recovery_cost=max(rec1, rec2))
    low_rec = _score(**base, recovery_cost=min(rec1, rec2))
    assert low_rec.commitment >= high_rec.commitment - 1e-9

    high_i = _score(**base, identity_cost=max(i1, i2))
    low_i = _score(**base, identity_cost=min(i1, i2))
    assert low_i.commitment >= high_i.commitment - 1e-9

    high_align = _score(**base, alignment_cost=max(align1, align2))
    low_align = _score(**base, alignment_cost=min(align1, align2))
    assert low_align.commitment >= high_align.commitment - 1e-9

    high_opp = _score(**base, opportunity_cost=max(opp1, opp2))
    low_opp = _score(**base, opportunity_cost=min(opp1, opp2))
    assert low_opp.commitment >= high_opp.commitment - 1e-9

    high_pe = _score(**base, prediction_error=max(pe1, pe2))
    low_pe = _score(**base, prediction_error=min(pe1, pe2))
    assert low_pe.commitment >= high_pe.commitment - 1e-9

    high_ie = _score(**base, interpretation_energy=max(ie1, ie2))
    low_ie = _score(**base, interpretation_energy=min(ie1, ie2))
    assert low_ie.commitment >= high_ie.commitment - 1e-9


@settings(max_examples=200, suppress_health_check=list(HealthCheck))
@given(
    r=_reward, m=_cost, rec=_cost, i=_cost, fov=_cost, cf=_cost,
    pe=_cost, ig=st.floats(0.0, 0.5), tg=st.floats(0.0, 0.5),
    au=st.floats(0.0, 0.3), align=_cost, ie=_cost, opp=_cost,
    pg=st.floats(0.0, 0.5), av=st.floats(0.0, 0.3),
)
def test_commitment_bounds(r, m, rec, i, fov, cf, pe, ig, tg, au, align, ie, opp, pg, av):
    """P3: commitment is always within [0, 1]."""
    s = _score(expected_reward=r, maintenance_cost=m, recovery_cost=rec,
               identity_cost=i, future_option_value=fov,
               counterfactual_diversity=cf, prediction_error=pe,
               information_gain=ig, theory_gain=tg, uncertainty_bonus=au,
               alignment_cost=align, interpretation_energy=ie,
               opportunity_cost=opp, project_coherence_gain=pg,
               aesthetic_value=av)
    assert 0.0 <= s.commitment <= 1.0
    assert 0.0 <= s.to_dict()["commitment"] <= 1.0


@settings(max_examples=100, suppress_health_check=list(HealthCheck))
@given(r=_reward, gamma=_gamma, h1=_horizon, h2=_horizon)
def test_gamma_discount_average_decreases(r, gamma, h1, h2):
    """P4: for positive reward, average per-term discounted_reward/horizon
    decreases with horizon (gamma < 1 discounts future terms more heavily)."""
    if h2 < h1:
        h1, h2 = h2, h1
    opt = CommitmentOptimizer(gamma=gamma)
    d1 = opt._compute_discounted_reward(r, h1)
    d2 = opt._compute_discounted_reward(r, h2)
    # Average per-term: for gamma < 1, later terms contribute less, so average drops
    if r > 0:
        assert (d2 / h2) <= (d1 / h1) + 1e-9
    elif r < 0:
        assert (d2 / h2) >= (d1 / h1) - 1e-9


@settings(max_examples=200, suppress_health_check=list(HealthCheck))
@given(
    r=_reward, m=_cost, rec=_cost, i=_cost, fov=_cost, cf=_cost,
    pe=_cost, ig=st.floats(0.0, 0.5), tg=st.floats(0.0, 0.5),
    au=st.floats(0.0, 0.3), align=_cost, ie=_cost, opp=_cost,
    pg=st.floats(0.0, 0.5), av=st.floats(0.0, 0.3),
)
def test_suppressed_full_consistency(r, m, rec, i, fov, cf, pe, ig, tg, au,
                                     align, ie, opp, pg, av):
    """P5: is_suppressed ⟺ commitment < 0.3; is_full ⟺ commitment > 0.8."""
    s = _score(expected_reward=r, maintenance_cost=m, recovery_cost=rec,
               identity_cost=i, future_option_value=fov,
               counterfactual_diversity=cf, prediction_error=pe,
               information_gain=ig, theory_gain=tg, uncertainty_bonus=au,
               alignment_cost=align, interpretation_energy=ie,
               opportunity_cost=opp, project_coherence_gain=pg,
               aesthetic_value=av)
    assert (s.is_suppressed) == (s.commitment < 0.3)
    assert (s.is_full) == (s.commitment > 0.8)


@settings(max_examples=100, suppress_health_check=list(HealthCheck))
@given(
    r=_reward, m=_cost, rec=_cost, i=_cost,
    horizon=_horizon,
    itype=st.sampled_from(["navigate", "reflex", "curiosity_explore", "halt"]),
)
def test_optimizer_evaluate_deterministic_and_bounded(r, m, rec, i, horizon, itype):
    """The optimizer's evaluate() is deterministic and returns a bounded score."""
    opt = CommitmentOptimizer(gamma=0.95)
    s1 = opt.evaluate(expected_reward=r, maintenance_cost=m, recovery_cost=rec,
                      identity_cost=i, horizon=horizon)
    s2 = opt.evaluate(expected_reward=r, maintenance_cost=m, recovery_cost=rec,
                      identity_cost=i, horizon=horizon)
    assert s1.commitment == s2.commitment
    assert 0.0 <= s1.commitment <= 1.0
    # admissibility gate: reflex/halt always admissible
    assert opt.is_trajectory_admissible(itype) is True or itype not in ("reflex", "halt")