
import { chromium } from 'playwright';
import zlib from 'zlib';
const port = process.argv[2];
const errors = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
await page.goto('http://localhost:' + port + '/dashboard.html',
  { waitUntil: 'networkidle', timeout: 25000 }).catch(() => {});
await page.waitForTimeout(3500);
// Item 6b proof — captured BEFORE any scroll: at initial load (nebula below
// the fold) the ~600 KB vendor chain must NOT be present, so three.js never
// blocks first paint. The lazy loader only injects it once the chapter-05
// panel approaches the viewport (IntersectionObserver, rootMargin 900px).
const preScroll = await page.evaluate(() => ({
  lazyState: (window.__kg3dLazy || {}).state,
  threeTag: !!document.querySelector('script[src*="three.min.js"]'),
  hint: (() => {
    const h = document.getElementById('kg3d-hint');
    return h ? { present: true, faded: h.classList.contains('fade') } : { present: false };
  })(),
}));
// The nebula chapter is below the fold — elementFromPoint needs it on screen.
await page.evaluate(() => {
  const el = document.getElementById('kg-bubble');
  const r = el.getBoundingClientRect();
  window.scrollTo({ top: window.scrollY + r.top + r.height / 2 - window.innerHeight / 2, behavior: 'instant' });
});
// Scrolling near chapter 05 triggers the LAZY loader — wait for the whole
// chain (three → OrbitControls → knowledge-3d) to boot the 3D scene.
const lazyBoot = await page.evaluate(async () => {
  const t0 = Date.now();
  while (!window.__kg3dDebug && Date.now() - t0 < 8000) {
    await new Promise(r2 => setTimeout(r2, 100));
  }
  return {
    lazy: window.__kg3dLazy || null,
    debug: !!window.__kg3dDebug,
  };
});
await page.waitForTimeout(900);
const r = await page.evaluate(() => {
  const canvas = document.getElementById('kg-bubble');
  const dbg = window.__kg3dDebug || null;
  const rc = canvas.getBoundingClientRect();
  const painted = (() => { try { return canvas.toDataURL('image/png').length > 2000; } catch (e) { return false; } })();
  const hit = document.elementFromPoint(Math.round(rc.left + rc.width / 2), Math.round(rc.top + rc.height / 2));
  return {
    bubble3d: !!window.__kgBubble3D,
    nodeCount: dbg ? dbg.nodeCount() : 0,
    edgeCount: dbg ? dbg.edgeCount() : 0,
    painted,
    selfPaints: hit === canvas,
    hud: document.getElementById('kg3d-hud').textContent,
    emptyShown: !document.getElementById('kg3d-empty').hidden,
    labels: document.querySelectorAll('#kg3d-labels .kg3d-cloud').length,
    treeAlive: !!(document.getElementById('kg-tree') && document.getElementById('kg-tree').getContext('2d')),
    solarAlive: !!(document.getElementById('kg-solar') && document.getElementById('kg-solar').getContext('2d')),
    bubbleBox: { x: rc.x, y: rc.y, w: rc.width, h: rc.height },
  };
});
// Honest screen-pixel proof: sample the COMPOSITED viewport (what a user
// sees). toDataURL is blank for in-view WebGL canvases in headless Chromium
// (presented-surface artifact) — the screenshot is ground truth.
const shot = await page.screenshot();
function decodePng(buf) {
  let pos = 8, w = 0, h = 0, colorType = 6, idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos);
    const ty = buf.toString('ascii', pos + 4, pos + 8);
    if (ty === 'IHDR') { w = buf.readUInt32BE(pos + 8); h = buf.readUInt32BE(pos + 12); colorType = buf[pos + 17]; }
    else if (ty === 'IDAT') idat.push(buf.slice(pos + 8, pos + 8 + len));
    pos += 12 + len;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const bpp = colorType === 6 ? 4 : 3;
  const stride = w * bpp;
  const out = Buffer.alloc(w * h * 4);
  let prev = Buffer.alloc(stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)];
    const line = raw.slice(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    const cur = Buffer.from(line);
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? cur[x - bpp] : 0, b = prev[x], c = x >= bpp ? prev[x - bpp] : 0;
      let v = cur[x];
      if (f === 1) v = (v + a) & 255;
      else if (f === 2) v = (v + b) & 255;
      else if (f === 3) v = (v + ((a + b) >> 1)) & 255;
      else if (f === 4) { const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c); v = (v + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c)) & 255; }
      cur[x] = v;
    }
    for (let x = 0; x < w; x++) { const s2 = x * bpp; out[(y * w + x) * 4] = cur[s2]; out[(y * w + x) * 4 + 1] = colorType === 6 ? cur[s2 + 1] : cur[s2]; out[(y * w + x) * 4 + 2] = colorType === 6 ? cur[s2 + 2] : cur[s2]; out[(y * w + x) * 4 + 3] = 255; }
    prev = cur;
  }
  return { w, h, data: out };
}
const img = decodePng(Buffer.from(shot));
const box = r.bubbleBox;
const x0 = Math.max(0, Math.round(box.x)), y0 = Math.max(0, Math.round(box.y));
const x1 = Math.min(img.w, Math.round(box.x + box.w)), y1 = Math.min(img.h, Math.round(box.y + box.h));
let lit = 0;
for (let y = y0; y < y1; y += 2) for (let x = x0; x < x1; x += 2) {
  const i = (y * img.w + x) * 4;
  if (img.data[i] + img.data[i + 1] + img.data[i + 2] > 60) lit++;
}
console.log(JSON.stringify({ r, preScroll, lazyBoot, screenLit: lit, errors }));
await browser.close();
