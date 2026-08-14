// TELOS v5 canvas-pixel probe — proves each NEW visualization paints with
// real-data pixels (not blank, not a solid fill): grid (scanned perimeter),
// the three memory modes (canopy/orbital/nebula), the two mind modes
// (aurora/rhizome). Also asserts the honest v5 captions render.
// Usage: node scripts/_dashboard_v5_probe.mjs <width> <height> <out.png>
import { chromium } from 'playwright';
import fs from 'fs';

const [W, H, OUT] = [Number(process.argv[2]), Number(process.argv[3]), process.argv[4]];
const BASE = process.env.PROBE_URL || 'http://localhost:8765';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: W, height: H } });
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));

await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
await page.waitForTimeout(4000);

// ── Canvas paint analysis: sample the canvas bitmap, count non-background
//    pixels + distinct colors. A real-data viz has thousands of painted
//    pixels across many hues; a blank/failed canvas is ~0 or 1 color. ──
async function analyzeCanvas(page, id) {
  return page.evaluate((cid) => {
    const c = document.getElementById(cid);
    if (!c) return { id: cid, missing: true };
    try {
      const ctx = c.getContext('2d');
      const w = c.width, h = c.height;
      if (!w || !h) return { id: cid, zeroSize: true };
      const img = ctx.getImageData(0, 0, w, h).data;
      const colors = new Set();
      let lit = 0;
      const stride = Math.max(1, Math.floor(img.length / 400000));
      for (let i = 0; i < img.length; i += stride * 4) {
        const r = img[i], g = img[i + 1], b = img[i + 2], a = img[i + 3];
        if (a > 30 && (r + g + b) > 60) {
          lit++;
          colors.add((r >> 4) + ',' + (g >> 4) + ',' + (b >> 4));
        }
      }
      return { id: cid, w, h, litPixels: lit, distinctColors: colors.size };
    } catch (e) {
      return { id: cid, error: String(e) };
    }
  }, id);
}

const CANVASES = ['grid-canvas', 'kg-tree', 'kg-solar', 'kg-bubble', 'brain-orbit', 'brain-tree'];
const paint = {};
for (const id of CANVASES) {
  // scroll each canvas into view so its rAF loop has drawn frames
  await page.evaluate((cid) => {
    const el = document.getElementById(cid);
    if (!el) return;
    const r = el.getBoundingClientRect();
    window.scrollTo({ top: Math.max(0, window.scrollY + r.top + r.height / 2 - window.innerHeight / 2), behavior: 'instant' });
  }, id);
  await page.waitForTimeout(500);
  paint[id] = await analyzeCanvas(page, id);
}

// ── Honest captions: v5 chapter counts must name the new vizzes ──
const captions = await page.evaluate(() => {
  const q = s => document.querySelector(s);
  const count = sel => { const e = q(sel); return e ? e.textContent.trim() : null; };
  return {
    worldCount: count('[data-chapter="02"] .ch-count'),
    treeCount: count('[data-chapter="03"] .ch-count'),
    solarCount: count('[data-chapter="04"] .ch-count'),
    bubbleCount: count('[data-chapter="05"] .ch-count'),
    orbitCount: count('[data-chapter="06"] .ch-count'),
    rootCount: count('[data-chapter="07"] .ch-count'),
  };
});

// ── Full-page screenshot ──
await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
await page.waitForTimeout(400);
await page.screenshot({ path: OUT, fullPage: true });

console.log(JSON.stringify({ paint, captions, errors }, null, 2));

// ── Assertions ──
const fail = [];
const ok = (cond, msg) => { if (!cond) fail.push(msg); };
for (const id of CANVASES) {
  const p = paint[id];
  ok(p && !p.missing, `canvas ${id} missing`);
  ok(p && !p.error, `canvas ${id} threw: ${p && p.error}`);
  ok(p && !p.zeroSize, `canvas ${id} zero size`);
  ok(p && p.litPixels > 300, `canvas ${id} has only ${p && p.litPixels} painted pixels (need >300)`);
  ok(p && p.distinctColors >= 4, `canvas ${id} only ${p && p.distinctColors} distinct colors (need >=4)`);
}
const capChecks = {
  worldCount: /scanned perimeter/i, treeCount: /canopy/i, solarCount: /orbital ecology/i,
  bubbleCount: /nebula/i, orbitCount: /aurora/i, rootCount: /rhizome/i,
};
for (const [k, re] of Object.entries(capChecks)) {
  ok(captions[k] && re.test(captions[k]), `caption ${k} = '${captions[k]}' (need /${re}/)`);
}
ok(errors.length === 0, `console errors: ${errors.join(' | ')}`);
if (fail.length) {
  console.error('V5 PROBE FAIL:\n- ' + fail.join('\n- '));
  process.exit(1);
}
console.log(`V5 PROBE PASS @ ${W}x${H} → ${OUT} — all 6 canvases painted with real data`);
await browser.close();
