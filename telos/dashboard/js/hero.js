// TELOS Hero Module — the "Cognitive Data Portraits" cinematic layer.
//
// Three honest jobs, all derived from real runtime data:
//   1. HERO BACKDROP — draws the REAL DI/MD history (state.diHistory /
//      state.mdHistory, fed by applyTrace from /api/checkpoints + WS pushes)
//      as a glowing pulse waveform across the full-viewport hero. No
//      randomness: every pixel is a measured cycle. Empty history renders an
//      honest "awaiting the first cycle" frame, never fabricated data.
//   2. TITLE DYE — letters of "Portraits" are coloured with the REAL domain
//      palette of the knowledge graph (same map story.js uses for chips).
//   3. PULL QUOTES — the editorial evidence lines in chapters 01–07, each
//      computed from real overview/trace fields (latest decision, position,
//      graph composition, stream activations). Never invented sentences.
//   4. SCROLL REVEAL — the wc26-style reveal (fade + 16px rise) per chapter.

(function () {
  if (typeof window === 'undefined') return;
  var reduced = !!(window.__reducedMotion) ||
    (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches);

  // ── 1. HERO BACKDROP — the real DI/MD pulse ─────────────────────────
  var heroCanvas = document.getElementById('hero-backdrop');
  var heroHost = null; // .story-strip, sized by CSS

  function cssVar(name, fallback) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (e) { return fallback; }
  }

  if (heroCanvas) {
    heroHost = document.getElementById('story-strip');
    var ctx = heroCanvas.getContext('2d');
    var W = 0, H = 0;

    function size() {
      if (!heroHost) return;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = heroHost.clientWidth;
      H = heroHost.clientHeight;
      if (!W || !H) return;
      heroCanvas.width = Math.round(W * dpr);
      heroCanvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function hexToRgb(hex) {
      var h = String(hex || '').replace('#', '');
      if (h.length !== 6) return [125, 151, 255];
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
    }

    function drawPulse(t) {
      if (!W || !H) return;
      var bg = cssVar('--canvas-bg', '#0b0817');
      var diCol = hexToRgb(cssVar('--success', '#4ade80'));
      var mdCol = hexToRgb(cssVar('--danger', '#f87171'));
      var faint = cssVar('--border', '#221c44');
      var dim = cssVar('--text-dim', '#8f89ad');

      // Base night.
      var grad = ctx.createLinearGradient(0, 0, 0, H);
      grad.addColorStop(0, '#171232');
      grad.addColorStop(0.5, bg);
      grad.addColorStop(1, '#0a0716');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);

      // Hairline grid (geometry, not data).
      ctx.strokeStyle = faint;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.55;
      ctx.beginPath();
      for (var gx = 0; gx <= W; gx += 96) {
        ctx.moveTo(gx + 0.5, 0); ctx.lineTo(gx + 0.5, H);
      }
      for (var gy = 0; gy <= H; gy += 64) {
        ctx.moveTo(0, gy + 0.5); ctx.lineTo(W, gy + 0.5);
      }
      ctx.stroke();
      ctx.globalAlpha = 1;

      var len = state.diHistory.length;
      if (len < 2) {
        // Honest empty state: no invented wave.
        ctx.fillStyle = dim;
        ctx.font = '14px "Space Mono", monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('awaiting the first decision cycle — the pulse will draw itself from real cycles', W / 2, H / 2);
        return;
      }

      var padL = 56, padR = 64, padT = 40, padB = 40;
      var plotW = W - padL - padR;
      var plotH = H - padT - padB;
      var midY = padT + plotH * 0.52;
      var diH = plotH * 0.46;     // DI occupies the upper band
      var mdH = plotH * 0.30;     // MD a smaller lower band
      var x0 = padL;
      var step = plotW / (len - 1);
      var pulse = reduced ? 1 : (0.82 + Math.sin(t * 1.6) * 0.18);

      function pt(i, v, hh, baseY) {
        return [x0 + i * step, baseY - v * hh];
      }

      // DI area + line (upper band).
      var diPts = state.diHistory.map(function (di, i) {
        return pt(i, Math.max(0, Math.min(1, di || 0)), diH, midY);
      });
      var diGrad = ctx.createLinearGradient(0, midY - diH, 0, midY);
      diGrad.addColorStop(0, 'rgba(' + diCol.join(',') + ',0.30)');
      diGrad.addColorStop(1, 'rgba(' + diCol.join(',') + ',0.01)');
      ctx.beginPath();
      ctx.moveTo(diPts[0][0], midY);
      for (var i = 0; i < diPts.length; i++) ctx.lineTo(diPts[i][0], diPts[i][1]);
      ctx.lineTo(diPts[diPts.length - 1][0], midY);
      ctx.closePath();
      ctx.fillStyle = diGrad;
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(diPts[0][0], diPts[0][1]);
      for (var j = 1; j < diPts.length; j++) ctx.lineTo(diPts[j][0], diPts[j][1]);
      ctx.strokeStyle = 'rgba(' + diCol.join(',') + ',0.9)';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // MD mirrored line (lower band).
      var mdPts = state.mdHistory.map(function (md, i) {
        return pt(i, Math.max(0, Math.min(5, md || 0)) / 5, mdH, midY);
      });
      ctx.beginPath();
      ctx.moveTo(mdPts[0][0], mdPts[0][1]);
      for (var k = 1; k < mdPts.length; k++) ctx.lineTo(mdPts[k][0], mdPts[k][1]);
      ctx.strokeStyle = 'rgba(' + mdCol.join(',') + ',0.75)';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Baseline.
      ctx.strokeStyle = faint;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.8;
      ctx.beginPath(); ctx.moveTo(x0, midY + 0.5); ctx.lineTo(W - padR, midY + 0.5); ctx.stroke();
      ctx.globalAlpha = 1;

      // Live head on the newest DI point — the ONE pulse on the page.
      var last = diPts[diPts.length - 1];
      var r = reduced ? 5 : (4 + Math.sin(t * 3) * 1.2);
      var glowR = (reduced ? 18 : 18 + Math.sin(t * 2.2) * 6) * pulse;
      var glow = ctx.createRadialGradient(last[0], last[1], 0, last[0], last[1], glowR);
      glow.addColorStop(0, 'rgba(' + diCol.join(',') + ',' + (0.30 * pulse) + ')');
      glow.addColorStop(1, 'rgba(' + diCol.join(',') + ',0)');
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(last[0], last[1], glowR, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.arc(last[0], last[1], r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + diCol.join(',') + ',0.95)';
      ctx.fill();
      ctx.beginPath(); ctx.arc(last[0], last[1], r * 0.38, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(235,255,240,0.95)';
      ctx.fill();

      // Axis labels (real scale, ≥13px).
      ctx.font = '13px "Space Mono", monospace';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = dim;
      ctx.textAlign = 'left';
      ctx.fillText('DI 1.0', 4, midY - diH);
      ctx.fillText('DI 0.5', 4, midY - diH * 0.5);
      ctx.fillText('DI 0', 4, midY);
      ctx.fillText('MD 0', W - padR + 8, midY);
      ctx.fillText('MD 5', W - padR + 8, midY + mdH);
      ctx.textAlign = 'right';
      ctx.fillText('cycle ' + len, W - padR, 16);
    }

    var raf = 0;
    function frame(t) {
      drawPulse(t / 1000);
      raf = requestAnimationFrame(frame);
    }
    function start() {
      if (raf || reduced) return;
      raf = requestAnimationFrame(frame);
    }
    function stop() { if (raf) cancelAnimationFrame(raf); raf = 0; }
    // Order matters: size() must run BEFORE the static reduced-motion frame,
    // or W/H are 0 and drawPulse early-returns (blank hero under reduce).
    size();
    if (reduced) {
      drawPulse(0);
    } else {
      start();
    }
    window.addEventListener('resize', function () {
      size(); if (reduced) drawPulse(0);
    });
  }

  // ── 2. TITLE DYE — "Portraits" letters from the REAL live domain palette ──
  // Honesty (DESIGN.md rule 7, brief rule 5): only domains PRESENT in the
  // live knowledge graph (/api/overview -> domains) may dye a letter. A
  // domain that is not in the live graph stays ink. With no graph at all,
  // every letter stays ink — never a fake hue. Sequence follows the palette’s
  // key order so a sparse graph still yields a coherent warm->cool ribbon.
  function dyeTitle() {
    var wrap = document.getElementById('hero-title-dyed');
    if (!wrap) return;
    var chars = wrap.querySelectorAll('.ch');
    if (!chars.length) return;
    var palette = window._DOMAIN_COLORS_STORY || {
      'navigation': '#4ade80', 'identity': '#f472b6', 'governance': '#c084fc',
      'terrain': '#fbbf24', 'preference': '#60a5fa', 'blocker': '#f87171',
      'perception': '#60a5fa', 'planning': '#fbbf24', 'simulation': '#4ade80',
    };
    // Live domains from the real overview payload (null until first fetch).
    var live = (_overview && _overview.domains && typeof _overview.domains === 'object')
      ? _overview.domains : {};
    var keys = Object.keys(live).filter(function (k) { return palette[k]; });
    if (!keys.length) return;   // honest: no live known domain -> all ink
    for (var i = 0; i < chars.length; i++) {
      var key = keys[i % keys.length];
      chars[i].style.color = palette[key] || '';
    }
  }

  // ── 3. PULL QUOTES — real lines from the live record ──
  var _overview = null;

  function latestDecision() {
    var rec = _overview && _overview.recent_decisions;
    return (rec && rec.length) ? rec[rec.length - 1] : null;
  }

  function renderQuotes() {
    var d = _overview;
    if (!d) return;

    // 01 The Signal — the latest real decision.
    var sq = document.getElementById('signal-quote');
    if (sq) {
      var last = latestDecision();
      if (last && d.decisions > 0) {
        var verdict = last.status === 'APPROVED'
          ? 'passed the council and became action'
          : 'was held back by ' + (last.firewall_blocked_by || last.blocking_validator || 'a validator') +
            ' — TELOS chose not to act';
        var diTxt = (typeof last.di === 'number') ? (last.di * 100).toFixed(0) + '%' : '—';
        sq.querySelector('.pq-body').textContent =
          'Cycle ' + (last.cycle_id != null ? last.cycle_id : '—') + ' — "' + (last.intent || 'a decision') +
          '", decided at DI ' + diTxt + '. It ' + verdict + '.';
      } else {
        sq.querySelector('.pq-body').textContent = 'The first real decision cycle starts the story.';
      }
      var sqCite = sq.querySelector('.pq-cite');
      if (sqCite) sqCite.textContent = 'latest decision · real trace · DI ' + fmtDi();
    }

    // 02 The World — real position + episode efficiency.
    var wq = document.getElementById('world-quote');
    if (wq) {
      var pos = (Array.isArray(d.position) && d.position.length === 2)
        ? '(' + Math.round(d.position[0]) + ',' + Math.round(d.position[1]) + ')'
        : 'the origin';
      var ep = d.episodes;
      var epBit = '—';
      if (ep && typeof ep.completed === 'number' && ep.completed > 0) {
        var avg = (typeof ep.avg_steps_per_goal === 'number') ? Math.round(ep.avg_steps_per_goal) + ' steps avg' : '—';
        epBit = ep.completed + ' goal' + (ep.completed === 1 ? '' : 's') + ' reached · ' + avg + ' (optimal ' + ep.optimal_steps + ')';
      }
      wq.querySelector('.pq-body').textContent =
        'TELOS stands at ' + pos + ' — ' + (d.world_states || 0) + ' cells mapped of 25, ' +
        (d.reward_collected || 0) + ' of ' + (d.reward_available || 0) + ' world value secured. ' + epBit + '.';
      var wqCite = wq.querySelector('.pq-cite');
      if (wqCite) wqCite.textContent = 'live position · measured world state';
    }

    // 03 The Memory — real graph composition.
    var mq = document.getElementById('memory-quote');
    if (mq) {
      var domains = d.domains || {};
      var top = null, topN = 0;
      for (var dn in domains) {
        if (domains[dn] > topN) { topN = domains[dn]; top = dn; }
      }
      // Honest name: `knowledge_nodes` (live KG nodes); `lessons` is a
      // deprecated alias. These are KnowledgeGraph active concepts, NOT
      // ExperienceManager lessons.
      var kn = d.knowledge_nodes !== undefined ? d.knowledge_nodes : d.lessons;
      if (kn > 0) {
        var topBit = top ? ' — ' + top + ' leads with ' + topN + ' knowledge nodes' : '';
        mq.querySelector('.pq-body').textContent =
          kn + ' knowledge nodes, ' + d.edges + ' connections drawn between them' + topBit + '.';
      } else {
        mq.querySelector('.pq-body').textContent = 'The graph is empty until TELOS records its first real observation.';
      }
      var mqCite = mq.querySelector('.pq-cite');
      if (mqCite) mqCite.textContent = 'knowledge graph · /api/knowledge';
    }

    // 04 The Mind — real stream activations from the latest full trace.
    // Real traces carry `priority` (0..1), not `activation`; fall back only
    // to a genuinely present numeric field (never a fabricated one).
    var mind = document.getElementById('mind-quote');
    if (mind) {
      var acts = null;
      try {
        var tr = state.traces[state.traces.length - 1];
        if (tr && Array.isArray(tr.stream_activations) && tr.stream_activations.length) {
          var sorted = tr.stream_activations.slice().sort(function (a, b) {
            var pa = (a && (typeof a.priority === 'number' ? a.priority : a.activation)) || 0;
            var pb = (b && (typeof b.priority === 'number' ? b.priority : b.activation)) || 0;
            return pb - pa;
          });
          acts = sorted[0];
        }
      } catch (e) {}
      if (acts && acts.name) {
        var actVal = (typeof acts.priority === 'number')
          ? (acts.priority * 100).toFixed(0) + '%'
          : (typeof acts.activation === 'number' ? (acts.activation * 100).toFixed(0) + '%' : '—');
        var _modeBit = (state.metaMode ? ' — cognition mode ' + state.metaMode : '');
        mind.querySelector('.pq-body').textContent =
          'Right now "' + acts.name + '" leads the mind at ' + actVal + ' activation.' + _modeBit;
        var mindCite = mind.querySelector('.pq-cite');
        if (mindCite) mindCite.textContent = 'latest cycle · stream_activations';
      } else if (d.decisions > 0) {
        var _modeBit2 = (state.metaMode ? ' Cognition mode: ' + state.metaMode + '.' : '');
        mind.querySelector('.pq-body').textContent =
          'TELOS has simulated ' + d.worlds_simulated + ' counterfactual worlds so far, and feels ' + d.mood + '.' + _modeBit2;
        var mindCite2 = mind.querySelector('.pq-cite');
        if (mindCite2) mindCite2.textContent = 'worlds simulated · measured mood';
      } else {
        mind.querySelector('.pq-body').textContent = 'The mind wakes with the first decision cycle.';
      }
    }

    // 04b The Memory · Solar System — domain composition as orbiting worlds.
    var msq = document.getElementById('memory-solar-quote');
    if (msq) {
      var doms = d.domains || {};
      var dNames = Object.keys(doms);
      if (dNames.length > 0) {
        var topD = null, topN = 0;
        for (var dn2 in doms) { if (doms[dn2] > topN) { topN = doms[dn2]; topD = dn2; } }
        var topBitD = topD ? ' — ' + topD + ' holds the densest ring with ' + topN + ' lesson' + (topN === 1 ? '' : 's') : '';
        msq.querySelector('.pq-body').textContent =
          dNames.length + ' domain' + (dNames.length === 1 ? ' orbits' : 's orbit') + ' the core' + topBitD + '.';
      } else {
        msq.querySelector('.pq-body').textContent = 'The solar system stays dark until TELOS records its first real observation.';
      }
      var msqCite = msq.querySelector('.pq-cite');
      if (msqCite) msqCite.textContent = 'domains · /api/knowledge';
    }

    // 04c The Memory · Bubble Map — edge composition (strongest connection).
    var mbq = document.getElementById('memory-bubble-quote');
    if (mbq) {
      var ets = d.edge_types || {};
      var etNames = Object.keys(ets);
      if (etNames.length > 0 && d.edges > 0) {
        var topE = null, topEC = 0;
        for (var en in ets) { if (ets[en] > topEC) { topEC = ets[en]; topE = en; } }
        mbq.querySelector('.pq-body').textContent =
          topE + ' is the strongest connection — ' + topEC + ' of ' + d.edges + ' edges' +
          ' (' + Math.round((topEC / d.edges) * 100) + '% of the graph).';
      } else {
        mbq.querySelector('.pq-body').textContent = 'No connections drawn yet — the bubbles stay empty.';
      }
      var mbqCite = mbq.querySelector('.pq-cite');
      if (mbqCite) mbqCite.textContent = 'edge types · /api/knowledge';
    }

    // 05b The Mind · Root System — the same real stream activations as a
    // pipeline-canopy reading (top stream + its closest follower).
    var mrq = document.getElementById('mind-root-quote');
    if (mrq) {
      var acts2 = null;
      try {
        var tr2 = state.traces[state.traces.length - 1];
        if (tr2 && Array.isArray(tr2.stream_activations) && tr2.stream_activations.length) {
          acts2 = tr2.stream_activations.slice().sort(function (a, b) {
            var pa = (a && (typeof a.priority === 'number' ? a.priority : a.activation)) || 0;
            var pb = (b && (typeof b.priority === 'number' ? b.priority : b.activation)) || 0;
            return pb - pa;
          });
        }
      } catch (e) {}
      if (acts2 && acts2.length && acts2[0] && acts2[0].name) {
        var pct = function (s) {
          return typeof s === 'number' ? (s * 100).toFixed(0) + '%' : '—';
        };
        var lead = acts2[0];
        var follow = acts2[1];
        var leadV = (typeof lead.priority === 'number') ? pct(lead.priority)
          : (typeof lead.activation === 'number' ? pct(lead.activation) : '—');
        var body = 'The canopy opens with "' + lead.name + '" at ' + leadV + ' activation';
        if (follow && follow.name) {
          var fv = (typeof follow.priority === 'number') ? pct(follow.priority)
            : (typeof follow.activation === 'number' ? pct(follow.activation) : '—');
          body += ' — "' + follow.name + '" follows at ' + fv;
        }
        mrq.querySelector('.pq-body').textContent = body + '.';
        var mrqCite = mrq.querySelector('.pq-cite');
        if (mrqCite) mrqCite.textContent = 'latest cycle · stream_activations';
      } else if (d.decisions > 0) {
        mrq.querySelector('.pq-body').textContent =
          'TELOS has run ' + d.decisions + ' real pipeline cycles so far, and feels ' + d.mood + '.';
        var mrqCite2 = mrq.querySelector('.pq-cite');
        if (mrqCite2) mrqCite2.textContent = 'decisions · measured mood';
      } else {
        mrq.querySelector('.pq-body').textContent = 'The canopy wakes with the first decision cycle.';
      }
    }

    // System Score readout in chapter 01 (bounded 0–100, real or honest —).
    var sc = document.getElementById('sig-score-val');
    if (sc) sc.textContent = (typeof d.score === 'number' && isFinite(d.score)) ? Math.round(d.score) : '—';
    var scNote = document.getElementById('sig-score-note');
    if (scNote && typeof d.score !== 'number') {
      scNote.textContent = 'bounded 0–100 composite — unavailable until a live cycle completes';
    }
  }

  function fmtDi() {
    var last = latestDecision();
    return (last && typeof last.di === 'number') ? (last.di * 100).toFixed(0) + '%' : '—';
  }

  // ── 4. SCROLL REVEAL — wc26-style chapter entrance ──
  function setupReveal() {
    var els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window)) {
      for (var i = 0; i < els.length; i++) els[i].classList.add('in');
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add('in');
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.12 });
    for (var j = 0; j < els.length; j++) io.observe(els[j]);
  }

  // ── Boot ──
  dyeTitle();          // honest frame: ink until the live graph speaks
  setupReveal();

  // Fresh overview every 5s (same cadence as story.js — cheap, honest, live).
  async function fetchOverviewForHero() {
    try {
      var resp = await fetch('/api/overview');
      var d = await resp.json();
      _overview = d;
      renderQuotes();
      dyeTitle();   // live domains may differ -> honest re-dye
    } catch (e) {
      // Offline: quotes keep their honest "awaiting…" copy.
    }
  }
  fetchOverviewForHero();
  setInterval(fetchOverviewForHero, 5000);

  // Re-render quotes whenever a live trace lands (state.traces grows).
  var _lastTraceLen = 0;
  setInterval(function () {
    if (state.traces.length !== _lastTraceLen) {
      _lastTraceLen = state.traces.length;
      renderQuotes();
    }
  }, 1000);
})();
