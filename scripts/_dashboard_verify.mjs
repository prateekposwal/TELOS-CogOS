// TELOS v3 LIVE verification — real browser, live producer, full-page shots.
// Usage: node scripts/_dashboard_verify.mjs <width> <height> <out.png>
// Asserts: zero console/page errors, story ≥400px + hero in viewport,
// zero overlaps (elementFromPoint center-paint), contrast ≥4.5 on the five
// gated pairs, REAL data renders (non-zero decisions, DI/MD, painted canvas),
// then captures a full-page screenshot.
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
await page.waitForTimeout(4000); // let the producer burst + first overview land

const r = await page.evaluate(() => {
  const q = s => document.querySelector(s);
  const cs = el => getComputedStyle(el);
  const parseC = s => {
    if (!s) return null;
    let m = s.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    if (m) return [+m[1] / 255, +m[2] / 255, +m[3] / 255, m[4] === undefined ? 1 : +m[4]];
    m = s.match(/#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i);
    if (m) return [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255, 1];
    return null;
  };
  const lum = c => {
    if (!c) return null;
    const lin = v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  };
  // Effective background: walk up until a non-transparent paint is found.
  const effBg = el => {
    let n = el;
    while (n) {
      const bg = parseC(cs(n).backgroundColor);
      if (bg && bg[3] > 0.02) return bg.slice(0, 3);
      n = n.parentElement;
    }
    return [0, 0, 0];
  };
  const contrast = (fgSel, el) => {
    const f = parseC(cs(el).color);
    const b = effBg(el);
    if (!f) return null;
    const l1 = lum(f), l2 = lum(b);
    const hi = Math.max(l1, l2), lo = Math.min(l1, l2);
    return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
  };
  const rect = el => { const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top), bottom: Math.round(r.bottom) }; };
  const inVp = r => r.bottom > 0 && r.top < window.innerHeight && r.width > 0 && r.height > 0;

  // ── Overlap gate: center-paint on key elements ──
  const targets = [
    '#story-decisions', '#story-headline', '#hero-title-dyed', '#story-stats',
    '#story-insight', '#story-mood', '#story-action', '#story-live',
    '#signal-quote .pq-body', '#world-quote .pq-body', '#memory-quote .pq-body',
    '#memory-solar-quote .pq-body', '#memory-bubble-quote .pq-body',
    '#mind-quote .pq-body', '#mind-root-quote .pq-body',
    '#chart-canvas', '#grid-canvas', '#chat-input',
    '#pipeline-timeline', '#btn-auto-refresh',
  ];

  // ── v4 single-section contract: one mode per chapter (GRIDWORLD pattern) ──
  const modeSections = ['kg-tree', 'kg-solar', 'kg-bubble', 'brain-orbit', 'brain-tree'].map(id => {
    const cv = document.getElementById(id);
    const sec = cv ? cv.closest('section.chapter') : null;
    const body = sec ? sec.querySelector('.chapter-body') : null;
    const panel = cv ? cv.closest('.panel') : null;
    return {
      canvas: id,
      hasOwnChapter: !!sec,
      hasChapterMark: !!(sec && sec.querySelector('.chapter-mark .ch-idx')),
      hasCount: !!(sec && sec.querySelector('.chapter-mark .ch-count')),
      hasCaption: !!(sec && sec.querySelector('.panel-caption')),
      panelIsFullWidth: !!(body && panel && panel.parentElement === body),
      quote: !!sec && (sec.querySelector('.pullquote .pq-body') || {}).textContent,
    };
  });

  // ── Compact timeline: must match the chat panel footprint (max 240px) ──
  const tl = document.getElementById('memory-timeline');
  const chatMsgs = document.querySelector('.chat-messages');
  const timeline = tl && chatMsgs ? {
    timelineMaxH: Math.round(getComputedStyle(tl).maxHeight.replace('px', '')),
    chatMaxH: Math.round(getComputedStyle(chatMsgs).maxHeight.replace('px', '')),
  } : null;
  const overlap = targets.map(sel => {
    const el = q(sel);
    if (!el) return { sel, missing: true };
    const r = el.getBoundingClientRect();
    if (!inVp(r)) return { sel, offscreen: true };
    const p = document.elementFromPoint(Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2));
    const selfPaints = p === el || (el.contains && el.contains(p));
    return { sel, selfPaints, paintedBy: p ? (p.id || p.className || p.tagName) : null };
  });

  // ── Story + sections ──
  const strip = q('#story-strip');
  const stripRect = strip.getBoundingClientRect();
  const heroR = q('#story-decisions').getBoundingClientRect();
  const chapters = [...document.querySelectorAll('.chapter .chapter-body')].map(el => ({
    ch: el.closest('.chapter').getAttribute('data-chapter'),
    h: Math.round(el.getBoundingClientRect().height),
    visible: el.getBoundingClientRect().height > 0,
  }));

  // ── Real data renders ──
  const decisions = parseInt(q('#story-decisions').textContent, 10) || 0;
  const diTxt = q('#story-di').textContent;
  const mdTxt = q('#story-md').textContent;
  const liveBadge = q('#story-live').textContent;
  const insightLen = (q('#story-insight').textContent || '').length;
  const lessons = parseInt(q('#story-lessons').textContent, 10) || 0;

  // Canvas painted? sample a horizontal strip of the chart (real series = non-uniform pixels).
  const chart = q('#chart-canvas');
  const chartPainted = (() => {
    try {
      const c = chart.getContext('2d');
      const { width: cw, height: ch } = chart.getBoundingClientRect();
      if (!cw || !ch) return false;
      const img = c.getImageData(0, Math.floor(ch / 2), Math.floor(cw), 2).data;
      let uniq = 0;
      for (let i = 0; i < img.length && uniq < 8; i += 4) {
        if (img[i] + img[i + 1] + img[i + 2] > 18) uniq++;
      }
      return uniq >= 8;
    } catch (e) { return null; }
  })();

  // ── Contrast (five gated pairs) ──
  const contrastPairs = {
    ssCaption: contrast(null, q('.ss-caption')),
    panelCaption: contrast(null, q('.panel-caption')),
    metricLabel: contrast(null, q('.metric-card .label')),
    pqCite: contrast(null, q('.pullquote .pq-cite')),
    heroLabel: contrast(null, q('.story-hero-label')),
  };

  return {
    viewport: { w: innerWidth, h: innerHeight },
    storyStrip: { clientHeight: strip.clientHeight, h: Math.round(stripRect.height), fullyAboveFold: stripRect.bottom <= innerHeight },
    hero: { h: Math.round(heroR.height), inViewport: inVp(heroR) },
    overlap, modeSections, timelineCompact: timeline, chapters,
    data: { decisions, diTxt, mdTxt, liveBadge, insightLen, lessons, chartPainted },
    contrastPairs,
    bodyFont: cs(document.body).fontSize,
    scrollHeight: document.documentElement.scrollHeight,
  };
});

await page.screenshot({ path: OUT, fullPage: true });
console.log(JSON.stringify({ probe: r, consoleErrors: errors }, null, 2));
await browser.close();

// ── Assertions (exit non-zero on failure) ──
const p = r;
const fail = [];
const ok = (cond, msg) => { if (!cond) fail.push(msg); };
ok(p.storyStrip.clientHeight >= 400, `story strip ${p.storyStrip.clientHeight}px < 400`);
ok(p.hero.inViewport, 'hero number not in viewport');
ok(p.hero.h > 0, 'hero number zero height');
for (const o of p.overlap) {
  if (o.missing) { fail.push(`missing element ${o.sel}`); continue; }
  if (!o.offscreen && !o.selfPaints) fail.push(`overlap on ${o.sel}: paints ${o.paintedBy}`);
}
for (const c of p.chapters) ok(c.visible, `chapter ${c.ch} collapsed to ${c.h}px`);
for (const ms of p.modeSections) {
  ok(ms.hasOwnChapter && ms.hasChapterMark && ms.hasCount && ms.hasCaption,
    `mode ${ms.canvas} missing own chapter/mark/count/caption`);
  ok(ms.panelIsFullWidth, `mode ${ms.canvas} panel not a full-width chapter child`);
  ok(ms.quote && ms.quote.length > 5, `mode ${ms.canvas} quote not derived`);
}
ok(p.timelineCompact && p.timelineCompact.timelineMaxH <= p.timelineCompact.chatMaxH,
  `memory timeline (${p.timelineCompact ? p.timelineCompact.timelineMaxH : '?'}px) not compact like chat (${p.timelineCompact ? p.timelineCompact.chatMaxH : '?'}px)`);
ok(p.data.decisions > 0, `no real decisions rendered (${p.data.decisions})`);
ok(p.data.diTxt !== '—' && p.data.diTxt !== '', `DI not rendered ('${p.data.diTxt}')`);
ok(p.data.insightLen > 25, `insight too thin (${p.data.insightLen})`);
ok(p.data.chartPainted, 'chart canvas has no painted series');
ok(/live/.test(p.data.liveBadge), `live badge missing ('${p.data.liveBadge}')`);
for (const [k, v] of Object.entries(p.contrastPairs)) {
  ok(typeof v === 'number' && v >= 4.5, `contrast ${k} = ${v} < 4.5`);
}
ok(errors.length === 0, `console errors: ${errors.join(' | ')}`);
if (fail.length) {
  console.error('VERIFY FAIL:\n- ' + fail.join('\n- '));
  process.exit(1);
}
console.log(`VERIFY PASS @ ${W}x${H} → ${OUT} (story ${p.storyStrip.clientHeight}px, decisions ${p.data.decisions}, DI ${p.data.diTxt}, MD ${p.data.mdTxt})`);
