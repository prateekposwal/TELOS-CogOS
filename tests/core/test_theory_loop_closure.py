"""Phase 4 — the learning loop closes honestly.

Regression lock for the missing hypothesis -> test -> evidence arrow. The live
pipeline records experiences via ``observe_outcome`` but never called the only
``test_hypotheses`` caller (``build``), so ``tests_passed`` stayed 0 and the
promotion criterion was unsatisfiable. These tests prove the loop now closes
with GENUINE tests (real outcomes, never manufactured) and stays inert when the
TheoryStream is not registered (default-off stability).
"""

from __future__ import annotations

from types import SimpleNamespace

from telos.core.infra_manager.knowledge_manager import KnowledgeManager
from telos.core.reasoning.genealogy import TheoryGenealogy
from telos.core.reasoning.theory.builder import TheoryBuilder


class TestBuilderEvidenceArrow:
    def _builder(self):
        b = TheoryBuilder(
            min_experiences_for_pattern=5,
            min_patterns_for_hypothesis=2,
            min_tests_for_theory=5,
            theory_confidence_threshold=0.8,
        )
        for i in range(5):
            b.add_experience({"state_preview": f"s{i}"}, "observed", 1.0,
                             domain="pipeline")
        b.cluster()
        b.hypothesize()
        return b

    def test_promotion_requires_five_genuine_tests(self):
        b = self._builder()
        assert len(b.get_active_hypotheses()) >= 1
        # Four confirming tests is genuinely below the criterion.
        for i in range(4):
            b.observe_outcome(1.0, context=f"new{i}")
            b.test_latest_experience()
        assert b.promote() == []
        assert b.total_theories == 0

        # The fifth genuine test satisfies it.
        b.observe_outcome(1.0, context="new5")
        b.test_latest_experience()
        promoted = b.promote()
        assert len(promoted) == 1
        theory = promoted[0]
        assert theory.tests_passed >= 5
        assert theory.confidence >= 0.8

    def test_promotion_registers_genealogy_and_fires_hook(self):
        b = self._builder()
        gen = TheoryGenealogy()
        b.set_genealogy(gen)
        seen = []
        b.set_promotion_hook(lambda t, gid: seen.append((t.id, gid)))
        for i in range(5):
            b.observe_outcome(1.0, context=f"new{i}")
            b.test_latest_experience()
        promoted = b.promote()
        assert len(promoted) == 1
        assert len(gen._nodes) == 1
        assert seen and seen[0][1] in gen._nodes

    def test_no_experience_is_a_noop(self):
        b = TheoryBuilder()
        assert b.test_latest_experience() == []


class TestGenealogyToKnowledgeLink:
    def test_pipeline_tagged_node_is_linked(self):
        km = KnowledgeManager(policy=None, system_self=None)
        km.knowledge.record("unknown", "navigate", 0.9,
                            tags=["unknown", "pipeline"])
        theory = SimpleNamespace(domains=["pipeline"])
        linked = km.link_promoted_theory(theory, "theory_phase4")
        assert linked == 1
        node = km.knowledge.search(tags=["pipeline"])[0]
        assert "theory_phase4" in km.linker.theories_for_node(node.node_id)

    def test_absent_domain_links_nothing(self):
        km = KnowledgeManager(policy=None, system_self=None)
        theory = SimpleNamespace(domains=["pipeline"])
        assert km.link_promoted_theory(theory, "theory_none") == 0


class TestLiveLoopClosure:
    def test_baseline_build_closes_the_loop(self, tmp_path):
        from telos.tools.bench_loop import drive
        from telos.tools.causal_baseline import build
        pipe, _sim, _ = build(str(tmp_path), seed=42)
        for _ in drive(pipe, 40, user_name="loop-closure"):
            pass
        tb = pipe._theory_builder
        assert tb.total_theories > 0, "loop never promoted a theory"
        assert len(pipe._theory_genealogy._nodes) > 0
        assert tb._promoted_hypothesis_ids  # promotion ids recorded

    def test_without_theory_stream_nothing_promotes(self, tmp_path):
        from telos.core.streams.implementations import TheoryStream
        from telos.tools.bench_loop import drive
        from telos.tools.causal_baseline import build
        pipe, _sim, _ = build(str(tmp_path), seed=42)
        # Default-off path: no TheoryStream => no test arrow => no promotions.
        pipe.streams = [s for s in pipe.streams
                        if not isinstance(s, TheoryStream)]
        for _ in drive(pipe, 40, user_name="default-off"):
            pass
        assert pipe._theory_builder.total_theories == 0
        assert len(pipe._theory_genealogy._nodes) == 0
