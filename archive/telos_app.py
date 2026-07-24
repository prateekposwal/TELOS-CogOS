"""
TELOS Web App — FastAPI + HTML chat interface.
TELOS reasons about your input live.

Run:  PYTHONPATH=. python3 telos_app.py
Open: http://localhost:8000
"""

import numpy as np
import logging
logging.basicConfig(level=logging.WARNING)

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

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

app = FastAPI(title="TELOS Chat")

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

class Message(BaseModel):
    text: str

@app.post("/reason")
def reason(msg: Message):
    state = np.array([hash(msg.text) % 10 * 0.1, len(msg.text) * 0.1])
    result = pipeline.execute(state)
    trace = result.decision_trace
    scores = [o.get("score", 0) for o in trace.strategic_options[:3]]
    return {
        "perceived": msg.text,
        "intent": trace.selected_intent.intent_type if trace.selected_intent else "none",
        "status": "BLOCKED" if (result.firewall_blocked or result.council_blocked) else "APPROVED",
        "di": round(trace.decision_integrity, 3),
        "md": round(trace.mission_drift, 3),
        "worlds": trace.worlds_simulated,
        "budget_ms": round(trace.budget_consumed_ms, 1),
        "top_futures": [round(s, 3) for s in scores],
    }

@app.get("/", response_class=HTMLResponse)
def chat_page():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
  <title>TELOS Chat</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Courier New', monospace; background: #0d1117; color: #c9d1d9; height: 100vh; display: flex; flex-direction: column; }
    .header { padding: 20px; border-bottom: 1px solid #30363d; text-align: center; }
    .header h1 { color: #58a6ff; font-size: 20px; }
    .header p { color: #8b949e; font-size: 12px; margin-top: 4px; }
    #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
    .msg { max-width: 80%; padding: 12px 16px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
    .user { background: #1f6feb; color: #fff; align-self: flex-end; }
    .telos { background: #161b22; border: 1px solid #30363d; align-self: flex-start; }
    .telos .field { display: flex; gap: 8px; margin: 2px 0; }
    .telos .label { color: #58a6ff; min-width: 100px; }
    .telos .value { color: #c9d1d9; }
    .telos .status-pass { color: #3fb950; font-weight: bold; }
    .telos .status-block { color: #f85149; font-weight: bold; }
    .input-bar { padding: 16px 20px; border-top: 1px solid #30363d; display: flex; gap: 12px; }
    .input-bar input { flex: 1; padding: 10px 14px; border: 1px solid #30363d; border-radius: 6px; background: #0d1117; color: #c9d1d9; font-family: 'Courier New', monospace; font-size: 13px; outline: none; }
    .input-bar input:focus { border-color: #58a6ff; }
    .input-bar button { padding: 10px 20px; border: none; border-radius: 6px; background: #238636; color: #fff; font-family: 'Courier New', monospace; cursor: pointer; font-size: 13px; }
    .input-bar button:hover { background: #2ea043; }
    .loading { color: #8b949e; font-style: italic; align-self: flex-start; padding: 8px; }
  </style>
</head>
<body>
  <div class="header">
    <h1>TELOS CogOS</h1>
    <p>Reasoning Engine — Type something, TELOS will reason</p>
  </div>
  <div id="chat"></div>
  <div class="input-bar">
    <input id="input" type="text" placeholder="Type a message..." autofocus>
    <button onclick="send()">Send</button>
  </div>
  <script>
    async function send() {
      const input = document.getElementById('input');
      const text = input.value.trim();
      if (!text) return;
      input.value = '';
      addMsg(text, 'user');
      const loading = addMsg('TELOS is reasoning...', 'loading');
      try {
        const res = await fetch('/reason', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({text}) });
        const data = await res.json();
        loading.remove();
        addTelosMsg(data);
      } catch(e) {
        loading.remove();
        addMsg('Error connecting to TELOS', 'telos');
      }
    }
    function addMsg(text, cls) {
      const div = document.createElement('div');
      div.className = 'msg ' + cls;
      div.textContent = text;
      document.getElementById('chat').appendChild(div);
      div.scrollIntoView();
      return div;
    }
    function addTelosMsg(d) {
      const div = document.createElement('div');
      div.className = 'msg telos';
      const status = d.status === 'APPROVED' ? '<span class="status-pass">PASS</span>' : '<span class="status-block">BLOCK</span>';
      div.innerHTML = `
        <div class="field"><span class="label">Perceived</span><span class="value">"${d.perceived}"</span></div>
        <div class="field"><span class="label">Intent</span><span class="value">${d.intent}</span></div>
        <div class="field"><span class="label">Council</span><span class="value">[${status}] DI=${d.di} MD=${d.md}</span></div>
        <div class="field"><span class="label">Worlds</span><span class="value">${d.worlds} simulated</span></div>
        <div class="field"><span class="label">Budget</span><span class="value">${d.budget_ms}ms</span></div>
        <div class="field"><span class="label">Futures</span><span class="value">${d.top_futures.join(', ')}</span></div>
      `;
      document.getElementById('chat').appendChild(div);
      div.scrollIntoView();
    }
    document.getElementById('input').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
  </script>
</body>
</html>
    """)

if __name__ == "__main__":
    print("TELOS Web App — http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
