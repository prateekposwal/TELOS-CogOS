
import { chromium } from 'playwright';
const port = process.argv[2];
const errors = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
await page.goto('http://localhost:' + port + '/dashboard.html',
  { waitUntil: 'networkidle', timeout: 20000 }).catch(() => {});
await page.waitForTimeout(1500);
const r = await page.evaluate(() => {
  const strip = document.getElementById('story-strip');
  const hero = document.getElementById('story-decisions');
  const hr = hero.getBoundingClientRect();
  const q = sel => document.querySelector(sel);
  const inVp = r0 => r0.bottom > 0 && r0.top < window.innerHeight;
  // v3 overlap gate: key elements must be in-flow; any element IN the
  // viewport must paint to itself or a descendant at its center.
  const checkVisible = (sel) => {
    const el = q(sel);
    if (!el) return null;
    const r0 = el.getBoundingClientRect();
    let painted = null, selfPaints = null;
    if (inVp(r0) && r0.width > 0 && r0.height > 0) {
      painted = document.elementFromPoint(Math.round(r0.left + r0.width / 2), Math.round(r0.top + r0.height / 2));
      selfPaints = (painted === el) || (el.contains && el.contains(painted));
    }
    return {
      sel, x: Math.round(r0.x), y: Math.round(r0.y),
      w: Math.round(r0.width), h: Math.round(r0.height),
      inDocFlow: r0.width > 0 && r0.height > 0,
      paintedBy: painted ? (painted.id || painted.className || painted.tagName) : null,
      selfPaints,
    };
  };
  const visibleElements = [
    '#hero-title-dyed', '#story-decisions', '#story-headline', '#story-stats',
    '#signal-quote .pq-body', '#world-quote .pq-body', '#memory-quote .pq-body',
    '#memory-solar-quote .pq-body', '#memory-bubble-quote .pq-body',
    '#mind-quote .pq-body', '#mind-root-quote .pq-body',
    '#story-insight', '#story-mood', '#story-action',
    '#chart-canvas', '#grid-canvas', '#memory-timeline', '#chat-input',
  ].map(checkVisible);
  // v4 single-section contract: every mode canvas has its OWN chapter with
  // a chapter-mark (ghost numeral + count) and a full-width panel that is a
  // direct child of the chapter body (the GRIDWORLD pattern, verified live).
  const modeSections = ['kg-tree', 'kg-solar', 'kg-bubble', 'brain-orbit', 'brain-tree'].map(id => {
    const cv = document.getElementById(id);
    const sec = cv ? cv.closest('section.chapter') : null;
    const body = sec ? sec.querySelector('.chapter-body') : null;
    const panel = cv ? cv.closest('.panel') : null;
    return {
      canvas: id,
      hasOwnChapter: !!sec,
      dataChapter: sec ? sec.getAttribute('data-chapter') : null,
      hasChapterMark: !!(sec && sec.querySelector('.chapter-mark .ch-idx')),
      hasCount: !!(sec && sec.querySelector('.chapter-mark .ch-count')),
      hasCaption: !!(sec && sec.querySelector('.panel-caption')),
      panelIsFullWidth: !!(body && panel && panel.parentElement === body),
    };
  });
  const chapterBodies = [...document.querySelectorAll('.chapter .chapter-body')].map(el => ({
    ch: el.closest('.chapter') ? el.closest('.chapter').getAttribute('data-chapter') : '?',
    h: Math.round(el.getBoundingClientRect().height),
    visible: el.getBoundingClientRect().height > 0,
  }));
  const hc = document.getElementById('hero-backdrop');
  const heroBackdrop = hc ? {
    w: Math.round(hc.getBoundingClientRect().width),
    h: Math.round(hc.getBoundingClientRect().height),
  } : null;
  return {
    stripClientHeight: strip.clientHeight,
    heroHeight: Math.round(hr.height * 100) / 100,
    heroInViewport: hr.bottom > 0 && hr.top < window.innerHeight && hr.height > 0,
    visibleElements,
    modeSections,
    chapterBodies,
    heroBackdrop,
  };
});

// ── v4 scroll-paint pass: below-the-fold single-mode sections must render
//    and paint to themselves (the visibility contract extends to every new
//    full-width mode section + the compact memory timeline + chat input). ──
const scrollChecks = [];
for (const sel of [
  '#kg-tree', '#kg-solar', '#kg-bubble',
  '#brain-orbit', '#brain-tree',
  '#memory-solar-quote .pq-body', '#memory-bubble-quote .pq-body',
  '#mind-root-quote .pq-body', '#memory-timeline', '#chat-input',
]) {
  // Instant scroll (html { scroll-behavior:smooth } would animate and leave
  // the check mid-flight) — compute the exact center target and jump.
  await page.evaluate((s) => {
    const el = document.querySelector(s);
    if (!el) return;
    const r = el.getBoundingClientRect();
    const y = window.scrollY + r.top + r.height / 2 - window.innerHeight / 2;
    window.scrollTo({ top: Math.max(0, y), behavior: 'instant' });
  }, sel);
  await page.waitForTimeout(350);
  const sc = await page.evaluate((s) => {
    const el = document.querySelector(s);
    if (!el) return { sel: s, missing: true };
    const r0 = el.getBoundingClientRect();
    const inFlow = r0.width > 0 && r0.height > 0;
    const p = inFlow ? document.elementFromPoint(Math.round(r0.left + r0.width / 2), Math.round(r0.top + r0.height / 2)) : null;
    const selfPaints = p === el || (el.contains && el.contains(p));
    return { sel: s, inFlow, selfPaints, paintedBy: p ? (p.id || p.className || p.tagName) : null };
  }, sel);
  scrollChecks.push(sc);
}
console.log(JSON.stringify({ probe: r, scrollChecks, errors }));
await browser.close();
