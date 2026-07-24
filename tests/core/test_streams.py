"""
Cognitive Stream tests — each stream processes World correctly.
Includes InquiryStream (5th cognitive stream, priority 0.8).
"""

import numpy as np

from telos.core.simulation import CounterfactualEngine
from telos.core.streams.implementations import ReflexStream, PerceptionStream, MemoryStream, PlanningStream
from telos.core.streams.inquiry_stream import InquiryStream
from telos.core.ledger.skill_library import SkillLibrary
from telos.world.world import World
from tests.core.conftest import MockSimulator


def test_streams():
    skill_lib = SkillLibrary()
    sim = MockSimulator()
    sim_engine = CounterfactualEngine(sim)

    # ReflexStream — no longer triggers on uncertainty alone
    # (old uncertainty > 0.8 → Reflex rule replaced by InquiryStream)
    reflex = ReflexStream(skill_lib)
    world = World(state=np.array([10.0, 10.0]), metadata={}, uncertainty=0.9)
    intent = reflex.process(world)
    assert intent.intent_type == "reflex"
    # Uncertainty alone no longer triggers reflex (confidence stays 0.0)
    assert intent.confidence == 0.0
    # Verify NaN still triggers reflex
    world_nan = World(state=np.array([float('nan'), 10.0]), metadata={}, uncertainty=0.5)
    intent_nan = reflex.process(world_nan)
    assert intent_nan.intent_type == "reflex"
    assert intent_nan.confidence >= 0.5

    # PerceptionStream
    perception = PerceptionStream(skill_lib)
    world = World(state=np.array([1.0, 2.0, 0.0, 0.0, 0.0, 0.0]))
    intent = perception.process(world)
    assert intent.intent_type == "perceive"
    assert "features" in intent.params
    assert len(world.entities) > 0

    # MemoryStream
    memory = MemoryStream(skill_lib)
    world = World(state=np.array([1.0, 2.0]))
    intent = memory.process(world)
    assert intent.intent_type == "memory_miss"

    # InquiryStream — new 5th stream, generates questions from uncertainty
    inquiry = InquiryStream(skill_lib)
    world_inq = World(state=np.array([1.0, 2.0]), metadata={
        "U_W": 0.6, "U_I": 0.2, "U_O": 0.4,
    })
    intent_inq = inquiry.process(world_inq)
    assert intent_inq.intent_type == "inquiry"
    assert "candidate_questions" in intent_inq.params
    assert len(intent_inq.params["candidate_questions"]) >= 2

    # PlanningStream
    planning = PlanningStream(skill_lib, sim_engine=sim_engine)
    world = World(state=np.array([1.0, 2.0]))
    intent = planning.process(world)
    assert intent.intent_type in ("plan_trajectory", "plan_empty", "plan_noop")
