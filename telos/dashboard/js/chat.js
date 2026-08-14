// TELOS Chat Module — command input and auto-refresh

function addLog(trace) {
  const c = document.getElementById('log-container');
  const b = trace.firewall_blocked || !trace.council_validated;
  const e = document.createElement('div');
  e.className = 'log-entry';
  e.innerHTML = `<span class="${b ? 'warn' : 'success'}">${b ? 'BLOCKED' : 'APPROVED'}</span> DI=${(trace.decision_integrity || 1).toFixed(2)} worlds=${trace.worlds_simulated || 0}`;
  c.prepend(e);
  while (c.children.length > 50) c.removeChild(c.lastChild);
}

function toggleAutoRefresh() {
  state.autoRefresh = !state.autoRefresh;
  const btn = document.getElementById('btn-auto-refresh');
  btn.textContent = state.autoRefresh ? '⏹ Stop' : '▶ Auto';
  btn.className = state.autoRefresh ? 'active' : '';
  if (state.autoRefresh) scheduleAuto();
}

let _autoT;
function scheduleAuto() {
  if (!state.autoRefresh) return;
  _autoT = setTimeout(async () => { await sendCmd('navigate'); scheduleAuto(); }, 3000);
}

async function sendCmd(cmd) {
  const msgDiv = document.getElementById('chat-messages');
  const input = document.getElementById('chat-input');
  const u = document.createElement('div');
  u.className = 'chat-msg user'; u.textContent = cmd;
  msgDiv.appendChild(u);
  input.disabled = true;
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: cmd, cycle: state.traces.length })
    });
    const data = await resp.json();
    const m = document.createElement('div');
    m.className = 'chat-msg telos';
    m.textContent = data.response || '(no response)';
    const ts = document.createElement('span');
    ts.className = 'time';
    ts.textContent = `DI=${data.di?.toFixed(3) || '—'} · ${data.status || ''} · ${new Date().toLocaleTimeString()}`;
    m.appendChild(ts);
    msgDiv.appendChild(m);
    msgDiv.scrollTop = msgDiv.scrollHeight;
    if (data.trace) applyTrace(data.trace);
  } catch (e) {
    const m = document.createElement('div');
    m.className = 'chat-msg telos'; m.textContent = `Error: ${e.message}`;
    msgDiv.appendChild(m);
  }
  input.disabled = false; input.value = ''; input.focus();
}
