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
var _prevEpisodes = null;   // goal-reach delta for the insight line
var _prevDecisions = null;  // hero number delta for the count-pop

var _DOMAIN_COLORS_STORY = {
  // ── THE canonical domain palette (single source of truth) ──────────
  // Observed live domains (2026-08-15, producer run): blocker, unknown,
  // navigation, identity, gridworld. knowledge-graph.js READS this map
  // (window._DOMAIN_COLORS_STORY) — there is exactly ONE domain palette
  // in the codebase; drifting copies are a pattern regression.
  'navigation': '#4ade80', 'gridworld': '#4ade80',
  'identity': '#f472b6', 'governance': '#c084fc',
  'terrain': '#fbbf24', 'preference': '#60a5fa',
  'user_preference': '#60a5fa', 'blocker': '#f87171',
  'perception': '#60a5fa', 'planning': '#fbbf24',
  'simulation': '#4ade80', 'pattern': '#94a3b8',
  'reflection': '#a78bfa', 'conversation': '#f472b6',
  'unknown': '#8f89ad',
  'general': '#94a3b8',
};
// Alias exposed to modules that load BEFORE story.js (knowledge-graph.js
// reads it at draw time, never at parse time — load order is safe).
if (typeof window !== 'undefined') window._DOMAIN_COLORS_STORY = _DOMAIN_COLORS_STORY;

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
    // Honest name: `knowledge_nodes` (live KG nodes). `lessons` is a
    // deprecated alias (was a naming collision with ExperienceManager
    // lessons). k.nodes is the producer knowledge payload's own count.
    lessons: d.knowledge_nodes !== undefined
      ? d.knowledge_nodes
      : (d.lessons !== undefined ? d.lessons : (k.nodes || 0)),
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
    score: (typeof d.score === 'number' && isFinite(d.score)) ? d.score : null,
    score_components: d.score_components || null,
    reward_collected: typeof d.reward_collected === 'number' ? d.reward_collected : 0,
    reward_available: typeof d.reward_available === 'number' ? d.reward_available : 0,
    episodes: d.episodes || null,
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
  var ep = n.episodes;
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
  //    The count-pop lives HERE and only here (DESIGN.md: sidebar values
  //    no longer flash; the hero number keeps the single attention pulse).
  var decEl = document.getElementById('story-decisions');
  if (decEl) {
    var decStr = String(decisions);
    if (decEl.textContent !== decStr) {
      decEl.textContent = decStr;
      if (typeof popValue === 'function') popValue(decEl);
    }
    _prevDecisions = decisions;
  }
  renderHeroCaption(n);

  // 4) Context stats — the 4 hero slots (captions live in the HTML markup).
  //    domains-count + graph render in the Knowledge-graph chip row;
  //    DI/MD render in the Chart panel caption (see below). Honesty: every
  //    value here comes from /api/overview measured data or a real delta.
  setNum('story-domains-count', domainNames.length);
  setNum('story-lessons', lessons);
  setNum('story-worlds', worldStates);
  // ROLLOUT STATES slot (audit C+D): the hero value is the PER-EPISODE
  // cumulative counterfactual states — episodes.current_worlds from the live
  // payload (the producer resets it at each goal). With the producer down,
  // the honest fallback is the LAST trace's own worlds_simulated (its most
  // recent measured rollout width) — never the lifetime total.
  var epWorlds = (ep && producer.running && typeof ep.current_worlds === 'number')
    ? ep.current_worlds
    : (recent.length ? (recent[recent.length - 1].worlds || 0) : 0);
  setNum('story-worlds-sim', epWorlds);
  setNum('story-graph', lessons + '/' + edges);
  // LIFETIME total + per-decision rate live in the TOOLTIP only (secondary
  // endurance facts — the slot's primary meaning is this episode). Rate =
  // lifetime / decisions = the run-wide mean rollout width, derived from two
  // measured totals (never invented) and inverted to confidence in fast mode,
  // so it is deliberately NOT a primary surface signal.
  var wsSimEl = document.getElementById('story-worlds-sim');
  if (wsSimEl) {
    var rate = (decisions > 0 && worldsSim > 0) ? (worldsSim / decisions) : null;
    wsSimEl.title = 'lifetime: ' + worldsSim + ' counterfactual states across all episodes' +
      (rate !== null ? ' — ~' + rate.toFixed(1) + ' per decision (horizon steps)' : '');
    // Audit: per-decision rollout rate as a READABLE SECONDARY line (was
    // tooltip-only). Deliberately NOT a primary slot: the rate is INVERSE to
    // confidence — in confident/fast mode the pipeline simulates fewer worlds
    // per decision on purpose (counterfactual_budget), so a LOWER number is
    // the designed healthy signal, never a quality defect.
    var rateEl = document.getElementById('story-worlds-sim-rate');
    if (rateEl) {
      rateEl.textContent = (rate !== null && rate > 0)
        ? '~' + rate.toFixed(1) + ' rollouts per decision — confident mode → deliberately fewer'
        : (decisions > 0 ? 'no rollouts this run yet' : '— rollouts per decision');
    }
  }
  // Audit Option E: "episodes today (IST)" — the calendar-day window from
  // the live producer snapshot (distinct label; never the consolidated
  // metric). Producer-down stays '—' (honest unmeasured).
  var todayEl = document.getElementById('story-today-episodes');
  if (todayEl) {
    var t = d.today;
    todayEl.textContent = (t && typeof t.episodes === 'number') ? String(t.episodes) : '—';
  }
  // DI / MD moved into the Chart panel caption (still measured values).
  var diEl = document.getElementById('story-di');
  if (diEl) diEl.textContent = n.di > 0 ? (n.di * 100).toFixed(0) + '%' : '—';
  var mdEl = document.getElementById('story-md');
  if (mdEl) mdEl.textContent = n.md > 0 ? n.md.toFixed(2) : '0.00';

  // Episode efficiency — REAL measured goal-reach events (producer-side
  // bookkeeping, ZERO sim mutation). Unmeasured (no episode yet, or no
  // producer) renders '—', never a fabricated number.
  var effEl = document.getElementById('story-efficiency');
  if (effEl) {
    if (!ep || !producer.running || ep.completed === 0 || typeof ep.avg_steps_per_goal !== 'number') {
      effEl.textContent = '—';
    } else {
      effEl.textContent = Math.round(ep.avg_steps_per_goal);
    }
  }
  // Moves-per-goal split: only cycles where the agent actually changed
  // position (blocked/no-op/inquiry cycles excluded) — real producer-side
  // bookkeeping, unmeasured stays '—' (never a fabricated number).
  var mvEl = document.getElementById('story-moves-per-goal');
  if (mvEl) {
    if (!ep || !producer.running || ep.completed === 0 || typeof ep.avg_moves_per_goal !== 'number') {
      mvEl.textContent = '—';
    } else {
      mvEl.textContent = Math.round(ep.avg_moves_per_goal);
    }
  }
  // Sidebar Episode readout (same live payload; honest empty state).
  var epVal = document.getElementById('episode-value');
  var epSub = document.getElementById('episode-sub');
  if (epVal) {
    epVal.textContent = (!ep || !producer.running) ? '—' : String(ep.current_steps);
  }
  if (epSub) {
    if (!ep || !producer.running) {
      epSub.textContent = 'episode stats need a live producer';
    } else if (ep.completed === 0) {
      epSub.textContent = 'steps into current episode — awaiting first goal…';
    } else {
      var avgTxt = (typeof ep.avg_steps_per_goal === 'number')
        ? Math.round(ep.avg_steps_per_goal) + ' cycles avg'
        : 'cycles avg —';
      var mvTxt = (typeof ep.avg_moves_per_goal === 'number')
        ? Math.round(ep.avg_moves_per_goal) + ' moves avg'
        : 'moves avg —';
      epSub.textContent = ep.completed + ' goal' + (ep.completed === 1 ? '' : 's') +
        ' reached · ' + avgTxt + ' · ' + mvTxt + ' · optimal ' + ep.optimal_steps;
    }
  }

  // Sidebar score breakdown: the System Score is a BOUNDED 0-100 composite
  // of measured signals (DI, mission drift, world value secured, grid
  // mapped). Cycles elapsed is an endurance fact — a separate readout —
  // never folded into the quality score. The caption is DERIVED from the
  // exact components the producer used (score_components), never invented.
  var sbEl = document.getElementById('score-breakdown');
  if (sbEl) {
    if (n.decisions === 0) {
      sbEl.textContent = '0–100 composite — waiting for first cycle';
    } else if (n.score === null) {
      sbEl.textContent = '0–100 composite — unavailable from persisted history (needs a live producer)';
    } else if (n.score_components) {
      var c = n.score_components;
      var valuePct = Math.round((c.reward_fraction || 0) * 100);
      var mappedPct = Math.round((c.world_coverage || 0) * 100);
      sbEl.textContent = '0–100 · DI ' + Math.round((c.di || 0) * 100) + '% · drift ' +
        (c.md || 0).toFixed(2) + ' · value ' + valuePct + '% · mapped ' + mappedPct + '%';
    } else {
      sbEl.textContent = '0–100 composite of DI, drift, rewards, exploration';
    }
  }

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
  renderMood(n, decisions, lessons, recent);

  // 10) Track poll deltas for the growth insight.
  if (_prevLessons === null) _prevLessons = lessons;
  if (_prevEdges === null) _prevEdges = edges;
  var epTrack = n.episodes;
  if (epTrack && typeof epTrack.completed === 'number') {
    if (_prevEpisodes === null) _prevEpisodes = epTrack.completed;
    _prevEpisodes = epTrack.completed;
  } else if (_prevEpisodes !== null) {
    _prevEpisodes = null;   // producer lost — reset the delta baseline
  }
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
  var verdict;
  if (last.status === 'APPROVED') {
    verdict = 'The last one passed the council and became action.';
  } else {
    // Name the ACTUAL gate from the live trace: the firewall's loop detector
    // ('action_loop') vs the council validator that rejected the action.
    var gate = last.blocked_by_gate || last.firewall_blocked_by || last.blocking_validator || 'a validator';
    verdict = 'The last one was held back by ' + gate + ' (' + (last.decision_mode || last.status || 'governance') + ') — TELOS chose not to act.';
  }
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

  // Goal-reach delta: a real completed episode since the last poll — the
  // efficiency signal, measured from the producer's goal-reach bookkeeping.
  var epNow = n.episodes;
  if (epNow && typeof epNow.completed === 'number' && _prevEpisodes !== null &&
      epNow.completed > _prevEpisodes && typeof epNow.last_steps === 'number') {
    var movesBit = (typeof epNow.last_moves === 'number')
      ? ' — ' + epNow.last_moves + ' actual move' + (epNow.last_moves === 1 ? '' : 's')
      : '';
    parts.push('TELOS reached the goal in ' + epNow.last_steps + ' decision cycles' +
      movesBit + ' — ' +
      epNow.completed + ' episode' + (epNow.completed === 1 ? '' : 's') +
      ' complete (optimal ' + epNow.optimal_steps + ').');
  }

  // Dominance: what the graph is mostly about (real share).
  var idCount = domainsObj['identity'] || 0;
  if (lessons > 0 && idCount / lessons >= 0.4) {
    parts.push('The knowledge graph is identity-heavy (' + idCount + '/' + lessons + ' knowledge nodes) — right now TELOS is mostly learning about itself.');
  }

  // Most active non-identity domain (real top-N pick).
  var top = null, topN = 0;
  for (var dn in domainsObj) {
    if (domainsObj[dn] > topN) { topN = domainsObj[dn]; top = dn; }
  }
  if (top && topN > 0 && top !== 'identity') {
    parts.push('Its most active knowledge domain is ' + top + ' (' + topN + ' knowledge node' + (topN === 1 ? '' : 's') + ').');
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
      (r.blocked_by_gate || r.firewall_blocked_by || r.blocking_validator || '') + '">C' + r.cycle_id + ' ' + (r.intent || '?') +
      ' DI=' + (r.di !== undefined ? (r.di * 100).toFixed(0) + '%' : '—') + ' ' + pos + '</span>';
  }).join('');
}

// ─── Mood reflection — honest "right now", no invented "today" ───
function renderMood(n, decisions, lessons, recent) {
  var moodEl = document.getElementById('story-mood');
  if (!moodEl) return;
  if (decisions === 0) {
    moodEl.textContent = '🌀 TELOS is warming up — the story will appear as soon as the first real decision cycle completes.';
    return;
  }
  var last = recent[recent.length - 1] || {};
  var lastBit = last.intent ? ', its latest move being "' + last.intent + '"' : '';
  var epMood = n.episodes;
  var goalsBit = '';
  if (epMood && typeof epMood.completed === 'number' && epMood.completed > 0) {
    goalsBit = ', ' + epMood.completed + ' goal' + (epMood.completed === 1 ? '' : 's') + ' reached';
  }
  moodEl.innerHTML = 'Right now TELOS feels <b>' + n.mood + '</b> — ' + decisions +
    ' decisions in, ' + lessons + ' knowledge nodes learned' + goalsBit + lastBit + '.';
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
