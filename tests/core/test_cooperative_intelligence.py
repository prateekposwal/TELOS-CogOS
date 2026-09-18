"""
Λ4.11 Cooperative Intelligence — the inequality is enforced and falsifiable.

Cooperation is justified only when the pooled collective clears the best
single agent minus the cost of the crew's disagreement. The predicate must
fail on a met-but-false verdict, not just on a missing one.
"""
from types import SimpleNamespace

from telos.core.coordination.cooperative import CooperativeCouncil, CooperativeVerdict
from telos.core.verifier.axiom_prover import AxiomProver


def _agent(di, weight=1.0):
    return {"decision_integrity": di, "weight": weight}


def test_aligned_competent_crew_cooperates():
    # Comparable, competent agents: collective ≈ best, tiny spread → justified.
    v = CooperativeCouncil().evaluate([_agent(0.9), _agent(0.88), _agent(0.87)])
    assert isinstance(v, CooperativeVerdict)
    assert v.n_agents == 3
    assert v.cooperative is True


def test_unanimous_crew_cooperates_at_the_zero_diversity_boundary():
    # REGRESSION (standard-mode Λ4.11): a unanimous crew has group ==
    # isolated and alignment_cost == 0. A strict `>` labelled maximal
    # consensus as non-cooperative (1.0 > 1.0 is False). The boundary is
    # inclusive: zero-cost unanimous cooperation is justified.
    v = CooperativeCouncil().evaluate([_agent(1.0), _agent(1.0), _agent(1.0)])
    assert v.diversity == 0.0 and v.alignment_cost == 0.0
    assert v.group_utility == v.isolated_utility == 1.0
    assert v.cooperative is True
    # Unanimity at a lower utility is equally justified (it is the lack of
    # disagreement, not the magnitude, that removes the alignment cost).
    v2 = CooperativeCouncil().evaluate([_agent(0.42), _agent(0.42)])
    assert v2.cooperative is True


def test_dominated_crew_does_not_cooperate():
    # One dominant agent, the rest far behind: pooling the others drags the
    # collective well below the best — cooperation is not justified.
    v = CooperativeCouncil().evaluate([_agent(1.0), _agent(0.05), _agent(0.05)])
    assert v.group_utility < v.isolated_utility - v.alignment_cost
    assert v.cooperative is False


def test_empty_crew_is_honest():
    v = CooperativeCouncil().evaluate([])
    assert v.n_agents == 0 and v.cooperative is False


def test_verdict_serializes():
    v = CooperativeCouncil().evaluate([_agent(0.9), _agent(0.8)])
    d = v.to_dict()
    assert set(d) == {"n_agents", "group_utility", "isolated_utility",
                      "alignment_cost", "diversity", "cooperative"}


def test_prover_4_11_passes_only_on_true_verdict():
    prover = AxiomProver()
    ctx = SimpleNamespace(cooperative_verdict={"cooperative": True})
    assert prover.verify(SimpleNamespace(), ctx)["4.11"]["passed"] is True

    ctx_bad = SimpleNamespace(cooperative_verdict={"cooperative": False})
    assert prover.verify(SimpleNamespace(), ctx_bad)["4.11"]["passed"] is False

    ctx_none = SimpleNamespace()
    assert prover.verify(SimpleNamespace(), ctx_none)["4.11"]["passed"] is False


def test_registry_marks_4_11_as_scaffold_not_aspirational():
    from telos.core.axioms.registry import AXIOMS
    entry = next(a for a in AXIOMS if a["id"] == "4.11")
    assert entry["enforcement"] == "scaffold"
    from telos.core.axioms.registry import accounting
    assert accounting()["aspirational"] == 0
