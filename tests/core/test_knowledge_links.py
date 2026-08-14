"""Tests for KnowledgeLinker — one canonical registry binding
KnowledgeGraph ↔ TheoryGenealogy ↔ SCM."""

from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.knowledge.links import KnowledgeLinker
from telos.core.reasoning.genealogy import TheoryGenealogy
from telos.core.reasoning.causal.scm import StructuralCausalModel


class TestKnowledgeLinker:
    def test_link_node_to_theory_bidirectional(self):
        linker = KnowledgeLinker()
        linker.link_node_to_theory("node_1", "theory_1")
        linker.link_node_to_theory("node_2", "theory_1")
        assert linker.theories_for_node("node_1") == ["theory_1"]
        assert linker.nodes_for_theory("theory_1") == ["node_1", "node_2"]

    def test_unlink_node_removes_reverse_refs(self):
        linker = KnowledgeLinker()
        linker.link_node_to_theory("node_1", "theory_1")
        linker.unlink_node("node_1")
        assert linker.theories_for_node("node_1") == []
        assert linker.nodes_for_theory("theory_1") == []

    def test_link_theory_to_scm_snapshots_structure(self):
        linker = KnowledgeLinker()
        scm = StructuralCausalModel()
        scm.add_edge("position", "distance")
        scm.add_edge("action", "position")
        scm.set_value("position", [1, 2])
        sid = linker.link_theory_to_scm("theory_1", scm)
        view = linker.scm_for_theory("theory_1")
        assert view["edges"] == ["position → distance", "action → position"]
        assert set(view["variables"]) == {"position"}  # variables = set values

    def test_relink_replaces_structure(self):
        linker = KnowledgeLinker()
        scm1 = StructuralCausalModel()
        scm1.add_edge("a", "b")
        scm2 = StructuralCausalModel()
        scm2.add_edge("x", "y")
        linker.link_theory_to_scm("t", scm1)
        linker.link_theory_to_scm("t", scm2)
        assert linker.scm_for_theory("t")["edges"] == ["x → y"]

    def test_get_connected_structure_full_neighborhood(self):
        # Build all three graphs + the linker
        kg = KnowledgeGraph()
        n1 = kg.record("x", "algo_1", 0.9)
        n2 = kg.record("x", "algo_2", 0.8)
        kg.add_edge(n1, n2, edge_type="competes")

        genealogy = TheoryGenealogy()
        parent = genealogy.register("BaseTheory", cycle=0)
        child = genealogy.register("RefinedTheory", parent_id=parent, cycle=1)

        scm = StructuralCausalModel()
        scm.add_edge("position", "distance")
        scm.set_value("position", [1, 2])

        linker = KnowledgeLinker()
        linker.attach_genealogy(genealogy)
        linker.link_node_to_theory(n1, child)
        linker.link_theory_to_scm(child, scm)

        structure = linker.get_connected_structure(n1, knowledge_graph=kg)
        assert structure["linked_theory_count"] == 1
        assert structure["knowledge_neighbors"][0]["node_id"] == n2
        theory = structure["theories"][0]
        assert theory["name"] == "RefinedTheory"
        assert theory["parent_id"] == parent
        assert theory["scm"]["edges"] == ["position → distance"]
        # n2 is the sibling node linked to nothing; child theory has no siblings
        assert theory.get("related_nodes", []) == []

    def test_get_connected_structure_isolated_node(self):
        linker = KnowledgeLinker()
        kg = KnowledgeGraph()
        n = kg.record("x", "solo", 0.5)
        structure = linker.get_connected_structure(n, knowledge_graph=kg)
        assert structure["linked_theory_count"] == 0
        assert structure["knowledge_neighbors"] == []
        assert structure["theories"] == []

    def test_to_dict_serializes_table(self):
        linker = KnowledgeLinker()
        linker.link_node_to_theory("n1", "t1")
        scm = StructuralCausalModel()
        scm.add_edge("a", "b")
        linker.link_theory_to_scm("t1", scm)
        d = linker.to_dict()
        assert d["node_to_theory"]["n1"] == ["t1"]
        assert d["theory_to_scm"]["t1"].startswith("scm_")


class TestPipelineWiring:
    """The runtime must actually wire the linker — not just appear to."""

    def _build_pipeline(self):
        import numpy as np
        from telos.core.runtime import TelosV14Pipeline, PipelineConfig
        from telos.core.contracts.domain_model import DomainAdapter
        from tests.core.conftest import MockSimulator

        class MockAdapter(DomainAdapter):
            def forward(self, x): return x
            def inverse(self, x): return x
            def intent_to_action(self, intent, state, mission_dir): return np.zeros(2)
            @property
            def name(self): return "mock"

        config = PipelineConfig(simulator=MockSimulator(), adapter=MockAdapter(),
                                checkpoint_path="/tmp/wiring_test_ckpt")
        return TelosV14Pipeline(config)

    def test_genealogy_attached_to_builder(self):
        pipeline = self._build_pipeline()
        assert pipeline._theory_builder._genealogy is pipeline._theory_genealogy

    def test_promotion_hook_wired(self):
        pipeline = self._build_pipeline()
        assert pipeline._theory_builder._promotion_hook is not None

    def test_linker_attached_to_knowledge_manager(self):
        pipeline = self._build_pipeline()
        km = pipeline._infra_manager.knowledge_mgr
        assert km.linker._genealogy is pipeline._theory_genealogy

    def test_promoted_theory_registers_in_genealogy_via_pipeline(self):
        pipeline = self._build_pipeline()
        tb = pipeline._theory_builder
        before = pipeline._theory_genealogy.to_dict()["total_nodes"]
        # Feed enough consistent outcomes to promote a theory through the
        # same observe_outcome path the ACT phase uses
        for i in range(12):
            tb.observe_outcome(outcome=0.9, context=f"state_{i}", action="navigate",
                               domain="gridworld")
            tb.build({"state_preview": f"state_{i}"}, "navigate", 0.9, domain="gridworld")
        after = pipeline._theory_genealogy.to_dict()["total_nodes"]
        assert after > before, "promotion must register theories in the genealogy"
        # Every promoted theory has a genealogy entry with the same name
        promoted = tb._theories
        for tid, theory in promoted.items():
            gid = getattr(theory, '_genealogy_id', None)
            if gid is not None:
                assert pipeline._theory_genealogy._nodes[gid].name == theory.name


    def test_conversation_outcome_feeds_theory_builder(self):
        """The chat path bridges into theory formation (Λ6.5): a turn
        becomes a conversation-domain experience, not just LLM text."""
        pipeline = self._build_pipeline()
        before = pipeline._theory_builder.total_experiences
        eid = pipeline.observe_conversation_outcome(
            message="go north", reply="I am navigating to the goal.",
            outcome=0.9, domain="conversation",
        )
        assert eid
        assert pipeline._theory_builder.total_experiences == before + 1
        exp = pipeline._theory_builder._experiences[eid]
        assert exp.domain == "conversation"
        assert "go north" in exp.context["state_preview"]

    def test_conversation_path_promotes_theory_into_genealogy(self):
        """Repeated conversation turns flow all the way: experience →
        pattern → hypothesis → theory → genealogy node (same path the
        ACT phase uses)."""
        pipeline = self._build_pipeline()
        tb = pipeline._theory_builder
        before = pipeline._theory_genealogy.to_dict()["total_nodes"]
        for i in range(12):
            pipeline.observe_conversation_outcome(
                message=f"turn {i}", reply="reply ok",
                outcome=0.9, domain="conversation",
            )
            tb.build({"state_preview": f"turn {i}"}, "conversation", 0.9,
                     domain="conversation")
        after = pipeline._theory_genealogy.to_dict()["total_nodes"]
        assert after > before, "conversation theories must register in the genealogy"
        for tid, theory in tb._theories.items():
            gid = getattr(theory, '_genealogy_id', None)
            if gid is not None:
                assert pipeline._theory_genealogy._nodes[gid].name == theory.name
