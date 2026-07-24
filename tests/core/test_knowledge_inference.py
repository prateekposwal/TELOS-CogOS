from telos.core.knowledge.inference import KGInferenceEngine
from telos.core.knowledge.graph import KnowledgeGraph

def test_inference_similarity():
    kg = KnowledgeGraph()
    kg.record("test", "approach1", 0.8, params={"a": 1, "b": 1})
    kg.record("test", "approach2", 0.9, params={"a": 2, "b": 2})
    
    engine = KGInferenceEngine(kg)
    similar = engine.find_similar_outcomes({"a": 1.1, "b": 1.1})
    assert similar[0].approach == "approach1"

def test_failure_patterns():
    kg = KnowledgeGraph()
    kg.record("test", "fail1", 0.2, failure_reason="reason1", params={"blocking_validator": "v1"})
    kg.record("test", "fail2", 0.3, failure_reason="reason1", params={"blocking_validator": "v1"})
    
    engine = KGInferenceEngine(kg)
    patterns = engine.detect_failure_patterns("test")
    assert len(patterns) == 1
    assert patterns[0]["validator"] == "v1"
    assert patterns[0]["count"] == 2
