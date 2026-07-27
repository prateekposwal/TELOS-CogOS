"""Smoke tests for all 19 v2/v2.5 modules — verify instantiation and basic methods don't crash."""

import math


# ============================
# v2 Modules (9)
# ============================

class TestCouncilReflectorSmoke:
    def test_instantiate(self):
        from telos.core.council.reflector import CouncilReflector
        cr = CouncilReflector(window_size=5)
        assert cr.reflection_count == 0

    def test_reflect(self):
        from telos.core.council.reflector import CouncilReflector
        cr = CouncilReflector(window_size=5)
        result = cr.reflect(
            cycle=0, selected_intent="move_north",
            validator_signals={}, predicted_di=0.8, actual_di=0.7,
            predicted_md=0.2, actual_md=0.3,
            was_blocked=False, outcome_success=True,
        )
        assert result.cycle == 0

    def test_validator_stats(self):
        from telos.core.council.reflector import CouncilReflector
        cr = CouncilReflector(window_size=5)
        adj = cr.get_validator_confidence_adjustments()
        assert isinstance(adj, dict)
        scores = cr.get_validator_trust_scores()
        assert isinstance(scores, dict)
        worst = cr.get_worst_performers(top_n=2)
        assert isinstance(worst, list)


class TestErrorAttributionSmoke:
    def test_instantiate(self):
        from telos.core.meta.error_attribution import ErrorAttributionEngine
        eae = ErrorAttributionEngine()
        assert eae.total_attributions == 0

    def test_attribute(self):
        from telos.core.meta.error_attribution import ErrorAttributionEngine
        eae = ErrorAttributionEngine()
        result = eae.attribute(
            cycle=0, predicted_state={"x": 1.0}, actual_state={"x": 2.0},
            was_blocked=False, should_have_blocked=False,
            council_signals={}, simulation_error=0.3,
            perception_quality=0.9, action_error=0.0, intent_type="move",
        )
        assert result.cycle == 0
        assert eae.total_attributions > 0
        health = eae.get_subsystem_health()
        assert isinstance(health, dict)
        worst = eae.get_most_erratic_subsystem()
        assert worst is None or isinstance(worst, tuple)

    def test_to_dict(self):
        from telos.core.meta.error_attribution import ErrorAttributionEngine
        eae = ErrorAttributionEngine()
        eae.attribute(0, {}, {}, False, False, {}, 0.1, 0.9, 0.0, "test")
        d = eae.to_dict()
        assert "total_attributions" in d


class TestAssumptionAuditorSmoke:
    def test_instantiate(self):
        from telos.core.curiosity.assumption_auditor import AssumptionAuditor
        aa = AssumptionAuditor()
        assert len(aa.active_assumptions) > 0

    def test_register_and_select(self):
        from telos.core.curiosity.assumption_auditor import AssumptionAuditor
        aa = AssumptionAuditor()
        aid = aa.register_assumption(description="users always provide valid input",
                                      type="domain")
        assert isinstance(aid, str)
        selected = aa.select_assumption_to_audit(cycle=5)
        assert selected is None or hasattr(selected, 'id')

    def test_should_audit(self):
        from telos.core.curiosity.assumption_auditor import AssumptionAuditor
        aa = AssumptionAuditor()
        result = aa.should_audit(cycle=100, curiosity_level=0.8)
        assert isinstance(result, bool)

    def test_to_dict(self):
        from telos.core.curiosity.assumption_auditor import AssumptionAuditor
        aa = AssumptionAuditor()
        d = aa.to_dict()
        assert isinstance(d, dict)


class TestIdentityUtilitySmoke:
    def test_instantiate(self):
        from telos.core.identity.utility_profiles import IdentityUtilityEngine
        iue = IdentityUtilityEngine()
        assert iue.active_profile is not None

    def test_register_and_compute(self):
        from telos.core.identity.utility_profiles import (
            IdentityUtilityEngine, UtilityProfile,
        )
        iue = IdentityUtilityEngine()
        iue.register_profile(UtilityProfile(
            name="explorer", description="explores",
            weights={"exploration": 1.0, "safety": 0.0},
            identity_markers=["explorer"],
        ))
        iue.register_profile(UtilityProfile(
            name="guardian", description="guards",
            weights={"exploration": 0.0, "safety": 1.0},
            identity_markers=["guardian"],
        ))
        iue.select_profile(identity_markers=["explorer"])
        u, profile = iue.compute_utility(dimension_scores={"exploration": 0.8, "safety": 0.2})
        assert isinstance(u, (int, float))
        assert not math.isnan(u)

    def test_to_dict(self):
        from telos.core.identity.utility_profiles import (
            IdentityUtilityEngine, UtilityProfile,
        )
        iue = IdentityUtilityEngine()
        iue.register_profile(UtilityProfile(
            name="p1", description="test",
            weights={"a": 1.0}, identity_markers=["p1"],
        ))
        d = iue.to_dict()
        assert "active_profile" in d


class TestIntrospectionSchedulerSmoke:
    def test_instantiate(self):
        from telos.core.introspection.scheduler import IntrospectionScheduler
        sch = IntrospectionScheduler()
        assert sch is not None

    def test_should_run_and_introspect(self):
        from telos.core.introspection.scheduler import IntrospectionScheduler
        sch = IntrospectionScheduler()
        due = sch.get_due_tiers(cycle=1)
        assert isinstance(due, list)
        result = sch.introspect(cycle=1)
        assert isinstance(result, list)

    def test_configure(self):
        from telos.core.introspection.scheduler import IntrospectionScheduler
        from telos.core.introspection.scheduler import IntrospectionTier
        sch = IntrospectionScheduler()
        sch.configure_tier(tier=IntrospectionTier.CYCLE, interval=50)
        assert sch.should_run(tier=IntrospectionTier.CYCLE, cycle=50)

    def test_to_dict(self):
        from telos.core.introspection.scheduler import IntrospectionScheduler
        sch = IntrospectionScheduler()
        d = sch.to_dict()
        assert isinstance(d, dict)


class TestRegretMemorySmoke:
    def test_instantiate(self):
        from telos.core.memory.regret_memory import RegretMemory
        rm = RegretMemory(max_records=10)
        assert rm.record_count == 0

    def test_record_and_query(self):
        from telos.core.memory.regret_memory import RegretMemory
        rm = RegretMemory(max_records=10)
        record = rm.record_decision(
            cycle=0, chosen_intent="move_north", chosen_score=0.8,
            chosen_outcome=True,
            counterfactual_options=[
                {"intent": "move_east", "estimated_score": 0.6},
            ],
        )
        assert rm.record_count == 1
        sim = rm.query_similar_contexts(context_hash="test", top_k=1)
        assert isinstance(sim, list)
        regret, count = rm.get_regret_by_type("exploration")
        assert isinstance(regret, float)
        assert isinstance(count, int)

    def test_blind_spots(self):
        from telos.core.memory.regret_memory import RegretMemory
        rm = RegretMemory(max_records=10)
        spots = rm.get_blind_spots()
        assert isinstance(spots, list)


class TestTheoryBuilderSmoke:
    def test_instantiate(self):
        from telos.core.reasoning.theory_builder import TheoryBuilder
        tb = TheoryBuilder(min_experiences_for_pattern=2)
        assert tb.total_experiences == 0

    def test_add_and_build(self):
        from telos.core.reasoning.theory_builder import TheoryBuilder
        tb = TheoryBuilder(min_experiences_for_pattern=1, min_patterns_for_hypothesis=1,
                          min_tests_for_theory=10, theory_confidence_threshold=0.99)
        eid = tb.add_experience(context={"x": 1.0}, action="go", outcome=True)
        assert isinstance(eid, str)
        eid2 = tb.add_experience(context={"x": 2.0}, action="go", outcome=True)
        assert tb.total_experiences >= 2
        clusters = tb.cluster()
        assert isinstance(clusters, (list, type(None)))
        hypotheses = tb.hypothesize()
        assert isinstance(hypotheses, (list, type(None)))

    def test_build_full(self):
        from telos.core.reasoning.theory_builder import TheoryBuilder
        tb = TheoryBuilder(min_experiences_for_pattern=1, min_patterns_for_hypothesis=1,
                          min_tests_for_theory=1, theory_confidence_threshold=0.0)
        for i in range(5):
            tb.add_experience(context={"x": float(i)}, action="go", outcome=True)
        clusters = tb.cluster()
        hypotheses = tb.hypothesize()
        promoted = tb.promote()
        assert promoted is None or isinstance(promoted, list)
        result = tb.build(context={"x": 1.0}, action="go", outcome=True)
        assert isinstance(result, dict)


class TestAxiomEvolutionSmoke:
    def test_instantiate(self):
        from telos.core.axioms.evolution import AxiomEvolutionEngine
        aee = AxiomEvolutionEngine()
        assert aee is not None

    def test_observe_and_propose(self):
        from telos.core.axioms.evolution import AxiomEvolutionEngine
        from telos.core.axioms.evolution import AxiomLayer
        aee = AxiomEvolutionEngine()
        obs = aee.observe(cycle=0, di=0.8, md=0.2, was_blocked=False,
                          council_signals={}, stream_activations={}, identity_state={})
        proposal = aee.propose(
            name="curiosity axiom",
            description="explore when uncertain",
            layer=AxiomLayer.ADAPTIVE_CAPACITY,
            rationale="observed pattern",
            evidence="high regret",
            implementation_suggestion="add weight",
        )
        assert proposal is not None

    def test_review(self):
        from telos.core.axioms.evolution import AxiomEvolutionEngine
        from telos.core.axioms.evolution import AxiomLayer
        aee = AxiomEvolutionEngine()
        aee.observe(0, 0.8, 0.2, False, {}, {}, {})
        prop = aee.propose("n", "d", AxiomLayer.ADAPTIVE_CAPACITY, "r", "e", "i")
        if prop:
            result = aee.review(proposal_id=prop.id, approved=True)
            assert result is True

    def test_to_dict(self):
        from telos.core.axioms.evolution import AxiomEvolutionEngine
        aee = AxiomEvolutionEngine()
        d = aee.to_dict()
        assert isinstance(d, dict)


class TestInterpretationEngineSmoke:
    def test_instantiate(self):
        from telos.core.reasoning.interpretation_engine import InterpretationEngine
        ie = InterpretationEngine()
        assert ie.total_conflicts == 0

    def test_detect_and_interpret(self):
        from telos.core.reasoning.interpretation_engine import (
            InterpretationEngine, Principle,
        )
        ie = InterpretationEngine()
        principles = [
            Principle(name="exploration", description="seek novelty",
                      axiom_ref="P1", current_priority=0.8),
            Principle(name="safety", description="avoid harm",
                      axiom_ref="P2", current_priority=0.5),
        ]
        conflict = ie.detect_conflict(principles=principles, context={"risk": 0.8})
        if conflict is not None:
            result = ie.interpret(
                conflict_type=conflict, principles=principles, context={"risk": 0.8},
            )
            assert hasattr(result, 'conflict_type') or hasattr(result, 'explanation')
            conflicts = ie.get_conflicts_by_type(conflict)
            assert isinstance(conflicts, list)

    def test_to_dict(self):
        from telos.core.reasoning.interpretation_engine import InterpretationEngine
        ie = InterpretationEngine()
        d = ie.to_dict()
        assert isinstance(d, dict)


# ============================
# v2.5 Modules (10)
# ============================

class TestUnknownUnknownDetectorSmoke:
    def test_instantiate(self):
        from telos.core.curiosity.unknown_unknown_detector import UnknownUnknownDetector
        uud = UnknownUnknownDetector(window_size=10, persistence_threshold=2)
        assert uud.unknown_unknown_count == 0

    def test_record_and_promote(self):
        from telos.core.curiosity.unknown_unknown_detector import UnknownUnknownDetector
        uud = UnknownUnknownDetector(window_size=10, persistence_threshold=2)
        res = uud.record_observation(
            cycle=0, predictions={"speed": 1.0, "direction": 0.5},
            observations={"speed": 3.0, "direction": 0.5, "altitude": 100.0},
        )
        assert len(res) >= 2
        for c in range(1, 5):
            uud.record_observation(cycle=c, predictions={"speed": 1.0},
                                   observations={"speed": 3.0})
        questions = uud.promote_to_questions(cycle=5)
        assert isinstance(questions, list)

    def test_learn(self):
        from telos.core.curiosity.unknown_unknown_detector import UnknownUnknownDetector
        uud = UnknownUnknownDetector(window_size=10, persistence_threshold=1)
        uud.learn_pattern("speed", residual=1.0)
        assert uud.known_pattern_count >= 1


class TestModelCompetitionSmoke:
    def test_instantiate(self):
        from telos.core.reasoning.model_competition import ModelCompetition
        mc = ModelCompetition(min_probability=0.01, max_models=10)
        assert mc is not None

    def test_propose_and_compete(self):
        from telos.core.reasoning.model_competition import ModelCompetition
        mc = ModelCompetition(min_probability=0.01, max_models=10)
        mid1 = mc.propose_model(name="Model A", description="explains X",
                               probability=0.5, source="initial")
        mid2 = mc.propose_model(name="Model B", description="explains Y",
                               probability=0.5, source="initial")
        assert isinstance(mid1, str)
        assert isinstance(mid2, str)
        mc.submit_evidence(description="test evidence",
                          likelihoods={mid1: 0.8, mid2: 0.2})
        ent = mc.compute_entropy()
        assert isinstance(ent, float)
        consensus = mc.compute_consensus()
        assert isinstance(consensus, float)
        dom = mc.dominant_model
        assert dom is None or hasattr(dom, 'name')
        winner = mc.get_winner()
        assert winner is None or hasattr(winner, 'name')

    def test_to_dict(self):
        from telos.core.reasoning.model_competition import ModelCompetition
        mc = ModelCompetition()
        mc.propose_model("x", "test", 0.5, "manual")
        d = mc.to_dict()
        assert isinstance(d, dict)


class TestTimeHorizonSmoke:
    def test_instantiate(self):
        from telos.core.decision.time_horizon import TimeHorizonSeparator
        ths = TimeHorizonSeparator()
        assert ths is not None

    def test_evaluate(self):
        from telos.core.decision.time_horizon import TimeHorizonSeparator
        ths = TimeHorizonSeparator()
        eval = ths.evaluate(
            action_id="explore", action_description="explore cave",
            horizon_scores={"immediate": 0.5, "short": 0.3, "long": 0.2},
        )
        assert hasattr(eval, 'action_id') or hasattr(eval, 'total_utility')

    def test_compare(self):
        from telos.core.decision.time_horizon import TimeHorizonSeparator
        ths = TimeHorizonSeparator()
        a = ths.evaluate("a", "desc", {"immediate": 0.8, "short": 0.5, "long": 0.2})
        b = ths.evaluate("b", "desc", {"immediate": 0.2, "short": 0.5, "long": 0.8})
        comp = ths.compare_actions([a, b])
        assert isinstance(comp, list)

    def test_to_dict(self):
        from telos.core.decision.time_horizon import TimeHorizonSeparator
        ths = TimeHorizonSeparator()
        d = ths.to_dict()
        assert isinstance(d, dict)


class TestSurpriseBudgetSmoke:
    def test_instantiate(self):
        from telos.core.attention.surprise_budget import SurpriseBudget
        sb = SurpriseBudget(base_budget_ms=100)
        assert sb is not None

    def test_record_and_compute(self):
        from telos.core.attention.surprise_budget import SurpriseBudget
        sb = SurpriseBudget(base_budget_ms=100)
        sb.record_prediction(correct=False, channel="vision", error=1.0)
        sb.record_prediction(correct=True, channel="vision", error=0.0)
        surprise = sb.surprise_level
        assert isinstance(surprise, float)
        budget = sb.compute_budget(cycle=1)
        assert hasattr(budget, 'total_budget_ms')

    def test_surprising_channels(self):
        from telos.core.attention.surprise_budget import SurpriseBudget
        sb = SurpriseBudget()
        channels = sb.get_surprising_channels(threshold=0.3)
        assert isinstance(channels, list)

    def test_reset(self):
        from telos.core.attention.surprise_budget import SurpriseBudget
        sb = SurpriseBudget()
        sb.record_prediction(correct=False, channel="test", error=1.0)
        sb.reset()
        assert sb.surprise_level == 0.0


class TestActiveForgettingSmoke:
    def test_instantiate(self):
        from telos.core.memory.active_forgetting import ActiveForgetting
        af = ActiveForgetting(examination_interval=10)
        assert af.total_beliefs > 0

    def test_register_and_belief_ops(self):
        from telos.core.memory.active_forgetting import ActiveForgetting
        af = ActiveForgetting(examination_interval=10)
        from telos.core.memory.active_forgetting import BeliefType
        bid = af.register_belief(description="sun rises in east",
                                 type=BeliefType.FACTUAL, confidence=0.9)
        assert isinstance(bid, str)
        af.strengthen(bid, amount=0.05)
        af.use_belief(bid)
        assert af.total_beliefs > 0

    def test_examine(self):
        from telos.core.memory.active_forgetting import ActiveForgetting
        from telos.core.memory.active_forgetting import BeliefType
        af = ActiveForgetting(examination_interval=1)
        bid = af.register_belief("test belief", BeliefType.FACTUAL, 0.5)
        result = af.examine(bid, cycle=5)
        if result is not None:
            assert hasattr(result, 'action')


class TestInternalDebateSmoke:
    def test_instantiate(self):
        from telos.core.council.internal_debate import InternalDebate
        idb = InternalDebate(max_rounds=3)
        assert idb.total_debates == 0

    def test_debate(self):
        from telos.core.council.internal_debate import InternalDebate
        idb = InternalDebate(max_rounds=2)
        result = idb.debate(
            context={
                "uncertainty": 0.7, "resources": {"budget": 100},
                "options": ["explore", "exploit"],
                "goals": {"survival": 1.0},
            },
            context_description="explore or exploit?",
        )
        assert idb.total_debates > 0
        latest = idb.latest_debate()
        if latest is not None:
            assert hasattr(latest, 'id')

    def test_to_dict(self):
        from telos.core.council.internal_debate import InternalDebate
        idb = InternalDebate()
        idb.debate(
            {"uncertainty": 0.5, "resources": {"budget": 100},
             "options": ["a"], "goals": {"x": 1.0}},
            None, "test",
        )
        d = idb.to_dict()
        assert isinstance(d, dict)


class TestCognitiveEnergySmoke:
    def test_instantiate(self):
        from telos.core.energy.cognitive_energy import CognitiveEnergy
        ce = CognitiveEnergy(max_energy=100)
        assert ce.energy_ratio == 1.0

    def test_consume_and_rest(self):
        from telos.core.energy.cognitive_energy import CognitiveEnergy
        ce = CognitiveEnergy(max_energy=100, recharge_rate=50)
        ce.consume(difficulty=0.5)
        assert ce.energy_ratio < 1.0
        ce.rest(cycles=2)
        assert ce.energy_ratio > 0.0

    def test_fatigue(self):
        from telos.core.energy.cognitive_energy import CognitiveEnergy
        ce = CognitiveEnergy(max_energy=10, recharge_rate=0, base_cost=5)
        assert not ce.is_fatigued
        ce.consume(difficulty=1.0)
        assert ce.is_fatigued

    def test_compute_difficulty(self):
        from telos.core.energy.cognitive_energy import CognitiveEnergy
        ce = CognitiveEnergy()
        d = ce.compute_difficulty(n_options=5, uncertainty=0.7)
        assert isinstance(d, float)


class TestDualConfidenceSmoke:
    def test_instantiate(self):
        from telos.core.confidence.dual_confidence import DualConfidence
        dc = DualConfidence(window_size=5)
        assert isinstance(dc.average_decision_confidence, float)

    def test_compute_and_report(self):
        from telos.core.confidence.dual_confidence import DualConfidence
        dc = DualConfidence(window_size=10)
        dc_1 = dc.compute_decision_confidence(
            predictive_accuracy=0.8, option_scores=[0.7, 0.3], familiarity=0.5,
        )
        ec_1 = dc.compute_explanation_confidence(
            causal_coherence=0.6, evidence_completeness=0.7, theory_support=0.5,
        )
        rpt = dc.report("d1", dc_1, ec_1)
        assert dc.average_decision_confidence > 0.0
        assert dc.average_explanation_confidence > 0.0
        trend = dc.get_recent_gap_trend(window=5)
        assert isinstance(trend, str)
        assert isinstance(dc.dominant_gap_type, str)

    def test_to_dict(self):
        from telos.core.confidence.dual_confidence import DualConfidence
        dc = DualConfidence()
        dc_ = dc.compute_decision_confidence(0.8, [0.7, 0.3], 0.5)
        ec_ = dc.compute_explanation_confidence(0.6, 0.7, 0.5)
        dc.report("x", dc_, ec_)
        d = dc.to_dict()
        assert isinstance(d, dict)


class TestIdentityCompressionSmoke:
    def test_instantiate(self):
        from telos.core.identity.identity_compression import IdentityCompression
        ic = IdentityCompression(batch_size=2)
        assert ic.total_experiences == 0

    def test_add_and_compress(self):
        from telos.core.identity.identity_compression import IdentityCompression
        ic = IdentityCompression(batch_size=2, similarity_threshold=0.3,
                                 min_compression_ratio=1.0)
        for i in range(6):
            ic.add_experience(description=f"experience {i}", source="pipeline")
        compressed = ic.compress()
        assert compressed is None or hasattr(compressed, 'principles')
        principles = ic.get_top_principles(top_n=3)
        assert isinstance(principles, list)
        markers = ic.get_identity_markers()
        assert isinstance(markers, dict)
        assert ic.total_principles >= 0
        assert ic.overall_compression_rate >= 0.0

    def test_no_crash_empty(self):
        from telos.core.identity.identity_compression import IdentityCompression
        ic = IdentityCompression(batch_size=2)
        result = ic.compress()
        assert result is None


class TestExplanationCompressionSmoke:
    def test_instantiate(self):
        from telos.core.knowledge.explanation_compression import ExplanationCompression
        ec = ExplanationCompression(min_instances_per_rule=2, max_rules=10)
        assert ec is not None

    def test_add_and_compress(self):
        from telos.core.knowledge.explanation_compression import ExplanationCompression
        ec = ExplanationCompression(min_instances_per_rule=2, max_rules=3,
                                    coverage_threshold=0.5)
        for i in range(4):
            ec.add_instance(phenomenon="light", cause="sun",
                           mechanism="nuclear fusion", context="physics")
        for i in range(4):
            ec.add_instance(phenomenon="rain", cause="clouds",
                           mechanism="condensation", context="weather")
        metrics = ec.compress()
        top = ec.get_top_rules(top_n=3)
        assert isinstance(top, list)
        expl = ec.explain(phenomenon="light", cause="sun")
        assert expl is None or isinstance(expl, dict)
        assert isinstance(ec.compression_ratio, float)
        d = ec.to_dict()
        assert isinstance(d, dict)


class TestResourceAccountingLayerSmoke:
    def test_instantiate(self):
        from telos.core.accounting.resource_accounting import ResourceAccountingLayer
        ral = ResourceAccountingLayer()
        assert ral.total_cost.compute_ms == 0.0

    def test_record_actions(self):
        from telos.core.accounting.resource_accounting import (
            ResourceAccountingLayer, ResourceCost,
        )
        ral = ResourceAccountingLayer()
        ral.set_cycle(1)
        ral.record_action("reflex", ResourceCost(compute_ms=2.0, memory_traces=1))
        ral.record_action("planning", ResourceCost(compute_ms=12.0, memory_traces=3,
                           bandwidth_bytes=500, storage_entries=1))
        tc = ral.total_cost
        assert tc.compute_ms == 14.0
        assert tc.memory_traces == 4
        assert tc.bandwidth_bytes == 500.0
        assert tc.storage_entries == 1
        summary = ral.cycle_summary()
        assert summary["total_compute_ms"] == 14.0
        assert summary["action_count"] == 2

    def test_stream_activation(self):
        from telos.core.accounting.resource_accounting import ResourceAccountingLayer
        ral = ResourceAccountingLayer()
        ral.set_cycle(1)
        ral.record_stream_activation("reflex", compute_ms=2.0)
        ral.record_stream_activation("planning", compute_ms=12.0, memory_traces=3)
        tc = ral.total_cost
        assert tc.compute_ms == 14.0

    def test_backend_commit(self):
        from telos.core.accounting.resource_accounting import (
            ResourceAccountingLayer, ResourceCost, DictLedgerBackend,
        )
        backend = DictLedgerBackend()
        ral = ResourceAccountingLayer(backend=backend)
        ral.set_cycle(1)
        ral.record_action("test", ResourceCost(compute_ms=5.0))
        ral.set_cycle(2)  # flushes cycle 1
        retrieved = ral.get_action_cost("test")
        assert retrieved is not None
        assert retrieved["cost"]["compute_ms"] == 5.0
        cycle_costs = ral.get_cycle_costs(1)
        assert len(cycle_costs) == 1

    def test_cost_addition(self):
        from telos.core.accounting.resource_accounting import ResourceCost
        a = ResourceCost(compute_ms=1.0, memory_traces=2, bandwidth_bytes=100, storage_entries=1)
        b = ResourceCost(compute_ms=3.0, memory_traces=1, bandwidth_bytes=50, storage_entries=0)
        c = a + b
        assert c.compute_ms == 4.0
        assert c.memory_traces == 3
        assert c.bandwidth_bytes == 150.0
        assert c.storage_entries == 1

    def test_to_dict(self):
        from telos.core.accounting.resource_accounting import (
            ResourceAccountingLayer, ResourceCost,
        )
        ral = ResourceAccountingLayer()
        ral.set_cycle(1)
        ral.record_action("a", ResourceCost(compute_ms=2.0))
        d = ral.to_dict()
        assert d["current_cycle"] == 1
        assert d["pending_actions"] == 1


class TestProjectSubstrateSmoke:
    def test_project_creation(self):
        from telos.core.project.substrate import ProjectPortfolio
        pp = ProjectPortfolio()
        p = pp.create_project("p1", "Test Project", "m1", cycle=0)
        assert p.id == "p1"
        assert pp.project_count == 1

    def test_lifecycle(self):
        from telos.core.project.substrate import ProjectPortfolio, ProjectLifecycle
        pp = ProjectPortfolio()
        pp.create_project("p1", "T", "m1", cycle=0)
        pp.set_lifecycle("p1", ProjectLifecycle.STALLED, cycle=10)
        assert pp._projects["p1"].lifecycle == ProjectLifecycle.STALLED

    def test_abandonment_continue(self):
        from telos.core.project.rational_abandonment import (
            AbandonmentGate, AbandonmentDecision, Trend,
        )
        gate = AbandonmentGate()
        result = gate.evaluate(Trend.RISING, Trend.RISING, 0.3, 0.5, 5)
        assert result.decision == AbandonmentDecision.CONTINUE

    def test_abandonment_obsession(self):
        from telos.core.project.rational_abandonment import (
            AbandonmentGate, AbandonmentDecision, Trend,
        )
        gate = AbandonmentGate()
        result = gate.evaluate(Trend.RISING, Trend.DECLINING, 0.8, 0.3, 100, level="project")
        assert result.decision == AbandonmentDecision.PAUSE

    def test_strategic_coherence(self):
        from telos.core.project.strategic_coherence import StrategicCoherence
        sc = StrategicCoherence()
        result = sc.evaluate("propose_theory", "p1", 0.8, 0)
        assert result.score > 0.5
        assert result.contribution == "direct"

    def test_to_dict(self):
        from telos.core.project.substrate import ProjectPortfolio
        pp = ProjectPortfolio()
        pp.create_project("p1", "T", "m1", cycle=0)
        d = pp.to_dict()
        assert d["total_projects"] == 1
