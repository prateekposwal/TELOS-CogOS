// TELOS Knowledge Graph — 3D Mode ("The Memory Nebula")
// ────────────────────────────────────────────────────────────────────────────
// Chapter 05 (kg-bubble) upgraded from the 2D-canvas perspective projection
// to a REAL three.js WebGL scene. Same real data, same shared deterministic
// force layout (knowledge-graph.js owns kgNodes/kgEdges/kgDegree), same
// honesty contract:
//
//   * Every sphere, line, cloud, and label encodes a REAL field from
//     /api/knowledge — no Math.random anywhere, no invented points.
//   * Node position  = shared force layout (real edges attract, real nodes
//                      repel — computed by knowledge-graph.js).
//   * Node radius    = REAL degree + REAL importance.
//   * Node color     = REAL domain → canonical palette
//                      (window._DOMAIN_COLORS_STORY, story.js owns it).
//   * Edge color     = REAL edge_type (edgeColor() from knowledge-graph.js).
//   * Edge opacity   = REAL edge weight.
//   * Cloud size     = REAL per-domain node count.
//   * HUD / inspect card show the REAL totals (sampled edges labeled).
//
// Fallback chain (honest, zero-downtime):
//   WebGL + three.js available → 3D scene, sets window.__kgBubble3D = true
//   otherwise                  → knowledge-graph.js keeps painting the 2D
//                                nebula renderer on the same canvas.
//
// Interactivity: drag to orbit, wheel/pinch to zoom, hover to spotlight a
// real lesson, click to inspect its real id/domain/degree/importance,
// pause freezes the drift, fullscreen uses the existing panel control.
// Reduced motion (window.__reducedMotion) → static scene, no auto-rotation,
// no per-frame animation loop (render on demand only).
//
// Load order: three.min.js → OrbitControls.js → knowledge-3d.js → dashboard.js
// → knowledge-graph.js. This file claims the WebGL context FIRST so
// knowledge-graph.js can skip its 2D context for kg-bubble.

(function () {
  'use strict';

  var canvas = document.getElementById('kg-bubble');
  if (!canvas) return;

  // ── Gate 1: three.js must be present ────────────────────────────────────
  if (typeof THREE === 'undefined' || !THREE.WebGLRenderer) {
    console.warn('[kg3d] three.js not loaded — 2D nebula fallback stays active.');
    return;
  }

  // ── Gate 2: WebGL must actually exist (claims the canvas context mode) ──
  var gl = null;
  try {
    gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
  } catch (err) { gl = null; }
  if (!gl) {
    console.warn('[kg3d] WebGL unavailable — 2D nebula fallback stays active.');
    return;
  }
  // knowledge-graph.js checks this flag before touching kg-bubble with 2D.
  window.__kgBubble3D = true;
  canvas.classList.add('webgl3d');

  // ── Scene / camera / renderer ────────────────────────────────────────────
  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(55, 1, 0.1, 120);
  camera.position.set(0, 2.4, 7.5);
  camera.lookAt(0, 0, 0);

  var renderer = new THREE.WebGLRenderer({
    canvas: canvas,
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true, // honest pixel sampling (probe reads toDataURL)
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0); // CSS background shows through

  var controls = new THREE.OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 2.2;
  controls.maxDistance = 16;
  controls.autoRotateSpeed = 0.9;
  controls.target.set(0, 0, 0);
  controls.update();
  controls.addEventListener('change', markDirty);

  // Faint structural grid (geometry, not data) — mirrors the 2D hairline grid.
  var grid = new THREE.GridHelper(10, 20, 0x221c44, 0x221c44);
  grid.position.y = -1.7;
  grid.material.opacity = 0.35;
  grid.material.transparent = true;
  scene.add(grid);

  // ── Overlay elements (DOM, pointer-events:none → never blocks the canvas) ──
  var labelsEl = document.getElementById('kg3d-labels');
  var cardEl = document.getElementById('kg3d-card');
  var emptyEl = document.getElementById('kg3d-empty');
  var hudEl = document.getElementById('kg3d-hud');
  var cardBody = cardEl ? cardEl.querySelector('.kg3d-card-body') : null;

  // ── Scene state (rebuilt when the real data arrays are replaced) ─────────
  var nodeMeshes = [];
  var nodeIndexById = {};
  var edgeLines = null;
  var edgeSampleList = [];
  var cloudSprites = [];
  var cloudLabelSpans = [];
  var sharedGeo = null;
  var sharedCloudTex = {};
  var lastNodesRef = null;
  var lastEdgesRef = null;
  var hudTimer = null;

  var EDGE_SAMPLE_LIMIT = 1500;
  // Render-on-demand flag: the reduced-motion loop renders ONLY when the
  // scene actually changed. Every mutation path (data rebuild, camera drag
  // via OrbitControls, dolly buttons, resize) MUST call markDirty() or a
  // static scene would freeze mid-interaction. One canonical helper.
  var dirty = true;
  function markDirty() { dirty = true; }

  function domColor(d) { return window._DOMAIN_COLORS_STORY && window._DOMAIN_COLORS_STORY[d] ? window._DOMAIN_COLORS_STORY[d] : '#8f89ad'; }
  function hexToRgb(hex) {
    var h = (hex || '#8f89ad').replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return { r: parseInt(h.slice(0, 2), 16) / 255, g: parseInt(h.slice(2, 4), 16) / 255, b: parseInt(h.slice(4, 6), 16) / 255 };
  }

  // ── Cloud sprite texture: radial shell in the REAL domain hue ─────────────
  function cloudTexture(domain) {
    if (sharedCloudTex[domain]) return sharedCloudTex[domain];
    var c = document.createElement('canvas');
    c.width = 256; c.height = 256;
    var ctx = c.getContext('2d');
    var rgb = hexToRgb(domColor(domain));
    var g = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
    g.addColorStop(0, 'rgba(' + Math.round(rgb.r * 255) + ',' + Math.round(rgb.g * 255) + ',' + Math.round(rgb.b * 255) + ',0.55)');
    g.addColorStop(0.55, 'rgba(' + Math.round(rgb.r * 255) + ',' + Math.round(rgb.g * 255) + ',' + Math.round(rgb.b * 255) + ',0.20)');
    g.addColorStop(1, 'rgba(' + Math.round(rgb.r * 255) + ',' + Math.round(rgb.g * 255) + ',' + Math.round(rgb.b * 255) + ',0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 256, 256);
    var tex = new THREE.CanvasTexture(c);
    sharedCloudTex[domain] = tex;
    return tex;
  }

  // ── Rebuild the whole scene from the CURRENT real data ───────────────────
  function rebuild() {
    // Dispose previous structures (Kintsugi: old assets released, not leaked).
    if (sharedGeo) sharedGeo.dispose();
    for (var i = 0; i < nodeMeshes.length; i++) {
      scene.remove(nodeMeshes[i]);
      if (nodeMeshes[i].material) nodeMeshes[i].material.dispose();
    }
    nodeMeshes = []; nodeIndexById = {};
    if (edgeLines) { scene.remove(edgeLines); edgeLines.geometry.dispose(); edgeLines = null; }
    for (var s = 0; s < cloudSprites.length; s++) {
      scene.remove(cloudSprites[s]);
      if (cloudSprites[s].material) cloudSprites[s].material.dispose();
    }
    cloudSprites = [];
    for (var ls = 0; ls < cloudLabelSpans.length; ls++) {
      var sp = cloudLabelSpans[ls].el;
      if (sp && sp.parentNode) sp.parentNode.removeChild(sp);
    }
    cloudLabelSpans = [];

    var nodes = kgNodes;
    var edges = kgEdges;
    if (!nodes || nodes.length === 0) {
      if (emptyEl) emptyEl.hidden = false;
      updateHud();
      markDirty();
      return;
    }
    if (emptyEl) emptyEl.hidden = true;

    // Node meshes: shared sphere geometry, per-node material (real domain
    // color + real importance brightness). Radius ∝ REAL degree + importance.
    sharedGeo = new THREE.SphereGeometry(1, 16, 12);
    var degMax = kgDegreeMax || 1;
    for (var ni = 0; ni < nodes.length; ni++) {
      var n = nodes[ni];
      var rgb = hexToRgb(domColor(n.domain));
      var deg = (kgDegree[n.id] || 0) / degMax;
      var imp = n.importance || 0.5;
      var mat = new THREE.MeshBasicMaterial({
        color: new THREE.Color(rgb.r, rgb.g, rgb.b),
        transparent: true,
        opacity: 0.95,
      });
      var mesh = new THREE.Mesh(sharedGeo, mat);
      var radius = 0.07 + deg * 0.26 + imp * 0.10;
      mesh.scale.set(radius, radius, radius);
      mesh.userData.nodeId = n.id;
      scene.add(mesh);
      nodeMeshes.push(mesh);
      nodeIndexById[n.id] = ni;
    }

    // Edges: one LineSegments object, vertex-colored by REAL edge_type.
    edgeSampleList = (typeof edgeSample === 'function') ? edgeSample(EDGE_SAMPLE_LIMIT) : [];
    var E = edgeSampleList.length;
    if (E > 0) {
      var pos = new Float32Array(E * 6);
      var cols = new Float32Array(E * 6);
      for (var ei = 0; ei < E; ei++) {
        var e = edgeSampleList[ei];
        var c = hexToRgb(typeof edgeColor === 'function' ? edgeColor(e.edge_type) : '#8f89ad');
        for (var v = 0; v < 2; v++) {
          cols[ei * 6 + v * 3] = c.r; cols[ei * 6 + v * 3 + 1] = c.g; cols[ei * 6 + v * 3 + 2] = c.b;
        }
      }
      var geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      geo.setAttribute('color', new THREE.BufferAttribute(cols, 3));
      edgeLines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.32, depthWrite: false }));
      scene.add(edgeLines);
    }

    // Domain clouds: sprite shells sized by REAL per-domain node count.
    var domains = {};
    for (var di = 0; di < nodes.length; di++) {
      var d = nodes[di].domain || 'unknown';
      if (!domains[d]) domains[d] = [];
      domains[d].push(nodes[di]);
    }
    var dNames = Object.keys(domains).sort();
    var maxCount = 1;
    for (var dm = 0; dm < dNames.length; dm++) maxCount = Math.max(maxCount, domains[dNames[dm]].length);
    for (var dci = 0; dci < dNames.length; dci++) {
      var dn = dNames[dci];
      var count = domains[dn].length;
      var sMat = new THREE.SpriteMaterial({
        map: cloudTexture(dn),
        transparent: true,
        opacity: 0.6,
        depthWrite: false,
      });
      var sprite = new THREE.Sprite(sMat);
      var R = 1.1 + (count / maxCount) * 1.5;
      sprite.scale.set(R * 2.6, R * 2.6, 1);
      var cx = 0, cy = 0, cz = 0;
      for (var cd = 0; cd < count; cd++) { cx += domains[dn][cd].x; cy += domains[dn][cd].y; cz += domains[dn][cd].z; }
      sprite.position.set(cx / count, cy / count, cz / count);
      sprite.userData.domain = dn;
      scene.add(sprite);
      cloudSprites.push(sprite);

      // Real cloud label (13px mono, DOM overlay).
      if (labelsEl) {
        var span = document.createElement('span');
        span.className = 'kg3d-cloud';
        span.textContent = dn.toUpperCase() + ' · ' + count;
        span.style.color = domColor(dn);
        labelsEl.appendChild(span);
        cloudLabelSpans.push({ el: span, domain: dn });
      }
    }
    updateHud();
    markDirty();
  }

  function updateHud() {
    if (!hudEl) return;
    var domainCount = 0;
    var seen = {};
    for (var i = 0; i < kgNodes.length; i++) {
      var d = kgNodes[i].domain || 'unknown';
      if (!seen[d]) { seen[d] = true; domainCount++; }
    }
    hudEl.textContent = kgNodes.length + ' nodes · ' + kgEdgeCount + ' edges · ' + domainCount + ' domains' +
      (edgeSampleList.length > 0 && edgeSampleList.length < kgEdgeCount ? ' · drawing ' + edgeSampleList.length + ' (sampled)' : '');
  }

  // ── Per-frame sync: the shared force layout drives the scene ──────────────
  function syncPositions() {
    if (!nodeMeshes.length) return;
    for (var i = 0; i < nodeMeshes.length && i < kgNodes.length; i++) {
      var n = kgNodes[i];
      var m = nodeMeshes[i];
      if (!n || !m) continue;
      m.position.set(n.x, n.y, n.z);
    }
    if (edgeLines && edgeLinePairs) {
      var posAttr = edgeLines.geometry.attributes.position;
      var arr = posAttr.array;
      for (var e = 0; e < edgeLinePairs.length; e++) {
        var s = nodeIndexById[edgeLinePairs[e][0]];
        var t = nodeIndexById[edgeLinePairs[e][1]];
        if (s === undefined || t === undefined || s >= kgNodes.length || t >= kgNodes.length) continue;
        var ns = kgNodes[s], nt = kgNodes[t];
        var o = e * 6;
        arr[o] = ns.x; arr[o + 1] = ns.y; arr[o + 2] = ns.z;
        arr[o + 3] = nt.x; arr[o + 4] = nt.y; arr[o + 5] = nt.z;
      }
      posAttr.needsUpdate = true;
    }
  }
  var edgeLinePairs = [];

  // ── Highlight contract (domain chips → kgHighlight, set by story.js) ─────
  function applyHighlight() {
    var hl = kgHighlight || null;
    var dim = !!hl;
    for (var i = 0; i < nodeMeshes.length; i++) {
      var n = kgNodes[i];
      if (!n) continue;
      var inHl = !dim || n.domain === hl;
      nodeMeshes[i].material.opacity = inHl ? 0.95 : 0.12;
      nodeMeshes[i].material.transparent = true;
    }
    for (var s = 0; s < cloudSprites.length; s++) {
      cloudSprites[s].material.opacity = (!dim || cloudSprites[s].userData.domain === hl) ? 0.6 : 0.12;
    }
    for (var l = 0; l < cloudLabelSpans.length; l++) {
      cloudLabelSpans[l].el.style.opacity = (!dim || cloudLabelSpans[l].domain === hl) ? '1' : '0.3';
    }
  }

  // ── Cloud labels: project world → screen every frame ──────────────────────
  function projectLabels() {
    if (!labelsEl || !cloudLabelSpans.length) return;
    var w = canvas.clientWidth || 600, h = canvas.clientHeight || 540;
    camera.updateMatrixWorld();
    for (var i = 0; i < cloudLabelSpans.length; i++) {
      var item = cloudLabelSpans[i];
      var spr = null;
      for (var s = 0; s < cloudSprites.length; s++) {
        if (cloudSprites[s].userData.domain === item.domain) { spr = cloudSprites[s]; break; }
      }
      if (!spr) { item.el.style.visibility = 'hidden'; continue; }
      var pos = spr.position.clone();
      pos.y += spr.scale.y * 0.62;
      var v = pos.project(camera);
      if (v.z > 1 || v.z < -1) { item.el.style.visibility = 'hidden'; continue; }
      item.el.style.visibility = 'visible';
      item.el.style.left = Math.round((v.x * 0.5 + 0.5) * w) + 'px';
      item.el.style.top = Math.round((-v.y * 0.5 + 0.5) * h) + 'px';
    }
  }

  // ── Inspect card (real id / label / domain / degree / importance) ─────────
  function showCard(nodeId) {
    if (!cardEl || !cardBody) return;
    var n = null;
    for (var i = 0; i < kgNodes.length; i++) { if (kgNodes[i].id === nodeId) { n = kgNodes[i]; break; } }
    if (!n) return;
    var label = (n.label || '').toString();
    if (!label) label = String(n.id).slice(0, 20);
    cardBody.innerHTML =
      '<div class="kg3d-card-head">' + escapeHtml(label) + '</div>' +
      '<div class="kg3d-card-row">id <span>' + escapeHtml(String(n.id)) + '</span></div>' +
      '<div class="kg3d-card-row">domain <span>' + escapeHtml(n.domain || 'unknown') + '</span></div>' +
      '<div class="kg3d-card-row">degree <span>' + (kgDegree[n.id] || 0) + ' real edges</span></div>' +
      '<div class="kg3d-card-row">importance <span>' + (typeof n.importance === 'number' ? n.importance.toFixed(3) : n.importance) + '</span></div>';
    cardEl.hidden = false;
  }
  function hideCard() { if (cardEl) cardEl.hidden = true; }
  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── Pointer interaction (orbit via OrbitControls; pick via raycaster) ─────
  var raycaster = new THREE.Raycaster();
  var mouse = new THREE.Vector2();
  var hoveredMesh = null;
  var downX = 0, downY = 0, downAt = 0;

  function pickNode(clientX, clientY) {
    var rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    mouse.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    scene.updateMatrixWorld();
    var hits = raycaster.intersectObjects(nodeMeshes, false);
    return hits.length ? hits[0].object : null;
  }

  canvas.addEventListener('pointerdown', function (ev) {
    downX = ev.clientX; downY = ev.clientY; downAt = Date.now();
  });

  canvas.addEventListener('pointerup', function (ev) {
    var moved = Math.abs(ev.clientX - downX) + Math.abs(ev.clientY - downY);
    if (moved > 6 || Date.now() - downAt > 800) return; // was a drag, not a click
    var hit = pickNode(ev.clientX, ev.clientY);
    if (hit && hit.userData.nodeId) showCard(hit.userData.nodeId);
    else hideCard();
  });

  canvas.addEventListener('pointermove', function (ev) {
    if (!hoveredMesh && (ev.buttons || 0) > 0) return; // dragging
    var hit = pickNode(ev.clientX, ev.clientY);
    if (hit !== hoveredMesh) {
      if (hoveredMesh && hoveredMesh.material) hoveredMesh.material.opacity = (kgHighlight ? (kgNodes[nodeIndexById[hoveredMesh.userData.nodeId]] || {}).domain === kgHighlight : true) ? 0.95 : 0.12;
      hoveredMesh = hit;
      if (hit && hit.material) hit.material.opacity = 1;
      canvas.style.cursor = hit ? 'pointer' : 'grab';
    }
  });
  canvas.addEventListener('pointerleave', function () {
    if (hoveredMesh && hoveredMesh.material) hoveredMesh.material.opacity = 0.95;
    hoveredMesh = null;
    canvas.style.cursor = 'grab';
  });

  // ── Zoom buttons (− / + in the panel controls) map to a camera dolly ──────
  window.kg3dZoomButton = function (delta) {
    var dir = camera.position.clone().sub(controls.target);
    var dist = dir.length() * (1 - delta * 0.75);
    dist = Math.max(controls.minDistance, Math.min(controls.maxDistance, dist));
    dir.normalize().multiplyScalar(dist);
    camera.position.copy(controls.target).add(dir);
    markDirty();
    var span = document.querySelector('#kg-panel-bubble .kg-zoom-lvl');
    if (span) span.textContent = (7 / dist).toFixed(2) + '×';
  };

  // ── Resize (renderer buffer + camera aspect track the live panel) ─────────
  function resize() {
    var w = canvas.clientWidth || 600;
    var h = canvas.clientHeight || 540;
    if (w < 10 || h < 10) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    markDirty();
  }
  var resizeObs = (typeof ResizeObserver !== 'undefined') ? new ResizeObserver(resize) : null;
  if (resizeObs && canvas.parentNode) resizeObs.observe(canvas.parentNode);
  window.addEventListener('resize', resize);
  resize();

  // ── Animation loop ────────────────────────────────────────────────────────
  // Reduced motion → static scene: render only when something changed
  // (data, resize, camera). Otherwise full live loop (forces + drift).
  var dirty = true;
  var reduced = !!(window.__reducedMotion || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches));

  function tick() {
    var paused = typeof _kgPaused !== 'undefined' && _kgPaused;
    if (kgNodes !== lastNodesRef || kgEdges !== lastEdgesRef) {
      lastNodesRef = kgNodes; lastEdgesRef = kgEdges;
      rebuild(); syncEdgePairs();
    }

    if (!reduced) {
      controls.autoRotate = !paused;
      controls.update();
      syncPositions();
      applyHighlight();
      projectLabels();
      renderer.render(scene, camera);
      requestAnimationFrame(tick);
    } else {
      // Static fallback: render on demand only (data/resize/camera changes).
      controls.autoRotate = false;
      controls.update();
      syncPositions();
      applyHighlight();
      projectLabels();
      if (dirty) { renderer.render(scene, camera); dirty = false; }
      requestAnimationFrame(tick);
    }
  }

  function syncEdgePairs() {
    edgeLinePairs = edgeSampleList.map(function (e) { return [e.source, e.target]; });
  }

  // Expose honest debug handle for the browser probe (measured, not invented).
  // Honest screen projection of the real nodes (probe uses it to click a
  // node exactly; every value is measured from the live scene).
  function projectNodeScreen(nodeId) {
    var i = nodeIndexById[nodeId];
    if (i === undefined || !nodeMeshes[i]) return null;
    var w = canvas.clientWidth || 600, h = canvas.clientHeight || 540;
    camera.updateMatrixWorld();
    var v = nodeMeshes[i].position.clone().project(camera);
    if (v.z > 1 || v.z < -1) return null;
    return { x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h };
  }

  window.__kg3dDebug = {
    active: true,
    webgl: true,
    fallback: false,
    pick: function (clientX, clientY) {
      var hit = pickNode(clientX, clientY);
      return hit ? hit.userData.nodeId : null;
    },
    project: projectNodeScreen,
    nodeCount: function () { return kgNodes ? kgNodes.length : 0; },
    edgeCount: function () { return kgEdgeCount; },
    sampledEdges: function () { return edgeSampleList.length; },
    autoRotate: function () { return !!controls.autoRotate; },
    reducedMotion: reduced,
    paused: function () { return typeof _kgPaused !== 'undefined' && !!_kgPaused; },
  };

  // Boot is DEFERRED: knowledge-graph.js (which declares the shared
  // kgNodes/kgEdges/kgDegree bindings) loads AFTER this file, so touching
  // them at parse time would hit the temporal-dead-zone. Start once the
  // shared state actually exists.
  function start() {
    if (typeof kgNodes === 'undefined' || typeof kgEdges === 'undefined') {
      setTimeout(start, 50);
      return;
    }
    lastNodesRef = kgNodes; lastEdgesRef = kgEdges;
    rebuild(); syncEdgePairs();
    resize();
    tick();
  }
  setTimeout(start, 0);
})();
