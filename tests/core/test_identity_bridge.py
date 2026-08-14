"""Gap-1 tests: identity↔knowledge wiring (IdentityBridge).

Proves the identity island is closed:
  1. identity updates (marker/mood/snapshot) produce knowledge structures
  2. get_connected_structure(identity_node) spans identity ↔ knowledge
  3. frozen IdentityCore is never mutated
  4. pipeline wiring is real (execute() produces identity knowledge nodes)
  5. the internal-write gate holds: record() still refuses identity; only
     the trusted bridge provenance can write internal domains.
"""

import dataclasses
import os
import numpy as np

from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.knowledge.links import KnowledgeLinker
from telos.core.identity.system_self import SystemSelf, IdentityCore
from telos.core.identity.identity_bridge import IdentityBridge


def _build_bridge():
    kg = KnowledgeGraph()
    linker = KnowledgeLinker()
    ss = SystemSelf()
    core = IdentityCore()
    bridge = IdentityBridge(system_self=ss, knowledge=kg, linker=linker,
                            identity_core=core)
    return kg, linker, ss, core, bridge


class TestIdentityBridge:
    def test_identity_update_produces_knowledge_node_with_provenance(self):
        kg, linker, ss, core, bridge = _build_bridge()
        node_id = bridge.sync(cycle=1, di=0.9, md=0.1, selected_intent="navigate")
        assert node_id, "sync must produce a knowledge node"
        node = kg._nodes[node_id]
        assert node.domain == "identity"
        assert node.provenance["caller"] == "identity_bridge"
        assert node.params["mood"] == "curious"
        assert "identity" in node.tags
        # The linker registry knows it as a self-observation node
        assert linker.is_identity_node(node_id)
        assert node_id in linker.identity_nodes()

    def test_marker_and_mood_changes_record_event_nodes(self):
        kg, linker, ss, core, bridge = _build_bridge()
        bridge.sync(cycle=1, di=0.9, md=0.0)
        # marker change (Kintsugi path mutates IdentityState markers)
        ss.state.identity_markers.add("effective_actor")
        bridge.sync(cycle=2, di=0.95, md=0.0)
        # mood change
        ss.state.mood = "confident"
        bridge.sync(cycle=3, di=0.95, md=0.0)
        identity_nodes = linker.identity_nodes()
        approaches = {kg._nodes[n].approach for n in identity_nodes if n in kg._nodes}
        assert any("marker_effective_actor" in a for a in approaches)
        assert any("mood_confident" in a for a in approaches)
        assert len(identity_nodes) >= 3

    def test_get_connected_structure_spans_identity_to_knowledge(self):
        kg, linker, ss, core, bridge = _build_bridge()
        # Empirical knowledge in a normal domain
        kg.record("navigation", "ucb_explore", 0.85, tags=["exploring", "navigation"])
        kg.record("navigation", "greedy", 0.6, tags=["navigation"])
        # Identity snapshot + semantic links
        node_id = bridge.sync(cycle=1, di=0.85, md=0.1)
        ss.state.identity_markers.add("exploring")
        bridge.sync(cycle=2, di=0.9, md=0.0)
        edges = bridge.link_markers_to_knowledge()
        assert edges >= 1, "markers must link to semantically-matching knowledge"
        # The identity snapshot node now has a real neighborhood
        cs = linker.get_connected_structure(node_id, knowledge_graph=kg)
        assert cs["identity_node"] is True
        assert len(cs["knowledge_neighbors"]) >= 1, \
            "identity node must have knowledge neighbors (identity↔knowledge)"

    def test_frozen_identity_core_never_mutated(self):
        kg, linker, ss, core, bridge = _build_bridge()
        core_snapshot = dataclasses.asdict(core)
        bridge.sync(cycle=1)
        ss.state.identity_markers.add("persistent")
        ss.state.mood = "cautious"
        bridge.sync(cycle=2)
        bridge.record_mission_completed("ship_gap_1", cycle=2)
        assert dataclasses.asdict(core) == core_snapshot, \
            "IdentityCore must remain frozen through bridge activity"
        # Frozen dataclass enforced by Python
        import pytest
        with pytest.raises(dataclasses.FrozenInstanceError):
            core.core_values = ("mutated",)

    def test_internal_write_gate_holds(self):
        """record() still refuses identity; only trusted provenance writes."""
        kg = KnowledgeGraph()
        assert kg.record("identity", "sneaky", 0.9) == "", \
            "normal record() must keep refusing internal domains"
        assert kg.record_internal("identity", "no_provenance", 0.9) == "", \
            "record_internal without trusted caller must be refused"
        node = kg.record_internal(
            "identity", "trusted", 0.9,
            provenance={"caller": "identity_bridge", "cycle": 1},
        )
        assert node, "trusted bridge provenance must write"

    def test_self_knowledge_query(self):
        kg, linker, ss, core, bridge = _build_bridge()
        kg.record("gridworld", "ucb", 0.9, tags=["exploring"])
        bridge.sync(cycle=1, di=0.8, md=0.2)
        bridge.link_markers_to_knowledge()
        sk = bridge.self_knowledge()
        assert sk["snapshot_node"] is not None
        assert "mood" in sk["snapshot"]
        assert sk["connected_structure"] is not None
        assert isinstance(sk["hot_identity_knowledge"], list)


class TestPipelineIdentityWiring:
    """The runtime must really run the bridge during execute()."""

    def _build_pipeline(self):
        from telos.core.runtime import TelosV14Pipeline, PipelineConfig
        from telos.core.contracts.domain_model import DomainAdapter
        from telos.core.ledger.skill_library import SkillLibrary
        from telos.core.streams.implementations import (
            ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
        )
        from telos.core.simulation import CounterfactualEngine
        from tests.core.conftest import MockSimulator

        class MockAdapter(DomainAdapter):
            def forward(self, x): return x
            def inverse(self, x): return x
            def intent_to_action(self, intent, state, mission_dir): return np.zeros(2)
            @property
            def name(self): return "mock"

        import tempfile
        sim = MockSimulator()
        ckpt_dir = tempfile.mkdtemp(prefix="id_wiring_")
        config = PipelineConfig(simulator=sim, adapter=MockAdapter(),
                                checkpoint_path=os.path.join(ckpt_dir, "ckpt"))
        pipeline = TelosV14Pipeline(config)
        sl = SkillLibrary()
        se = CounterfactualEngine(sim, seed=7)
        pipeline.register_stream(ReflexStream(sl))
        pipeline.register_stream(PerceptionStream(sl))
        pipeline.register_stream(MemoryStream(sl))
        pipeline.register_stream(PlanningStream(sl, sim_engine=se))
        return pipeline

    def test_pipeline_runs_bridge_and_produces_identity_nodes(self):
        pipeline = self._build_pipeline()
        state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
        pipeline.execute(state)
        pipeline.execute(state)
        bridge = pipeline.identity_bridge
        assert bridge is not None, "pipeline must own an IdentityBridge"
        sk = pipeline.get_identity_knowledge()
        assert sk["snapshot_node"] is not None, \
            "execute() must record identity self-snapshots into the KG"
        kg = pipeline._infra_manager.knowledge
        id_nodes = [n for n in kg._nodes.values() if n.domain == "identity"]
        assert id_nodes, "identity-domain knowledge nodes must exist"
        assert all(n.provenance.get("caller") == "identity_bridge"
                   for n in id_nodes)
        # linked into the canonical registry
        linker = pipeline._infra_manager.knowledge_mgr.linker
        assert len(linker.identity_nodes()) >= 1

    def test_pipeline_identity_core_frozen_through_cycles(self):
        pipeline = self._build_pipeline()
        state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
        for _ in range(3):
            pipeline.execute(state)
        core = pipeline._identity_core
        assert core.axioms_count == 42
        import pytest
        with pytest.raises(dataclasses.FrozenInstanceError):
            core.core_values = ("mutated",)
