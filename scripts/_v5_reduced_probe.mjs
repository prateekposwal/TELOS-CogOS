import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
const page = await context.newPage();
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
await page.goto('http://localhost:8765', { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
await page.waitForTimeout(2500);
const ids = ['grid-canvas', 'kg-tree', 'kg-solar', 'kg-bubble', 'brain-orbit', 'brain-tree'];
const paint = {};
for (const id of ids) {
  await page.evaluate((cid) => {
    const el = document.getElementById(cid);
    const r = el.getBoundingClientRect();
    window.scrollTo({ top: Math.max(0, window.scrollY + r.top + r.height / 2 - window.innerHeight / 2), behavior: 'instant' });
  }, id);
  await page.waitForTimeout(300);
  paint[id] = await page.evaluate((cid) => {
    const c = document.getElementById(cid);
    const ctx = c.getContext('2d');
    const img = ctx.getImageData(0, 0, c.width, c.height).data;
    let lit = 0;
    for (let i = 0; i < img.length; i += 64) {
      if (img[i] + img[i + 1] + img[i + 2] > 60) lit++;
    }
    return lit;
  }, id);
}
console.log(JSON.stringify({ paint, errors }));
const fail = [];
for (const id of ids) if ((paint[id] || 0) < 200) fail.push(`${id} static frame thin: ${paint[id]}`);
if (errors.length) fail.push('errors: ' + errors.join(' | '));
if (fail.length) { console.error('REDUCED-MOTION FAIL: ' + fail.join('\n')); process.exit(1); }
console.log('REDUCED-MOTION PASS — all canvases render a static real-data frame, zero errors');
await browser.close();
