"""
TELOS Server — Web chat UI + TELOS reasoning + local LLM speaking.
All local, no API key.

Run:  PYTHONPATH=. python3 telos_server.py
Open: http://localhost:8000
"""

import numpy as np
import logging
import json
import http.client
from fastapi import FastAPI
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

logging.basicConfig(level=logging.WARNING)
OLLAMA_MODEL = "qwen2:0.5b"

def ollama_chat(messages: list) -> str:
    conn = http.client.HTTPConnection("localhost", 11434, timeout=30)
    payload = json.dumps({"model": OLLAMA_MODEL, "messages": messages, "stream": False})
    conn.request("POST", "/api/chat", body=payload, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return data.get("message", {}).get("content", "")

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

chat_history = []

app = FastAPI(title="TELOS Server")

class Message(BaseModel):
    text: str

@app.post("/chat")
def chat(msg: Message):
    global chat_history
    state = np.array([hash(msg.text) % 10 * 0.1, len(msg.text) * 0.1])
    result = pipeline.execute(state)
    trace = result.decision_trace

    council = "APPROVED" if not (result.firewall_blocked or result.council_blocked) else "BLOCKED"
    scores = [round(o.get("score", 0), 3) for o in trace.strategic_options[:3]]
    intent = trace.selected_intent.intent_type if trace.selected_intent else "none"

    reasoning = json.dumps({
        "intent": intent, "council": council,
        "di": round(trace.decision_integrity, 3),
        "md": round(trace.mission_drift, 3),
        "worlds": trace.worlds_simulated, "futures": scores,
    })

    chat_history.append({"role": "user", "content": msg.text})
    system = {"role": "system", "content": f"You are TELOS, a Cognitive Operating System. Your reasoning: {reasoning}. Be concise."}
    reply = ollama_chat([system] + chat_history[-6:])
    chat_history.append({"role": "assistant", "content": reply})

    trace_data = {
        "perceived": msg.text,
        "intent": intent,
        "council": council,
        "di": round(trace.decision_integrity, 3),
        "md": round(trace.mission_drift, 3),
        "worlds": trace.worlds_simulated,
        "futures": scores,
        "reply": reply,
    }
    return trace_data

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
  <title>TELOS Server</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Courier New', monospace; background: #0d1117; color: #c9d1d9; height: 100vh; display: flex; flex-direction: column; }
    .header { padding: 16px; border-bottom: 1px solid #30363d; text-align: center; }
    .header h1 { color: #58a6ff; font-size: 18px; }
    .header p { color: #8b949e; font-size: 11px; }
    #chat { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
    .msg { max-width: 80%; padding: 10px 14px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
    .user { background: #1f6feb; color: #fff; align-self: flex-end; }
    .telos { background: #161b22; border: 1px solid #30363d; align-self: flex-start; }
    .trace { font-size: 11px; color: #8b949e; margin-top: 6px; border-top: 1px solid #30363d; padding-top: 6px; }
    .trace span { color: #58a6ff; }
    .pass { color: #3fb950; font-weight: bold; }
    .block { color: #f85149; font-weight: bold; }
    .input-bar { padding: 12px 16px; border-top: 1px solid #30363d; display: flex; gap: 8px; }
    .input-bar input { flex: 1; padding: 8px 12px; border: 1px solid #30363d; border-radius: 6px; background: #0d1117; color: #c9d1d9; font-family: 'Courier New', monospace; font-size: 13px; outline: none; }
    .input-bar input:focus { border-color: #58a6ff; }
    .input-bar button { padding: 8px 16px; border: none; border-radius: 6px; background: #238636; color: #fff; cursor: pointer; font-size: 13px; font-family: 'Courier New', monospace; }
    .input-bar button:hover { background: #2ea043; }
    .loading { color: #8b949e; font-style: italic; align-self: flex-start; }
  </style>
</head>
<body>
  <div class="header">
    <h1>TELOS — Cognitive Operating System</h1>
    <p>Reasoning + Local LLM | All local, no API key</p>
  </div>
  <div id="chat"></div>
  <div class="input-bar">
    <input id="input" type="text" placeholder="Talk to TELOS..." autofocus>
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
      const res = await fetch('/chat', { method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({text}) });
      const d = await res.json();
      loading.remove();
      const div = document.createElement('div');
      div.className = 'msg telos';
      const s = d.council === 'APPROVED' ? '<span class="pass">PASS</span>' : '<span class="block">BLOCK</span>';
      div.innerHTML = d.reply +
        '<div class="trace">[' + s + '] <span>DI</span>=' + d.di + ' <span>MD</span>=' + d.md +
        ' <span>intent</span>=' + d.intent + ' <span>worlds</span>=' + d.worlds +
        ' <span>futures</span>=' + d.futures.join(',') + '</div>';
      document.getElementById('chat').appendChild(div);
      div.scrollIntoView();
    }
    function addMsg(text, cls) {
      const div = document.createElement('div');
      div.className = 'msg ' + cls;
      div.textContent = text;
      document.getElementById('chat').appendChild(div);
      div.scrollIntoView();
      return div;
    }
    document.getElementById('input').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
  </script>
</body>
</html>
    """)

if __name__ == "__main__":
    print("TELOS Server — http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
