// TELOS Knowledge Graph Module — Tree, Solar, Bubble visualizations

// ─── Knowledge Graph: Force-Directed 3D ───
let kgNodes = [];
let kgEdges = [];
let kgRotation = 0;
let kgLoaded = false;
let kgNoData = false;
let kgHighlight = null;  // connected-stories state: story.js domain chips set this

// Connected stories (STORYTELLING.md feature #4): called by story.js when a
// domain chip is clicked. Highlights that domain's nodes in all three KG
// canvases; passing null clears the highlight. Returns nothing.
function highlightKGByDomain(domain) {
  kgHighlight = domain || null;
  // The KG is part of the "All" landing wall — return there so the
  // highlight is actually visible (never destructive; 'all' is the default).
  if (domain && typeof switchTab === 'function') switchTab('all');
}

async function fetchKnowledge() {
  try {
    const resp = await fetch('/api/knowledge');
    const data = await resp.json();
    if (data && Array.isArray(data.nodes)) {
      // Real serialized data only: nodes AND their edges. If the graph has
      // no edges yet, the empty-set state renders (no invented links).
      initKnowledgeGraph(data);
      kgNoData = data.nodes.length === 0;
    }
    kgLoaded = true;
  } catch {
    kgLoaded = true;
    kgNoData = false;
  }
}


function initKnowledgeGraph(data) {
  const count = data.nodes.length;
  kgEdges = (data.edges || []).map(e => ({
    source: e.source || e.from,
    target: e.target || e.to,
    weight: e.weight || e.strength || 0.5,
  }));
  kgNodes = data.nodes.map((n, i) => {
    const angle = (i / count) * Math.PI * 2 + Math.random() * 0.2;
    const radius = 1.5 + Math.random() * 0.8;
    return {
      id: n.id || n.name || n.label || `n${i}`,
      label: n.label || n.name || n.id || '',
      domain: n.domain || n.category || 'general',
      importance: n.importance || n.relevance || n.weight || 0.5,
      x: Math.cos(angle) * radius * 0.5 + (Math.random() - 0.5) * 0.3,
      y: (Math.random() - 0.5) * 0.8,
      z: Math.sin(angle) * radius * 0.5 + (Math.random() - 0.5) * 0.3,
      vx: 0, vy: 0, vz: 0,
    };
  });
  document.getElementById('node-count').textContent = `${count} nodes`;
  // Run initial force simulation iterations
  for (let iter = 0; iter < 60; iter++) simulateKnowledgeForces(true);
}

function simulateKnowledgeForces(initial) {
  const nodes = kgNodes;
  if (nodes.length < 2) return;
  const rep = initial ? 0.015 : 0.008;
  const att = initial ? 0.008 : 0.004;
  const grav = initial ? 0.003 : 0.001;
  const damp = initial ? 0.8 : 0.92;

  for (const n of nodes) n.fx = 0, n.fy = 0, n.fz = 0;

  // Repulsion between all pairs
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      let dx = nodes[j].x - nodes[i].x;
      let dy = nodes[j].y - nodes[i].y;
      let dz = nodes[j].z - nodes[i].z;
      const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) || 0.01;
      const force = rep / (dist * dist + 0.01);
      dx = dx / dist * force;
      dy = dy / dist * force;
      dz = dz / dist * force;
      nodes[i].fx -= dx; nodes[i].fy -= dy; nodes[i].fz -= dz;
      nodes[j].fx += dx; nodes[j].fy += dy; nodes[j].fz += dz;
    }
  }

  // Attraction along edges
  for (const e of kgEdges) {
    const s = nodes.find(n => n.id === e.source);
    const t = nodes.find(n => n.id === e.target);
    if (!s || !t) continue;
    let dx = t.x - s.x, dy = t.y - s.y, dz = t.z - s.z;
    const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) || 0.01;
    const ideal = 0.8;
    const force = (dist - ideal) * att * (e.weight || 0.5) * 2;
    dx = dx / dist * force;
    dy = dy / dist * force;
    dz = dz / dist * force;
    s.fx += dx; s.fy += dy; s.fz += dz;
    t.fx -= dx; t.fy -= dy; t.fz -= dz;
  }

  // Center gravity
  for (const n of nodes) {
    n.fx -= n.x * grav;
    n.fy -= n.y * grav;
    n.fz -= n.z * grav;
  }

  // Apply
  for (const n of nodes) {
    n.vx = (n.vx + n.fx) * damp;
    n.vy = (n.vy + n.fy) * damp;
    n.vz = (n.vz + n.fz) * damp;
    n.x += n.vx;
    n.y += n.vy;
    n.z += n.vz;
  }
}

const DOMAIN_COLORS = {
  'user_preferences': '#60a5fa',
  'preferences': '#60a5fa',
  'user': '#60a5fa',
  'navigation': '#4ade80',
  'nav': '#4ade80',
  'intent': '#4ade80',
  'failures': '#c084fc',
  'failure': '#c084fc',
  'error': '#c084fc',
  'outcome': '#c084fc',
  'terrain': '#fbbf24',
  'memory': '#fbbf24',
  'general': '#888888',
  'context': '#f472b6',
  'cognition': '#60a5fa',
  'governance': '#c084fc',
  'metrics': '#4ade80',
  'system': '#94a3b8',
};

var _kgFullscreen = false;
function toggleKGFullscreen() {
  _kgFullscreen = !_kgFullscreen;
  var kp = document.querySelector('.knowledge-panel');
  if (!kp) return;
  if (_kgFullscreen) {
    kp.style.position = 'fixed'; kp.style.top = '0'; kp.style.left = '0';
    kp.style.width = '100vw'; kp.style.height = '100vh'; kp.style.zIndex = '1000';
    kp.style.margin = '0'; kp.style.borderRadius = '0';
  } else {
    kp.style.position = ''; kp.style.top = ''; kp.style.left = '';
    kp.style.width = ''; kp.style.height = ''; kp.style.zIndex = '';
    kp.style.margin = ''; kp.style.borderRadius = '';
  }
  setTimeout(resizeKgCanvas, 100);
}

function resizeKgCanvas() {
  var ids = ['kg-tree', 'kg-solar', 'kg-bubble'];
  ids.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) { el.width = el.clientWidth || 600; el.height = el.clientHeight || 580; }
  });
}

// ─── Pause/Resume for KG ───
var _kgPaused=false;
function toggleKGPause(){
  _kgPaused=!_kgPaused;
  var btn=document.getElementById('btn-kg-pause');
  if(btn)btn.textContent=_kgPaused?'▶ Play':'⏸ Pause';
}

// Init KG with demo data so it's ready when the IIFE runs
// Honest boot: empty graph until real serialized data arrives via /api/knowledge
if(kgNodes.length===0) initKnowledgeGraph({nodes: [], edges: []});

// ─── 5-Mode KG Visualization (single rAF loop) ───
(function(){
  var kgIds=['kg-tree','kg-solar','kg-bubble'];
  var kgLabels=['Knowledge Tree','Solar System','Bubble Map'];
  var kgCanvases=[], kgContexts=[];
  for(var ki=0;ki<kgIds.length;ki++){
    var el=document.getElementById(kgIds[ki]);
    if(!el)return;
    var cx=el.getContext('2d');
    if(!cx)return;
    kgCanvases.push(el); kgContexts.push(cx);
  }
  var kgt=0;
  function kgResize(c){c.width=c.clientWidth||300;c.height=c.clientHeight||580;}
  function kgProject(){
    if(kgNodes.length===0)return[];
    var ref=kgCanvases[0],w=ref.width||200,h=ref.height||900;
    var focal=4,scale=Math.min(w,h)*0.28;
    return kgNodes.map(function(n){
      var nx=n.x||0,ny=n.y||0,nz=n.z||0;
      var cosR=Math.cos(kgRotation),sinR=Math.sin(kgRotation);
      var rx=nx*cosR-nz*sinR;
      var rz=nx*sinR+nz*cosR+focal;
      var persp=focal/Math.max(rz,0.1);
      return {id:n.id,label:n.label,domain:n.domain,importance:n.importance,
        px:rx*scale*persp,py:-ny*scale*persp,size:(3.5+n.importance*6)*persp,
        persp:persp,depth:rz};
    });
  }
  function kgDrawAll(){
    try{
    if(!_kgPaused)kgt+=0.02;
    if(kgNodes.length>0)simulateKnowledgeForces(false);
    if(!_kgPaused)kgRotation+=0.004;
    var proj=kgProject();
    for(var ki=0;ki<kgCanvases.length;ki++){
      kgResize(kgCanvases[ki]);
      var ctx=kgContexts[ki],w=kgCanvases[ki].width,h=kgCanvases[ki].height;
      var bg=ctx.createRadialGradient(w/2,h/2,0,w/2,h/2,w*0.6);
      bg.addColorStop(0,'#111122');bg.addColorStop(1,'#06060a');
      ctx.fillStyle=bg;ctx.fillRect(0,0,w,h);
      ctx.fillStyle='rgba(255,255,255,0.35)';ctx.font='18px sans-serif';ctx.textAlign='center';ctx.textBaseline='top';
      ctx.fillText((ki+1)+'. '+kgLabels[ki]+' ('+kgNodes.length+' nodes)',w/2,6);
      if(kgNodes.length===0){
        ctx.fillStyle='rgba(136,136,136,0.5)';ctx.font='16px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
        ctx.fillText('No knowledge nodes yet',w/2,h/2);continue;
      }
      var modeNodes=proj.slice();
      modeNodes.sort(function(a,b){return a.depth-b.depth;});
      if(kgHighlight){
        for(var hi=0;hi<modeNodes.length;hi++){
          modeNodes[hi].dimmed=modeNodes[hi].domain!==kgHighlight;
          modeNodes[hi].hl=modeNodes[hi].domain===kgHighlight;
        }
      }
      switch(ki){
        case 0:kgTree(ctx,w,h,modeNodes);break;
        case 1:kgSolar(ctx,w,h,modeNodes);break;
        case 2:kgBubble(ctx,w,h,modeNodes);break;
      }
    }
    var kd=document.getElementById('kg-debug');
    if(kd&&proj.length>0){
      var html='';
      for(var pi=0;pi<Math.min(10,proj.length);pi++){
        var n=proj[pi];
        html+='<span style="color:'+(DOMAIN_COLORS[n.domain]||'#888')+';margin:2px 4px;font-size:9px;">\u25CF '+(n.label||'?')+'</span>';
      }
      kd.innerHTML=html;
    }
    }catch(e){}
    requestAnimationFrame(kgDrawAll);
  }
  // ── 1. Knowledge Tree ──
  function kgTree(ctx,w,h,nodes){
    var rootX=w/2,rootY=h-24,trunkH=h*0.50;
    ctx.beginPath();ctx.moveTo(rootX-5,rootY);
    ctx.quadraticCurveTo(rootX-4,rootY-trunkH*0.5,rootX-9,rootY-trunkH);
    ctx.lineTo(rootX+9,rootY-trunkH);
    ctx.quadraticCurveTo(rootX+4,rootY-trunkH*0.5,rootX+5,rootY);
    ctx.closePath();ctx.fillStyle='rgba(40,30,20,0.4)';ctx.fill();
    var domains={};
    for(var i=0;i<nodes.length;i++){
      var d=nodes[i].domain||'general';
      if(!domains[d])domains[d]=[];
      domains[d].push(nodes[i]);
    }
    var dNames=Object.keys(domains),dCount=dNames.length;
    for(var di=0;di<dCount;di++){
      var dNodes=domains[dNames[di]],dAngle=-Math.PI/2+((di+0.5)/(dCount+1))*Math.PI;
      var bx=rootX+Math.cos(dAngle)*160,by=rootY-trunkH+Math.sin(dAngle)*160;
      ctx.beginPath();ctx.moveTo(rootX,rootY-trunkH);
      ctx.quadraticCurveTo(rootX+Math.cos(dAngle)*65,rootY-trunkH+Math.sin(dAngle)*45-16,bx,by);
      ctx.strokeStyle='rgba(60,80,70,'+(0.18+0.07*Math.sin(kgt+di))+')';ctx.lineWidth=2;ctx.stroke();
      ctx.fillStyle='rgba(255,255,255,0.4)';ctx.font='15px sans-serif';
      ctx.textAlign='center';ctx.fillText(dNames[di].substring(0,6),bx,by+8);
      for(var ni=0;ni<dNodes.length;ni++){
        var n=dNodes[ni],pct=(ni+0.5)/dNodes.length;
        var lx=bx+Math.cos(dAngle+0.5)*pct*65,ly=by+Math.sin(dAngle+0.5)*pct*65-26;
        var col=DOMAIN_COLORS[n.domain]||'#888';
        var r=10+Math.sin(kgt+ni+di)*4;
        if(n.dimmed){ctx.globalAlpha=0.06;ctx.fillStyle=col;ctx.beginPath();ctx.arc(lx,ly,r*2,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;continue;}
        ctx.fillStyle=col;ctx.beginPath();ctx.arc(lx,ly,r*4,0,Math.PI*2);ctx.fill();
        if(n.hl){ctx.strokeStyle='rgba(255,255,255,0.85)';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(lx,ly,r*4+3,0,Math.PI*2);ctx.stroke();}
        if(n.label&&pct>0.4){
          ctx.fillStyle='rgba(200,200,200,0.5)';ctx.font='13px sans-serif';
          ctx.textAlign='center';ctx.fillText(n.label,lx,ly+18);
        }
      }
    }
    ctx.fillStyle='rgba(255,255,255,0.22)';ctx.font='15px sans-serif';
    ctx.textAlign='center';ctx.fillText('Knowledge',rootX,rootY+18);
    // Tree ambient particles
    for(var tp=0;tp<5;tp++){
      var tpct=(kgt*0.1+tp*0.2+state.time*0.005)%1;
      var tx=rootX+Math.sin(kgt*0.5+tp*2)*60*tpct,tty=rootY+Math.sin(kgt*0.3+tp)*25*tpct-30*tpct;
      ctx.fillStyle='rgba(74,222,128,'+(0.08*(1-tpct))+')';ctx.beginPath();ctx.arc(tx,tty,1.5+tpct*2,0,Math.PI*2);ctx.fill();
    }
  }
  // ── 3. Solar System ──
  function kgSolar(ctx,w,h,nodes){
    var cx=w/2,cy=h/2,domains={};
    for(var i=0;i<nodes.length;i++){
      var d=nodes[i].domain||'general';
      if(!domains[d])domains[d]=[];
      domains[d].push(nodes[i]);
    }
    var dNames=Object.keys(domains),dCount=dNames.length;
    var sg=ctx.createRadialGradient(cx,cy,0,cx,cy,65);
    sg.addColorStop(0,'rgba(255,200,100,0.6)');sg.addColorStop(1,'transparent');
    ctx.fillStyle=sg;ctx.beginPath();ctx.arc(cx,cy,65,0,Math.PI*2);ctx.fill();
    ctx.fillStyle='rgba(255,200,100,0.9)';ctx.beginPath();ctx.arc(cx,cy,16,0,Math.PI*2);ctx.fill();
    ctx.fillStyle='rgba(255,255,255,0.7)';ctx.font='20px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText('TELOS',cx,cy+26);
    for(var di=0;di<dCount;di++){
      var domDim=kgHighlight?(dNames[di]!==kgHighlight):false;
      if(domDim)ctx.globalAlpha=0.10;
      var orbitR=50+(di+1)*(Math.min(w,h)*0.20);
      var angle=kgt*(0.3+di*0.1)+di*1.2;
      var px=cx+Math.cos(angle)*orbitR,py=cy+Math.sin(angle)*orbitR;
      var col=DOMAIN_COLORS[dNames[di]]||'#888';
      ctx.beginPath();ctx.arc(cx,cy,orbitR,0,Math.PI*2);
      ctx.strokeStyle='rgba(80,80,120,'+(0.07+di*0.035)+')';ctx.lineWidth=1;ctx.stroke();
      ctx.fillStyle=col;ctx.beginPath();ctx.arc(px,py,17,0,Math.PI*2);ctx.fill();
      ctx.fillStyle='rgba(255,255,255,0.15)';ctx.beginPath();ctx.arc(px-5,py-5,5,0,Math.PI*2);ctx.fill();
      ctx.fillStyle='rgba(255,255,255,0.4)';ctx.font='17px sans-serif';ctx.textAlign='center';ctx.textBaseline='top';
      ctx.fillText(dNames[di].substring(0,5),px,py+20);
      if(!domDim&&kgHighlight){ctx.strokeStyle='rgba(255,255,255,0.85)';ctx.lineWidth=2;ctx.beginPath();ctx.arc(px,py,24,0,Math.PI*2);ctx.stroke();}
      var moons=domains[dNames[di]];
      for(var mi=0;mi<moons.length;mi++){
        var m=moons[mi],mAngle=angle+Math.PI/2+(mi/moons.length)*Math.PI*2+kgt*0.5;
        var mR=24+mi*13;
        var mx=px+Math.cos(mAngle)*mR,my=py+Math.sin(mAngle)*mR;
        ctx.fillStyle=col;ctx.beginPath();ctx.arc(mx,my,10,0,Math.PI*2);ctx.fill();
      }
      ctx.globalAlpha=1;
    }
  }
  // ── 3. Bubble Map ──
  function kgBubble(ctx,w,h,nodes){
    var domains={};
    for(var i=0;i<nodes.length;i++){
      var d=nodes[i].domain||'general';
      if(!domains[d])domains[d]=[];
      domains[d].push(nodes[i]);
    }
    var dNames=Object.keys(domains),dCount=dNames.length;
    var centerAngle=kgt*0.05;
    for(var di=0;di<dCount;di++){
      var angle=(di/dCount)*Math.PI*2+centerAngle;
      var radius=Math.min(w,h)*0.28;
      var bx=w/2+Math.cos(angle)*radius,by=h/2+Math.sin(angle)*radius*0.7;
      var bSize=65+Math.sin(kgt*0.5+di)*10;
      var col=DOMAIN_COLORS[dNames[di]]||'#888';
      var domDim=kgHighlight?(dNames[di]!==kgHighlight):false;
      if(domDim)ctx.globalAlpha=0.08;
      var bg2=ctx.createRadialGradient(bx,by,0,bx,by,bSize*1.5);
      bg2.addColorStop(0,col+'22');bg2.addColorStop(1,'transparent');
      ctx.fillStyle=bg2;ctx.beginPath();ctx.arc(bx,by,bSize*1.5,0,Math.PI*2);ctx.fill();
      ctx.strokeStyle=col+'44';ctx.lineWidth=1.5;
      ctx.beginPath();ctx.arc(bx,by,bSize,0,Math.PI*2);ctx.stroke();
      ctx.fillStyle='rgba(255,255,255,0.45)';ctx.font='16px sans-serif';
      ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(dNames[di].substring(0,5),bx,by-bSize-10);
      var innerNodes=domains[dNames[di]];
      for(var ni=0;ni<innerNodes.length;ni++){
        var n=innerNodes[ni];
        var ia=(ni/innerNodes.length)*Math.PI*2+kgt*0.3+di;
        var ir=13+ni*9;
        var ix=bx+Math.cos(ia)*ir,iy=by+Math.sin(ia)*ir;
        var r=9+Math.sin(kgt+ni+di)*3;
        ctx.fillStyle=col;ctx.beginPath();ctx.arc(ix,iy,r*(1+n.importance),0,Math.PI*2);ctx.fill();
        ctx.fillStyle='rgba(255,255,255,0.1)';
        ctx.beginPath();ctx.arc(ix-r*0.2,iy-r*0.2,r*0.3,0,Math.PI*2);ctx.fill();
      }
      if(!domDim&&kgHighlight){ctx.strokeStyle='rgba(255,255,255,0.85)';ctx.lineWidth=2;ctx.beginPath();ctx.arc(bx,by,bSize+8,0,Math.PI*2);ctx.stroke();}
      ctx.globalAlpha=1;
    }
  }
  kgDrawAll();
})();
