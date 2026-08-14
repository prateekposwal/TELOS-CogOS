// TELOS Story Module — the "big data story" hero strip.
// Every number rendered here comes from /api/overview (measured runtime
// data or persisted history). No fabricated values, ever.
var _lastOverview = null;
var _overviewUpdatedAt = null;

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

function renderOverview(d) {
  if (!d || typeof d !== 'object') return;
  _lastOverview = d;
  _overviewUpdatedAt = Date.now();

  var decisions = d.decisions || 0;
  var domainsObj = d.domains || {};
  var domainNames = Object.keys(domainsObj);
  var lessons = d.lessons || 0;
  var edges = d.edges || 0;
  var worldStates = d.world_states || 0;
  var worldsSim = d.worlds_simulated || 0;
  var di = d.di || 0;
  var md = d.md || 0;
  var mood = d.mood || 'neutral';
  var producer = d.producer || { running: false, cycles: 0 };
  var recent = d.recent_decisions || [];
  var edgeTypes = d.edge_types || {};

  // Headline sentence (big data story).
  var h = document.getElementById('story-headline');
  if (h) {
    if (decisions > 0) {
      h.textContent = 'TELOS has made ' + decisions + ' decision' + (decisions === 1 ? '' : 's') +
        ' across ' + domainNames.length + ' domain' + (domainNames.length === 1 ? '' : 's') +
        ', learned ' + lessons + ' lesson' + (lessons === 1 ? '' : 's') +
        ', explored ' + worldStates + ' world-state' + (worldStates === 1 ? '' : 's') + '.';
    } else {
      h.textContent = '🌀 TELOS is live — waiting for the first decision cycle…';
    }
  }

  // Live badge.
  if (producer.running) {
    setStoryLive('', '● live · ' + (producer.cycles || 0) + ' cycles');
  } else {
    setStoryLive('off', 'history only (' + (producer.cycles || 0) + ' cycles on disk)');
  }

  // Big numbers.
  setNum('story-decisions', decisions);
  setNum('story-domains-count', domainNames.length);
  setNum('story-lessons', lessons);
  setNum('story-worlds', worldStates);
  setNum('story-worlds-sim', worldsSim);
  setNum('story-graph', lessons + '/' + edges);
  var diEl = document.getElementById('story-di');
  if (diEl) diEl.textContent = di > 0 ? (di * 100).toFixed(0) + '%' : '—';
  var mdEl = document.getElementById('story-md');
  if (mdEl) mdEl.textContent = md > 0 ? md.toFixed(2) : '0.00';

  // Per-domain knowledge chips.
  var dchip = document.getElementById('story-domain-chips');
  if (dchip) {
    if (domainNames.length === 0) {
      dchip.innerHTML = '<span class="story-chip dim">no knowledge yet</span>';
    } else {
      dchip.innerHTML = domainNames.sort().map(function (dn) {
        var c = _DOMAIN_COLORS_STORY[dn] || '#94a3b8';
        return '<span class="story-chip" style="color:' + c + ';border-color:' + c + '44">' +
          dn + ' <b>' + domainsObj[dn] + '</b></span>';
      }).join('');
    }
  }

  // Edge type chips.
  var echip = document.getElementById('story-edge-chips');
  if (echip) {
    var etNames = Object.keys(edgeTypes);
    if (etNames.length === 0) {
      echip.innerHTML = '<span class="story-chip dim">no edges yet</span>';
    } else {
      echip.innerHTML = etNames.sort().map(function (et) {
        return '<span class="story-chip">' + et + ' <b>' + edgeTypes[et] + '</b></span>';
      }).join('');
    }
  }

  // Recent decisions.
  var rec = document.getElementById('story-recent');
  if (rec) {
    if (recent.length === 0) {
      rec.innerHTML = '<span class="story-chip dim">no decisions yet</span>';
    } else {
      rec.innerHTML = recent.slice(-8).reverse().map(function (r) {
        var ok = r.status === 'APPROVED';
        var pos = Array.isArray(r.position) ? '(' + Math.round(r.position[0]) + ',' + Math.round(r.position[1]) + ')' : '';
        return '<span class="story-decision ' + (ok ? 'ok' : 'warn') + '" title="' +
          (r.blocking_validator || '') + '">C' + r.cycle_id + ' ' + (r.intent || '?') +
          ' DI=' + (r.di !== undefined ? (r.di * 100).toFixed(0) + '%' : '—') + ' ' + pos + '</span>';
      }).join('');
    }
  }

  // Mood sentence.
  var moodEl = document.getElementById('story-mood');
  if (moodEl) {
    if (decisions > 0) {
      var last = recent[recent.length - 1] || {};
      var lastBit = last.intent ? ', its last move being "' + last.intent + '"' : '';
      moodEl.innerHTML = 'Today TELOS feels <b>' + mood + '</b>, having navigated ' +
        worldStates + ' distinct cells and simulated ' + worldsSim + ' futures' + lastBit + '.';
    } else {
      moodEl.textContent = '🌀 TELOS is warming up — the story will appear as soon as the first real decision cycle completes.';
    }
  }
}

function setNum(id, val) {
  var el = document.getElementById(id);
  if (el && el.textContent !== String(val)) el.textContent = val;
}

// ─── Boot ───
fetchOverview();
setInterval(fetchOverview, 5000);
