"""Tests for AxiomEvolutionEngine — observation-driven axiom gap detection,
manual proposal, human review workflow, and serialization summary."""

from telos.core.axioms.evolution import (
    AxiomEvolutionEngine,
    AxiomProposal,
    AxiomLayer,
)


def _observe(engine, cycle, di=0.9, md=0.1, was_blocked=False):
    return engine.observe(
        cycle=cycle,
        di=di,
        md=md,
        was_blocked=was_blocked,
        council_signals=[],
        stream_activations=[],
        identity_state={},
    )


class TestAxiomLayer:
    def test_layer_enum_values(self):
        assert AxiomLayer.ARCHITECTURAL.value == 1
        assert AxiomLayer.FEEDBACK_MEMORY.value == 2
        assert AxiomLayer.ADAPTIVE_CAPACITY.value == 3
        assert AxiomLayer.EMERGENT_INTELLIGENCE.value == 4
        assert AxiomLayer.COMMITMENT_THEORY.value == 5
        assert AxiomLayer.NEW_LAYER.value == 6


class TestProposalDefaults:
    def test_default_status_and_proposer(self):
        p = AxiomProposal(
            id="p1", name="n", description="d", layer=AxiomLayer.NEW_LAYER,
            rationale="r", evidence=["e"], implementation_suggestion="i",
        )
        assert p.status == "proposed"
        assert p.proposed_by == "AxiomEvolution"
        assert p.confidence == 0.0
        assert p.reviewed_by is None


class TestObservePatterns:
    def test_no_proposal_under_normal_conditions(self):
        engine = AxiomEvolutionEngine()
        for i in range(20):
            assert _observe(engine, i) is None

    def test_repeated_council_blocks_propose_once(self):
        engine = AxiomEvolutionEngine()
        proposals = [None] * 9
        for i in range(9):
            _observe(engine, i, was_blocked=True)
        # 10th consecutive blocked cycle triggers council-deadlock proposal
        proposal = _observe(engine, 9, was_blocked=True)
        assert proposal is not None
        assert proposal.name == "Council Deadlock Resolution"
        assert proposal.layer == AxiomLayer.FEEDBACK_MEMORY
        assert proposal.confidence == 0.7
        assert proposal.id.startswith("axiom_council_resolution_")
        assert len(proposal.evidence) == 1
        # Only proposed once — later blocked cycles do not re-propose
        for i in range(10, 15):
            assert _observe(engine, i, was_blocked=True) is None

    def test_blocked_cycles_below_10_do_not_propose(self):
        engine = AxiomEvolutionEngine()
        for i in range(9):
            _observe(engine, i, was_blocked=True)
        assert _observe(engine, 9, was_blocked=False) is None

    def test_low_di_proposes_epistemic_audit_after_10_observations(self):
        engine = AxiomEvolutionEngine()
        for i in range(10):
            assert _observe(engine, i, di=0.2) is None
        proposal = _observe(engine, 10, di=0.2)
        assert proposal is not None
        assert proposal.name == "Mandatory Epistemic Audit on Low DI"
        assert proposal.layer == AxiomLayer.ADAPTIVE_CAPACITY
        assert proposal.confidence == 0.6

    def test_low_di_with_short_history_does_not_propose(self):
        engine = AxiomEvolutionEngine()
        for i in range(5):
            assert _observe(engine, i, di=0.1) is None

    def test_observation_history_is_capped(self):
        engine = AxiomEvolutionEngine()
        for i in range(250):
            # blocked=False, di=0.9 expects no proposals; only history grows
            _observe(engine, i)
        assert len(engine._observation_history) == engine._max_observations == 200


class TestManualPropose:
    def test_propose_stores_proposal(self):
        engine = AxiomEvolutionEngine()
        p = engine.propose(
            name="Test Axiom",
            description="desc",
            layer=AxiomLayer.NEW_LAYER,
            rationale="because",
            evidence=["obs1"],
            implementation_suggestion="module.py",
            confidence=0.8,
        )
        assert isinstance(p, AxiomProposal)
        assert p.id.startswith("axiom_manual_")
        assert p.status == "proposed"
        assert p.created > 0
        assert engine.get_pending_proposals() == [p]
        assert engine.get_approved_proposals() == []

    def test_proposal_ids_monotonic(self):
        engine = AxiomEvolutionEngine()
        p1 = engine.propose("A", "d", AxiomLayer.NEW_LAYER, "r", ["e"], "s")
        p2 = engine.propose("B", "d", AxiomLayer.NEW_LAYER, "r", ["e"], "s")
        assert p1.id != p2.id
        assert engine._total_proposals == 2


class TestReview:
    def test_approve(self):
        engine = AxiomEvolutionEngine()
        p = engine.propose("A", "d", AxiomLayer.NEW_LAYER, "r", ["e"], "s")
        ok = engine.review(p.id, approved=True, reviewer="human", notes="looks good")
        assert ok is True
        assert p.status == "approved"
        assert p.reviewed_by == "human"
        assert p.review_notes == "looks good"
        assert engine.get_approved_proposals() == [p]
        assert engine.get_pending_proposals() == []

    def test_reject(self):
        engine = AxiomEvolutionEngine()
        p = engine.propose("A", "d", AxiomLayer.NEW_LAYER, "r", ["e"], "s")
        assert engine.review(p.id, approved=False, reviewer="human", notes="no") is True
        assert p.status == "rejected"

    def test_unknown_proposal_returns_false(self):
        engine = AxiomEvolutionEngine()
        assert engine.review("not_real", approved=True) is False


class TestToDict:
    def test_summary_counts(self):
        engine = AxiomEvolutionEngine()
        engine.propose("A", "d", AxiomLayer.NEW_LAYER, "r", ["e"], "s")
        engine.propose("B", "d", AxiomLayer.NEW_LAYER, "r", ["e"], "s")
        pending = engine.get_pending_proposals()[0]
        engine.review(pending.id, approved=True)
        # hygiene: evolution write-through registers into the module-global
        # AXIOMS — remove it so the constitution count stays 42 for later tests
        from telos.core.axioms.registry import AXIOMS
        AXIOMS[:] = [a for a in AXIOMS if a["id"] != pending.id]
        d = engine.to_dict()
        assert d["total_proposals"] == 2
        assert d["pending"] == 1
        assert d["approved"] == 1
        assert len(d["proposals"]) == 2
        first = d["proposals"][0]
        assert set(first) == {"id", "name", "status", "layer", "confidence"}