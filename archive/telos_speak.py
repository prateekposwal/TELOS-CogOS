"""
TELOS Speaking — TELOS reasons, LLM speaks.
Requires OPENAI_API_KEY environment variable.
"""

import os, sys, numpy as np, logging, json
logging.basicConfig(level=logging.WARNING)

from openai import OpenAI
from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR

class ChatSim(DomainSimulator):
    def initialize(self): pass
    def cleanup(self): pass
    def legal_transitions(self, s): return [np.array([1,0]), np.array([0,1])]
    def transition(self, s, a): return s + a * 0.1
    def simulate(self, s, h): return [World(state=s.copy() + np.random.randn(2)*0.1) for _ in range(5)]
    def get_facts(self, s):
        return DomainFacts(state=s.copy(), resources={}, constraints=[], events=[], metrics={"uncertainty": 0.1})
    def terminal(self, s): return False
    def evaluate(self, s):
        return EvaluationReport(objectives={"coherence": float(np.linalg.norm(s))}, risks=0.0)

class ChatAdpt(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, md):
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        return np.zeros(2)
    @property
    def name(self): return "chat"

pipeline = TelosV14Pipeline(PipelineConfig(
    adapter=ChatAdpt(), simulator=ChatSim(),
    compute_budget_ms=50.0, state_dim=2, n_worlds=5, horizon=3,
))
skill_lib = SkillLibrary()
sim_engine = CounterfactualEngine(ChatSim())
pipeline.register_stream(ReflexStream(skill_lib))
pipeline.register_stream(PerceptionStream(skill_lib))
pipeline.register_stream(MemoryStream(skill_lib))
pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
pipeline.register_validator(RealityValidator())
pipeline.register_validator(ConstraintValidator())
pipeline.register_validator(MemoryAdvisor(skill_lib))
pipeline.register_validator(MissionDriftDetector())

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def telos_speak(user_input: str) -> str:
    state = np.array([hash(user_input) % 10 * 0.1, len(user_input) * 0.1])
    result = pipeline.execute(state)
    trace = result.decision_trace

    council_status = "APPROVED" if not (result.firewall_blocked or result.council_blocked) else "BLOCKED"
    scores = [round(o.get("score", 0), 3) for o in trace.strategic_options[:3]]
    intent = trace.selected_intent.intent_type if trace.selected_intent else "none"

    reasoning = json.dumps({
        "intent": intent,
        "council": council_status,
        "di": round(trace.decision_integrity, 3),
        "md": round(trace.mission_drift, 3),
        "worlds_simulated": trace.worlds_simulated,
        "top_futures": scores,
    })

    if council_status == "BLOCKED":
        return f"[TELOS BLOCKED] Council rejected the response. DI={trace.decision_integrity:.3f}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"You are TELOS, a Cognitive Operating System. You reason through {trace.worlds_simulated} simulated futures before speaking. Your last reasoning trace: {reasoning}. Answer concisely based on this reasoning."},
            {"role": "user", "content": user_input},
        ],
    )
    return response.choices[0].message.content

print("TELOS is speaking. Type 'quit' to exit.\n")
while True:
    user = input("You: ")
    if user.lower() in ("quit", "exit"):
        break
    reply = telos_speak(user)
    print(f"TELOS: {reply}\n")
