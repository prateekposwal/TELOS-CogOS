// TELOS Story Module — the narrative hero strip.
//
// Narrative arc (per telos/dashboard/STORYTELLING.md):
//   hook → hero number → context (captioned stats) → insight → evidence (chips)
//   → reflection (mood) → action (chat command box).
//
// HONESTY CONTRACT: every number AND every sentence rendered here is computed
// from /api/overview (measured runtime data or persisted history) — or from a
// real delta between two polls. The narrative is DERIVED from the numbers,
// never invented to make a better story.
var _lastOverview = null;
var _overviewUpdatedAt = null;
// Previous-poll state: honest "is TELOS learning right now?" deltas.
var _prevLessons = null;
var _prevEdges = null;

var _DOMAIN_COLORS_STORY = {
  'navigation': '#4ade80', 'gridworld': '#4ade80',
  'identity': '#f472b6', 'governance': '#c084fc',
  'terrain': '#fbbf24', 'preference': '#60a5fa',
  'user_preference': '#60a5fa', 'blocker': '#f87171',
  'perception': '#60a5fa', 'planning': '#fbbf24',
  'simulation': '#4ade80', 'pattern': '#94a3b8',
  'reflection': '#a78bfa', 'conversation': '#f472b6',
  'general': '#94a3b8',
};

async function fetchOverview() {
  try {
    const resp = await fetch('/api/overview');
    const d = await resp.json();
    renderOverview(d);
  } catch (e) {
    setStoryLive('offline', 'data source offline');
  }
}

function setStoryLive(cls, text) {
  var el = document.getElementById('story-live');
  if (el) { el.textContent = text; el.className = 'story-live ' + cls; }
}

// Normalize the two payload shapes (HTTP /api/overview AND the WebSocket
// overview push carry the same facts but in different positions). Without
// this, the WS push would render zeros over the story every ~2s.
function _normalize(d) {
  var k = d.knowledge || {};
  return {
    decisions: d.decisions || 0,
    domains: d.domains || k.domains || {},
    lessons: d.lessons !== undefined ? d.lessons : (k.nodes || 0),
    edges: d.edges !== undefined ? d.edges : (k.edges || 0),
    edge_types: d.edge_types || k.edge_types || {},
    world_states: d.world_states || 0,
    worlds_simulated: d.worlds_simulated || 0,
    di: d.di || 0,
    md: d.md || 0,
    mood: d.mood || 'neutral',
    producer: d.producer || { running: false, cycles: 0 },
    recent_decisions: d.recent_decisions || [],
    position: d.position || [],
    score: d.score || 0,
  };
}

function renderOverview(d) {
  if (!d || typeof d !== 'object') return;
  var n = _normalize(d);
  _lastOverview = n;
  _overviewUpdatedAt = Date.now();

  var decisions = n.decisions;
  var domainsObj = n.domains;
  var domainNames = Object.keys(domainsObj);
  var lessons = n.lessons;
  var edges = n.edges;
  var edgeTypes = n.edge_types;
  var worldStates = n.world_states;
  var worldsSim = n.worlds_simulated;
  var recent = n.recent_decisions;
  var producer = n.producer;

  // 1) HOOK — what is TELOS doing RIGHT NOW (live beat, state-aware).
  renderHook(n);

  // 2) Live badge.
  if (producer.running) {
    setStoryLive('', '● live · ' + (producer.cycles || 0) + ' cycles');
  } else {
    setStoryLive('off', 'history only (' + (producer.cycles || 0) + ' cycles on disk)');
  }

  // 3) Hero number (decisions) + caption that explains why it matters.
  setNum('story-decisions', decisions);
  renderHeroCaption(n);

  // 4) Context stats (captions live in the HTML markup).
  setNum('story-domains-count', domainNames.length);
  setNum('story-lessons', lessons);
  setNum('story-worlds', worldStates);
  setNum('story-worlds-sim', worldsSim);
  setNum('story-graph', lessons + '/' + edges);
  var diEl = document.getElementById('story-di');
  if (diEl) diEl.textContent = n.di > 0 ? (n.di * 100).toFixed(0) + '%' : '—';
  var mdEl = document.getElementById('story-md');
  if (mdEl) mdEl.textContent = n.md > 0 ? n.md.toFixed(2) : '0.00';

  // 5) INSIGHT — the "stories with words" layer: a sentence computed from
  //    the live numbers (integrity trend, growth since last poll, dominance).
  renderInsight(n, lessons, edges, domainsObj, recent);

  // 6) Evidence — domain chips, CLICKABLE (connected stories: click a domain
  //    to highlight it in the knowledge graph).
  renderDomainChips(domainNames, domainsObj);

  // 7) Edge-type chips.
  renderEdgeChips(edgeTypes, edges);

  // 8) Recent decisions.
  renderRecent(recent, decisions);

  // 9) Reflection — honest "right now" wording (no invented time-frame).
  renderMood(n, decisions, lessons, worldsSim, recent);

  // 10) Track poll deltas for the growth insight.
  if (_prevLessons === null) _prevLessons = lessons;
  if (_prevEdges === null) _prevEdges = edges;
  _prevLessons = lessons;
  _prevEdges = edges;
}

// ─── Hook: the live beat ───
function renderHook(n) {
  var h = document.getElementById('story-headline');
  if (!h) return;
  if (n.decisions === 0) {
    h.textContent = '🌀 TELOS is live — waiting for the first decision cycle…';
    return;
  }
  var recent = n.recent_decisions;
  var last = recent[recent.length - 1] || {};
  var pos = Array.isArray(n.position) && n.position.length === 2
    ? '(' + Math.round(n.position[0]) + ',' + Math.round(n.position[1]) + ')'
    : 'the grid';
  var intent = last.intent ? '"' + last.intent + '"' : 'a decision';
  var diBit = n.di > 0 ? ' · DI ' + (n.di * 100).toFixed(0) + '%' : '';
  h.textContent = 'TELOS is moving right now — last decision: ' + intent + ' from ' + pos + diBit + '.';
}

// ─── Hero caption: why the hero number matters, state-aware ───
function renderHeroCaption(n) {
  var el = document.getElementById('story-hero-caption');
  if (!el) return;
  if (n.decisions === 0) {
    el.textContent = 'The first real decision cycle starts the story.';
    return;
  }
  var last = (n.recent_decisions || [])[(n.recent_decisions || []).length - 1] || {};
  var verdict = last.status === 'APPROVED'
    ? 'The last one passed the council and became action.'
    : 'The last one was held back by a validator — TELOS chose not to act.';
  el.textContent = 'Each decision is a real pipeline run — DI-gated and council-checked. ' + verdict;
}

// ─── Insight: sentences DERIVED from live numbers, never hardcoded ───
function renderInsight(n, lessons, edges, domainsObj, recent) {
  var el = document.getElementById('story-insight');
  if (!el) return;
  if (n.decisions === 0) {
    el.innerHTML = '🌀 The story starts with the first real decision cycle.';
    return;
  }
  var parts = [];

  // Integrity trend from the real per-cycle DI series.
  var dis = recent.map(function (r) { return r.di; })
                   .filter(function (v) { return typeof v === 'number'; });
  if (dis.length >= 3) {
    var lastDi = dis[dis.length - 1];
    var prev = dis.slice(0, -1);
    var avgPrev = prev.reduce(function (a, b) { return a + b; }, 0) / prev.length;
    if (avgPrev - lastDi > 0.02) {
      parts.push('TELOS is being cautious this cycle — decision integrity dipped from ' +
        (avgPrev * 100).toFixed(0) + '% to ' + (lastDi * 100).toFixed(0) + '%.');
    } else if (lastDi >= 0.98 && avgPrev >= 0.98) {
      parts.push('Decision integrity has held at ' + (lastDi * 100).toFixed(0) + '% across the last ' +
        dis.length + ' cycles — TELOS keeps choosing inside its axioms.');
    }
  }

  // Growth right now: a REAL delta between two polls, not a fabricated trend.
  var newLessons = (_prevLessons !== null) ? lessons - _prevLessons : 0;
  if (newLessons > 0) {
    parts.push('TELOS is learning — ' + newLessons + ' new lesson' + (newLessons === 1 ? '' : 's') +
      ' since the last update.');
  }

  // Dominance: what the graph is mostly about (real share).
  var idCount = domainsObj['identity'] || 0;
  if (lessons > 0 && idCount / lessons >= 0.4) {
    parts.push('The knowledge graph is identity-heavy (' + idCount + '/' + lessons + ' lessons) — right now TELOS is mostly learning about itself.');
  }

  // Most active non-identity domain (real top-N pick).
  var top = null, topN = 0;
  for (var dn in domainsObj) {
    if (domainsObj[dn] > topN) { topN = domainsObj[dn]; top = dn; }
  }
  if (top && topN > 0 && top !== 'identity') {
    parts.push('Its most active knowledge domain is ' + top + ' (' + topN + ' lesson' + (topN === 1 ? '' : 's') + ').');
  }

  if (parts.length === 0) {
    parts.push('Steady state — decisions at DI ' + (n.di * 100).toFixed(0) + '%, mission drift ' + n.md.toFixed(2) + '.');
  }
  el.innerHTML = '💡 ' + parts.join(' ');
}

// ─── Domain chips — clickable, connected to the knowledge graph ───
function renderDomainChips(domainNames, domainsObj) {
  var dchip = document.getElementById('story-domain-chips');
  if (!dchip) return;
  if (domainNames.length === 0) {
    dchip.innerHTML = '<span class="story-chip dim">no knowledge yet</span>';
    return;
  }
  dchip.innerHTML = domainNames.sort().map(function (dn) {
    var c = _DOMAIN_COLORS_STORY[dn] || '#94a3b8';
    // Token-driven chip color: the palette lives in JS (data-driven domains);
    // the CSS reads it via --chip-c / --chip-b custom properties.
    return '<span class="story-chip clickable" data-domain="' + dn +
      '" title="Highlight ' + dn + ' in the knowledge graph (click again to clear)"' +
      ' style="--chip-c:' + c + ';--chip-b:' + c + '44">' +
      dn + ' <b>' + domainsObj[dn] + '</b></span>';
  }).join('');

  // Connected stories (feature 4): clicking a domain highlights it in the KG.
  var chips = dchip.querySelectorAll('.story-chip.clickable');
  for (var i = 0; i < chips.length; i++) {
    chips[i].addEventListener('click', (function (el) {
      return function () {
        var dn = el.getAttribute('data-domain');
        var wasActive = el.classList.contains('active');
        if (typeof highlightKGByDomain === 'function') highlightKGByDomain(wasActive ? null : dn);
        for (var j = 0; j < chips.length; j++) chips[j].classList.remove('active');
        if (!wasActive) el.classList.add('active');
      };
    })(chips[i]));
  }
}

// ─── Edge-type chips — raw counts plus a one-line gloss on dominance ───
function renderEdgeChips(edgeTypes, edges) {
  var echip = document.getElementById('story-edge-chips');
  if (!echip) return;
  var etNames = Object.keys(edgeTypes);
  if (etNames.length === 0) {
    echip.innerHTML = '<span class="story-chip dim">no edges yet</span>';
    return;
  }
  echip.innerHTML = etNames.sort().map(function (et) {
    var share = edges > 0 ? Math.round((edgeTypes[et] / edges) * 100) : 0;
    var title = share >= 50 ? et + ' dominates the graph (' + share + '%)' : et;
    return '<span class="story-chip" title="' + title + '">' + et + ' <b>' + edgeTypes[et] + '</b></span>';
  }).join('');
}

// ─── Recent decisions ───
function renderRecent(recent, decisions) {
  var rec = document.getElementById('story-recent');
  if (!rec) return;
  if (decisions === 0 || recent.length === 0) {
    rec.innerHTML = '<span class="story-chip dim">no decisions yet</span>';
    return;
  }
  rec.innerHTML = recent.slice(-8).reverse().map(function (r) {
    var ok = r.status === 'APPROVED';
    var pos = Array.isArray(r.position) ? '(' + Math.round(r.position[0]) + ',' + Math.round(r.position[1]) + ')' : '';
    return '<span class="story-decision ' + (ok ? 'ok' : 'warn') + '" title="' +
      (r.blocking_validator || '') + '">C' + r.cycle_id + ' ' + (r.intent || '?') +
      ' DI=' + (r.di !== undefined ? (r.di * 100).toFixed(0) + '%' : '—') + ' ' + pos + '</span>';
  }).join('');
}

// ─── Mood reflection — honest "right now", no invented "today" ───
function renderMood(n, decisions, lessons, worldsSim, recent) {
  var moodEl = document.getElementById('story-mood');
  if (!moodEl) return;
  if (decisions === 0) {
    moodEl.textContent = '🌀 TELOS is warming up — the story will appear as soon as the first real decision cycle completes.';
    return;
  }
  var last = recent[recent.length - 1] || {};
  var lastBit = last.intent ? ', its latest move being "' + last.intent + '"' : '';
  moodEl.innerHTML = 'Right now TELOS feels <b>' + n.mood + '</b> — ' + decisions +
    ' decisions in, ' + lessons + ' lessons learned, ' + worldsSim +
    ' futures simulated' + lastBit + '.';
}

function setNum(id, val) {
  var el = document.getElementById(id);
  if (el && el.textContent !== String(val)) el.textContent = val;
}

// ─── Action: the story ends facing forward (chat command box) ───
function openChat() {
  if (typeof switchTab === 'function') switchTab('chat');
  var input = document.getElementById('chat-input');
  if (input) {
    input.focus();
    try { input.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) {}
  }
}

// ─── Boot ───
fetchOverview();
setInterval(fetchOverview, 5000);
