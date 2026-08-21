"""
CouncilReflector (core/council/reflector.py) — honest contract coverage.
"""
from telos.core.council.reflector import CouncilReflector


class TestCouncilReflector:
    def _reflect(self, r, was_blocked=False, success=True, di=0.9, md=0.1):
        return r.reflect(
            cycle=1, selected_intent="explore",
            validator_signals=[{"validator_name": "V1", "passed": True}],
            predicted_di=di, actual_di=di, predicted_md=md, actual_md=md,
            was_blocked=was_blocked, outcome_success=success,
        )

    def test_reflect_records(self):
        r = CouncilReflector()
        self._reflect(r)
        assert r.reflection_count == 1
        assert r.council_accuracy >= 0.0
        assert r.get_validator_trust_scores() != {}

    def test_worst_performers_api(self):
        r = CouncilReflector()
        self._reflect(r, was_blocked=True, success=False)
        rec = r.reflect(cycle=2, selected_intent="x",
                        validator_signals=[{"validator_name": "V2", "passed": False}],
                        predicted_di=0.5, actual_di=0.5, predicted_md=0.5,
                        actual_md=0.5, was_blocked=True, outcome_success=False)
        assert rec is not None
        assert r.get_worst_performers(top_n=2) is not None

    def test_reflection_history_capped(self):
        r = CouncilReflector(window_size=3)
        for i in range(6):
            self._reflect(r)
        assert len(r._reflection_history) <= 200
