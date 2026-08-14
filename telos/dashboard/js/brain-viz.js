// TELOS Brain Visualization Module — v5 "Activation Aurora" + "Synapse Rhizome".
//
// Both modes are built on REAL per-cycle signals, never a fake timer:
//   * stream_activations (names + real priorities) from the latest trace;
//   * diHistory / mdHistory (real per-cycle series);
//   * meta_cognition.mode + current_state (real cognition-mode readouts);
//   * attention_metrics.identity_entropy, system_mood (real);
//   * per-stream MEAN priority over recent cycles (computed from real
//     traces — drives the rhizome root lengths).
// The 9 pipeline phases and 6 identity layers are STRUCTURE (architectural
// constants, labeled + clickable) — there is no real per-phase duration in
// the trace, so no phase is ever faked as "active". The phase ring carries
// the REAL cognition MODE instead (PLAN / DELEGATE / ...).
//
// Honesty: the previous hardcoded core label (a static name that was not a
// real trace field) is gone; the core now reads 'TELOS · CORE' with the real
// mood underneath.
// No rainbow: every hue is a semantic stream/domain color.

var _BRAIN_PHASES = ['PERCEIVE','STREAMS','SIMULATE','EVALUATE','SYNTHESIS','SELECT','COUNCIL','ACT','REFLECT'];
var _brainPaused=false;
var _lastHealthData={di:0.5, compute:{c_compute:0.5,c_memory:0.5,c_bandwidth:0.5}};
var _brainOrbitAngle=0;
var _brainPhasePositions=[];
var _hoveredPhase=-1;
var _brainDragState={active:false,startX:0,startY:0,startAngle:0};

// ─── Semantic stream palette (single source; extends dashboard.js SC) ───
var _STREAM_COLORS = {
  'ReflexStream':    '#ff6b6b',
  'PerceptionStream':'#4ade80',
  'MemoryStream':    '#60a5fa',
  'InquiryStream':   '#7d97ff',
  'PlanningStream':  '#fbbf24',
  'TheoryStream':    '#c084fc',
};
function streamColor(name) { return _STREAM_COLORS[name] || '#8f89ad'; }

// ─── Real data accessors (all measured, honest) ───
function _latestStreams() {
  var tr = state.traces[state.traces.length - 1];
  if (tr && Array.isArray(tr.stream_activations)) return tr.stream_activations;
  return [];
}
function _streamMeanPriorities() {
  // Mean REAL priority per stream across recent cycles (rhizome roots).
  var sums = {}, counts = {};
  var hist = state.streamHistory || [];
  var slice = hist.slice(-30);
  for (var i = 0; i < slice.length; i++) {
    var strs = slice[i].streams || [];
    for (var j = 0; j < strs.length; j++) {
      var s = strs[j];
      if (!s || !s.name) continue;
      sums[s.name] = (sums[s.name] || 0) + (s.priority || 0);
      counts[s.name] = (counts[s.name] || 0) + 1;
    }
  }
  var out = [];
  for (var k in sums) out.push({ name: k, mean: sums[k] / counts[k], seen: counts[k] });
  out.sort(function (a, b) { return b.mean - a.mean; });
  return out;
}
function _di() {
  return state.diHistory.length > 0 ? state.diHistory[state.diHistory.length - 1] : 0.5;
}
function _diTint() {
  var v = _di();
  return v > 0.8 ? '74,222,128' : v > 0.5 ? '251,191,36' : '255,68,68';
}

(function(){
  var bco=document.getElementById('brain-orbit');
  var bct=document.getElementById('brain-tree');
  if(!bco||!bct)return;
  var co=bco.getContext('2d'), ct=bct.getContext('2d');
  if(!co||!ct)return;
  var P=_BRAIN_PHASES;
  var L_=['Core','Narrative','Mission','Project','Method','Action'];
  var to=0; var _co=co, _bco=bco;
  var tt=0; var _ct=ct, _bct=bct;

  // ── MODE 1: ACTIVATION AURORA (brain-orbit) ──
  // DI tints the whole sky (score-tinted sky dome, wc26 spirit); the REAL
  // stream priorities are flowing aurora ribbons; phases are structure.
  function drawAurora() {
    if(!_brainPaused && !window.__reducedMotion)to+=0.02;
    var diVal=_di();
    var ringClr=_diTint();
    var w=_bco.width=_bco.clientWidth||280, h=_bco.height=_bco.clientHeight||800;
    var cx=w/2, cy=h/2, R=Math.min(w,h)*0.46;

    // Sky tinted by REAL DI (like the reference's score-tinted sky dome).
    var tint = diVal > 0.8 ? '22,48,34' : diVal > 0.5 ? '44,38,18' : '44,20,20';
    var bg=_co.createRadialGradient(cx,cy,0,cx,cy,Math.max(w,h)*0.72);
    bg.addColorStop(0,'rgba('+tint+',0.55)');
    bg.addColorStop(0.5,'#0d0a1a');
    bg.addColorStop(1,'#070512');
    _co.fillStyle=bg; _co.fillRect(0,0,w,h);

    // Header (mono editorial).
    _co.fillStyle='rgba(241,239,248,0.85)';
    _co.font='13px "Space Mono", monospace';
    _co.textAlign='left'; _co.textBaseline='top';
    _co.fillText('ACTIVATION AURORA — stream energy, measured',14,12);

    // ── Identity-layer structure rings (architectural constant) ──
    for(var li=0;li<L_.length;li++){
      var ri=R*(0.22+li*0.12);
      _co.beginPath(); _co.arc(cx,cy,ri,0,Math.PI*2);
      _co.strokeStyle='rgba('+ringClr+','+(0.04+li*0.02)+')';
      _co.lineWidth=1.0; _co.stroke();
      _co.fillStyle='rgba(241,239,248,'+(0.05+li*0.015)+')';
      _co.font='13px "Space Mono", monospace'; _co.textAlign='left'; _co.textBaseline='middle';
      _co.fillText(L_[li],cx+ri+8,cy+1);
    }

    // ── REAL stream ribbons (aurora): brightness/width ∝ real priority ──
    var streams=_latestStreams();
    if(streams.length===0&&state.traces.length===0){
      _co.fillStyle='rgba(143,137,173,0.85)';
      _co.font='13px "Space Mono", monospace'; _co.textAlign='center'; _co.textBaseline='middle';
      _co.fillText('awaiting the first real stream activation…',cx,h/2+30);
    }
    var lead=null;
    for(var si=0;si<streams.length;si++){
      var s=streams[si];
      if(!s||!s.name)continue;
      var pr = (typeof s.priority==='number')?s.priority:(typeof s.activation==='number'?s.activation:0);
      if(!lead||pr>(typeof lead.priority==='number'?lead.priority:0))lead=s;
      var col=streamColor(s.name);
      var band=R*(0.40+si*0.09);
      var amp=6+pr*14;                       // REAL priority → energy
      _co.beginPath();
      var pts=[];
      for(var a=0;a<=Math.PI*2;a+=0.07){
        var wob=Math.sin(a*5+to*(0.8+pr)+si*2)*amp*0.5+Math.sin(a*8+to*1.3+si)*amp*0.3;
        var rx=cx+Math.cos(a)*(band+wob);
        var ry=cy+Math.sin(a)*(band*0.72+wob*0.72);
        pts.push([rx,ry]);
        if(a===0)_co.moveTo(rx,ry); else _co.lineTo(rx,ry);
      }
      _co.strokeStyle=col;
      _co.globalAlpha=0.18+pr*0.5;           // REAL priority → presence
      _co.lineWidth=2+pr*3.5;
      _co.stroke();
      // bright core filament for the top stream
      if(lead===s){
        _co.globalAlpha=0.35+pr*0.4;
        _co.lineWidth=1;
        _co.stroke();
      }
      _co.globalAlpha=1;
      // Stream label at its band (real name + priority).
      var la=(-Math.PI/2+si*0.55)+Math.sin(to*0.2+si)*0.05;
      var lx=cx+Math.cos(la)*(band+amp+10), ly=cy+Math.sin(la)*(band*0.72+amp*0.72+8);
      _co.fillStyle=col;
      _co.font='13px "Space Mono", monospace';
      _co.textAlign='center'; _co.textBaseline='middle';
      _co.fillText(s.name.replace('Stream','').toUpperCase()+' '+(pr*100).toFixed(0)+'%',lx,ly);
    }

    // ── Phase ring: STRUCTURE ticks + REAL cognition-mode marker ──
    _brainPhasePositions=[];
    for(var i=0;i<P.length;i++){
      var aa=(i/P.length)*Math.PI*2-Math.PI/2+_brainOrbitAngle;
      var ppx=cx+Math.cos(aa)*R, ppy=cy+Math.sin(aa)*R*0.78;
      var pu=6+Math.sin(to*1.2+i*1.1)*1.5;
      _brainPhasePositions.push({x:ppx,y:ppy,name:P[i],color:'#8f89ad',index:i,active:false,size:pu});
      _co.fillStyle='rgba(143,137,173,0.8)';
      _co.beginPath(); _co.arc(ppx,ppy,pu,0,Math.PI*2); _co.fill();
      _co.fillStyle='rgba(200,198,222,0.8)';
      _co.font='13px "Space Mono", monospace'; _co.textAlign='center'; _co.textBaseline='top';
      _co.fillText(P[i],ppx,ppy+pu+4);
    }
    // Real cognition mode marker (meta_cognition.mode).
    var mode=state.metaMode||'—';
    var modeA=(-Math.PI/2)+(to*0.05)%(Math.PI*2)+_brainOrbitAngle;
    var mx=cx+Math.cos(modeA)*R, my=cy+Math.sin(modeA)*R*0.78;
    var mg=_co.createRadialGradient(mx,my,0,mx,my,34);
    mg.addColorStop(0,'rgba(125,151,255,0.5)'); mg.addColorStop(1,'transparent');
    _co.fillStyle=mg; _co.beginPath(); _co.arc(mx,my,34,0,Math.PI*2); _co.fill();
    _co.fillStyle='#7d97ff';
    _co.beginPath(); _co.arc(mx,my,7,0,Math.PI*2); _co.fill();
    _co.fillStyle='rgba(183,178,214,0.95)';
    _co.font='13px "Space Mono", monospace'; _co.textAlign='center'; _co.textBaseline='top';
    _co.fillText('MODE · '+mode+(state.metaState?(' / '+state.metaState.toUpperCase()):''),mx,my+12);

    // ── Core: TELOS + REAL mood (no invented core name — real fields only) ──
    _co.shadowColor='rgba(0,0,0,0.8)'; _co.shadowBlur=12;
    _co.fillStyle='rgba(241,239,248,0.95)';
    _co.font='bold 22px "Space Mono", monospace'; _co.textAlign='center'; _co.textBaseline='middle';
    _co.fillText('TELOS',cx,cy-2);
    _co.shadowBlur=0;
    _co.fillStyle='rgba(143,137,173,0.9)';
    _co.font='13px "Space Mono", monospace';
    _co.fillText('CORE',cx,cy+16);
    if(state.sysMood){
      _co.fillStyle='rgba(125,151,255,0.95)';
      _co.fillText('MOOD · '+String(state.sysMood).toUpperCase(),cx,cy+34);
    }

    // ── Real readout rail (bottom) ──
    var ent = (state.attn && typeof state.attn.identity_entropy==='number') ? state.attn.identity_entropy.toFixed(1) : '—';
    _co.fillStyle='rgba(143,137,173,0.9)';
    _co.font='13px "Space Mono", monospace'; _co.textAlign='left'; _co.textBaseline='bottom';
    _co.fillText('DI '+ (diVal*100).toFixed(0)+'% · ENTROPY '+ent,14,h-10);
    _co.textAlign='center';

    // Hover tooltip (real values only).
    if(_hoveredPhase>=0&&_hoveredPhase<P.length&&_brainPhasePositions[_hoveredPhase]){
      var hp=_brainPhasePositions[_hoveredPhase];
      var hpx=hp.x,hpy=hp.y-24;
      var hw=190,hh=36;
      var hx2=Math.max(2,Math.min(w-hw-2,hpx-hw/2));
      var hy2=Math.max(2,hpy-hh-2);
      _co.save();
      _co.shadowColor='rgba(0,0,0,0.5)';_co.shadowBlur=10;
      _co.fillStyle='rgba(10,10,22,0.92)';_co.strokeStyle='rgba(80,80,140,0.3)';_co.lineWidth=1;
      roundRect(_co,hx2,hy2,hw,hh,6);_co.fill();_co.stroke();
      _co.shadowBlur=0;
      _co.fillStyle='#ddd';_co.font='bold 13px "Space Mono", monospace';_co.textAlign='left';_co.textBaseline='top';
      _co.fillText(P[_hoveredPhase],hx2+8,hy2+6);
      _co.fillStyle='#888';_co.font='13px "Space Mono", monospace';
      _co.fillText('DI '+diVal.toFixed(2)+' · pipeline phase (structure)',hx2+8,hy2+22);
      _co.restore();
    }
  }

  // ── MODE 2: SYNAPSE RHIZOME (brain-tree) ──
  // Trunk = growth rings of REAL DI history; roots = REAL streams with
  // length ∝ mean priority; canopy = phase structure + REAL mood tint.
  function drawRhizome() {
    if(!_brainPaused && !window.__reducedMotion)tt+=0.02;
    var w=_bct.width=_bct.clientWidth||280, h=_bct.height=_bct.clientHeight||800;
    var bg=_ct.createRadialGradient(w/2,h*0.2,0,w/2,h*0.2,Math.max(w,h)*0.75);
    bg.addColorStop(0,'#131027'); bg.addColorStop(1,'#070512');
    _ct.fillStyle=bg; _ct.fillRect(0,0,w,h);
    _ct.fillStyle='rgba(241,239,248,0.85)';
    _ct.font='13px "Space Mono", monospace'; _ct.textAlign='left'; _ct.textBaseline='top';
    _ct.fillText('SYNAPSE RHIZOME — streams as roots, DI as growth rings',14,12);
    _ct.textAlign='center';

    var rx=w/2, baseY=h-40, trunkH=Math.min(h*0.42, 300);

    // ── Trunk: growth rings from REAL diHistory ──
    var hist=state.diHistory||[];
    var ringCount=Math.min(hist.length, 40);
    _ct.fillStyle='rgba(50,40,35,0.35)';
    _ct.fillRect(rx-9, baseY-trunkH, 18, trunkH);
    for(var ri=0;ri<ringCount;ri++){
      var v=hist[hist.length-1-ri]||0.5;
      var y=baseY-trunkH*(1-ri/ringCount);
      var col=v>0.8?'74,222,128':v>0.5?'251,191,36':'255,68,68';
      _ct.fillStyle='rgba('+col+','+(0.16+v*0.16)+')';
      _ct.fillRect(rx-9, y-1, 18, Math.max(2, trunkH/ringCount));
    }
    // Trunk label (real cycle count).
    _ct.fillStyle='rgba(200,198,222,0.85)';
    _ct.font='13px "Space Mono", monospace'; _ct.textAlign='center'; _ct.textBaseline='top';
    _ct.fillText('TRUNK · '+hist.length+' CYCLES', rx, baseY-trunkH-18);

    // ── Roots: REAL streams, length ∝ mean priority over recent cycles ──
    var roots=_streamMeanPriorities();
    var rootCount=roots.length||1;
    for(var ri2=0;ri2<roots.length;ri2++){
      var r=roots[ri2];
      var ang=-Math.PI/2+Math.PI*0.18+(ri2/(Math.max(1,rootCount-1)))*Math.PI*0.64;
      var len=(26+r.mean*70)*(0.9+Math.sin(tt*0.6+ri2)*0.06);
      var ex=rx+Math.cos(ang)*len, ey=baseY+Math.sin(ang)*len;
      _ct.beginPath(); _ct.moveTo(rx,baseY);
      _ct.quadraticCurveTo(rx+Math.cos(ang)*len*0.5,baseY+Math.sin(ang)*len*0.5-6,ex,ey);
      _ct.strokeStyle=streamColor(r.name);
      _ct.globalAlpha=0.55+r.mean*0.45;
      _ct.lineWidth=2.5+r.mean*4;
      _ct.stroke();
      _ct.globalAlpha=1;
      _ct.fillStyle=streamColor(r.name);
      _ct.font='13px "Space Mono", monospace'; _ct.textAlign='center'; _ct.textBaseline='top';
      _ct.fillText(r.name.replace('Stream','').toUpperCase()+' '+(r.mean*100).toFixed(0)+'%', ex, ey+2);
    }
    if(roots.length===0&&state.traces.length===0){
      _ct.fillStyle='rgba(143,137,173,0.85)';
      _ct.font='13px "Space Mono", monospace'; _ct.textAlign='center'; _ct.textBaseline='middle';
      _ct.fillText('awaiting the first real stream activation…',rx,h/2+30);
      _ct.textAlign='center';
    }

    // ── Canopy: phase structure, glow tinted by REAL mood ──
    var moodTint='125,151,255';
    var mood=state.sysMood?String(state.sysMood).toLowerCase():'';
    if(mood.indexOf('confident')>=0||mood.indexOf('explor')>=0)moodTint='74,222,128';
    else if(mood.indexOf('cautious')>=0||mood.indexOf('neutral')>=0)moodTint='125,151,255';
    else if(mood.indexOf('stress')>=0||mood.indexOf('anxious')>=0)moodTint='255,107,107';
    var cpY=baseY-trunkH-30, cpR=Math.min(w,h)*0.40;
    var cg=_ct.createRadialGradient(rx,cpY-10,0,rx,cpY-10,cpR*1.4);
    cg.addColorStop(0,'rgba('+moodTint+',0.22)'); cg.addColorStop(1,'transparent');
    _ct.fillStyle=cg; _ct.fillRect(rx-cpR*1.4,cpY-10-cpR*1.4,cpR*2.8,cpR*2.8);
    for(var i=0;i<P.length;i++){
      var ang=-Math.PI+(i/(P.length-1))*Math.PI;
      var bx=rx+Math.cos(ang)*cpR*0.8, by=cpY+Math.sin(ang)*cpR*0.52;
      _ct.beginPath(); _ct.moveTo(rx,cpY);
      _ct.quadraticCurveTo(rx+Math.cos(ang)*cpR*0.3,cpY+Math.sin(ang)*cpR*0.16-6,bx,by);
      _ct.strokeStyle='rgba('+moodTint+',0.22)'; _ct.lineWidth=1; _ct.stroke();
      var pu=6.5+Math.sin(tt*1.2+i*0.9)*1.2;
      _ct.fillStyle='rgba('+moodTint+',0.8)';
      _ct.beginPath(); _ct.arc(bx,by,pu,0,Math.PI*2); _ct.fill();
      _ct.fillStyle='rgba(200,198,222,0.85)';
      _ct.font='13px "Space Mono", monospace'; _ct.textAlign='center'; _ct.textBaseline='top';
      _ct.fillText(P[i],bx,by+pu+3);
    }
    _ct.fillStyle='rgba(241,239,248,0.8)';
    _ct.font='13px "Space Mono", monospace'; _ct.textAlign='center'; _ct.textBaseline='bottom';
    _ct.fillText('CANOPY · MODE '+ (state.metaMode||'—'), rx, cpY-cpR*0.52-8);

    // ── Real readout rail: latest decision intent ──
    var intent=state.latestIntent?String(state.latestIntent).replace(/_/g,' ').toUpperCase():'—';
    _ct.fillStyle='rgba(143,137,173,0.9)';
    _ct.font='13px "Space Mono", monospace'; _ct.textAlign='left'; _ct.textBaseline='bottom';
    _ct.fillText('LAST MOVE · '+intent,14,h-10);
    _ct.textAlign='center';

    var bd=document.getElementById('brain-debug');
    if(bd)bd.textContent='Aurora / Rhizome — lead stream: '+(roots.length?roots[0].name.replace('Stream',''):'—');
  }

  function draw(){
    try{
      drawAurora();
      drawRhizome();
    }catch(e){}
    requestAnimationFrame(draw);
  }
  draw();
})();

// ─── Brain orbit mouse drag (pan the phase ring) ───
(function(){
  var boc=document.getElementById('brain-orbit');
  if(!boc)return;
  boc.addEventListener('mousedown',function(e){
    _brainDragState.active=true;
    _brainDragState.startX=e.clientX;
    _brainDragState.startY=e.clientY;
    _brainDragState.startAngle=_brainOrbitAngle;
  });
  window.addEventListener('mousemove',function(e){
    if(!_brainDragState.active)return;
    var dx=e.clientX-_brainDragState.startX;
    _brainOrbitAngle=_brainDragState.startAngle+dx*0.008;
  });
  window.addEventListener('mouseup',function(){_brainDragState.active=false;});
  boc.addEventListener('mousemove',function(e){
    var rect=boc.getBoundingClientRect();
    var mx=e.clientX-rect.left,my=e.clientY-rect.top;
    var found=-1;
    for(var i=0;i<_brainPhasePositions.length;i++){
      var p=_brainPhasePositions[i];
      var d2=(mx-p.x)*(mx-p.x)+(my-p.y)*(my-p.y);
      if(d2<1600){found=i;break;}
    }
    _hoveredPhase=found;
  });
  boc.addEventListener('mouseleave',function(){_hoveredPhase=-1;});
  boc.addEventListener('click',function(e){
    var rect=boc.getBoundingClientRect();
    var mx=e.clientX-rect.left,my=e.clientY-rect.top;
    for(var i=0;i<_brainPhasePositions.length;i++){
      var p=_brainPhasePositions[i];
      var d2=(mx-p.x)*(mx-p.x)+(my-p.y)*(my-p.y);
      if(d2<1600){
        showPhaseDetail(_BRAIN_PHASES[i], i,
          state.diHistory.length > 0 ? state.diHistory[state.diHistory.length-1] : 0.5);
        return;
      }
    }
  });
})();

// ─── Pause/Resume for brain ───
function toggleBrainPause(){
  _brainPaused=!_brainPaused;
  document.querySelectorAll('.brain-pause-btn').forEach(function(btn){btn.textContent=_brainPaused?'▶ Play':'⏸ Pause';});
}

// ─── Fullscreen for brain ───
var _brainFullscreen=false;
function toggleBrainFullscreen(btn){
  _brainFullscreen=!_brainFullscreen;
  // Each mind mode is now its own section/panel — fullscreen the panel the
  // button lives in (fallback: first panel, pre-split behaviour).
  var bp = btn && btn.closest ? btn.closest('.brain-panel') : document.querySelector('.brain-panel');
  if(!bp)return;
  if(_brainFullscreen){
    bp.style.position='fixed';bp.style.top='0';bp.style.left='0';
    bp.style.width='100vw';bp.style.height='100vh';bp.style.zIndex='1000';
    bp.style.margin='0';bp.style.borderRadius='0';
  }else{
    bp.style.position='';bp.style.top='';bp.style.left='';
    bp.style.width='';bp.style.height='';bp.style.zIndex='';
    bp.style.margin='';bp.style.borderRadius='';
  }
}

// ─── Zoom controls ───
var _brainZoom=1;
function zoomBrain(delta){
  _brainZoom=Math.max(0.5,Math.min(3,_brainZoom+delta));
  document.querySelectorAll('.brain-zoom-lvl').forEach(function(el){el.textContent=_brainZoom.toFixed(1)+'×';});
  document.querySelectorAll('.brain-panel .zoom-wrap canvas').forEach(function(c){
    c.style.transform='scale('+_brainZoom+')';
    c.parentNode.style.height=Math.round(540*_brainZoom)+'px';
  });
}
