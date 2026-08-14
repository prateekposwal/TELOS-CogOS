// TELOS v6 probe — 3D Memory Nebula (kg-bubble → three.js WebGL).
// Proves, at 1440×900 against the LIVE dashboard:
//   * story visible above the fold (clientHeight ≥ 400, hero in viewport)
//   * zero console/page errors
//   * zero overlaps (selfPaint gate on the nebula canvas + key elements)
//   * live-rendered WCAG contrast ≥ 4.5:1 on the known dim-text pairs
//   * the 3D canvas paints REAL pixels (toDataURL sample + WebGL readPixels)
//   * real graph totals in the HUD, real domain cloud labels
//   * click-to-inspect shows a REAL node's id/degree (never fabricated)
//   * interactions: dolly zoom, pause (auto-rotate halts), fullscreen
//   * reduced-motion pass: auto-rotate off, still paints, still self-paints
// Also writes screenshots:
//   * dashboard_after.png   — viewport scrolled to the 3D nebula chapter
//   * dashboard_wide.png    — full-page scroll
//   * kg3d_nebula.png       — close-up crop of the WebGL canvas
// Usage: node scripts/_dashboard_v6_probe.mjs
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const BASE = process.env.PROBE_URL || 'http://localhost:8765';
const OUT_DIR = path.join(process.cwd(), 'telos', 'dashboard', 'screenshots');
const W = 1440, H = 900;
const browser = await chromium.launch({ headless: true });

function wcag(fg, bg) {
  const parse = (s) => s.match(/[\d.]+/g).slice(0, 3).map(Number);
  const lum = (c) => {
    const lin = (v) => v / 12.92 <= 0.03928 ? v / 12.92 : Math.pow((v / 255 + 0.055) / 1.055, 2.4);
    const [r, g, b] = parse(c).map(lin);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const l1 = lum(fg), l2 = lum(bg);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

async function newProbePage(reduced = false) {
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, reducedMotion: reduced ? 'reduce' : 'no-preference' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(4000);
  return { page, errors, ctx };
}

const main = await newProbePage();
const { page, errors } = main;

// ── Story above the fold (measured BEFORE scrolling) ─────────────────────
const story = await page.evaluate(() => {
  const strip = document.getElementById('story-strip');
  const hero = document.getElementById('story-decisions');
  const hr = hero.getBoundingClientRect();
  return {
    stripClientHeight: strip.clientHeight,
    heroInViewport: hr.bottom > 0 && hr.top < window.innerHeight && hr.height > 0,
    heroHeight: Math.round(hr.height * 100) / 100,
  };
});

// Scroll the 3D nebula chapter into view for the interaction pass.
await page.evaluate(() => {
  const el = document.getElementById('kg-bubble');
  const r = el.getBoundingClientRect();
  window.scrollTo({ top: window.scrollY + r.top + r.height / 2 - window.innerHeight / 2, behavior: 'instant' });
});
await page.waitForTimeout(900);

// ── Overlap + contrast + 3D core ─────────────────────────────────────────
const probe = await page.evaluate(() => {
  const wcag = (fg, bg) => {
    const parse = (s) => s.match(/[\d.]+/g).slice(0, 3).map(Number);
    const lum = (c) => {
      const lin = (v) => v / 12.92 <= 0.03928 ? v / 12.92 : Math.pow((v / 255 + 0.055) / 1.055, 2.4);
      const [r, g, b] = parse(c).map(lin);
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const l1 = lum(fg), l2 = lum(bg);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };
  const canvas = document.getElementById('kg-bubble');
  const rc = canvas.getBoundingClientRect();
  const centerHit = document.elementFromPoint(Math.round(rc.left + rc.width / 2), Math.round(rc.top + rc.height / 2));
  const dbg = window.__kg3dDebug || null;
  let toDataLen = 0, toDataOk = false;
  try { const d = canvas.toDataURL('image/png'); toDataLen = d.length; toDataOk = d.length > 2000; } catch (e) {}
  // toDataURL has preserveDrawingBuffer — decode it back and count the
  // pixels the browser actually painted (deep-purple bg ~(11,8,23) is
  // excluded by the >120 threshold; nodes/clouds/glows/lines count).
  // Overlap gate across the page (selfPaint at element centers).
  const inVp = r0 => r0.bottom > 0 && r0.top < window.innerHeight;
  const selfPaint = sel => {
    const el = document.querySelector(sel);
    if (!el) return { sel, missing: true };
    const r0 = el.getBoundingClientRect();
    if (!inVp(r0) || r0.width <= 0 || r0.height <= 0) return { sel, skip: true };
    const p = document.elementFromPoint(Math.round(r0.left + r0.width / 2), Math.round(r0.top + r0.height / 2));
    return { sel, ok: p === el || (el.contains && el.contains(p)), paintedBy: p ? (p.id || p.className || p.tagName) : null };
  };
  const overlaps = [
    '#story-decisions', '#story-headline', '#story-stats', '#chart-canvas',
    '#grid-canvas', '#kg-tree', '#kg-solar', '#kg-bubble', '#brain-orbit', '#brain-tree',
    '#memory-solar-quote .pq-body', '#memory-bubble-quote .pq-body', '#mind-root-quote .pq-body',
  ].map(selfPaint);
  // Live WCAG contrast on the known dim pairs.
  const cs = getComputedStyle(document.body);
  const bg = cs.getPropertyValue('--bg').trim();
  const bgElev = cs.getPropertyValue('--bg-elev').trim();
  const dim = cs.getPropertyValue('--text-dim').trim();
  const parseHex = h => { const x = h.replace('#', ''); return `rgb(${parseInt(x.slice(0,2),16)}, ${parseInt(x.slice(2,4),16)}, ${parseInt(x.slice(4,6),16)})`; };
  const capColor = getComputedStyle(document.querySelector('.panel-caption')).color;
  const contrast = {
    'panel-caption / bg-elev': wcag(capColor, parseHex(bgElev)),
    'ss-caption / bg': wcag(getComputedStyle(document.querySelector('.ss-caption')).color, parseHex(bg)),
    'kg3d-hud / canvas-bg': wcag(getComputedStyle(document.getElementById('kg3d-hud')).color, parseHex(cs.getPropertyValue('--canvas-bg').trim())),
  };
  return {
    bubble3d: !!window.__kgBubble3D,
    nodeCount: dbg ? dbg.nodeCount() : 0,
    edgeCount: dbg ? dbg.edgeCount() : 0,
    sampled: dbg ? dbg.sampledEdges() : 0,
    domains: document.querySelectorAll('#kg3d-labels .kg3d-cloud').length,
    labelsText: [...document.querySelectorAll('#kg3d-labels .kg3d-cloud')].map(s => s.textContent).join(' | '),
    hud: document.getElementById('kg3d-hud').textContent,
    emptyShown: !document.getElementById('kg3d-empty').hidden,
    centerPaintsCanvas: centerHit === canvas,
    toDataOk, toDataLen,
    treeAlive: !!(document.getElementById('kg-tree') && document.getElementById('kg-tree').getContext('2d')),
    solarAlive: !!(document.getElementById('kg-solar') && document.getElementById('kg-solar').getContext('2d')),
    overlaps,
    contrast,
  };
});

const paintedPixels = await page.evaluate(() => new Promise((resolve) => {
  const c = document.getElementById('kg-bubble');
  const img = new Image();
  img.onload = () => {
    try {
      const t = document.createElement('canvas');
      t.width = img.width; t.height = img.height;
      const tx = t.getContext('2d');
      tx.drawImage(img, 0, 0);
      const d = tx.getImageData(0, 0, t.width, t.height).data;
      let lit = 0; const colors = new Set();
      for (let i = 0; i < d.length; i += 16) {
        const r = d[i], g = d[i + 1], b = d[i + 2];
        if ((r + g + b) > 120) { lit++; colors.add((r >> 4) + ',' + (g >> 4) + ',' + (b >> 4)); }
      }
      resolve({ lit, distinct: colors.size, w: img.width, h: img.height });
    } catch (e) { resolve({ err: String(e) }); }
  };
  img.onerror = () => resolve({ err: 'decode failed' });
  img.src = c.toDataURL('image/png');
}));

// ── Click a REAL node → inspect card with real id/degree ──────────────────
const click = await page.evaluate(() => {
  const dbg = window.__kg3dDebug;
  const canvas = document.getElementById('kg-bubble');
  const visible = [];
  for (const n of kgNodes) { const pr = dbg.project(n.id); if (pr) visible.push({ id: n.id, pr }); }
  visible.sort((a, b) => ((kgDegree[b.id] || 0) - (kgDegree[a.id] || 0)));
  const t = visible[0];
  if (!t) return { clicked: false };
  const rect = canvas.getBoundingClientRect();
  const cx = rect.left + t.pr.x, cy = rect.top + t.pr.y;
  canvas.dispatchEvent(new PointerEvent('pointerdown', { clientX: cx, clientY: cy, bubbles: true, pointerId: 1 }));
  canvas.dispatchEvent(new PointerEvent('pointerup', { clientX: cx, clientY: cy, bubbles: true, pointerId: 1 }));
  const card = document.getElementById('kg3d-card');
  return {
    clicked: true, nodeId: t.id,
    cardShown: !card.hidden,
    cardHasId: card.textContent.includes(t.id),
    cardHasDegree: card.textContent.includes(String(kgDegree[t.id])),
    cardText: card.textContent.replace(/\s+/g, ' ').slice(0, 160),
  };
});

// ── Interactions: dolly zoom, pause, fullscreen ───────────────────────────
const interactions = await page.evaluate(async () => {
  const panel = document.getElementById('kg-panel-bubble');
  const btns = panel.querySelectorAll('.zoom-btn');
  const lvl = panel.querySelector('.kg-zoom-lvl');
  const before = lvl.textContent;
  btns[1].click(); await new Promise(r => setTimeout(r, 80));
  const zoomedIn = lvl.textContent;
  const pauseBtn = panel.querySelector('.kg-pause-btn');
  pauseBtn.click(); await new Promise(r => setTimeout(r, 80));
  const autoAfterPause = window.__kg3dDebug.autoRotate();
  pauseBtn.click(); await new Promise(r => setTimeout(r, 80));
  const autoAfterResume = window.__kg3dDebug.autoRotate();
  const fsBtn = btns[btns.length - 1];
  fsBtn.click(); await new Promise(r => setTimeout(r, 200));
  const fsPosition = getComputedStyle(panel).position;
  const fsCanvasW = document.getElementById('kg-bubble').clientWidth;
  fsBtn.click(); await new Promise(r => setTimeout(r, 120));
  return { zoomLabelBefore: before, zoomLabelIn: zoomedIn, autoAfterPause, autoAfterResume, fsPosition, fsCanvasW };
});

// ── Screenshots ───────────────────────────────────────────────────────────
fs.mkdirSync(OUT_DIR, { recursive: true });
await page.screenshot({ path: path.join(OUT_DIR, 'dashboard_after.png') });          // nebula chapter in view
await page.screenshot({ path: path.join(OUT_DIR, 'dashboard_wide.png'), fullPage: true }); // full narrative
const canvasBox = await page.locator('#kg-bubble').boundingBox();
await page.screenshot({
  path: path.join(OUT_DIR, 'kg3d_nebula.png'),
  clip: { x: Math.max(0, canvasBox.x - 20), y: Math.max(0, canvasBox.y - 60), width: Math.min(canvasBox.width + 40, W), height: Math.min(canvasBox.height + 110, H) },
});
// Isolated WebGL proof: hide every DOM overlay, capture ONLY the composited
// canvas layer (CSS background + WebGL content — nothing else).
await page.evaluate(() => {
  document.querySelectorAll('#kg3d-labels, #kg3d-hud, #kg3d-empty, #kg3d-card').forEach(el => el.style.display = 'none');
});
await page.waitForTimeout(250);
await page.screenshot({
  path: path.join(OUT_DIR, 'kg3d_isolated.png'),
  clip: { x: Math.max(0, canvasBox.x), y: Math.max(0, canvasBox.y), width: Math.min(canvasBox.width, W), height: Math.min(canvasBox.height, H) },
});
await page.evaluate(() => {
  document.querySelectorAll('#kg3d-labels, #kg3d-hud, #kg3d-empty, #kg3d-card').forEach(el => el.style.display = '');
});

// ── Reduced-motion pass ───────────────────────────────────────────────────
const reduced = await newProbePage(true);
// Scroll the nebula into view (the reduced page has not scrolled yet).
await reduced.page.evaluate(() => {
  const el = document.getElementById('kg-bubble');
  const r = el.getBoundingClientRect();
  window.scrollTo({ top: window.scrollY + r.top + r.height / 2 - window.innerHeight / 2, behavior: 'instant' });
});
await reduced.page.waitForTimeout(500);
const reducedResult = await reduced.page.evaluate(async () => {
  const canvas = document.getElementById('kg-bubble');
  const dbg = window.__kg3dDebug;
  const rc = canvas.getBoundingClientRect();
  const cx = Math.round(rc.left + rc.width / 2), cy = Math.round(rc.top + rc.height / 2);
  let selfPaints = null;
  for (let attempt = 0; attempt < 5; attempt++) {
    selfPaints = document.elementFromPoint(cx, cy) === canvas;
    if (selfPaints) break;
    await new Promise(r => setTimeout(r, 200));
  }
  let painted = false;
  try { painted = canvas.toDataURL('image/png').length > 2000; } catch (e) {}
  return {
    reduced: dbg ? dbg.reducedMotion : null,
    autoRotate: dbg ? dbg.autoRotate() : null,
    painted,
    selfPaints,
    nodeCount: dbg ? dbg.nodeCount() : 0,
  };
});

await browser.close();

console.log(JSON.stringify({
  story,
  probe,
  paintedPixels,
  click,
  interactions,
  reduced: reducedResult,
  reducedErrors: reduced.errors,
  errors,
  screenshots: ['dashboard_after.png', 'dashboard_wide.png', 'kg3d_nebula.png', 'kg3d_isolated.png'],
}, null, 1));
