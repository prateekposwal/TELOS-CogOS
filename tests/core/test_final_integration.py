import pytest
from telos.core.planning_horizon import PlanningHorizon
from telos.core.knowledge.inference import KGInferenceEngine
from telos.intent_ir import IntentIR
from telos.core.knowledge.graph import KnowledgeGraph

def test_final_integration():
    # 1. Setup
    kg = KnowledgeGraph()
    kg.record_failure(domain="test_domain", approach="test_approach", outcome=0.1, 
                      failure_reason="past_failure", params={'blocking_validator': 'MemoryAdvisor'})
    
    inference = KGInferenceEngine(kg)
    planner = PlanningHorizon()
    
    # Setup a plan
    plan = [IntentIR(intent_type="task1"), IntentIR(intent_type="task2")]
    planner.set_plan(plan)
    
    # 2. Multi-cycle task sequence
    assert planner.has_plan
    step1 = planner.get_next_step()
    assert step1.intent_type == "task1"
    
    # 3. Simulate Council rejection
    # (Assuming we have a mechanism to mock the council rejection)
    rejection = True
    if rejection:
        # 4. KGInferenceEngine surfacing suggestion
        patterns = inference.detect_failure_patterns(domain="test_domain")
        assert len(patterns) > 0
        assert patterns[0]['validator'] == 'MemoryAdvisor'
        # Suggestion to continue the plan
        assert "past_failure" in patterns[0]['reason']

    # Continue plan
    step2 = planner.get_next_step()
    assert step2.intent_type == "task2"
