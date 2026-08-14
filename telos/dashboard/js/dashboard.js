// TELOS Core Dashboard Module — state, data flow, UI logic
var _display = { di:0, md:0, cycles:0, health:0, system:0, mission:0, score:null, worlds:0, terrain:'' };
var _displayTarget = { di:0, md:0, cycles:0, health:0, system:0, mission:0, score:null, worlds:0, terrain:'' };
var _displayPrev = { di:0, md:0, cycles:0, health:0, system:0, mission:0, score:null, worlds:0, terrain:'' };
var _lastUpdate = null;
function popValue(el) { if(el){el.classList.remove('val-pop');void el.offsetWidth;el.classList.add('val-pop');} }

var _activeTab = 'all';
function switchTab(name) {
  _activeTab = name;
  document.querySelectorAll('.tab-bar .tab').forEach(function(t) { t.classList.toggle('active', t.getAttribute('data-tab') === name); });
  document.querySelectorAll('[data-section]').forEach(function(el) {
    if (name === 'all') {
      el.classList.remove('section-hidden');
      el.classList.remove('tab-active');
    } else {
      el.classList.toggle('section-hidden', el.getAttribute('data-section') !== name);
      el.classList.toggle('tab-active', el.getAttribute('data-section') === name);
    }
  });
  var spacers = document.querySelectorAll('.section-spacer');
  spacers.forEach(function(s) { s.classList.toggle('section-hidden', name !== 'all'); });
  setTimeout(function() {
    window.dispatchEvent(new Event('resize'));
  }, 50);
}

const TC = {'plains':'#1a2a1a','forest':'#0d2818','water':'#0a1628','desert':'#2a2418','mountain':'#1e1e2a','blocked':'#2a1a1a'};
const TCOST = {'plains':1,'forest':2,'water':3,'desert':1.5,'mountain':4};
const SC = {'Reflex':'#ff6b6b','Perception':'#4ade80','Memory':'#60a5fa','Planning':'#fbbf24'};
const PN = ['PERCEIVE','STREAMS','SIMULATE','EVALUATE','SYNTHESIS','SELECT','COUNCIL'];

const state = {
  traces: [], diHistory: [], mdHistory: [], cycleLabels: [],
  gridSize: 5, blocked: [[1,1],[2,2],[3,1]], rewards: {'0,4':10,'4,0':5},
  goal: [4,4], position: [0,0], animPos: [0,0], prevPos: [0,0], animT: 0,
  agent2Pos: [4,0], agent2Reward: 0,
  visited: [], time: 0,
  selectedCycle: -1, autoRefresh: false, rewardFlash: 0,
  particles: [],
  terrain: {
    '0,0':'plains','1,0':'plains','2,0':'forest','3,0':'plains','4,0':'desert',
    '0,1':'plains','1,1':'blocked','2,1':'plains','3,1':'blocked','4,1':'forest',
    '0,2':'water','1,2':'plains','2,2':'blocked','3,2':'desert','4,2':'plains',
    '0,3':'plains','1,3':'forest','2,3':'plains','3,3':'plains','4,3':'mountain',
    '0,4':'desert','1,4':'plains','2,4':'plains','3,4':'forest','4,4':'plains',
  },
  showCosts: false,
  heatMode: false,
  omegaHeatmap: false,
  visitCounts: {},
  shortestPath: [],
  hoveredCell: null,
  hoverPos: null,
  altPaths: [],
};

const TH = {
  'plains': 0, 'forest': 2.0, 'water': -0.5,
  'desert': 0.5, 'mountain': 4.5, 'blocked': 3.5,
};
const TC3D = {
  'plains':   { top: '#4a8a3a', left: '#2d5a22', right: '#386a2a', edge: '#5a9a4a' },
  'forest':   { top: '#1a6a2a', left: '#0d3a18', right: '#145020', edge: '#2a8a3a' },
  'water':    { top: '#1a5a9a', left: '#0d3a6a', right: '#144a7a', edge: '#2a7aba' },
  'desert':   { top: '#d4b86a', left: '#a88e4a', right: '#c0a45a', edge: '#e4c87a' },
  'mountain': { top: '#8a8a9a', left: '#5a5a6a', right: '#6a6a7a', edge: '#9a9aaa' },
  'blocked':  { top: '#3a2a2a', left: '#2a1a1a', right: '#2a1a1a', edge: '#4a3a3a' },
};

// ─── Checkpoint loading & trace application (unchanged) ───
async function loadCheckpoints() {
  try {
    const resp = await fetch('/api/checkpoints');
    const traces = await resp.json();
    for (const t of traces) {
      if (!state.traces.some(x => x.cycle_id === t.cycle_id)) applyTrace(t);
    }
  } catch {}
}

function applyTrace(trace) {
  state.traces.push(trace);
  state.diHistory.push(trace.decision_integrity || 1.0);
  state.mdHistory.push(trace.mission_drift || 0);
  state.cycleLabels.push(`C${trace.cycle_id || state.cycleLabels.length}`);

  _displayTarget.di = trace.decision_integrity || 1.0;
  _displayTarget.md = trace.mission_drift || 0;
  _displayTarget.cycles = state.traces.length;
  _displayTarget.worlds = trace.worlds_simulated || 0;
  _lastUpdate = Date.now();
  // Omega Vector display (Inquiry Stream)
  var _ov = trace.inquiry_omega_vector;
  var _omegaCard = document.getElementById('omega-card');
  if (_ov && (_ov.world || _ov.identity || _ov.other)) {
    _omegaCard.style.display = '';
    document.getElementById('omega-value').textContent = 
      '\u03a9_W: ' + (_ov.world || 0).toFixed(2) + ' | \u03a9_I: ' + (_ov.identity || 0).toFixed(2) + ' | \u03a9_O: ' + (_ov.other || 0).toFixed(2);
    // ── Gap 5: Omega narrative ──
    const omega = trace.inquiry_omega_vector || {};
    const ow = omega.world || 0, oi = omega.identity || 0, oo = omega.other || 0;
    if (ow > 0 || oi > 0 || oo > 0) {
      let narrative = '';
      if (ow > 0.4) narrative += '\uD83C\uDF0D Exploring unknown terrain. ';
      if (oi > 0.4) narrative += '\uD83D\uDD04 Recalibrating identity. ';
      if (oo > 0.4) narrative += '\uD83E\uDD1D Resolving council disagreement. ';
      if (!narrative) narrative = '\uD83D\uDCA1 Mild uncertainty, proceeding normally.';
      document.getElementById('omega-sub').textContent = narrative;
    } else {
      // ── Change 4: inquiry_blend display ──
      const blend = trace.inquiry_blend || 0;
      if (blend > 0) {
        document.getElementById('omega-sub').textContent = 
          `Blend: ${(blend * 100).toFixed(0)}% inquiry | ${((1-blend) * 100).toFixed(0)}% action`;
      } else {
        document.getElementById('omega-sub').textContent = '\u03a9 > 0.5 = inquiry active';
      }
    }
  } else {
    _omegaCard.style.display = 'none';
  }
  document.getElementById('status-text').textContent = trace.firewall_blocked ? 'BLOCKED' : trace.council_validated ? 'Approved' : 'Pending';

  if (trace.world_state) {
    state.prevPos = [...state.position];
    state.animT = 0;
    state.position = trace.world_state;
    if (!state.visited.some(p => p[0] === state.position[0] && p[1] === state.position[1])) {
      state.visited.push([...state.position]);
    }
    // Feature 5: Increment visit count for heat map
    const vk = `${Math.round(state.position[0])},${Math.round(state.position[1])}`;
    state.visitCounts[vk] = (state.visitCounts[vk] || 0) + 1;
    document.getElementById('step-counter').textContent = `Step ${state.visited.length}`;
  }
  // Feature 4: Extract alternative paths from strategic_options
  // ── Upgrades: agent2, score, terrain ──
  if (trace.agent2_pos) {
    state.agent2Pos = trace.agent2_pos;
    var a2val = document.getElementById('agent2-value');
    var a2card = document.getElementById('agent2-card');
    if (a2val) a2val.textContent = `(${trace.agent2_pos[0]},${trace.agent2_pos[1]})`;
    if (a2card) a2card.style.display = '';
  }
  if (trace.agent2_reward !== undefined) {
    state.agent2Reward = trace.agent2_reward;
  }
  // System Score is bounded 0-100 by definition (range is part of the
  // metric). Legacy persisted traces carry the old unbounded timer score
  // (100 - cycles + rewards, e.g. -271); out-of-range values are rejected
  // structurally rather than displayed.
  if (typeof trace.score === 'number' && isFinite(trace.score) && trace.score >= 0 && trace.score <= 100) {
    state.score = trace.score;
    _displayTarget.score = trace.score;
    var sc = document.getElementById('score-card');
    if (sc) {
      sc.style.display = '';
      var scv = document.getElementById('score-card-value');
      if (scv) scv.textContent = Math.round(state.score);
    }
  }
  if (trace.terrain_changes && trace.terrain_changes.length > 0) {
    state.terrainChanges = trace.terrain_changes;
    // Trigger terrain flash animation
    trace.terrain_changes.forEach(function(c) {
      if(!state.terrainFlash) state.terrainFlash={};
      var key = c.x + "," + c.y;
      state.terrainFlash[key] = { start: state.time, old: c.old, new: c.new };
    });
  }
  if (trace.world_state && trace.strategic_options && trace.strategic_options.length > 0) {
    const cx = Math.round(trace.world_state[0]), cy = Math.round(trace.world_state[1]);
    const dirMap = {
      'move right': [1, 0], 'move left': [-1, 0],
      'move up': [0, -1], 'move down': [0, 1],
      'right': [1, 0], 'left': [-1, 0],
      'up': [0, -1], 'down': [0, 1],
    };
    const altMoves = [];
    const sorted = [...trace.strategic_options].sort((a, b) => (b.score || 0) - (a.score || 0));
    for (const opt of sorted) {
      const moved = dirMap[opt.intent_type || opt.type || ''];
      if (!moved) continue;
      const nx = cx + moved[0], ny = cy + moved[1];
      if (nx < 0 || nx >= state.gridSize || ny < 0 || ny >= state.gridSize) continue;
      if (getTerrainAt(nx, ny) === 'blocked') continue;
      altMoves.push([[cx, cy], [nx, ny]]);
      if (altMoves.length >= 3) break;
    }
    state.altPaths = altMoves;
  }

  if (trace.domain_facts && trace.domain_facts.metadata) {
    if (trace.domain_facts.metadata.terrain) state.terrain = trace.domain_facts.metadata.terrain;
    if (trace.domain_facts.metadata.current_terrain) {
      const emojis = {plains:'🌿', forest:'🌲', water:'🌊', desert:'🏜️', mountain:'⛰️'};
      _displayTarget.terrain = trace.domain_facts.metadata.current_terrain;
      var terrainEl = document.getElementById('terrain-value');
      if (terrainEl) {
        var tVal = (emojis[trace.domain_facts.metadata.current_terrain] || '') + ' ' + trace.domain_facts.metadata.current_terrain;
        if (terrainEl.textContent !== tVal) { terrainEl.textContent = tVal; popValue(terrainEl); }
      }
    }
  }

  try { addLog(trace); } catch(e) {}
  renderAll();
}

function renderAll() {
  try { renderGrid(); } catch(e) {}
  try { renderChart(); } catch(e) {}
  try { renderMemoryTimeline(); } catch(e) {}
  try { renderPipelineTimeline(); } catch(e) {}
  try { animateResourceGauge(); } catch(e) {}
  try { drawHealthMeter(); } catch(e) {}
  try { drawMinimap(); } catch(e) {}
}

var _gridFullscreen = false;
function toggleGridFullscreen(){
  _gridFullscreen=!_gridFullscreen;
  var gp=document.querySelector('.grid-panel');
  if(!gp)return;
  if(_gridFullscreen){
    gp.style.position='fixed';gp.style.top='0';gp.style.left='0';
    gp.style.width='100vw';gp.style.height='100vh';gp.style.zIndex='1000';
    gp.style.margin='0';gp.style.borderRadius='0';
  }else{
    gp.style.position='';gp.style.top='';gp.style.left='';
    gp.style.width='';gp.style.height='';gp.style.zIndex='';
    gp.style.margin='';gp.style.borderRadius='';
  }
}

// ─── Theme toggle ───
var _themeDark=true;
function toggleTheme(){
  _themeDark=!_themeDark;
  var body=document.body;
  if(_themeDark){
    body.classList.remove('theme-light');
    document.getElementById('btn-theme-toggle').textContent='🌙 Dark';
  }else{
    body.classList.add('theme-light');
    document.getElementById('btn-theme-toggle').textContent='☀️ Light';
  }
}

// ─── Sidebar toggle ───
var _sidebarOpen=true;
function toggleSidebar(){
  _sidebarOpen=!_sidebarOpen;
  var sb=document.getElementById('sidebar');
  if(!sb)return;
  sb.classList.toggle('collapsed',!_sidebarOpen);
  var mn=document.querySelector('.main');
  if(mn){
    mn.classList.toggle('expanded',!_sidebarOpen);
    if(!_sidebarOpen)setTimeout(function(){mn.classList.add('centered');},350);
    else mn.classList.remove('centered');
  }
  var tb=document.getElementById('sidebar-toggle');
  if(tb){
    tb.classList.toggle('shifted',!_sidebarOpen);
    tb.textContent=_sidebarOpen?'◀':'▶';
    tb.title=_sidebarOpen?'Hide sidebar':'Show sidebar';
  }
}
// ─── Zoom controls ───
var _kgZoom=1;
function zoomKG(delta){
  _kgZoom=Math.max(0.5,Math.min(3,_kgZoom+delta));
  document.getElementById('kg-zoom-lvl').textContent=_kgZoom.toFixed(1)+'×';
  document.querySelectorAll('.knowledge-panel .zoom-wrap canvas').forEach(function(c){
    c.style.transform='scale('+_kgZoom+')';
    c.parentNode.style.height=Math.round(900*_kgZoom)+'px';
  });
}
// ─── Phase detail panel ───
function showPhaseDetail(phaseName,phaseIndex,di){
  var panel=document.getElementById('phase-detail-panel');
  if(!panel)return;
  document.getElementById('pd-title').textContent='🌀 '+phaseName+' Phase';
  var trace=state.traces.length>0?state.traces[state.traces.length-1]:null;
  var cost=trace&&trace.phase_durations_ms?trace.phase_durations_ms[phaseName.toLowerCase()]||'—':'—';
  var streams=trace&&trace.stream_activations?trace.stream_activations.map(function(s){return s.name;}).join(', '):'—';
  var mdVal=state.mdHistory.length>0?state.mdHistory[state.mdHistory.length-1].toFixed(2):'—';
  document.getElementById('pd-body').innerHTML=
    '<div class="pd-row"><span>DI</span><span>'+(di||'—')+'</span></div>'+
    '<div class="pd-row"><span>MD</span><span>'+mdVal+'</span></div>'+
    '<div class="pd-row"><span>Cost</span><span>'+cost+'ms</span></div>'+
    '<div class="pd-row"><span>Streams</span><span>'+streams+'</span></div>'+
    '<div class="pd-row"><span>Cycles</span><span>'+state.traces.length+'</span></div>';
  panel.style.display='block';
}

// ─── Pipeline Timeline ───
var PP=['PERCEIVE','STREAMS','SIMULATE','EVALUATE','SYNTHESIS','SELECT','COUNCIL','ACT','REFLECT'];
function renderPipelineTimeline(){
  var container=document.getElementById('pipeline-timeline');
  if(!container)return;
  var phases=PP;
  var doneCount=state.traces.length;
  container.innerHTML=phases.map(function(p,i){
    var status=i<doneCount?'done':i===doneCount?'active':'pending';
    var color=status==='done'?'#4ade80':status==='active'?'#fbbf24':'#2a2a3a';
    return '<div class="t-dot" style="background:'+color+';width:18px;height:18px;font-size:7px;" title="'+p+': '+status+'">'+
      (status==='done'?'✓':status==='active'?'▶':'')+'</div>';
  }).join('');
}

// ─── Resource Gauge ───
function animateResourceGauge(){
  var h=_lastHealthData||{di:0.5,compute:{c_compute:0.5,c_memory:0.5,c_bandwidth:0.5}};
  var c=h.compute||{c_compute:0.5,c_memory:0.5,c_bandwidth:0.5};
  var comp=Math.round((c.c_compute||0.5)*100);
  var mem=Math.round((c.c_memory||0.5)*100);
  var bw=Math.round((c.c_bandwidth||0.5)*100);
  var elc=document.getElementById('rg-comp');
  var elm=document.getElementById('rg-mem');
  var elb=document.getElementById('rg-bw');
  if(elc){elc.style.width=comp+'%';elc.style.background=comp>80?'#ff4444':comp>60?'#fbbf24':'#4ade80';}
  if(elm){elm.style.width=mem+'%';elm.style.background=mem>80?'#ff4444':mem>60?'#fbbf24':'#60a5fa';}
  if(elb){elb.style.width=bw+'%';elb.style.background=bw>80?'#ff4444':bw>60?'#fbbf24':'#fbbf24';}
  var vc=document.getElementById('rg-comp-val');
  var vm=document.getElementById('rg-mem-val');
  var vb=document.getElementById('rg-bw-val');
  if(vc)vc.textContent=comp+'%';
  if(vm)vm.textContent=mem+'%';
  if(vb)vb.textContent=bw+'%';
}

// ─── Aesthetic Health Meter ───
function drawHealthMeter(){
  var canvas=document.getElementById('health-meter-canvas');
  if(!canvas)return;
  var ctx=canvas.getContext('2d');
  var w=64,h=64,cx=32,cy=32,r=26;
  var diVal=state.diHistory.length>0?state.diHistory[state.diHistory.length-1]:0.5;
  var pulse=Math.sin(state.time*2)*0.1+0.9;
  var diFrac=diVal*pulse;
  ctx.clearRect(0,0,w,h);
  ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);
  ctx.strokeStyle='#1e1e2e';ctx.lineWidth=5;ctx.stroke();
  var startA=-Math.PI/2,endA=startA+diFrac*Math.PI*2;
  var grad=ctx.createConicGradient?ctx.createConicGradient(startA,cx,cy):null;
  var clr=diVal>0.8?'#4ade80':diVal>0.5?'#fbbf24':'#ff4444';
  ctx.beginPath();ctx.arc(cx,cy,r,startA,endA);
  ctx.strokeStyle=clr;ctx.lineWidth=5;ctx.lineCap='round';ctx.stroke();
  ctx.fillStyle='rgba(255,255,255,0.3)';ctx.font='bold 9px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillText('κA',cx,cy-3);
  ctx.fillStyle='rgba(255,255,255,0.5)';ctx.font='7px sans-serif';
  ctx.fillText((diVal*100).toFixed(0)+'%',cx,cy+10);
  var el=document.getElementById('hm-val');
  if(el)el.textContent=(diVal*100).toFixed(0)+'%';
  var sub=document.getElementById('hm-sub');
  if(sub)sub.textContent=diVal>0.8?'Healthy':diVal>0.5?'Adequate':'Needs attention';
}

// ─── Mini-map ───
function drawMinimap(){
  var canvas=document.getElementById('minimap-canvas');
  if(!canvas)return;
  var ctx=canvas.getContext('2d');
  var w=150,h=150;
  ctx.fillStyle='#0a0a0f';ctx.fillRect(0,0,w,h);
  var gs=state.gridSize||5;
  var cs=Math.floor(w/gs)-2;
  var ox=Math.floor((w-gs*cs)/2),oy=Math.floor((h-gs*cs)/2);
  for(var y=0;y<gs;y++){
    for(var x=0;x<gs;x++){
      var tt=getTerrainAt(x,y)||'plains';
      var col={plains:'#2d5a22',forest:'#0d3a18',water:'#0d3a6a',desert:'#a88e4a',mountain:'#5a5a6a',blocked:'#2a1a1a'};
      ctx.fillStyle=col[tt]||'#2d5a22';
      ctx.fillRect(ox+x*cs,oy+y*cs,cs,cs);
      ctx.strokeStyle='rgba(255,255,255,0.05)';ctx.lineWidth=0.5;
      ctx.strokeRect(ox+x*cs,oy+y*cs,cs,cs);
    }
  }
  // Goal
  var gx=state.goal[0],gy=state.goal[1];
  ctx.fillStyle='#fbbf24';ctx.beginPath();ctx.arc(ox+gx*cs+cs/2,oy+gy*cs+cs/2,3,0,Math.PI*2);ctx.fill();
  // Agent
  var ax=Math.round(state.animPos[0]),ay=Math.round(state.animPos[1]);
  ctx.fillStyle='#ff6b6b';ctx.beginPath();ctx.arc(ox+ax*cs+cs/2,oy+ay*cs+cs/2,3,0,Math.PI*2);ctx.fill();
  // Agent2
  if(state.agent2Pos){
    ctx.fillStyle='#60a5fa';ctx.beginPath();ctx.arc(ox+Math.round(state.agent2Pos[0])*cs+cs/2,oy+Math.round(state.agent2Pos[1])*cs+cs/2,2,0,Math.PI*2);ctx.fill();
  }
}

// ─── (toggleCostView, toggleHeatMode, toggleOmegaHeatmap, toggleAutoRefresh, scheduleAuto defined in gridworld.js / chat.js) ───
async function exportTraces() {
  const blob = new Blob([JSON.stringify(state.traces, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `telos_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
}

async function pollCheckpoints() {
  try {
    const resp = await fetch('/api/checkpoints');
    const traces = await resp.json();
    for (const t of traces) {
      if (!state.traces.some(x => x.cycle_id === t.cycle_id)) applyTrace(t);
    }
  } catch {}
  _lastUpdate = Date.now();
  // Also fetch health scores
  try {
    const hresp = await fetch('/api/health');
    const h = await hresp.json();
    _lastHealthData.di = typeof h.decision_integrity === 'number' ? h.decision_integrity : (state.diHistory.length > 0 ? state.diHistory[state.diHistory.length-1] : 0.5);
    if (h.resources) _lastHealthData.compute = h.resources;
    var _healthVal=typeof h.health==='number'?h.health:(state.diHistory.length>0?state.diHistory[state.diHistory.length-1]:null);
    var _systemVal=typeof h.system_score==='number'?h.system_score:(state.diHistory.length>0?state.diHistory[state.diHistory.length-1]:null);
    var _missionVal=typeof h.mission==='number'?h.mission:(state.diHistory.length>0?state.diHistory.slice(-3).reduce(function(a,b){return a+b;},0)/Math.max(state.diHistory.length,3):null);
    updateHealthDisplay(_healthVal,_systemVal,_missionVal);
    if (healthPanelVisible) fetchHealthDetail();
  } catch(e) {
    // API unavailable — use demo trace data as fallback
    var _d=state.diHistory.length>0?state.diHistory[state.diHistory.length-1]:null;
    updateHealthDisplay(_d,_d,_d?Math.max(0.3,Math.min(0.9,_d*0.8+0.2)):null);
  }
}

function updateHealthDisplay(hv,sv,mv){
  if (hv!==null&&hv>0) _displayTarget.health = hv;
  if (sv!==null&&sv>0) _displayTarget.system = sv;
  if (mv!==null&&mv>0) _displayTarget.mission = mv;
}
var healthPanelVisible = false;
var openSections = {};
function toggleHealth() {
  healthPanelVisible = !healthPanelVisible;
  var hp = document.getElementById('health-panel');
  if (hp) hp.style.display = healthPanelVisible ? 'block' : 'none';
  if (healthPanelVisible) fetchHealthDetail();
}
function toggleSection(id) {
  openSections[id] = !openSections[id];
  var body = document.getElementById('cat-body-'+id);
  var arr = document.getElementById('cat-arr-'+id);
  if (body) body.classList.toggle('open', openSections[id]);
  if (arr) arr.classList.toggle('open', openSections[id]);
}
async function fetchHealthDetail() {
  try {
    const r = await fetch('/api/benchmark');
    const d = await r.json();
    if (d.error) return;
    var cats = ['perception','learning','identity','knowledge','resources','projects','social'];
    var clrs = {'perception':'#4af','learning':'#4a4','identity':'#f4a','knowledge':'#a4f','resources':'#fa4','projects':'#4ff','social':'#f44'};
    var clbl = {'perception':'Perception','learning':'Learning','identity':'Identity','knowledge':'Knowledge','resources':'Resources','projects':'Projects','social':'Social'};
    var _diFallback=state.diHistory.length>0?state.diHistory[state.diHistory.length-1]:0.5;
    var h = d.system_score && d.system_score.current !== undefined ? d.system_score.current : _diFallback;
    var m = d.mission_score !== undefined ? d.mission_score : (state.diHistory.length>0?Math.max(0.3,Math.min(0.9,_diFallback*0.8+0.2)):0.5);
    var html = '<button onclick="toggleHealth()" style="position:absolute;top:12px;right:14px;background:none;border:none;color:#666;font-size:18px;cursor:pointer;">✕</button>';
    html += '<h2>🧠 Cognitive Health</h2><div class="hdr-scores">';
    html += '<div class="bx"><div class="val" style="color:#4af">'+(h*100).toFixed(0)+'%</div><div class="lbl">System Score</div></div>';
    html += '<div class="bx"><div class="val" style="color:#a4f">'+(m*100).toFixed(0)+'%</div><div class="lbl">Mission Score</div></div></div>';
    cats.forEach(function(c){
      var s = d.epochs && d.epochs.last_10 ? d.epochs.last_10[c] : null;
      if (!s) return;
      var sc = s.score !== undefined ? Math.min(1, Math.max(0, s.score)) * 100 : 0;
      var pct = sc.toFixed(0);
      var cclr = clrs[c] || '#888';
      html += '<div class="cat">';
      html += '<div class="cat-hdr" onclick="toggleSection(\''+c+'\')">';
      html += '<span class="arr" id="cat-arr-'+c+'">▶</span>';
      html += '<span class="nm">'+clbl[c]+'</span>';
      html += '<span class="sc" style="color:'+cclr+'">'+pct+'%</span>';
      html += '<div class="pbar"><div class="fl" style="width:'+pct+'%;background:'+cclr+'"></div></div>';
      html += '</div>';
      html += '<div class="cat-body" id="cat-body-'+c+'">';
      html += '<div class="cat-body-inner">';
      if (s.metrics) {
        for (var k in s.metrics) {
          var v = typeof s.metrics[k] === 'number' ? (s.metrics[k] * 100).toFixed(1) : s.metrics[k];
          html += '<div class="m"><span>'+k+'</span><span class="mv"><span class="num">'+v+'</span>%</span></div>';
        }
      }
      html += '</div></div></div>';
    });
    document.getElementById('health-content').innerHTML = html;
  } catch(e) { console.warn('Health detail failed:', e); }
}
function connectWebSocket() {
  try {
    const ws = new WebSocket('ws://localhost:8766');
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d.type === 'overview' && d.overview) { renderOverview(d.overview); }
        else if (d.decision_trace) { applyTrace(d.decision_trace); _refreshAfterTrace(); }
        else if (d.type === 'trace') { applyTrace(d); _refreshAfterTrace(); }
      } catch {}
    };
    ws.onclose = () => setTimeout(connectWebSocket, 3000);
    ws.onerror = () => setTimeout(connectWebSocket, 3000);
  } catch {}
}

document.addEventListener('DOMContentLoaded', () => {
  // Drag/orbit + click-to-set-goal
  const gc = document.getElementById('grid-canvas');
  if (gc) {
    let dragging = false, startX, startY, moved = false;
    let initialX = 0, initialY = 0;  // frozen at mousedown for cumulative drag detection
    gc.onmousedown = (e) => {
      e.preventDefault();
      if (e.button === 1) {
        ISO.rotY = -0.6; ISO.rotX = -0.4; ISO.zoom = 1; ISO.camX = 0; ISO.camY = 0;
        return;
      }
      dragging = true;
      moved = false;
      startX = e.clientX;
      startY = e.clientY;
      initialX = e.clientX;
      initialY = e.clientY;
      gc.style.cursor = 'grabbing';
    };
    gc.onmousemove = (e) => {
      // Hover tracking for tooltip (Feature 2)
      if (!dragging) {
        const rect = gc.getBoundingClientRect();
        const mx = (e.clientX - rect.left) * (gc.width / rect.width);
        const my = (e.clientY - rect.top) * (gc.height / rect.height);
        let bestDist = Infinity, bestCell = null;
        for (let y = 0; y < state.gridSize; y++) {
          for (let x = 0; x < state.gridSize; x++) {
            const p = isoToScreen(x, y);
            const d = Math.hypot(mx - p.sx, my - p.sy);
            if (d < bestDist && d < ISO.tw * ISO.zoom * 0.5) { bestDist = d; bestCell = [x, y]; }
          }
        }
        state.hoveredCell = bestCell;
        if (bestCell) {
          const p = isoToScreen(bestCell[0], bestCell[1]);
          const ttt = getTerrainAt(bestCell[0], bestCell[1]);
          const hp = (TH[ttt] || 0) * ISO.hs;
          const br = Math.sin((state.time || 0) * 1.5) * 1.5;
          const ty = hp >= 0 ? p.sy - hp * ISO.zoom + br : p.sy + br;
          state.hoverPos = { sx: p.sx, sy: ty };
        } else {
          state.hoverPos = null;
        }
        return;
      }
      if (Math.abs(e.clientX - initialX) > 3 || Math.abs(e.clientY - initialY) > 3) moved = true;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      ISO.rotY += dx * 0.01;
      ISO.rotX = Math.max(-1.5, Math.min(0, ISO.rotX - dy * 0.008));
      startX = e.clientX;
      startY = e.clientY;
    };
    gc.onmouseup = (e) => {
      dragging = false;
      gc.style.cursor = 'grab';
      if (moved) return;
      const rect = gc.getBoundingClientRect();
      const mx = (e.clientX - rect.left) * (gc.width / rect.width);
      const my = (e.clientY - rect.top) * (gc.height / rect.height);
      let bestDist = Infinity, bestCell = null;
      for (let y = 0; y < state.gridSize; y++) {
        for (let x = 0; x < state.gridSize; x++) {
          const p = isoToScreen(x, y);
          const d = Math.hypot(mx - p.sx, my - p.sy);
          if (d < bestDist && d < ISO.tw * ISO.zoom * 0.5) { bestDist = d; bestCell = [x, y]; }
        }
      }
      if (bestCell) { state.goal = bestCell; document.getElementById('step-counter').textContent = `Goal → (${bestCell[0]},${bestCell[1]})`; }
    };
    gc.onmouseleave = () => { dragging = false; gc.style.cursor = 'grab'; state.hoveredCell = null; state.hoverPos = null; };
    // Touch support for mobile orbit
    gc.ontouchstart = (e) => { const t = e.touches[0]; dragging = true; moved = false; startX = t.clientX; startY = t.clientY; initialX = t.clientX; initialY = t.clientY; };
    gc.ontouchmove = (e) => { if (!dragging) return; if (Math.abs(e.touches[0].clientX - initialX) > 3 || Math.abs(e.touches[0].clientY - initialY) > 3) moved = true; const dx = e.touches[0].clientX - startX; const dy = e.touches[0].clientY - startY; ISO.rotY += dx * 0.01; ISO.rotX = Math.max(-1.5, Math.min(0, ISO.rotX - dy * 0.008)); startX = e.touches[0].clientX; startY = e.touches[0].clientY; };
    gc.ontouchend = () => { dragging = false; };
    // Use addEventListener with {passive: false} so preventDefault() is honoured (critical on macOS)
    gc.addEventListener('wheel', (e) => {
      e.preventDefault();
      ISO.zoom = Math.max(0.3, Math.min(3, ISO.zoom - e.deltaY * 0.001));
    }, { passive: false });
  }

  state.shortestPath = computeShortestPath();
  renderGrid();
  renderChart();
  resizeKgCanvas();
  window.addEventListener('resize', resizeKgCanvas);
  animate();
});
var _animCounter = 0;
 function animate() {
   state.time += 0.016;
   _animCounter++;
   if (_animCounter === 1) _dbg('Animation started');
   if (_animCounter === 60) _dbg('Animation running (' + kgNodes.length + ' KG nodes)');
   state.animT = Math.min(1, state.animT + 0.025);
   const e = 1 - Math.pow(1 - state.animT, 3);
   state.animPos[0] = state.prevPos[0] + (state.position[0] - state.prevPos[0]) * e;
   state.animPos[1] = state.prevPos[1] + (state.position[1] - state.prevPos[1]) * e;

   // Agent motion is driven ONLY by real trace data (state.position /
   // state.agent2Pos are updated in applyTrace from live cycles). No
   // random goals, no fabricated motion — the grid is honest.

  // Knowledge graph nodes/edges come ONLY from /api/knowledge
  // (fetchKnowledge in knowledge-graph.js) — real serialized data,
  // never generated here from traces or randomness.
  // Honest boot state lives in knowledge-graph.js (empty set until data).

   try { renderGrid(); } catch (er) { console.warn('Grid render error:', er); }
   try { renderChart(); } catch (er) { console.warn('Chart render error:', er); }
   try { renderMemoryTimeline(); } catch (er) {}
   // KG drawn by 5-mode rAF loop above
   try { renderPipelineTimeline(); } catch (er) {}
   try { animateResourceGauge(); } catch (er) {}
   try { drawHealthMeter(); } catch (er) {}
   try { drawMinimap(); } catch (er) {}
   try { spawnParticles(); } catch (er) {}
   // Smooth sidebar value interpolation
   try {
     ['di','md','cycles','health','system','mission','score','worlds'].forEach(function(k){
       var t = _displayTarget[k];
       var c = _display[k];
       var p = _displayPrev[k];
       if (typeof t === 'number' && typeof c === 'number') {
         if (Math.abs(t - c) < 0.001) { _display[k] = t; }
         else { _display[k] = c + (t - c) * 0.15; }
       } else if (typeof t === 'number') {
         _display[k] = t; // snap from null (honest empty) to the first real value
       }
     });
     var diEl = document.getElementById('di-value');
     if (diEl) {
       var diD = _display.di;
       var diPrev = _displayPrev.di;
       if (Math.abs(diD - diPrev) > 0.005) { diEl.textContent = diD.toFixed(3); popValue(diEl); _displayPrev.di = diD; }
       else { diEl.textContent = diD.toFixed(3); }
     }
     var mdEl = document.getElementById('md-value');
     if (mdEl) {
       var mdD = _display.md;
       var mdPrev = _displayPrev.md;
       if (Math.abs(mdD - mdPrev) > 0.005) { mdEl.textContent = mdD.toFixed(3); popValue(mdEl); _displayPrev.md = mdD; }
       else { mdEl.textContent = mdD.toFixed(3); }
     }
     var cyEl = document.getElementById('cycles-value');
     if (cyEl) {
       var cyD = Math.round(_display.cycles);
       if (cyD !== _displayPrev.cycles) { cyEl.textContent = cyD; popValue(cyEl); _displayPrev.cycles = cyD; }
       else { cyEl.textContent = cyD; }
     }
     var scEl = document.getElementById('score-value');
     if (scEl) {
       if (typeof _display.score === 'number' && isFinite(_display.score)) {
         var scD = Math.round(_display.score);
         if (scD !== _displayPrev.score) { scEl.textContent = scD; popValue(scEl); _displayPrev.score = scD; }
         else { scEl.textContent = scD; }
       } else {
         if (scEl.textContent !== '\u2014') { scEl.textContent = '\u2014'; }
       }
     }
     var wEl = document.getElementById('worlds-value');
     if (wEl) {
       var wD = Math.round(_display.worlds);
       if (wD !== _displayPrev.worlds) { wEl.textContent = wD; popValue(wEl); _displayPrev.worlds = wD; }
       else { wEl.textContent = wD; }
     }
     var hEl = document.getElementById('health-score');
     if (hEl) {
       var hD = _display.health;
       var hStr = hD > 0 ? (hD * 100).toFixed(0) + '%' : '--';
       if (hStr !== hEl.textContent) { hEl.textContent = hStr; popValue(hEl.parentElement); }
       else { hEl.textContent = hStr; }
     }
     var sEl = document.getElementById('system-score');
     if (sEl) {
       var sysD = _display.system;
       var sysStr = sysD > 0 ? (sysD * 100).toFixed(0) + '%' : '--';
       if (sysStr !== sEl.textContent) { sEl.textContent = sysStr; popValue(sEl.parentElement); }
       else { sEl.textContent = sysStr; }
     }
     var mEl = document.getElementById('mission-score');
     if (mEl) {
       var misD = _display.mission;
       var misStr = misD > 0 ? (misD * 100).toFixed(0) + '%' : '--';
       if (misStr !== mEl.textContent) { mEl.textContent = misStr; popValue(mEl.parentElement); }
       else { mEl.textContent = misStr; }
     }
     // Live clock update
     var clockEl = document.getElementById('live-clock');
     if (clockEl && _lastUpdate) {
       var secs = Math.floor((Date.now() - _lastUpdate) / 1000);
       clockEl.textContent = secs < 5 ? 'just now' : secs + 's ago';
     }
   } catch (er) {}
   requestAnimationFrame(animate);
 }

// ─── Debug console logger ───
var _dbg = function(msg) { console.log('[TELOS]', msg); try { var e = document.getElementById('debug-log'); if (e) e.textContent = msg; } catch(ex) {} };

// ─── Learning ticker — show data freshness ───
setInterval(function() {
  var ticker = document.getElementById('learning-ticker');
  if (!ticker) return;
  if (_lastUpdate) {
    var s = Math.floor((Date.now() - _lastUpdate) / 1000);
    var traceCount = state.traces.length;
    var di = _displayTarget.di || 0;
    ticker.textContent = '🌀 ' + traceCount + ' cycles · DI ' + (di * 100).toFixed(0) + '% · updated ' + (s < 5 ? 'just now' : s + 's ago');
  } else {
    ticker.textContent = '🌀 System idle — waiting for data...';
  }
}, 2000);

// ─── Boot ───
_dbg('Starting dashboard...');

loadCheckpoints();
pollCheckpoints();
connectWebSocket();
setInterval(pollCheckpoints, 5000);
// fetchKnowledge lives in knowledge-graph.js, which loads AFTER this file.
// Calling it at parse time throws ReferenceError, so the initial knowledge
// fetch never ran (only the 30s interval did). Defer to DOMContentLoaded.
document.addEventListener('DOMContentLoaded', function() {
  fetchKnowledge();
  fetchOverview();
  setInterval(fetchKnowledge, 5000);
  setInterval(fetchOverview, 5000);
});

// Throttled re-fetch after a live trace push (max once per 2s) so the
// knowledge graph + story track the producer without hammering the API.
var _lastTraceRefresh = 0;
function _refreshAfterTrace() {
  var now = Date.now();
  if (now - _lastTraceRefresh < 2000) return;
  _lastTraceRefresh = now;
  fetchKnowledge();
  fetchOverview();
}

