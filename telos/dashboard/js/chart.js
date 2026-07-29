// TELOS Chart Module — DI/MD ridge and valley visualization

function drawChart(canvas) {
  const ctx = canvas.getContext('2d');
  const w = 520, h = 200;
  ctx.fillStyle = '#0a0a0f';
  ctx.fillRect(0, 0, w, h);

  const len = state.diHistory.length;
  if (len < 2) {
    ctx.fillStyle = '#2a2a3a';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Waiting for data...', w / 2, h / 2);
    return;
  }

  const time = state.time || 0;
  const pad = { top: 6, bottom: 22, left: 10, right: 10 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;
  const step = chartW / (len - 1);

  // Pulsing glow: brightness oscillates ±10%
  const diPulse = 0.9 + Math.sin(time * 1.5) * 0.1;

  // ── Build column data with perspective ──
  // Left (past) = far (compressed vertically), Right (present) = near (full height)
  const cols = [];
  for (let i = 0; i < len; i++) {
    const t = i / (len - 1);
    const persp = 0.35 + t * 0.65;           // 0.35 at far left, 1.0 at near right
    const diVal = Math.max(0.05, state.diHistory[i] || 0.5);
    const mdVal = state.mdHistory[i] || 0;
    const x = pad.left + i * step;
    const diY = pad.top + chartH - diVal * chartH * persp;
    const mdY = pad.top + chartH - mdVal * chartH * 0.05 * persp;
    const baseY = pad.top + chartH;
    const colW = Math.max(1, step * (0.25 + t * 0.45));
    cols.push({ x, diY, mdY, baseY, colW, diVal, mdVal, t, persp });
  }

  // ── 1. Vertical depth pillars (DI ridge → baseline) ──
  ctx.shadowBlur = 0;
  for (const c of cols) {
    if (c.colW < 0.5) continue;
    const pillarA = (0.05 + c.diVal * 0.09) * diPulse;
    // Main pillar fill
    ctx.fillStyle = `rgba(74,222,128,${pillarA})`;
    ctx.fillRect(c.x - c.colW / 2, c.diY, c.colW, c.baseY - c.diY);
    // Left edge (darker for 3D depth)
    ctx.fillStyle = `rgba(40,180,80,${pillarA * 0.5})`;
    ctx.fillRect(c.x - c.colW / 2, c.diY, 1, c.baseY - c.diY);
    // Right edge (lighter highlight)
    ctx.fillStyle = `rgba(100,255,160,${pillarA * 0.3})`;
    ctx.fillRect(c.x + c.colW / 2 - 1, c.diY, 1, c.baseY - c.diY);
  }

  // ── 2. MD valley area with heat shimmer at peaks ──
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top + chartH);
  for (const c of cols) {
    const shimmer = Math.sin(time * 3 + c.t * 10) * 1.8 * c.persp;
    ctx.lineTo(c.x, c.mdY + shimmer);
  }
  ctx.lineTo(pad.left + (len - 1) * step, pad.top + chartH);
  ctx.closePath();
  const mg = ctx.createLinearGradient(0, pad.top, 0, pad.top + chartH);
  mg.addColorStop(0, `rgba(255,107,107,${0.14 * diPulse})`);
  mg.addColorStop(0.5, `rgba(255,80,60,${0.06 * diPulse})`);
  mg.addColorStop(1, 'rgba(255,107,107,0.01)');
  ctx.fillStyle = mg;
  ctx.fill();

  // MD line with shimmer vertices
  ctx.beginPath();
  for (let i = 0; i < len; i++) {
    const c = cols[i];
    const shimmer = Math.sin(time * 3 + i * 2) * 1.8 * c.persp;
    if (i === 0) ctx.moveTo(c.x, c.mdY + shimmer);
    else ctx.lineTo(c.x, c.mdY + shimmer);
  }
  ctx.strokeStyle = `rgba(255,107,107,${0.45 + Math.sin(time * 2) * 0.1})`;
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Flame lick particles at MD peaks
  for (let i = 1; i < len - 1; i++) {
    const c = cols[i];
    if (c.mdVal > 3.5 && Math.random() < 0.008) {
      const lx = c.x + (Math.random() - 0.5) * 4;
      const ly = c.mdY - 2 + Math.sin(time * 5 + i) * 2;
      ctx.beginPath();
      ctx.arc(lx, ly, 1 + Math.random() * 1.5, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,150,80,${0.2 + Math.random() * 0.2})`;
      ctx.fill();
    }
  }

  // ── 3. DI ridge area with pulsing glow ──
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top + chartH);
  for (const c of cols) {
    ctx.lineTo(c.x, c.diY);
  }
  ctx.lineTo(pad.left + (len - 1) * step, pad.top + chartH);
  ctx.closePath();
  const dg = ctx.createLinearGradient(0, pad.top, 0, pad.top + chartH);
  const glowInt = 0.3 * diPulse;
  dg.addColorStop(0, `rgba(74,222,128,${glowInt})`);
  dg.addColorStop(0.4, `rgba(74,222,128,${glowInt * 0.5})`);
  dg.addColorStop(1, 'rgba(74,222,128,0.02)');
  ctx.fillStyle = dg;
  ctx.fill();

  // DI ridge line with glow
  ctx.beginPath();
  for (let i = 0; i < len; i++) {
    const c = cols[i];
    if (i === 0) ctx.moveTo(c.x, c.diY);
    else ctx.lineTo(c.x, c.diY);
  }
  ctx.strokeStyle = `rgba(74,222,128,${0.7 * diPulse})`;
  ctx.lineWidth = 2;
  ctx.shadowColor = '#4ade80';
  ctx.shadowBlur = 8 * diPulse;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // ── 4. Breathing endpoint dot with corona/aura ──
  const last = cols[len - 1];
  const endPulse = Math.sin(time * 2.2) * 0.2 + 0.8;

  // Corona rings
  for (let r = 1; r <= 3; r++) {
    const rad = 5 + r * 5 + Math.sin(time * 1.5 + r) * 2;
    const ringA = (0.15 / r) * endPulse;
    ctx.beginPath();
    ctx.arc(last.x, last.diY, rad, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(74,222,128,${ringA})`;
    ctx.lineWidth = 1.5 - r * 0.3;
    ctx.stroke();
  }

  // Outer glow
  const coronaGrad = ctx.createRadialGradient(last.x, last.diY, 0, last.x, last.diY, 22 * endPulse);
  coronaGrad.addColorStop(0, `rgba(74,222,128,${0.35 * endPulse})`);
  coronaGrad.addColorStop(0.4, `rgba(74,222,128,${0.12 * endPulse})`);
  coronaGrad.addColorStop(1, 'rgba(74,222,128,0)');
  ctx.fillStyle = coronaGrad;
  ctx.beginPath();
  ctx.arc(last.x, last.diY, 22 * endPulse, 0, Math.PI * 2);
  ctx.fill();

  // Dot body
  ctx.beginPath();
  ctx.arc(last.x, last.diY, 3.5 + Math.sin(time * 3) * 1.5, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(74,222,128,${endPulse})`;
  ctx.shadowColor = '#4ade80';
  ctx.shadowBlur = 16 * endPulse;
  ctx.fill();
  ctx.shadowBlur = 0;

  // Inner bright core
  ctx.beginPath();
  ctx.arc(last.x, last.diY, 1.8, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(200,255,200,${0.85 * endPulse})`;
  ctx.fill();

  // ── 5. Labels ──
  ctx.fillStyle = '#4ade80';
  ctx.font = '7px sans-serif';
  ctx.textAlign = 'start';
  ctx.fillText('DI', pad.left, pad.top - 2);
  ctx.fillStyle = '#ff6b6b';
  ctx.fillText('MD', pad.left + 14, pad.top - 2);
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
    cp.style.margin = '0'; cp.style.borderRadius = '0';
  } else {
    cp.style.position = ''; cp.style.top = ''; cp.style.left = '';
    cp.style.width = ''; cp.style.height = ''; cp.style.zIndex = '';
    cp.style.margin = ''; cp.style.borderRadius = '';
  }
}
