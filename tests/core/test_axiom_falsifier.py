"""
External Axiom Falsifier — the anti-self-reference contract.

The AxiomProver proves internal consistency. These tests prove the stronger
property: every one of the 42 axioms CAN be made to fail from the outside, so
a green prover is meaningful rather than tautological.
"""
from telos.core.axioms.registry import AXIOM_IDS
from telos.core.verifier.axiom_prover import AxiomProver
from telos.core.verifier.axiom_falsifier import AxiomFalsifier, healthy_setup


def test_healthy_setup_satisfies_all_42():
    s = healthy_setup()
    results = AxiomProver(infra_manager=s.infra, skill_library=s.sl).verify(
        s.trace, s.ctx, **s.kwargs)
    assert len(results) == 42
    assert [a for a, r in results.items() if not r["passed"]] == []


def test_axiom_ids_cover_registry_exactly():
    s = healthy_setup()
    results = AxiomProver(infra_manager=s.infra, skill_library=s.sl).verify(
        s.trace, s.ctx, **s.kwargs)
    assert sorted(results) == sorted(AXIOM_IDS)


def test_every_axiom_is_externally_falsifiable():
    report = AxiomFalsifier().run()
    assert report["healthy_passed"] is True
    assert report["healthy_failed"] == []
    assert report["unfalsifiable"] == [], (
        "these axioms could not be made to fail — they are unfalsifiable: "
        f"{report['unfalsifiable']}")
    assert sorted(report["falsifiable"]) == sorted(AXIOM_IDS)


def test_a_missing_sabotage_is_reported_unfalsifiable():
    # Drop one attacker: the falsifier must flag that axiom honestly rather
    # than assume it passes.
    from telos.core.verifier import axiom_falsifier as af
    full = af._sabotages()
    del full["2.3"]
    report = AxiomFalsifier(sabotage=full).run()
    assert "2.3" in report["unfalsifiable"]
    assert "2.3" not in report["falsifiable"]
