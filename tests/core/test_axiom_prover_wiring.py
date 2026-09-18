"""Axiom prover wiring/exposure contract.

Locks the fix for the 14 live wiring/exposure gaps:

  * the prover reads the pipeline's REAL live components via a canonical
    accessor when no explicit kwarg is passed (prover_input_incomplete);
  * the live SystemSelf is resolved from `infra_manager.system_self`, not the
    never-assigned `pipeline._system_self` (exposure_gap);
  * a condition that genuinely did not occur is represented as
    not-applicable, distinct from a failure (2.7, 4.11), while absence and a
    present-but-false verdict still fail (fail-closed);
  * falsifiability is preserved: nulling the kwarg on a pipeline-less setup
    still yields absence -> failure.
"""
from types import SimpleNamespace

from telos.core.verifier.axiom_prover import AxiomProver

WIRED_AXIOMS = ("4.8", "4.9", "4.10", "6.3", "6.4", "6.5",
                "6.6", "6.7", "6.8", "6.9", "6.10")


def _live_pipeline():
    """A stand-in pipeline exposing the same private attributes as the real one."""
    infra = SimpleNamespace(system_self=object())
    return SimpleNamespace(
        _model_competition=SimpleNamespace(
            dominant_model="m", compute_entropy=lambda *a, **k: 1.0),
        _interpretation_engine=object(),
        _identity_compression=object(),
        _theory_builder=object(),
        _explanation_compression=object(),
        _curiosity_drive=object(),
        _unknown_unknown_detector=object(),
        _relational_context=SimpleNamespace(relational_coherence=1.0),
        _infra_manager=infra,
    )


def test_pipeline_fallback_feeds_every_wired_component():
    prover = AxiomProver()
    results = prover.verify(SimpleNamespace(), SimpleNamespace(),
                            pipeline=_live_pipeline())
    for aid in WIRED_AXIOMS:
        assert results[aid]["passed"] is True, (aid, results[aid])


def test_system_self_resolves_from_infra_manager_not_dead_attr():
    # `pipeline._system_self` is never assigned; the live SystemSelf lives on
    # the infra manager. The prover must find it without any kwargs.
    prover = AxiomProver()
    pipe = SimpleNamespace(_infra_manager=SimpleNamespace(system_self=object()),
                           _theory_builder=object())
    results = prover.verify(SimpleNamespace(), SimpleNamespace(), pipeline=pipe)
    assert results["4.10"]["passed"] is True
    assert results["6.8"]["passed"] is True


def test_falsifiability_preserved_for_wired_components():
    # Explicit None kwargs + no pipeline -> genuine absence -> failure.
    prover = AxiomProver()
    kwargs = {name: None for name in (
        "model_competition", "relational_context", "system_self",
        "theory_builder", "interpretation_engine", "identity_compression",
        "explanation_compression", "curiosity_drive",
        "unknown_unknown_detector")}
    results = prover.verify(SimpleNamespace(), SimpleNamespace(),
                            pipeline=None, **kwargs)
    for aid in WIRED_AXIOMS:
        assert results[aid]["passed"] is False, (aid, results[aid])


def test_2_7_not_applicable_is_distinct_from_failure():
    prover = AxiomProver()
    na = prover.verify(SimpleNamespace(),
                       SimpleNamespace(error_attribution_status="not_applicable"))["2.7"]
    assert na["passed"] is True and na["not_applicable"] is True

    # A failure with no attribution and no not-applicable record still fails.
    failed = prover.verify(SimpleNamespace(), SimpleNamespace())["2.7"]
    assert failed["passed"] is False and failed["not_applicable"] is False

    # A stored attribution is the verified path.
    ok = prover.verify(SimpleNamespace(),
                       SimpleNamespace(error_attribution={"primary": "council"}))["2.7"]
    assert ok["passed"] is True and ok["not_applicable"] is False


def test_4_11_not_applicable_is_distinct_from_failure():
    prover = AxiomProver()
    na = prover.verify(SimpleNamespace(), SimpleNamespace(
        cooperative_verdict={"cooperative": None, "not_applicable": True}))["4.11"]
    assert na["passed"] is True and na["not_applicable"] is True

    # Present-but-false inequality fails.
    bad = prover.verify(SimpleNamespace(), SimpleNamespace(
        cooperative_verdict={"cooperative": False}))["4.11"]
    assert bad["passed"] is False and bad["not_applicable"] is False

    # Absent verdict fails (fail-closed).
    absent = prover.verify(SimpleNamespace(), SimpleNamespace())["4.11"]
    assert absent["passed"] is False


def test_4_5_performed_check_without_escape_passes():
    prover = AxiomProver()
    checked = prover.verify(SimpleNamespace(
        local_optima_escape={"checked": True, "escaped": False}),
        SimpleNamespace())["4.5"]
    assert checked["passed"] is True and checked["escaped"] is False

    escaped = prover.verify(SimpleNamespace(
        local_optima_escape={"checked": True, "escaped": True}),
        SimpleNamespace())["4.5"]
    assert escaped["passed"] is True and escaped["escaped"] is True

    absent = prover.verify(SimpleNamespace(local_optima_escape=None),
                           SimpleNamespace())["4.5"]
    assert absent["passed"] is False
