// TELOS dashboard LIVE DOM probe — 1440x900, paint-level verification
import { chromium } from 'playwright';

const BASE = process.env.PROBE_URL || 'http://localhost:8765';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));

await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 }).catch(()=>{});
await page.waitForTimeout(3000);

const r = await page.evaluate(() => {
  const parseC = s => {
    if (!s) return null;
    const m = s.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    if (m) return [+m[1]/255, +m[2]/255, +m[3]/255];
    const h = s.match(/#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i);
    if (h) return [parseInt(h[1],16)/255, parseInt(h[2],16)/255, parseInt(h[3],16)/255];
    return null;
  };
  const lum = c => {
    if (!c) return null;
    const lin = v => v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4);
    return 0.2126*lin(c[0]) + 0.7152*lin(c[1]) + 0.0722*lin(c[2]);
  };
  const contrast = (fg, bg) => {
    const l1 = lum(parseC(fg)), l2 = lum(parseC(bg));
    if (l1 === null || l2 === null) return null;
    const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1];
    return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
  };
  const q = s => document.querySelector(s);
  const rect = el => { const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top), bottom: Math.round(r.bottom) }; };
  const cs = el => getComputedStyle(el);
  const inViewport = r => r.bottom > 0 && r.top < window.innerHeight && (r.height || r.h) > 0;
  const paintAt = (x, y) => { const el = document.elementFromPoint(x, y); return el ? (el.id || el.className || el.tagName) : null; };

  const story = q('#story-strip');
  const storyRect = rect(story);
  const statsRect = rect(q('#story-stats'));
  const hero = q('#story-decisions');
  const heroRect = rect(hero);
  const headline = q('#story-headline');
  const headlineRect = rect(headline);
  const insight = q('#story-insight');
  const insightRect = rect(insight);
  const mood = q('#story-mood');
  const moodRect = rect(mood);

  // Paint checks: elementFromPoint at the CENTER of hero / headline / insight.
  const heroPaint = paintAt(heroRect.x + Math.floor(heroRect.w/2), heroRect.y + Math.floor(heroRect.h/2));
  const headlinePaint = paintAt(headlineRect.x + Math.floor(headlineRect.w/2), headlineRect.y + Math.floor(headlineRect.h/2));
  const insightPaint = paintAt(insightRect.x + Math.floor(insightRect.w/2), insightRect.y + Math.floor(insightRect.h/2));

  // Panel clipping: every panel must have nonzero visible height.
  const panels = [...document.querySelectorAll('.graph-wall .panel, .main > .panel, .story-strip')].map(el => {
    const r = el.getBoundingClientRect();
    return { id: el.id || el.className.split(' ')[0] || el.tagName, h: Math.round(r.height), visible: r.height > 0 };
  });

  // Canvas sizes (Step 5: meaningful canvas footprint).
  const canvases = {};
  for (const id of ['brain-orbit', 'brain-tree', 'grid-canvas', 'chart-canvas', 'kg-tree', 'kg-solar', 'kg-bubble']) {
    const el = document.getElementById(id);
    const r = el.getBoundingClientRect();
    canvases[id] = { w: Math.round(r.width), h: Math.round(r.height) };
  }

  return {
    viewport: { w: window.innerWidth, h: window.innerHeight },
    storyStrip: { ...storyRect, clientHeight: story.clientHeight, scrollHeight: story.scrollHeight, fullyAboveFold: storyRect.bottom <= window.innerHeight },
    hero: { ...heroRect, paintedBy: heroPaint, inViewport: inViewport(heroRect) },
    headline: { ...headlineRect, paintedBy: headlinePaint },
    insight: { ...insightRect, paintedBy: insightPaint, inViewport: inViewport(insightRect) },
    mood: { ...moodRect, inViewport: inViewport(moodRect) },
    storyStats: { count: document.querySelectorAll('#story-stats .story-stat').length, ...statsRect, inViewport: inViewport(statsRect) },
    sidebarClusters: [...document.querySelectorAll('.sidebar .sidebar-cluster')].map(s => s.getAttribute('aria-label')),
    panels,
    canvases,
    chartInWall: !!document.querySelector('.graph-wall .chart-panel'),
    contrast: {
      ssCaption: contrast(cs(q('.ss-caption')).color, cs(q('.story-stat')).backgroundColor),
      panelCaption: contrast(cs(q('.panel-caption')).color, cs(q('.panel')).backgroundColor),
      metricLabel: contrast(cs(q('.metric-card .label')).color, cs(q('.metric-card')).backgroundColor),
    },
    fonts: {
      ssCaption: cs(q('.ss-caption')).fontSize,
      panelCaption: cs(q('.panel-caption')).fontSize,
      metricLabel: cs(q('.metric-card .label')).fontSize,
      hero: cs(q('.story-hero-val')).fontSize,
      headline: cs(q('#story-headline')).fontSize,
      storyMood: cs(q('.story-mood')).fontSize,
      body: cs(document.body).fontSize,
    },
    data: {
      decisions: q('#story-decisions') ? q('#story-decisions').textContent : null,
      lessons: q('#story-lessons') ? q('#story-lessons').textContent : null,
      di: q('#story-di') ? q('#story-di').textContent : null,
      md: q('#story-md') ? q('#story-md').textContent : null,
      liveBadge: q('#story-live') ? q('#story-live').textContent : null,
      insightText: q('#story-insight') ? q('#story-insight').textContent.slice(0, 90) : null,
      moodText: q('#story-mood') ? q('#story-mood').textContent.slice(0, 90) : null,
    },
    ariaLive: {
      insight: q('#story-insight').getAttribute('aria-live'),
      mood: q('#story-mood').getAttribute('aria-live'),
    },
  };
});

console.log(JSON.stringify({ probe: r, consoleErrors: errors }, null, 2));
await browser.close();
