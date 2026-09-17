"""Phase 5 — the evolution lever: the declared 42-axiom constitution is now
enforced-or-honestly-accounted, and governed human-gated amendment works.

Key contracts under test:
  - The axiom registry accounts exactly AXIOMS.md's declared count (42) with
    an honest enforcement status per axiom (Λ5.2 — the historical 39/42
    drift can never recur invisibly).
  - The AxiomProver verifies all 42 ids (predicates exist for every declared
    axiom; aspirational ones FAIL-CLOSED — they can never silently pass).
  - An approved amendment (human-gated) registers a new axiom in the
    executable registry; the rejected path registers nothing.
"""
import pytest

from telos.core.axioms.registry import (
    AXIOMS, AXIOM_IDS, accounted_count, accounting, enforced_ids, registry,
)
from telos.core.verifier.axiom_prover import AxiomProver
from telos.core.reasoning.relational import RelationalContext
from telos.core.reasoning.interpretation_engine import InterpretationEngine


def _ctx():
    return type("C", (), {
        "stream_activations": [],
        "governance_blocked": False,
        "resource_budgets": {"energy": {"consumed_ms": 1, "total_ms": 10}},
        "meta_cognition": None, "curiosity_state": None,
        "identity_state": None, "reflection": None,
        "error_attribution": None, "j_term_breakdown": {},
    })()


def _trace():
    return type("T", (), {
        "decision_integrity": 0.8, "council_validated": True,
        "strategic_options": ["a"], "local_optima_escape": {},
        "attention_metrics": {}, "j_term_breakdown": {
            "alignment_cost": 0.1, "opportunity_cost": 0.2},
        "causal_graph": {}, "spent_ctx_id": "x", "produced_ctx_id": "y",
    })()


class TestRegistryAccountability:
    def test_registry_accounts_exactly_42(self):
        assert accounted_count() == 42
        assert len(AXIOM_IDS) == 42
        assert len({a["id"] for a in AXIOMS}) == 42, "no duplicates"

    def test_accounting_is_honest(self):
        acct = accounting()
        assert acct["total"] == 42
        assert acct["total"] == acct["enforced"] + acct["scaffold"] + acct["aspirational"]
        assert acct["aspirational"] == 0, "4.11 graduated to scaffold"
        assert acct["scaffold"] == 2, "4.9 + 4.11 honestly scaffold"

    def test_prover_covers_all_42_ids(self):
        p = AxiomProver()
        results = p.verify(_trace(), _ctx())
        assert set(results.keys()) == set(AXIOM_IDS), \
            "prover must cover every declared axiom id"


class TestProverPredicates:
    def test_relational_scaffold_passes_when_wired(self):
        p = AxiomProver()
        r = p.verify(_trace(), _ctx(), relational_context=RelationalContext())
        assert r["4.9"]["passed"] is True

    def test_relational_scaffold_fail_closed_absent(self):
        p = AxiomProver()
        r = p.verify(_trace(), _ctx())
        assert r["4.9"]["passed"] is False, "never silently passes"

    def test_interpretation_energy_predicate(self):
        p = AxiomProver()
        r = p.verify(_trace(), _ctx(),
                     interpretation_engine=InterpretationEngine())
        assert r["6.3"]["passed"] is True
        r2 = p.verify(_trace(), _ctx())
        assert r2["6.3"]["passed"] is False

    def test_cooperative_intelligence_fail_closed_absent(self):
        p = AxiomProver()
        r = p.verify(_trace(), _ctx())
        assert r["4.11"]["passed"] is False
        assert "not evaluated (fail-closed)" in r["4.11"]["reason"]

    def test_cooperative_intelligence_passes_on_true_verdict(self):
        from types import SimpleNamespace
        p = AxiomProver()
        r = p.verify(_trace(), _ctx(),
                     cooperative_intelligence=SimpleNamespace(cooperative=True))
        assert r["4.11"]["passed"] is True
        r2 = p.verify(_trace(), _ctx(),
                      cooperative_intelligence=SimpleNamespace(cooperative=False))
        assert r2["4.11"]["passed"] is False, "presence alone must not pass"


class TestGovernedAmendment:
    def test_approved_amendment_registers_new_axiom(self):
        from telos.core.axioms.evolution import (
            AxiomEvolutionEngine, AxiomProposal, AxiomLayer,
        )
        engine = AxiomEvolutionEngine()
        n_before = accounted_count()
        proposal = engine.propose(
            name="Test Axiom", description="d", layer=AxiomLayer.NEW_LAYER,
            rationale="r", evidence=["e"], implementation_suggestion="",
        )
        new_id = proposal.id
        assert new_id.startswith("axiom_")
        assert engine.review(proposal.id, approved=True, reviewer="human") is True
        # The write-through registered the approved axiom's generated id.
        assert new_id in {a["id"] for a in AXIOMS}
        assert accounted_count() == n_before + 1
        # Cleanup so the test is repeatable.
        AXIOMS[:] = [a for a in AXIOMS if a["id"] != new_id]

    def test_rejected_amendment_registers_nothing(self):
        from telos.core.axioms.evolution import (
            AxiomEvolutionEngine, AxiomLayer,
        )
        engine = AxiomEvolutionEngine()
        n_before = accounted_count()
        proposal = engine.propose(
            name="Rejected", description="d", layer=AxiomLayer.NEW_LAYER,
            rationale="r", evidence=["e"], implementation_suggestion="",
        )
        engine.review(proposal.id, approved=False, reviewer="human")
        assert proposal.id not in {a["id"] for a in AXIOMS}
        assert accounted_count() == n_before