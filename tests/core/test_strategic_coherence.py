"""Contract tests for StrategicCoherence — does today's action increase
P(solve | project)?"""

import pytest

from telos.core.project.strategic_coherence import StrategicCoherence, CoherenceScore


class TestActionContribution:
    def test_theory_actions_direct_high_coherence(self):
        sc = StrategicCoherence()
        score = sc.evaluate("test_hypothesis", "p1", project_value=0.8,
                            project_stagnation=0)
        assert score.contribution == "direct"
        assert score.score == pytest.approx(0.9)  # value+0.2 -> clamped to 1.0

    def test_curiosity_explore_stagnant_project(self):
        sc = StrategicCoherence()
        stale = sc.evaluate("curiosity_explore", "p1", project_value=0.8,
                            project_stagnation=6)
        fresh = sc.evaluate("curiosity_explore", "p1", project_value=0.8,
                            project_stagnation=1)
        assert stale.contribution == "exploratory"
        assert stale.score == pytest.approx(0.7)
        assert fresh.score == pytest.approx(0.4)

    def test_navigation_direct_when_project_valuable(self):
        sc = StrategicCoherence()
        score = sc.evaluate("navigate", "p1", project_value=0.5,
                            project_stagnation=0)
        assert score.contribution == "direct"
        assert score.score == pytest.approx(0.6 * min(1.0, 0.7))

    def test_memory_recall_exploratory(self):
        sc = StrategicCoherence()
        score = sc.evaluate("memory_miss", "p1", project_value=0.5,
                            project_stagnation=0)
        assert score.contribution == "exploratory"
        assert score.score == pytest.approx(0.5 * min(1.0, 0.7))

    def test_unknown_action_irrelevant(self):
        sc = StrategicCoherence()
        score = sc.evaluate("random_action", "p1", project_value=0.5,
                            project_stagnation=0)
        assert score.contribution == "irrelevant"
        assert score.score == pytest.approx(0.3 * min(1.0, 0.7))

    def test_dead_project_counterproductive(self):
        sc = StrategicCoherence()
        score = sc.evaluate("test_hypothesis", "p1", project_value=0.0,
                            project_stagnation=0)
        assert score.contribution == "counterproductive"
        assert score.score == 0.0

    def test_result_is_coherence_score(self):
        sc = StrategicCoherence()
        score = sc.evaluate("propose_theory", "p1", project_value=0.5,
                            project_stagnation=0)
        assert isinstance(score, CoherenceScore)
        assert score.project_id == "p1"
        assert score.action_type == "propose_theory"


class TestHistory:
    def test_evaluate_appends_history(self):
        sc = StrategicCoherence()
        sc.evaluate("navigate", "p1", project_value=0.5, project_stagnation=0)
        assert len(sc._history) == 1
        assert sc._history[0]["project_id"] == "p1"

    def test_history_capped(self):
        sc = StrategicCoherence()
        for i in range(250):
            sc.evaluate("navigate", f"p{i % 3}", project_value=0.5,
                        project_stagnation=0)
        assert len(sc._history) == 200