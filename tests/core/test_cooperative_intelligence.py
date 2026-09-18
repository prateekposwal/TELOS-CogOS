"""
Λ4.11 Cooperative Intelligence — the inequality is enforced and falsifiable.

Cooperation is justified only when the pooled collective clears the best
single agent *net of* the cost of the crew's disagreement
(``group − C_align >= isolated``, Λ4.11). Disagreement therefore raises the
bar; a high-diversity crew can legitimately fail. The predicate must fail on a
met-but-false verdict, not just on a missing one.
"""
import io
import os
from types import SimpleNamespace

from telos.core.coordination.cooperative import CooperativeCouncil, CooperativeVerdict
from telos.core.verifier.axiom_prover import AxiomProver


def _agent(di, weight=1.0):
    return {"decision_integrity": di, "weight": weight}


def test_zero_cost_aligned_crew_cooperates():
    # STRICT SEMANTICS (Λ4.11 "whenever alignment costs are sufficiently low"):
    # a zero-disagreement crew pays no alignment cost, so the pooled collective
    # (== the best agent) is justified. The cost is overcome trivially.
    v = CooperativeCouncil().evaluate([_agent(0.9), _agent(0.9), _agent(0.9)])
    assert isinstance(v, CooperativeVerdict)
    assert v.n_agents == 3
    assert v.alignment_cost == 0.0
    assert v.cooperative is True


def test_spread_crew_must_overcome_its_alignment_cost():
    # The strict reading turns disagreement into a real bar: the pooled mean
    # (0.883) does NOT clear the best agent (0.9) once the 0.018 alignment cost
    # is paid, so cooperation is honestly rejected. Under the old lenient form
    # (group >= isolated - cost) this passed — which is the semantic error this
    # task resolved.
    v = CooperativeCouncil().evaluate([_agent(0.9), _agent(0.88), _agent(0.87)])
    assert v.group_utility < v.isolated_utility
    assert v.group_utility - v.alignment_cost < v.isolated_utility
    assert v.cooperative is False


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
    assert v.group_utility - v.alignment_cost < v.isolated_utility
    assert v.cooperative is False


def test_empty_crew_is_honest():
    v = CooperativeCouncil().evaluate([])
    assert v.n_agents == 0 and v.cooperative is False


def test_verdict_serializes():
    v = CooperativeCouncil().evaluate([_agent(0.9), _agent(0.8)])
    d = v.to_dict()
    assert set(d) == {"n_agents", "group_utility", "isolated_utility",
                      "alignment_cost", "diversity", "di_spread",
                      "validation_disagreement", "cooperative"}


def _crewed_agent(di, validated, weight=1.0):
    """An agent as the real DistributedCouncil emits it (DI + validated)."""
    return {"decision_integrity": di, "validated": validated, "weight": weight}


def test_validation_axis_only_disagreement_is_now_visible():
    # THE regression this widening fixes: every role DI is 1.0 (di_spread 0),
    # yet one conservative lens dissents on `validated` (md_cap fired). The
    # old metric reported diversity = 0.0; the widened metric must not.
    agents = [_crewed_agent(1.0, True)] * 4 + [_crewed_agent(1.0, False)]
    v = CooperativeCouncil().evaluate(agents)
    assert v.di_spread == 0.0
    assert v.validation_disagreement > 0.0
    assert v.diversity > 0.0
    # One dissenter of five: 2 * 1/5 == 0.4.
    assert v.validation_disagreement == 0.4
    assert v.diversity == 0.4
    assert v.alignment_cost == 0.6 * 0.4
    # STRICT SEMANTICS: the crew's DI is unanimous (group == isolated == 1.0),
    # but the validation-axis disagreement imposes a real 0.24 cost that the
    # crew does not overcome — so this md-cap cycle is honestly non-cooperative.
    assert v.group_utility == v.isolated_utility == 1.0
    assert v.cooperative is False


def test_diversity_is_max_of_both_axes_and_bounded():
    # DI axis dominates.
    v = CooperativeCouncil().evaluate(
        [_crewed_agent(1.0, True), _crewed_agent(0.0, True)])
    assert v.di_spread == 1.0 and v.validation_disagreement == 0.0
    assert v.diversity == 1.0
    # Validation axis dominates.
    v2 = CooperativeCouncil().evaluate(
        [_crewed_agent(0.9, True), _crewed_agent(0.85, False)])
    assert v2.di_spread < v2.validation_disagreement
    assert v2.diversity == v2.validation_disagreement


def test_unanimous_rejection_is_not_disagreement():
    # All roles block: unanimous, not diverse. Guards against a naive
    # `1 - consensus` definition that would call agreement maximal dissent.
    v = CooperativeCouncil().evaluate(
        [_crewed_agent(0.3, False), _crewed_agent(0.3, False)])
    assert v.validation_disagreement == 0.0 and v.diversity == 0.0


def test_diversity_stays_bounded_on_perfect_split():
    # Even split on both axes can never exceed 1.0.
    v = CooperativeCouncil().evaluate([
        _crewed_agent(1.0, True), _crewed_agent(0.0, False)])
    assert v.diversity <= 1.0
    assert v.validation_disagreement == 1.0


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


# ── Semantics decision (docs vs code): isolated = max_i U_i, not ΣU_i ──────
# Λ4.11's *Meaning* column says collective optimization exceeds *isolated*
# optimization — the best a single agent can do alone. Λ6.11 uses max(U_i) for
# "the best option" and cooperative.py computes isolated_utility = max_i u_i.
# The ΣU_i notation was a slip: against the weighted-mean group utility it is
# either degenerate-false for every crew (mean ≤ max ≤ Σ for N ≥ 2) or, with a
# summed group, collapses to a zero-disagreement test — never the substantive,
# falsifiable synergy claim. These tests lock the max reading in docs AND code.

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(relpath):
    with io.open(os.path.join(_REPO, relpath), encoding="utf-8") as f:
        return f.read()


def test_axioms_md_4_11_formal_uses_max_not_sum():
    row = next(line for line in _read("telos/AXIOMS.md").splitlines()
               if line.startswith("| 4.11 |"))
    assert "max_i U_i" in row, row
    assert "\u03a3U_i" not in row and "\u03a3 U_i" not in row, row


def test_cooperative_module_docstring_matches_axioms_md():
    text = _read("telos/core/coordination/cooperative.py")
    assert "U_group \u2212 C_align \u2265 max_i U_i" in text
    assert "U_group \u2212 C_align \u2265 \u03a3 U_i" not in text


def test_isolated_utility_is_max_not_sum():
    utils = [0.9, 0.88, 0.87]
    v = CooperativeCouncil().evaluate([_agent(u) for u in utils])
    assert v.isolated_utility == max(utils)
    assert v.isolated_utility != sum(utils)


def test_sum_reading_would_be_degenerate_not_the_implemented_semantics():
    # The implemented (max) reading is a real test that can pass on a healthy
    # crew ...
    crew = [_agent(0.9), _agent(0.9), _agent(0.9)]
    v = CooperativeCouncil().evaluate(crew)
    assert v.cooperative is True
    # ... whereas the same pooled group compared against the *sum* of per-agent
    # utilities cannot: mean − cost < Σ u_i for every N ≥ 2. That is why ΣU_i
    # was the notation slip, not the predicate.
    assert v.group_utility - v.alignment_cost < sum(
        a["decision_integrity"] for a in crew)
