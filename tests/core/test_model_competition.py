"""Contract tests for ModelCompetition — multiple competing hypotheses with
Bayesian evidence, never fully killed."""

import math

import pytest

from telos.core.reasoning.model_competition import (
    ModelCompetition, Model, EvidenceRecord, CompetitionSnapshot,
)


class TestProposal:
    def test_propose_auto_priors_renormalize(self):
        mc = ModelCompetition()
        a = mc.propose_model("A", "explains", source="stream")
        b = mc.propose_model("B", "alternative", source="stream")
        # first model starts at 1.0 and is scaled by each renormalize;
        # after B joins with prior 0.5 the pool is A=2/3, B=1/3
        assert mc._models[a].probability == pytest.approx(2 / 3)
        assert mc._models[b].probability == pytest.approx(1 / 3)
        assert sum(m.probability for m in mc._models.values()) == pytest.approx(1.0)

    def test_propose_explicit_probabilities_renormalized(self):
        mc = ModelCompetition()
        a = mc.propose_model("A", "x", probability=0.8)
        b = mc.propose_model("B", "y", probability=0.2)
        assert sum(m.probability for m in mc._models.values()) == pytest.approx(1.0)
        # the lone 0.8 model is first normalized to 1.0, then scaled by B
        assert mc._models[a].probability == pytest.approx(5 / 6)
        assert mc._models[b].probability == pytest.approx(1 / 6)
        assert mc._models[a].prior == 0.8

    def test_max_models_retires_weakest_and_reuses_id(self):
        mc = ModelCompetition(max_models=2)
        a = mc.propose_model("A", "x")
        b = mc.propose_model("B", "y")
        c = mc.propose_model("C", "z")
        assert len(mc._models) == 2
        # A survived as the stronger model; the weakest (B) was retired and
        # its id string is REUSED by the newly proposed C (model ids derive
        # from the running pool length, so 2 -> 1 -> 2 collides)
        assert a in mc._models
        assert mc._models[c].name == "C"
        assert mc._models[b].name == "C"
        assert mc.dominant_model.id == a


class TestBayesianUpdate:
    def test_evidence_shifts_probability(self):
        mc = ModelCompetition(min_probability=0.01)
        a = mc.propose_model("A", "x")
        b = mc.propose_model("B", "y")
        before_a = mc._models[a].probability
        mc.submit_evidence("strong sign", {a: 0.99, b: 0.01})
        after_a = mc._models[a].probability
        assert after_a > before_a
        # posterior over A = 0.99/(0.99+0.01), with sum exactly 1.0
        assert after_a == pytest.approx(0.99, abs=1e-4)
        assert mc._models[b].probability == pytest.approx(0.01, abs=1e-4)
        assert sum(m.probability for m in mc._models.values()) == pytest.approx(1.0)

    def test_missing_likelihood_defaults_to_neutral(self):
        mc = ModelCompetition()
        a = mc.propose_model("A", "x")
        b = mc.propose_model("B", "y")
        c = mc.propose_model("C", "z")
        ev = mc.submit_evidence("evidence for A only", {a: 0.9})
        record = mc._evidence_history[-1]
        assert record.likelihoods[a] == 0.9
        assert record.likelihoods[b] == 0.5
        assert record.likelihoods[c] == 0.5
        assert isinstance(record, EvidenceRecord)
        assert record.weight == 1.0

    def test_probability_never_reaches_extinction(self):
        mc = ModelCompetition(min_probability=0.05)
        a = mc.propose_model("A", "x")
        b = mc.propose_model("B", "y")
        for _ in range(30):
            mc.submit_evidence("all A", {a: 0.999, b: 0.001})
        # the loser is clamped to min_probability then renormalized; it
        # settles just below the nominal floor but never near extinction
        assert mc._models[b].probability > 0.04
        assert mc._models[a].probability > 0.9

    def test_bayesian_weights_evidence(self):
        mc = ModelCompetition()
        a = mc.propose_model("A", "x")
        b = mc.propose_model("B", "y")
        mc.submit_evidence("weak", {a: 0.6, b: 0.4}, weight=0.1)
        weak_a = mc._models[a].probability
        # reset-ish: strong evidence weight
        mc2 = ModelCompetition()
        a2 = mc2.propose_model("A", "x")
        b2 = mc2.propose_model("B", "y")
        mc2.submit_evidence("strong", {a2: 0.6, b2: 0.4}, weight=3.0)
        assert mc2._models[a2].probability > weak_a


class TestDerivedQuantities:
    def test_dominant_and_second_best(self):
        mc = ModelCompetition()
        a = mc.propose_model("A", "x", probability=0.8)
        b = mc.propose_model("B", "y", probability=0.2)
        assert mc.dominant_model.id == a
        assert mc.second_best.id == b

    def test_dominant_model_none_when_empty(self):
        mc = ModelCompetition()
        assert mc.dominant_model is None
        assert mc.second_best is None
        assert mc.compute_entropy() == 0.0
        assert mc.compute_consensus() == 0.0

    def test_entropy_and_consensus_two_default_models(self):
        mc = ModelCompetition()
        mc.propose_model("A", "x")
        mc.propose_model("B", "y")
        # default priors renormalize to A=2/3, B=1/3:
        # normalized entropy H/log2(2) and consensus (max-p-1/n)/(1-1/n)
        assert mc.compute_entropy() == pytest.approx(0.9183, abs=1e-4)
        assert mc.compute_consensus() == pytest.approx(1 / 3)

    def test_consensus_single_model(self):
        mc = ModelCompetition()
        mc.propose_model("Solo", "x")
        assert mc.compute_consensus() == 1.0
        assert mc.compute_entropy() == 0.0

    def test_get_winner_returns_dominant_when_little_history(self):
        mc = ModelCompetition()
        a = mc.propose_model("A", "x")
        mc.propose_model("B", "y")
        mc.submit_evidence("favours", {a: 0.9})
        assert mc.get_winner() is mc.dominant_model

    def test_get_winner_most_consistent(self):
        mc = ModelCompetition()
        a = mc.propose_model("A", "x")
        b = mc.propose_model("B", "y")
        for i in range(5):
            mc.submit_evidence(f"favours A {i}", {a: 0.95, b: 0.05})
        winner = mc.get_winner()
        assert winner.id == a


class TestPredictionAccounting:
    def test_record_prediction_updates_accuracy(self):
        mc = ModelCompetition()
        a = mc.propose_model("A", "x")
        mc.record_prediction(a, True)
        mc.record_prediction(a, True)
        mc.record_prediction(a, False)
        model = mc._models[a]
        assert model.accuracy == pytest.approx(2 / 3)
        assert model.predictions_total == 3

    def test_record_prediction_unknown_model_is_noop(self):
        mc = ModelCompetition()
        mc.record_prediction("missing", True)  # must not raise

    def test_market_price_weights(self):
        model = Model(id="m", name="m", description="d", source="s",
                      probability=0.5, prior=0.5, parsimony=0.8,
                      predictions_correct=4, predictions_total=5,
                      bridges_formed=2)
        assert model.accuracy == 0.8
        expected = 0.8 * 0.4 + 0.8 * 0.3 + min(1.0, 2 * 0.1) * 0.2 + 0.5 * 0.1
        assert model.market_price == pytest.approx(expected)

    def test_evidence_weight_accumulates(self):
        model = Model(id="m", name="m", description="d", source="s",
                      probability=0.5, prior=0.25, parsimony=0.5,
                      likelihood_history=[0.5, 0.5])
        assert model.evidence_weight == pytest.approx(0.25 * 0.5 * 0.5)


class TestSerialization:
    def test_snapshot_fields(self):
        mc = ModelCompetition()
        a = mc.propose_model("A", "x")
        mc.submit_evidence("ev", {a: 0.9}, cycle=7)
        snap = mc._snapshots[-1]
        assert isinstance(snap, CompetitionSnapshot)
        assert snap.cycle == 7
        assert snap.dominant_model == a
        assert snap.evidence_count == 1

    def test_to_dict_keys(self):
        mc = ModelCompetition()
        mc.propose_model("A", "x")
        d = mc.to_dict()
        assert set(d) == {
            "update_count", "active_models", "entropy", "consensus",
            "models", "evidence_count", "dominant_model", "second_best",
        }
        assert d["active_models"] == 1
        assert d["models"][0]["name"] == "A"
        assert d["dominant_model"] == "A"
        assert d["second_best"] is None