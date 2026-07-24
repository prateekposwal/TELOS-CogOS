/**
 * Aviku Brain — Canvas 2D cognitive pipeline visualization
 * Enhanced: 3D perspective, grid floor, fog, rotating rings, motion trails, pulsing rings
 * Self-contained, no WebGL/Three.js needed. Works in any browser including Capacitor WebView.
 */

let brainCanvas, ctx, brainW, brainH;
let brainAnimId = null;
let brainTime = 0;
let phaseNodes2D = [];
let activePulses2D = [];
let traceHistory2D = [];
let burstParticles = [];
let expandingRings = [];
let lastRingSpawn = -10;
let fogPhase = 0;
let orbitalTrailHistory = [];
let prevOrbitalPositions = null;

const PHASE_NAMES_BRAIN = ['PERCEIVE', 'STREAMS', 'SIMULATE', 'EVALUATE', 'SYNTHESIS', 'SELECT', 'COUNCIL'];
const PHASE_COLORS_2D = ['#4ade80','#60a5fa','#fbbf24','#a78bfa','#f472b6','#fb923c','#34d399'];
const STREAM_COLORS_2D = { Reflex: '#ff6b6b', Perception: '#4ade80', Memory: '#60a5fa', Planning: '#fbbf24' };

function initBrain() {
  brainCanvas = document.getElementById('brain-container');
  if (!brainCanvas || brainCanvas.tagName !== 'CANVAS') {
    const container = document.getElementById('brain-container') || document.querySelector('.brain-panel');
    if (!container) return;
    brainCanvas = document.createElement('canvas');
    brainCanvas.id = 'brain-canvas';
    brainCanvas.style.width = '100%';
    brainCanvas.style.height = '100%';
    container.innerHTML = '';
    container.appendChild(brainCanvas);
  }

  ctx = brainCanvas.getContext('2d');
  if (!ctx) { console.warn('Canvas not supported'); return; }

  resizeBrain();
  window.addEventListener('resize', resizeBrain);

  const count = PHASE_NAMES_BRAIN.length;
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
    phaseNodes2D.push({
      x: 0, y: 0,
      angle: angle,
      baseColor: PHASE_COLORS_2D[i],
      glow: 0.3,
      targetGlow: 0.3,
      label: PHASE_NAMES_BRAIN[i],
      active: false,
      zDepth: 0,
      scale: 1,
    });
  }

  brainAnimId = requestAnimationFrame(renderBrain);
}

function resizeBrain() {
  if (!brainCanvas || !ctx) return;
  const rect = brainCanvas.parentElement?.getBoundingClientRect() || { width: 340, height: 300 };
  brainW = rect.width || 340;
  brainH = rect.height || 300;
  brainCanvas.width = brainW * (window.devicePixelRatio || 1);
  brainCanvas.height = brainH * (window.devicePixelRatio || 1);
  brainCanvas.style.width = brainW + 'px';
  brainCanvas.style.height = brainH + 'px';
  ctx.setTransform((window.devicePixelRatio || 1), 0, 0, (window.devicePixelRatio || 1), 0, 0);
}

function renderBrain(timestamp) {
  brainAnimId = requestAnimationFrame(renderBrain);
  if (!ctx || !brainCanvas) return;

  brainTime = timestamp / 1000 || 0;
  const cx = brainW / 2;
  const cy = brainH / 2;
  const radius = Math.min(brainW, brainH) * 0.38;

  // ── Clear ──
  ctx.clearRect(0, 0, brainW, brainH);

  // ── Background glow ──
  const bgGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 1.5);
  bgGrad.addColorStop(0, 'rgba(20,20,50,0.3)');
  bgGrad.addColorStop(1, 'rgba(10,10,15,0)');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, brainW, brainH);

  // ── 1. Grid floor (wireframe hex/radar style) ──
  drawGridFloor(ctx, cx, cy, radius);

  // ── 2. Update node positions with 3D perspective ──
  phaseNodes2D.forEach((node, i) => {
    const breathOffset = Math.sin(brainTime * 0.5 + i) * 6;
    node.x = cx + Math.cos(node.angle) * (radius + breathOffset);
    node.y = cy + Math.sin(node.angle) * (radius * 0.7 + breathOffset * 0.5);

    // zDepth: -1 (top/far) → +1 (bottom/near)
    node.zDepth = Math.sin(node.angle);
    node.scale = 0.7 + (node.zDepth + 1) * 0.3;

    node.glow += (node.targetGlow - node.glow) * 0.05;
  });

  // Sort far→near for correct draw order
  const sortedNodes = [...phaseNodes2D].sort((a, b) => a.zDepth - b.zDepth);

  // ── 3. Neural connections ──
  for (let i = 0; i < phaseNodes2D.length; i++) {
    const j = (i + 1) % phaseNodes2D.length;
    const n1 = phaseNodes2D[i];
    const n2 = phaseNodes2D[j];

    const midX = (n1.x + n2.x) / 2 + Math.sin(brainTime * 0.3 + i) * 16;
    const midY = (n1.y + n2.y) / 2 + Math.cos(brainTime * 0.4 + i) * 10;

    ctx.beginPath();
    ctx.moveTo(n1.x, n1.y);
    ctx.quadraticCurveTo(midX, midY, n2.x, n2.y);
    ctx.strokeStyle = `rgba(100,100,150,${0.12 + Math.sin(brainTime + i) * 0.06})`;
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(n1.x, n1.y);
    ctx.quadraticCurveTo(midX, midY, n2.x, n2.y);
    ctx.strokeStyle = `rgba(${hexToRgb(n1.baseColor)},${0.05 + nodeGlow(i) * 0.08})`;
    ctx.lineWidth = 5;
    ctx.stroke();
  }

  // ── 4. Expanding pulsing rings from center ──
  if (brainTime - lastRingSpawn > 3.8) {
    lastRingSpawn = brainTime;
    const hue = 200 + Math.random() * 60;
    expandingRings.push({
      progress: 0,
      speed: 0.010 + Math.random() * 0.005,
      maxRadius: radius * 1.6,
      hue: hue,
    });
  }
  for (let r = expandingRings.length - 1; r >= 0; r--) {
    const ring = expandingRings[r];
    ring.progress += ring.speed;
    if (ring.progress > 1) { expandingRings.splice(r, 1); continue; }

    const ringR = ring.progress * ring.maxRadius;
    const alpha = 0.35 * (1 - ring.progress);

    ctx.beginPath();
    ctx.ellipse(cx, cy, ringR, ringR * 0.7, 0, 0, Math.PI * 2);
    ctx.strokeStyle = `hsla(${ring.hue}, 80%, 65%, ${alpha})`;
    ctx.lineWidth = 2.5 * (1 - ring.progress);
    ctx.shadowColor = `hsl(${ring.hue}, 80%, 65%)`;
    ctx.shadowBlur = 10 * (1 - ring.progress);
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Inner ghost ring
    ctx.beginPath();
    ctx.ellipse(cx, cy, ringR * 0.85, ringR * 0.6, 0, 0, Math.PI * 2);
    ctx.strokeStyle = `hsla(${ring.hue + 30}, 60%, 70%, ${alpha * 0.4})`;
    ctx.lineWidth = 1 * (1 - ring.progress);
    ctx.stroke();
  }

  // ── 5. Pulse particles (data trace animations) ──
  for (let p = activePulses2D.length - 1; p >= 0; p--) {
    const pulse = activePulses2D[p];
    pulse.progress += pulse.speed;
    if (pulse.progress > 1) { activePulses2D.splice(p, 1); continue; }

    const from = phaseNodes2D[pulse.fromIdx];
    const to = phaseNodes2D[pulse.toIdx];
    if (!from || !to) { activePulses2D.splice(p, 1); continue; }

    const t = pulse.progress;
    const midX2 = (from.x + to.x) / 2 + Math.sin(pulse.seed + t * Math.PI) * 24;
    const midY2 = (from.y + to.y) / 2 + Math.cos(pulse.seed + t * Math.PI) * 16;
    const tt = t * t;
    const px = (1 - t) * (1 - t) * from.x + 2 * (1 - t) * t * midX2 + tt * to.x;
    const py = (1 - t) * (1 - t) * from.y + 2 * (1 - t) * t * midY2 + tt * to.y;

    const alpha = 1 - t * 0.5;
    const size = 3 + Math.sin(t * Math.PI) * 4;

    ctx.beginPath();
    ctx.arc(px, py, size, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${hexToRgb(pulse.color)},${alpha})`;
    ctx.shadowColor = pulse.color;
    ctx.shadowBlur = 16 * alpha;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // ── 6. Phase nodes (far→near) ──
  sortedNodes.forEach((node) => {
    const idx = phaseNodes2D.indexOf(node);
    const pulse = Math.sin(brainTime * 2 + idx * 1.5) * 0.3 + 0.7;
    const size = (18 + node.glow * 12 + pulse * 4) * node.scale;
    const alpha = 0.5 + node.glow * 0.4;

    // Outer glow
    const grad = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, size * 2.5);
    grad.addColorStop(0, `rgba(${hexToRgb(node.baseColor)},${alpha * 0.3})`);
    grad.addColorStop(1, `rgba(${hexToRgb(node.baseColor)},0)`);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(node.x, node.y, size * 2.5, 0, Math.PI * 2);
    ctx.fill();

    // Core
    ctx.beginPath();
    ctx.arc(node.x, node.y, size * 0.6, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${hexToRgb(node.baseColor)},${alpha})`;
    ctx.shadowColor = node.baseColor;
    ctx.shadowBlur = (25 + pulse * 10) * node.scale;
    ctx.fill();
    ctx.shadowBlur = 0;

    // Label — glows brighter when active, with upward float
    const floatOffset = node.active ? Math.sin(brainTime * 2 + idx) * 3 : 0;
    const labelBrightness = 0.4 + node.glow * 0.3 + (node.active ? 0.25 : 0);
    ctx.fillStyle = `rgba(180,180,200,${labelBrightness})`;
    ctx.font = `${14 * node.scale}px monospace`;
    ctx.textAlign = 'center';

    if (node.active) {
      ctx.shadowColor = node.baseColor;
      ctx.shadowBlur = 12 + Math.sin(brainTime * 3 + idx) * 6;
      ctx.fillText(node.label, node.x, node.y + size * 1.8 + floatOffset);
      ctx.shadowBlur = 0;
    } else {
      ctx.fillText(node.label, node.x, node.y + size * 1.8);
    }
  });

  // ── 7. Central AVIKU label + rotating rings + spiral ──
  drawCenterLabel(ctx, cx, cy);

  // ── 8. Orbiting particles with motion trails ──
  drawOrbitingParticles(ctx, cx, cy, radius);

  // ── 9. Burst particles ──
  for (let i = burstParticles.length - 1; i >= 0; i--) {
    const p = burstParticles[i];
    p.x += Math.cos(p.angle) * p.speed;
    p.y += Math.sin(p.angle) * p.speed;
    p.life -= 0.015;
    p.speed *= 0.97;
    if (p.life <= 0) { burstParticles.splice(i, 1); continue; }
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${hexToRgb(p.color)},${p.life * 0.6})`;
    ctx.shadowColor = p.color;
    ctx.shadowBlur = 10 * p.life;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // ── 10. Fog/haze overlay ──
  fogPhase += 0.002;
  const fogGrad = ctx.createRadialGradient(cx, cy, radius * 0.5, cx, cy, radius * 1.5);
  fogGrad.addColorStop(0, 'rgba(0,0,0,0)');
  fogGrad.addColorStop(0.6, 'rgba(0,0,0,0)');
  const fogA = 0.06 + Math.sin(brainTime * 0.08 + fogPhase) * 0.03;
  const fogHue = 220 + Math.sin(brainTime * 0.04) * 40;
  fogGrad.addColorStop(0.85, `hsla(${fogHue}, 25%, 8%, ${fogA})`);
  fogGrad.addColorStop(1, `hsla(${fogHue + 30}, 35%, 4%, ${fogA * 1.6})`);
  ctx.fillStyle = fogGrad;
  ctx.fillRect(0, 0, brainW, brainH);
}

// ─── Grid floor (concentric ellipses + radial spokes) ───
function drawGridFloor(ctx, cx, cy, radius) {
  const rings = 5;
  const spokes = 8;

  ctx.save();
  ctx.strokeStyle = 'rgba(60,60,120,0.07)';
  ctx.lineWidth = 0.5;

  for (let r = 1; r <= rings; r++) {
    const rr = (r / rings) * radius * 1.25;
    ctx.beginPath();
    ctx.ellipse(cx, cy, rr, rr * 0.7, 0, 0, Math.PI * 2);
    ctx.stroke();
  }

  for (let i = 0; i < spokes; i++) {
    const a = (i / spokes) * Math.PI * 2 + brainTime * 0.015;
    const dx = Math.cos(a) * radius * 1.25;
    const dy = Math.sin(a) * radius * 0.7 * 1.25;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + dx, cy + dy);
    ctx.stroke();
  }

  ctx.restore();
}

// ─── Central AVIKU label with rotating rings and spiral ───
function drawCenterLabel(ctx, cx, cy) {
  // Inner rotating ring (clockwise) — 2x larger, brighter, glowing
  const innerDots = 24;
  const innerR = 26 + Math.sin(brainTime * 0.4) * 4;
  for (let i = 0; i < innerDots; i++) {
    const a = (i / innerDots) * Math.PI * 2 + brainTime * 0.7;
    const dx = Math.cos(a) * innerR;
    const dy = Math.sin(a) * innerR * 0.55;
    const dotA = 0.5 + Math.sin(brainTime * 1.5 + i * 2) * 0.2;
    const pulse = Math.sin(brainTime * 2.5 + i * 1.3) * 0.5 + 0.5;
    ctx.beginPath();
    ctx.arc(cx + dx, cy + dy, 2 + Math.sin(brainTime + i) * 1, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(180,220,255,${dotA * (0.7 + pulse * 0.3)})`;
    ctx.shadowColor = 'rgba(140,180,255,0.6)';
    ctx.shadowBlur = 8 + Math.sin(brainTime * 2 + i) * 4;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // Outer ring (counter-clockwise) — 2x larger, brighter, glowing
  const outerDots = 16;
  const outerR = innerR + 18;
  for (let i = 0; i < outerDots; i++) {
    const a = (i / outerDots) * Math.PI * 2 - brainTime * 0.35;
    const dx = Math.cos(a) * outerR;
    const dy = Math.sin(a) * outerR * 0.55;
    const pulse = Math.sin(brainTime * 2 + i * 1.5) * 0.5 + 0.5;
    ctx.beginPath();
    ctx.arc(cx + dx, cy + dy, 1.6, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(220,170,255,${(0.35 + Math.sin(brainTime * 0.8 + i) * 0.15) * (0.8 + pulse * 0.2)})`;
    ctx.shadowColor = 'rgba(200,150,255,0.6)';
    ctx.shadowBlur = 8 + Math.sin(brainTime * 1.5 + i) * 3;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // Spiral arm — 2x larger, brighter, glowing
  const spiralN = 14;
  for (let i = 0; i < spiralN; i++) {
    const t = i / spiralN;
    const a = t * Math.PI * 4 + brainTime * 0.55;
    const dist = t * (innerR + 24);
    const dx = Math.cos(a) * dist;
    const dy = Math.sin(a) * dist * 0.55;
    const pulse = Math.sin(brainTime * 3 + i * 2) * 0.3 + 0.7;
    ctx.beginPath();
    ctx.arc(cx + dx, cy + dy, 3.2 - t * 2.0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(180,230,255,${(1 - t) * 0.6 * pulse})`;
    ctx.shadowColor = 'rgba(150,210,255,0.5)';
    ctx.shadowBlur = 6 * (1 - t) + 2;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // Label glow — scaled proportionally
  const labelPulse = Math.sin(brainTime * 1.2) * 0.12 + 0.88;
  const labelGlow = Math.sin(brainTime * 0.6) * 0.35 + 0.65;

  const lGrad = ctx.createRadialGradient(cx, cy + 6, 0, cx, cy + 6, 64);
  lGrad.addColorStop(0, `rgba(130,170,255,${labelGlow * 0.3})`);
  lGrad.addColorStop(1, 'rgba(130,170,255,0)');
  ctx.fillStyle = lGrad;
  ctx.beginPath();
  ctx.arc(cx, cy + 6, 64, 0, Math.PI * 2);
  ctx.fill();

  // AVIKU text — with pulsing glow
  ctx.shadowColor = 'rgba(130,170,255,0.8)';
  ctx.shadowBlur = 20 + Math.sin(brainTime * 1.5) * 10;
  ctx.fillStyle = `rgba(200,200,240,${0.5 * labelPulse})`;
  ctx.font = 'bold 28px monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('AVIKU', cx, cy + 6);
  ctx.shadowBlur = 0;

  // Subtle underline glow — scaled
  ctx.fillStyle = `rgba(130,200,255,${0.15 * labelPulse})`;
  ctx.fillRect(cx - 48, cy + 19, 96, 1.5);
}

// ─── Orbiting particles with motion trails ───
function drawOrbitingParticles(ctx, cx, cy, radius) {
  const count = 80;
  const currentPositions = [];

  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2 + brainTime * 0.05;
    const dist = radius * 1.35 + Math.sin(brainTime * 0.3 + i * 0.5) * 15;
    const px = cx + Math.cos(a) * dist;
    const py = cy + Math.sin(a) * (dist * 0.7);
    currentPositions.push({ x: px, y: py });
  }

  orbitalTrailHistory.push(currentPositions);
  if (orbitalTrailHistory.length > 10) orbitalTrailHistory.shift();

  // Draw trails (fading older → newer)
  for (let t = 0; t < orbitalTrailHistory.length; t++) {
    const frac = t / orbitalTrailHistory.length;
    const trailA = frac * 0.06;
    const trailS = 1.2 * frac;
    for (const pos of orbitalTrailHistory[t]) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, trailS, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(100,150,255,${trailA})`;
      ctx.fill();
    }
  }

  // Draw current particles
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2 + brainTime * 0.05;
    const dist = radius * 1.35 + Math.sin(brainTime * 0.3 + i * 0.5) * 15;
    const px = cx + Math.cos(a) * dist;
    const py = cy + Math.sin(a) * (dist * 0.7);
    const alpha2 = 0.12 + Math.sin(brainTime + i) * 0.06;
    ctx.beginPath();
    ctx.arc(px, py, 1.5 + Math.sin(brainTime * 0.5 + i) * 1, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(100,150,255,${alpha2})`;
    ctx.fill();
  }
}

function nodeGlow(i) {
  return phaseNodes2D[i] ? phaseNodes2D[i].glow : 0;
}

function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? `${parseInt(result[1],16)},${parseInt(result[2],16)},${parseInt(result[3],16)}` : '100,100,100';
}

// ─── Visualize a trace on the brain ───
function visualizeTrace(trace) {
  if (!trace || phaseNodes2D.length === 0) return;
  traceHistory2D.push(trace);
  if (traceHistory2D.length > 20) traceHistory2D.shift();

  const cx = brainW / 2;
  const cy = brainH / 2;
  for (let i = 0; i < 30; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 2 + Math.random() * 4;
    burstParticles.push({
      x: cx, y: cy, angle, speed,
      life: 1, color: PHASE_COLORS_2D[Math.floor(Math.random() * PHASE_COLORS_2D.length)],
      size: 2 + Math.random() * 3,
    });
  }

  const blocked = trace.firewall_blocked || !trace.council_validated;
  const worlds = trace.worlds_simulated || 0;

  // Update node glows
  phaseNodes2D.forEach((node, i) => {
    if (blocked) {
      node.targetGlow = 0.5 + (i / 7) * 0.3;
    } else {
      node.targetGlow = 0.3 + (i / 7) * 0.5;
    }
    node.active = !blocked;
    node.targetGlow = Math.min(1, node.targetGlow + 0.4);
    setTimeout(() => { if (node) node.targetGlow = Math.max(0.2, node.targetGlow - 0.4); }, 300);
  });

  // Fire pulses along connections
  const pulseCount = blocked ? 1 : 2 + Math.min(Math.floor(worlds / 5), 4);
  for (let p = 0; p < pulseCount; p++) {
    const fromIdx = Math.floor(Math.random() * (phaseNodes2D.length - 1));
    activePulses2D.push({
      fromIdx,
      toIdx: (fromIdx + 1) % phaseNodes2D.length,
      progress: 0,
      speed: 0.015 + Math.random() * 0.02,
      color: PHASE_COLORS_2D[fromIdx] || '#4ade80',
      seed: Math.random() * 100,
    });
  }

  // Update sidebar DI/MD
  const diEl = document.getElementById('di-value');
  const mdEl = document.getElementById('md-value');
  if (diEl) diEl.textContent = (trace.decision_integrity || 1.0).toFixed(3);
  if (mdEl) mdEl.textContent = (trace.mission_drift || 0).toFixed(3);
}

// Auto-init
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initBrain);
else setTimeout(initBrain, 100);

// Expose for dashboard integration
window.visualizeTrace = visualizeTrace;
