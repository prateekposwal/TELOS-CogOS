// TELOS Knowledge Graph Module — v5 "Memory" visualizations.
//
// Three ORIGINAL modes, one shared real-data source (/api/knowledge):
//   kg-tree   → THE CANOPY        — domain branches, real edges as filaments,
//                                   node height = real importance.
//   kg-solar  → ORBITAL ECOLOGY   — domain orbital bands, nodes as orbiting
//                                   bodies, real edges as chords.
//   kg-bubble → NEBULA CLUSTERS   — domains as layered nebula clouds sized by
//                                   real node count, nodes = constellation
//                                   points sized by REAL degree.
//
// Honesty contract (inherited + hardened):
//   * Nodes and edges come ONLY from /api/knowledge (real serialized data).
//   * ALL THREE modes draw the REAL edges (edge_type color-coded); none may
//     show isolated dots for a graph that has connections. Edges are sampled
//     deterministically for performance (label shows the real total).
//   * Layout is deterministic (no Math.random for positions); node radius may
//     encode real importance and real degree — nothing invented.
//   * The domain palette is the ONE canonical map (window._DOMAIN_COLORS_STORY
//     defined in story.js). This file must NEVER define a second palette.
//   * Empty graph → honest empty state, never fabricated points.
//   * Motion (orbit, pulses) gated by window.__reducedMotion.

// ─── Shared graph state (real data only) ───
let kgNodes = [];
let kgEdges = [];
let kgRotation = 0;
let kgLoaded = false;
let kgNoData = false;
let kgHighlight = null;   // connected-stories: story.js domain chips set this
let kgDegree = {};        // node id → real degree (edges incident), recomputed on data change
let kgEdgeCount = 0;      // real edge total (for honest "showing m of n" readouts)

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
    edge_type: e.edge_type || 'related',
  }));
  kgEdgeCount = kgEdges.length;
  kgNodes = data.nodes.map((n, i) => {
    // Deterministic layout (no Math.random): golden-angle fan in 3D space.
    const phi = i * 2.39996323;                    // golden angle, deterministic
    const radius = 1.2 + (i % 5) * 0.22;           // ring by index, stable
    return {
      id: n.id || n.name || n.label || `n${i}`,
      label: n.label || n.name || n.id || '',
      domain: n.domain || n.category || 'unknown',
      importance: n.importance || n.relevance || n.weight || 0.5,
      x: Math.cos(phi) * radius * 0.5 + Math.sin(i * 1.7) * 0.12,
      y: Math.cos(i * 0.9) * 0.42,
      z: Math.sin(phi) * radius * 0.5 + Math.cos(i * 2.3) * 0.12,
      vx: 0, vy: 0, vz: 0,
    };
  });
  // Real degree: edges incident to each node (from the REAL edge list).
  kgDegree = {};
  for (const e of kgEdges) {
    kgDegree[e.source] = (kgDegree[e.source] || 0) + 1;
    kgDegree[e.target] = (kgDegree[e.target] || 0) + 1;
  }
  const degVals = Object.values(kgDegree);
  kgDegreeMax = degVals.length ? Math.max.apply(null, degVals) : 1;
  const nc = document.getElementById('node-count');
  if (nc) nc.textContent = `${count} nodes · ${kgEdgeCount} edges`;
  // Run initial force iterations (springs follow the REAL edges).
  for (let iter = 0; iter < 60; iter++) simulateKnowledgeForces(true);
}
let kgDegreeMax = 1;

// ─── Canonical colors (single source — story.js owns the domain palette) ───
function domColor(d) {
  var P = (typeof window !== 'undefined' && window._DOMAIN_COLORS_STORY) || {};
  return P[d] || '#8f89ad';
}
// Edge-type semantics: color carries the kind of connection (real data).
const EDGE_COLORS = {
  'follows': '#4ade80',          // temporal chain between navigation moves
  'at_location': '#fbbf24',      // spatial: node ↔ terrain it was seen in
  'identity_affinity': '#7d97ff',// identity self-relations (periwinkle)
  'related': '#8f89ad',
};
function edgeColor(et) { return EDGE_COLORS[et] || EDGE_COLORS['related']; }

// ─── Deterministic real-edge sampling (honest, performance-bounded) ───
// Every Nth real edge (stride by index, deterministic) up to a limit. The
// label always shows the REAL total (kgEdgeCount) next to the drawn sample.
function edgeSample(limit) {
  const n = kgEdges.length;
  if (n === 0) return [];
  const stride = Math.max(1, Math.ceil(n / limit));
  const out = [];
  for (let i = 0; i < n; i += stride) out.push(kgEdges[i]);
  return out;
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

  // Attraction along edges (REAL edges only)
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

var _kgFullscreen = false;
function toggleKGFullscreen(btn) {
  _kgFullscreen = !_kgFullscreen;
  // Each knowledge mode is now its own section/panel — fullscreen the panel
  // the button lives in (fallback: first panel, pre-split behaviour).
  var kp = btn && btn.closest ? btn.closest('.knowledge-panel') : document.querySelector('.knowledge-panel');
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
    if (id === 'kg-bubble' && window.__kgBubble3D) return; // 3D renderer owns the buffer
    var el = document.getElementById(id);
    if (el) { el.width = el.clientWidth || 600; el.height = el.clientHeight || 580; }
  });
}

// ─── Pause/Resume for KG ───
var _kgPaused=false;
function toggleKGPause(){
  _kgPaused=!_kgPaused;
  document.querySelectorAll('.kg-pause-btn').forEach(function(btn){btn.textContent=_kgPaused?'▶ Play':'⏸ Pause';});
}

// Honest boot: empty graph until real serialized data arrives via /api/knowledge
if(kgNodes.length===0) initKnowledgeGraph({nodes: [], edges: []});

// ─── Shared helpers ───
function kgBg(ctx, w, h) {
  var bg = ctx.createRadialGradient(w/2, h*0.42, 0, w/2, h*0.42, Math.max(w, h) * 0.7);
  bg.addColorStop(0, '#131027');
  bg.addColorStop(1, '#070512');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);
  // hairline grid (geometry, not data)
  ctx.strokeStyle = 'rgba(34,28,68,0.5)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (var gx = 0; gx <= w; gx += 72) { ctx.moveTo(gx + 0.5, 0); ctx.lineTo(gx + 0.5, h); }
  for (var gy = 0; gy <= h; gy += 72) { ctx.moveTo(0, gy + 0.5); ctx.lineTo(w, gy + 0.5); }
  ctx.stroke();
}

function kgHeader(ctx, w, title, meta) {
  ctx.fillStyle = 'rgba(241,239,248,0.85)';
  ctx.font = '13px "Space Mono", monospace';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText(title, 14, 12);
  ctx.fillStyle = 'rgba(143,137,173,0.9)';
  ctx.fillText(meta, w - 14, 12);
  ctx.textAlign = 'center';
}

function kgEmpty(ctx, w, h, msg) {
  ctx.fillStyle = 'rgba(143,137,173,0.85)';
  ctx.font = '13px "Space Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(msg, w / 2, h / 2);
}

// Draw REAL edges as fine filaments between projected node positions.
// positions: {id: {x, y, domain, alpha}} — only nodes being drawn.
function kgDrawEdges(ctx, positions, limit, dimOthers, highlight) {
  var sample = edgeSample(limit || 800);
  ctx.lineWidth = 1;
  for (var i = 0; i < sample.length; i++) {
    var e = sample[i];
    var s = positions[e.source], t = positions[e.target];
    if (!s || !t) continue;
    var a = 0.10 * (e.weight || 0.5);
    if (dimOthers && (s.domain !== highlight || t.domain !== highlight)) a *= 0.25;
    ctx.strokeStyle = edgeColor(e.edge_type);
    ctx.globalAlpha = a;
    ctx.beginPath();
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(t.x, t.y);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

// ─── 3-Mode KG Visualization (single rAF loop) ───
(function(){
  var kgIds=['kg-tree','kg-solar','kg-bubble'];
  var kgLabels=['The Canopy','Orbital Ecology','Nebula Clusters'];
  var kgCanvases=[], kgContexts=[];
  for(var ki=0;ki<kgIds.length;ki++){
    var el=document.getElementById(kgIds[ki]);
    if(!el)return;
    // 3D Memory Nebula (knowledge-3d.js) owns kg-bubble when WebGL is up —
    // claiming '2d' here would lock the canvas's context mode and kill the
    // 3D engine. A null context makes the draw loop skip that canvas.
    if(el.id==='kg-bubble' && window.__kgBubble3D){ kgCanvases.push(el); kgContexts.push(null); continue; }
    var cx=el.getContext('2d');
    if(!cx)return;
    kgCanvases.push(el); kgContexts.push(cx);
  }
  var kgt=0;
  function kgResize(c){c.width=c.clientWidth||300;c.height=c.clientHeight||580;}

  // ── 1. THE CANOPY ─────────────────────────────────────────────────
  // A living crown: the corpus spine on the left, one branch per REAL
  // domain (thickness ∝ node count), nodes as luminous buds raised by
  // their REAL importance. REAL edges drawn as color-coded filaments.
  function kgCanopy(ctx, w, h, nodes) {
    kgBg(ctx, w, h);
    kgHeader(ctx, w, 'THE CANOPY — domains as branches', kgNodes.length + ' nodes · ' + kgEdgeCount + ' edges (sampled)');
    if (nodes.length === 0) { kgEmpty(ctx, w, h, 'No knowledge nodes yet — the canopy fills as TELOS records real observations.'); return; }

    var spineX = w * 0.14;
    var topY = 56, botY = h - 44, usable = botY - topY;
    var domains = {};
    for (var i = 0; i < nodes.length; i++) {
      var d = nodes[i].domain || 'unknown';
      if (!domains[d]) domains[d] = [];
      domains[d].push(nodes[i]);
    }
    var dNames = Object.keys(domains).sort();
    var maxCount = 1;
    for (var di = 0; di < dNames.length; di++) maxCount = Math.max(maxCount, domains[dNames[di]].length);

    // Positions map (id → screen) for the edge filaments.
    var posMap = {};
    var hl = kgHighlight;

    // Domain branches (thickness ∝ real node count).
    for (var di = 0; di < dNames.length; di++) {
      var dn = dNames[di];
      var dNodes = domains[dn];
      var y0 = topY + (di / Math.max(1, dNames.length)) * usable + usable / Math.max(2, dNames.length * 2);
      var bEndX = w * 0.88;
      var col = domColor(dn);
      var thick = 1.5 + (dNodes.length / maxCount) * 3.5;
      var domDim = hl ? (dn !== hl) : false;

      // Branch arc: quadratic from spine → tip, slight bow.
      ctx.strokeStyle = col;
      ctx.globalAlpha = domDim ? 0.12 : 0.32;
      ctx.lineWidth = thick;
      ctx.beginPath();
      ctx.moveTo(spineX, y0);
      ctx.quadraticCurveTo(spineX + (bEndX - spineX) * 0.45, y0 - 26, bEndX, y0);
      ctx.stroke();
      ctx.globalAlpha = 1;

      // Domain label at the branch tip (mono uppercase, editorial).
      ctx.fillStyle = domDim ? 'rgba(143,137,173,0.35)' : col;
      ctx.font = '13px "Space Mono", monospace';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText(dn.toUpperCase() + ' · ' + dNodes.length, bEndX - 10, y0 - 4);

      // Buds (nodes) along the branch: height above = real importance.
      for (var ni = 0; ni < dNodes.length; ni++) {
        var n = dNodes[ni];
        var t = (ni + 0.5) / dNodes.length;
        var bx = spineX + (bEndX - spineX) * t;
        var by = y0 - 26 * 2 * t * (1 - t);          // follow the branch bow
        var lift = (n.importance || 0.5) * 26;       // REAL importance → height
        var deg = kgDegree[n.id] || 0;
        var glow = Math.min(1, (deg / (kgDegreeMax || 1)) + (n.importance || 0.5) * 0.5);
        var r = 2.5 + (n.importance || 0.5) * 4.5;
        if (!window.__reducedMotion && !_kgPaused) r += Math.sin(kgt * 1.6 + ni + di) * 0.7;
        var px = bx, py = by - lift;
        posMap[n.id] = { x: px, y: py, domain: n.domain };

        if (domDim) { ctx.globalAlpha = 0.12; } else { ctx.globalAlpha = 0.72 + glow * 0.28; }
        // halo
        var g = ctx.createRadialGradient(px, py, 0, px, py, r * 3.2);
        g.addColorStop(0, col + '55');
        g.addColorStop(1, 'transparent');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(px, py, r * 3.2, 0, Math.PI * 2); ctx.fill();
        // body
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
        if (hl && n.domain === hl) {
          ctx.strokeStyle = 'rgba(255,255,255,0.8)';
          ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(px, py, r + 3, 0, Math.PI * 2); ctx.stroke();
        }
        // Sparse domain → readable labels (13px floor).
        if (dNodes.length <= 10 && n.label) {
          ctx.fillStyle = domDim ? 'rgba(143,137,173,0.4)' : 'rgba(200,198,222,0.9)';
          ctx.font = '13px "Space Mono", monospace';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          var lbl = n.label.length > 18 ? n.label.slice(0, 17) + '…' : n.label;
          ctx.fillText(lbl, px + r + 4, py - 6);
        }
      }
    }
    // REAL edges — drawn UNDER the buds but OVER the branches (readable).
    kgDrawEdges(ctx, posMap, 800, !!hl, hl);
    // Spine label.
    ctx.fillStyle = 'rgba(241,239,248,0.5)';
    ctx.font = '13px "Space Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText('CORPUS', spineX, botY + 14);
  }

  // ── 2. ORBITAL ECOLOGY ────────────────────────────────────────────
  // No sun, no moons. Each REAL domain is an orbital BAND (radius by rank,
  // width ∝ node count, tinted by domain); nodes are orbiting bodies whose
  // speed ∝ real importance. REAL edges = chords between bodies.
  function kgOrbital(ctx, w, h, nodes) {
    kgBg(ctx, w, h);
    kgHeader(ctx, w, 'ORBITAL ECOLOGY — domains as orbital bands', kgNodes.length + ' nodes · ' + kgEdgeCount + ' edges');
    if (nodes.length === 0) { kgEmpty(ctx, w, h, 'No knowledge nodes yet — the orbits stay dark until TELOS records real observations.'); return; }

    var cx = w / 2, cy = h / 2 - 6;
    var domains = {};
    for (var i = 0; i < nodes.length; i++) {
      var d = nodes[i].domain || 'unknown';
      if (!domains[d]) domains[d] = [];
      domains[d].push(nodes[i]);
    }
    var dNames = Object.keys(domains).sort();
    var maxCount = 1;
    for (var di = 0; di < dNames.length; di++) maxCount = Math.max(maxCount, domains[dNames[di]].length);
    var maxR = Math.min(w, h) * 0.44 - 60;
    var ringStep = maxR / Math.max(1, dNames.length);
    var hl = kgHighlight;
    var posMap = {};

    // Core: the knowledge corpus (REAL count — never a static label).
    var coreG = ctx.createRadialGradient(cx, cy, 0, cx, cy, 60);
    coreG.addColorStop(0, 'rgba(125,151,255,0.35)');
    coreG.addColorStop(1, 'transparent');
    ctx.fillStyle = coreG;
    ctx.beginPath(); ctx.arc(cx, cy, 60, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#7d97ff';
    ctx.beginPath(); ctx.arc(cx, cy, 12, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'rgba(241,239,248,0.9)';
    ctx.font = '13px "Space Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('CORE · ' + kgNodes.length, cx, cy + 26);

    for (var di = 0; di < dNames.length; di++) {
      var dn = dNames[di];
      var dNodes = domains[dn];
      var R = 48 + di * ringStep + ringStep * 0.5;
      var col = domColor(dn);
      var domDim = hl ? (dn !== hl) : false;
      var bandW = 1.5 + (dNodes.length / maxCount) * 3.5;

      // Orbital band (ring).
      ctx.strokeStyle = col;
      ctx.globalAlpha = domDim ? 0.06 : 0.28;
      ctx.lineWidth = bandW;
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
      ctx.globalAlpha = 1;

      // Domain label on the band's outer edge (mono uppercase).
      ctx.fillStyle = domDim ? 'rgba(143,137,173,0.3)' : col;
      ctx.font = '13px "Space Mono", monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText(dn.toUpperCase() + ' · ' + dNodes.length, cx + R + 4, cy - 4);

      // Bodies: orbital angle advances with REAL importance (faster = more
      // important). Static frame under reduced-motion / pause.
      var baseA = di * 0.7;
      for (var ni = 0; ni < dNodes.length; ni++) {
        var n = dNodes[ni];
        var speed = 0.015 + (n.importance || 0.5) * 0.045;
        var a = baseA + (ni / dNodes.length) * Math.PI * 2;
        if (!_kgPaused && !window.__reducedMotion) a += kgt * speed;
        var px = cx + Math.cos(a) * R;
        var py = cy + Math.sin(a) * R;
        var deg = kgDegree[n.id] || 0;
        var glow = Math.min(1, (deg / (kgDegreeMax || 1)) + (n.importance || 0.5) * 0.5);
        var r = 3 + (n.importance || 0.5) * 3.5;
        posMap[n.id] = { x: px, y: py, domain: n.domain };

        var g = ctx.createRadialGradient(px, py, 0, px, py, r * 3);
        g.addColorStop(0, col + (domDim ? '22' : '55'));
        g.addColorStop(1, 'transparent');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(px, py, r * 3, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = domDim ? 0.14 : 0.78 + glow * 0.22;
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
        if (hl && n.domain === hl) {
          ctx.strokeStyle = 'rgba(255,255,255,0.8)';
          ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(px, py, r + 2.5, 0, Math.PI * 2); ctx.stroke();
        }
        // Sparse band → readable labels.
        if (dNodes.length <= 6 && n.label) {
          ctx.fillStyle = domDim ? 'rgba(143,137,173,0.4)' : 'rgba(200,198,222,0.9)';
          ctx.font = '13px "Space Mono", monospace';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          var lbl = n.label.length > 18 ? n.label.slice(0, 17) + '…' : n.label;
          ctx.fillText(lbl, px + r + 3, py - 5);
        }
      }
    }
    // REAL edges as chords (sampled deterministically).
    kgDrawEdges(ctx, posMap, 600, !!hl, hl);
  }

  // ── 3. NEBULA CLUSTERS ────────────────────────────────────────────
  // Domains as layered nebula clouds (radius ∝ real node count); nodes are
  // constellation points positioned by the REAL-edge force layout, sized by
  // REAL degree. Cross-domain REAL edges = filaments between clouds.
  function kgNebula(ctx, w, h, nodes) {
    kgBg(ctx, w, h);
    kgHeader(ctx, w, 'NEBULA CLUSTERS — domains as clouds', kgNodes.length + ' nodes · ' + kgEdgeCount + ' edges (sampled)');
    if (nodes.length === 0) { kgEmpty(ctx, w, h, 'No knowledge nodes yet — the nebulae stay empty until TELOS records real observations.'); return; }

    // Perspective projection of the force-layout (rotation = slow drift).
    var focal = 4, scale = Math.min(w, h) * 0.30;
    var proj = nodes.map(function (n) {
      var cosR = Math.cos(kgRotation), sinR = Math.sin(kgRotation);
      var rx = n.x * cosR - n.z * sinR;
      var rz = n.x * sinR + n.z * cosR + focal;
      var persp = focal / Math.max(rz, 0.1);
      return {
        id: n.id, label: n.label, domain: n.domain, importance: n.importance,
        px: w / 2 + rx * scale * persp, py: h / 2 - n.y * scale * persp,
        depth: rz,
      };
    });

    var domains = {};
    for (var i = 0; i < proj.length; i++) {
      var d = proj[i].domain || 'unknown';
      if (!domains[d]) domains[d] = [];
      domains[d].push(proj[i]);
    }
    var dNames = Object.keys(domains).sort();
    var maxCount = 1;
    for (var di = 0; di < dNames.length; di++) maxCount = Math.max(maxCount, domains[dNames[di]].length);
    var hl = kgHighlight;
    var posMap = {};

    // REAL edges first (filaments under the clouds).
    for (var i = 0; i < proj.length; i++) posMap[proj[i].id] = { x: proj[i].px, y: proj[i].py, domain: proj[i].domain };
    kgDrawEdges(ctx, posMap, 800, !!hl, hl);

    // Clouds (sorted by domain for deterministic draw order).
    proj.sort(function (a, b) { return a.depth - b.depth; });
    var clouds = [];
    for (var di = 0; di < dNames.length; di++) {
      var dn = dNames[di];
      var dNodes = domains[dn];
      var sx = 0, sy = 0;
      for (var j = 0; j < dNodes.length; j++) { sx += dNodes[j].px; sy += dNodes[j].py; }
      sx /= dNodes.length; sy /= dNodes.length;
      clouds.push({ name: dn, nodes: dNodes, x: sx, y: sy, count: dNodes.length });
    }
    for (var ci = 0; ci < clouds.length; ci++) {
      var c = clouds[ci];
      var col = domColor(c.name);
      var domDim = hl ? (c.name !== hl) : false;
      var R = 42 + (c.count / maxCount) * 68;
      if (!domDim) R *= (0.94 + Math.sin(kgt * 0.8 + ci) * 0.03);
      var alpha = domDim ? 0.35 : 1;

      // Layered nebula: three radial shells in the domain hue. The cloud
      // body is REAL structure (domain node count → R), shells carry the
      // domain hue — alpha scales with domDim only.
      var rgb = col.replace('#', '');
      var shell = function (r, a) {
        var g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, r);
        g.addColorStop(0, 'rgba(' + parseInt(rgb.slice(0,2),16) + ',' + parseInt(rgb.slice(2,4),16) + ',' + parseInt(rgb.slice(4,6),16) + ',' + a + ')');
        g.addColorStop(0.65, 'rgba(' + parseInt(rgb.slice(0,2),16) + ',' + parseInt(rgb.slice(2,4),16) + ',' + parseInt(rgb.slice(4,6),16) + ',' + (a * 0.55).toFixed(3) + ')');
        g.addColorStop(1, 'transparent');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI * 2); ctx.fill();
      };
      ctx.globalAlpha = alpha;
      shell(R * 1.7, 0.14); shell(R * 1.15, 0.22); shell(R * 0.55, 0.32);
      ctx.globalAlpha = 1;

      // Cloud label (ghost mono numeral above the cloud).
      ctx.fillStyle = domDim ? 'rgba(143,137,173,0.35)' : col;
      ctx.font = '13px "Space Mono", monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText(c.name.toUpperCase() + ' · ' + c.count, c.x, c.y - R - 6);

      // Constellation points: sized by REAL degree, brightness by importance.
      for (var k = 0; k < c.nodes.length; k++) {
        var n = c.nodes[k];
        var deg = kgDegree[n.id] || 0;
        var r = 3.5 + Math.min(6, (deg / (kgDegreeMax || 1)) * 6) + (n.importance || 0.5) * 2;
        var g2 = ctx.createRadialGradient(n.px, n.py, 0, n.px, n.py, r * 2.6);
        g2.addColorStop(0, col + (domDim ? '11' : '44'));
        g2.addColorStop(1, 'transparent');
        ctx.fillStyle = g2;
        ctx.beginPath(); ctx.arc(n.px, n.py, r * 2.6, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = domDim ? 0.14 : 0.7 + (n.importance || 0.5) * 0.3;
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(n.px, n.py, r, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
        if (hl && n.domain === hl) {
          ctx.strokeStyle = 'rgba(255,255,255,0.75)';
          ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.arc(n.px, n.py, r + 2, 0, Math.PI * 2); ctx.stroke();
        }
      }
      if (!domDim && hl) {
        ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 5]);
        ctx.beginPath(); ctx.arc(c.x, c.y, R + 10, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]);
      }
    }
  }

  // ── Draw loop ──
  function kgDrawAll(){
    try{
    if(!_kgPaused && !window.__reducedMotion)kgt+=0.02;
    if(kgNodes.length>0)simulateKnowledgeForces(false);
    if(!_kgPaused && !window.__reducedMotion)kgRotation+=0.0025;
    for(var ki=0;ki<kgCanvases.length;ki++){
      var ctx=kgContexts[ki];
      if(!ctx)continue; // kg-bubble in 3D mode — knowledge-3d.js owns it
      kgResize(kgCanvases[ki]);
      var w=kgCanvases[ki].width,h=kgCanvases[ki].height;
      switch(ki){
        case 0:kgCanopy(ctx,w,h,kgNodes);break;
        case 1:kgOrbital(ctx,w,h,kgNodes);break;
        case 2:kgNebula(ctx,w,h,kgNodes);break;
      }
    }
    var kd=document.getElementById('kg-debug');
    if(kd&&kgNodes.length>0){
      var html='';
      var shown=Math.min(10,kgNodes.length);
      for(var pi=0;pi<shown;pi++){
        var n=kgNodes[pi];
        html+='<span style="color:'+(domColor(n.domain)||'#888')+';margin:2px 4px;font-size:13px;">\u25CF '+(n.label||'?')+'</span>';
      }
      kd.innerHTML=html;
    }
    }catch(e){}
    requestAnimationFrame(kgDrawAll);
  }
  kgDrawAll();
})();
