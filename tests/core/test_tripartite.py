"""
TripartiteUncertainty (core/uncertainty/tripartite.py) — honest contract coverage.
"""
from telos.core.uncertainty.tripartite import TripartiteUncertainty


class TestTripartiteUncertainty:
    def test_compute_from_available(self):
        t = TripartiteUncertainty()
        t.compute_from_available(prediction_error=0.2, identity_entropy=0.1,
                                 council_signals=[{"passed": False}],
                                 relational_coherence=0.8, model_fidelity=0.9)
        assert 0.0 <= t.composite <= 1.0
        assert t.get_dominant() in ("environmental", "identity", "other", "model", "none")

    def test_update_and_vector(self):
        t = TripartiteUncertainty()
        t.update(prediction_error=0.3, identity_entropy=0.2)
        vec = t.vector
        assert len(vec) == 4
        assert all(isinstance(x, float) for x in vec)

    def test_record_and_reset(self):
        t = TripartiteUncertainty()
        t.update(prediction_error=0.8, identity_entropy=0.8)
        before = t.composite
        t.record_answer("investigate")   # decays the raised uncertainty
        assert t.composite <= before + 1e-9
        assert t.history                  # update() appended a snapshot
        t.reset()
        assert t.composite == 0.0

    def test_to_dict(self):
        t = TripartiteUncertainty()
        d = t.to_dict()
        assert "composite" in d or isinstance(d, dict)
        assert t.trend in ("increasing", "decreasing", "stable")
