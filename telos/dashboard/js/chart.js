// TELOS Chart Module — DI/MD history plot, big-data-portrait treatment.
//
// Honesty contract: the ONLY data drawn here is state.diHistory /
// state.mdHistory, fed by applyTrace() from real /api/checkpoints traces or
// live WebSocket pushes. No Math.random values, no fabricated series.
// The endpoint dot pulses only when the user has not asked for reduced
// motion (window.__reducedMotion is set in dashboard.js).
// Colors are read from the design tokens (no hard-coded hex in components).

// Read a design token (with fallback for headless/unit contexts).
function _token(name, fallback) {
  try {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch (e) { return fallback; }
}
function _rgba(hex, alpha) {
  var h = String(hex || '').replace('#', '');
  if (h.length !== 6) return 'rgba(125,151,255,' + alpha + ')';
  var r = parseInt(h.slice(0, 2), 16);
  var g = parseInt(h.slice(2, 4), 16);
  var b = parseInt(h.slice(4, 6), 16);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

function drawChart(canvas) {
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || canvas.width;
  const cssH = canvas.clientHeight || canvas.height;
  if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = cssW, h = cssH;

  const reducedMotion = !!(window.__reducedMotion) ||
    (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches);
  const time = state.time || 0;

  // Tokens (single source of color).
  const cDi = _token('--success', '#4ade80');
  const cMd = _token('--danger', '#f87171');
  const cBg = _token('--canvas-bg', '#0b0817');
  const cDim = _token('--text-dim', '#8f89ad');
  const cGrid = _token('--border', '#221c44');
  const cText = _token('--text', '#f1eff8');

  // Plot area. Left axis = DI (0..1), right axis = MD (0..5).
  const pad = { top: 34, bottom: 34, left: 56, right: 64 };
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;
  const x0 = pad.left, x1 = pad.left + plotW;
  const y0 = pad.top, y1 = pad.top + plotH;

  const diY = v => y1 - (v / 1.0) * plotH;   // DI 0 → bottom, 1 → top
  const mdY = v => y1 - (v / 5.0) * plotH;   // MD 0 → bottom, 5 → top

  // ── Background ──
  ctx.fillStyle = cBg;
  ctx.fillRect(0, 0, w, h);

  // ── Gridlines + tick labels (≥13px per DESIGN.md) ──
  ctx.font = '13px "Space Mono", monospace';
  ctx.textBaseline = 'middle';
  ctx.strokeStyle = _rgba(cGrid, 0.5);
  ctx.lineWidth = 1;

  // DI ticks (left axis)
  const diTicks = [0, 0.25, 0.5, 0.75, 1];
  ctx.fillStyle = _rgba(cDi, 0.95);
  ctx.textAlign = 'right';
  for (const t of diTicks) {
    const y = diY(t);
    ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
    ctx.fillText(t.toFixed(2), x0 - 8, y);
  }
  // MD ticks (right axis)
  const mdTicks = [0, 1, 2, 3, 4, 5];
  ctx.fillStyle = _rgba(cMd, 0.95);
  ctx.textAlign = 'left';
  for (const t of mdTicks) {
    const y = mdY(t);
    ctx.fillText(String(t), x1 + 8, y);
  }

  // ── Axis captions ──
  ctx.fillStyle = _rgba(cDi, 0.9);
  ctx.textAlign = 'right';
  ctx.fillText('DI 0–1', x0, 14);
  ctx.fillStyle = _rgba(cMd, 0.9);
  ctx.textAlign = 'left';
  ctx.fillText('MD 0–5', x1, 14);

  const len = state.diHistory.length;
  if (len < 2) {
    ctx.fillStyle = cDim;
    ctx.font = '14px "Space Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Waiting for real trace data…', w / 2, h / 2);
    return;
  }

  // x positions: even spacing across the plot area.
  const step = plotW / (len - 1);
  const pts = state.diHistory.map((di, i) => ({
    x: x0 + i * step,
    di: Math.max(0, Math.min(1, di || 0)),
    md: Math.max(0, Math.min(5, state.mdHistory[i] || 0)),
  }));

  // ── DI area + line (green, left axis) ──
  ctx.beginPath();
  ctx.moveTo(pts[0].x, y1);
  for (const p of pts) ctx.lineTo(p.x, diY(p.di));
  ctx.lineTo(pts[pts.length - 1].x, y1);
  ctx.closePath();
  const dg = ctx.createLinearGradient(0, y0, 0, y1);
  dg.addColorStop(0, _rgba(cDi, 0.26));
  dg.addColorStop(1, _rgba(cDi, 0.02));
  ctx.fillStyle = dg;
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(pts[0].x, diY(pts[0].di));
  for (const p of pts) ctx.lineTo(p.x, diY(p.di));
  ctx.strokeStyle = _rgba(cDi, 0.95);
  ctx.lineWidth = 2.5;
  ctx.stroke();

  // ── MD area + line (red, right axis) ──
  ctx.beginPath();
  ctx.moveTo(pts[0].x, y1);
  for (const p of pts) ctx.lineTo(p.x, mdY(p.md));
  ctx.lineTo(pts[pts.length - 1].x, y1);
  ctx.closePath();
  const mg = ctx.createLinearGradient(0, y0, 0, y1);
  mg.addColorStop(0, _rgba(cMd, 0.16));
  mg.addColorStop(1, _rgba(cMd, 0.01));
  ctx.fillStyle = mg;
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(pts[0].x, mdY(pts[0].md));
  for (const p of pts) ctx.lineTo(p.x, mdY(p.md));
  ctx.strokeStyle = _rgba(cMd, 0.8);
  ctx.lineWidth = 1.8;
  ctx.stroke();

  // ── Legend (top-right, 13px) ──
  ctx.font = '13px "Space Mono", monospace';
  ctx.textBaseline = 'middle';
  let lx = x1;
  for (let i = 1; i >= 0; i--) {
    const item = i === 0 ? { color: cDi, label: 'DI' } : { color: cMd, label: 'MD' };
    ctx.fillStyle = item.color;
    ctx.fillRect(lx - 12, 24, 12, 4);
    ctx.fillText(item.label, lx, 26);
    lx -= 44;
  }

  // ── Endpoint dot + "now" readout on the latest DI value ──
  const last = pts[pts.length - 1];
  const pulse = reducedMotion ? 1 : 0.75 + Math.sin(time * 2.2) * 0.25;
  const r = reducedMotion ? 5 : 4 + Math.sin(time * 3) * 1.2;
  const ly = diY(last.di);
  const glow = ctx.createRadialGradient(last.x, ly, 0, last.x, ly, 18 * pulse);
  glow.addColorStop(0, _rgba(cDi, 0.30 * pulse));
  glow.addColorStop(1, _rgba(cDi, 0));
  ctx.fillStyle = glow;
  ctx.beginPath(); ctx.arc(last.x, ly, 18 * pulse, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(last.x, ly, r, 0, Math.PI * 2);
  ctx.fillStyle = _rgba(cDi, 0.7 + 0.3 * pulse);
  ctx.fill();
  ctx.beginPath(); ctx.arc(last.x, ly, r * 0.4, 0, Math.PI * 2);
  ctx.fillStyle = _rgba('#d7ffe4', 0.95);
  ctx.fill();

  // "now" plate: real last-cycle values (honest readout of the series head).
  const cLabel = state.cycleLabels[state.cycleLabels.length - 1] || ('C' + len);
  const mdLast = Math.max(0, Math.min(5, state.mdHistory[state.mdHistory.length - 1] || 0));
  const nowTxt = cLabel + '  DI ' + (last.di * 100).toFixed(0) + '%  ·  MD ' + mdLast.toFixed(2);
  ctx.font = '13px "Space Mono", monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'bottom';
  const tw = ctx.measureText(nowTxt).width;
  const px = Math.min(x1 - 8, last.x);
  const py = Math.max(y0 + 6, ly - 14);
  ctx.fillStyle = _rgba('#0b0817', 0.75);
  ctx.fillRect(px - tw - 14, py - 16, tw + 20, 22);
  ctx.strokeStyle = _rgba(cGrid, 0.7);
  ctx.strokeRect(px - tw - 14, py - 16, tw + 20, 22);
  ctx.fillStyle = cText;
  ctx.fillText(nowTxt, px - 8, py - 1);
}

function renderChart() { const c = document.getElementById('chart-canvas'); if (c) drawChart(c); }

// ─── Fullscreen for Chart ───
var _chartFullscreen = false;
function toggleChartFullscreen() {
  _chartFullscreen = !_chartFullscreen;
  var cp = document.querySelector('.chart-panel');
  if (!cp) return;
  if (_chartFullscreen) {
    cp.style.position = 'fixed'; cp.style.top = '0'; cp.style.left = '0';
    cp.style.width = '100vw'; cp.style.height = '100vh'; cp.style.zIndex = '1000';
    cp.style.margin = '0'; cp.style.borderRadius = '0'; cp.style.background = _token('--bg', '#0d0a1a');
  } else {
    cp.style.position = ''; cp.style.top = ''; cp.style.left = '';
    cp.style.width = ''; cp.style.height = ''; cp.style.zIndex = '';
    cp.style.margin = ''; cp.style.borderRadius = ''; cp.style.background = '';
  }
}
